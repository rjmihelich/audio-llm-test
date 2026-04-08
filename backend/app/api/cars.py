"""Car noise profile API endpoints."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.models.base import get_session
from backend.app.models.car import Car, CarNoiseFile
from backend.app.audio.io import load_audio

logger = logging.getLogger(__name__)

router = APIRouter()

CARS_STORAGE = settings.audio_storage_path / "cars"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CarCreate(BaseModel):
    name: str
    description: str | None = None
    metadata_json: dict | None = None


class CarResponse(BaseModel):
    id: str
    name: str
    description: str | None
    metadata_json: dict | None
    noise_file_count: int = 0


class CarDetailResponse(CarResponse):
    noise_files: list["NoiseFileResponse"]


class NoiseFileResponse(BaseModel):
    id: str
    noise_category: str
    speed: float
    condition: str | None
    file_path: str
    duration_s: float | None
    sample_rate: int | None
    metadata_json: dict | None


# ---------------------------------------------------------------------------
# Car CRUD
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[CarResponse])
async def list_cars(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Car).order_by(Car.name))
    cars = result.scalars().all()
    return [
        CarResponse(
            id=str(c.id),
            name=c.name,
            description=c.description,
            metadata_json=c.metadata_json,
            noise_file_count=len(c.noise_files),
        )
        for c in cars
    ]


@router.get("/{car_id}", response_model=CarDetailResponse)
async def get_car(car_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    car = await session.get(Car, car_id)
    if not car:
        raise HTTPException(404, "Car not found")
    return CarDetailResponse(
        id=str(car.id),
        name=car.name,
        description=car.description,
        metadata_json=car.metadata_json,
        noise_file_count=len(car.noise_files),
        noise_files=[
            NoiseFileResponse(
                id=str(nf.id),
                noise_category=nf.noise_category,
                speed=nf.speed,
                condition=nf.condition,
                file_path=nf.file_path,
                duration_s=nf.duration_s,
                sample_rate=nf.sample_rate,
                metadata_json=nf.metadata_json,
            )
            for nf in car.noise_files
        ],
    )


@router.post("/", response_model=CarResponse, status_code=201)
async def create_car(body: CarCreate, session: AsyncSession = Depends(get_session)):
    car = Car(name=body.name, description=body.description, metadata_json=body.metadata_json)
    session.add(car)
    await session.commit()
    await session.refresh(car)
    return CarResponse(
        id=str(car.id),
        name=car.name,
        description=car.description,
        metadata_json=car.metadata_json,
        noise_file_count=0,
    )


@router.patch("/{car_id}", response_model=CarResponse)
async def update_car(
    car_id: uuid.UUID, body: CarCreate, session: AsyncSession = Depends(get_session),
):
    car = await session.get(Car, car_id)
    if not car:
        raise HTTPException(404, "Car not found")
    car.name = body.name
    if body.description is not None:
        car.description = body.description
    if body.metadata_json is not None:
        car.metadata_json = body.metadata_json
    await session.commit()
    await session.refresh(car)
    return CarResponse(
        id=str(car.id),
        name=car.name,
        description=car.description,
        metadata_json=car.metadata_json,
        noise_file_count=len(car.noise_files),
    )


@router.delete("/{car_id}", status_code=204)
async def delete_car(car_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    car = await session.get(Car, car_id)
    if not car:
        raise HTTPException(404, "Car not found")
    await session.delete(car)
    await session.commit()


# ---------------------------------------------------------------------------
# Noise file management
# ---------------------------------------------------------------------------

@router.post("/{car_id}/noise-files", response_model=NoiseFileResponse, status_code=201)
async def upload_noise_file(
    car_id: uuid.UUID,
    file: UploadFile = File(...),
    noise_category: str = Form(...),
    speed: float = Form(...),
    condition: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
):
    """Upload a noise WAV file for a car."""
    car = await session.get(Car, car_id)
    if not car:
        raise HTTPException(404, "Car not found")

    if noise_category not in ("road", "fan"):
        raise HTTPException(400, "noise_category must be 'road' or 'fan'")

    # Build storage path: storage/audio/cars/{car_name_slug}/{category}_{speed}_{condition}.wav
    car_slug = car.name.lower().replace(" ", "_").replace("/", "_")
    car_dir = CARS_STORAGE / car_slug
    car_dir.mkdir(parents=True, exist_ok=True)

    parts = [noise_category, str(int(speed) if speed == int(speed) else speed)]
    if condition:
        parts.append(condition.lower().replace(" ", "_"))
    filename = "_".join(parts) + ".wav"
    dest = car_dir / filename

    # Write file
    content = await file.read()
    dest.write_bytes(content)

    # Probe audio metadata
    try:
        audio = load_audio(str(dest))
        duration_s = audio.duration_s
        sample_rate = audio.sample_rate
    except Exception:
        duration_s = None
        sample_rate = None

    # Relative path from storage/audio/
    relative_path = f"cars/{car_slug}/{filename}"

    nf = CarNoiseFile(
        car_id=car.id,
        noise_category=noise_category,
        speed=speed,
        condition=condition,
        file_path=relative_path,
        duration_s=duration_s,
        sample_rate=sample_rate,
    )
    session.add(nf)
    await session.commit()
    await session.refresh(nf)

    logger.info("Uploaded noise file %s for car %s: %s", nf.id, car.name, relative_path)

    return NoiseFileResponse(
        id=str(nf.id),
        noise_category=nf.noise_category,
        speed=nf.speed,
        condition=nf.condition,
        file_path=nf.file_path,
        duration_s=nf.duration_s,
        sample_rate=nf.sample_rate,
        metadata_json=nf.metadata_json,
    )


@router.delete("/{car_id}/noise-files/{file_id}", status_code=204)
async def delete_noise_file(
    car_id: uuid.UUID,
    file_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    nf = await session.get(CarNoiseFile, file_id)
    if not nf or nf.car_id != car_id:
        raise HTTPException(404, "Noise file not found")

    # Remove physical file
    full_path = settings.audio_storage_path / nf.file_path
    if full_path.exists():
        full_path.unlink()

    await session.delete(nf)
    await session.commit()


@router.get("/{car_id}/noise-files", response_model=list[NoiseFileResponse])
async def list_noise_files(
    car_id: uuid.UUID,
    noise_category: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """List noise files for a car, optionally filtered by category."""
    q = select(CarNoiseFile).where(CarNoiseFile.car_id == car_id)
    if noise_category:
        q = q.where(CarNoiseFile.noise_category == noise_category)
    q = q.order_by(CarNoiseFile.noise_category, CarNoiseFile.speed)
    result = await session.execute(q)
    files = result.scalars().all()
    return [
        NoiseFileResponse(
            id=str(nf.id),
            noise_category=nf.noise_category,
            speed=nf.speed,
            condition=nf.condition,
            file_path=nf.file_path,
            duration_s=nf.duration_s,
            sample_rate=nf.sample_rate,
            metadata_json=nf.metadata_json,
        )
        for nf in files
    ]


@router.get("/{car_id}/noise-types", response_model=list[str])
async def get_noise_types(
    car_id: uuid.UUID,
    noise_category: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Return noise_type strings ready for use in sweep configs.

    Each entry is in the format: car_file:<relative_path>
    These can be passed directly into SweepConfigRequest.noise_types.
    """
    car = await session.get(Car, car_id)
    if not car:
        raise HTTPException(404, "Car not found")

    q = select(CarNoiseFile).where(CarNoiseFile.car_id == car_id)
    if noise_category:
        q = q.where(CarNoiseFile.noise_category == noise_category)
    q = q.order_by(CarNoiseFile.noise_category, CarNoiseFile.speed)
    result = await session.execute(q)
    files = result.scalars().all()

    return [f"car_file:{nf.file_path}" for nf in files]
