"""Models for car noise profiles: vehicles and their noise file libraries."""

import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base


class NoiseCategoryEnum(str, enum.Enum):
    road = "road"
    fan = "fan"


class Car(Base):
    __tablename__ = "cars"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, default=dict,
        comment="Extensible metadata (make, model, year, cabin type, etc.)",
    )

    # Relationships
    noise_files: Mapped[list["CarNoiseFile"]] = relationship(
        back_populates="car", lazy="selectin", cascade="all, delete-orphan",
    )


class CarNoiseFile(Base):
    __tablename__ = "car_noise_files"

    car_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cars.id", ondelete="CASCADE"), nullable=False,
    )
    noise_category: Mapped[str] = mapped_column(
        Enum(NoiseCategoryEnum, name="noise_category_enum", native_enum=False),
        nullable=False,
    )
    speed: Mapped[float] = mapped_column(
        Float, nullable=False,
        comment="Road: mph. Fan: 0-10 integer speed setting.",
    )
    condition: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Road surface or condition (highway, city, gravel, wet, etc.)",
    )
    file_path: Mapped[str] = mapped_column(
        String(500), nullable=False,
        comment="Path to WAV file relative to storage/audio/cars/",
    )
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, default=dict,
        comment="Extra info (recording equipment, notes, etc.)",
    )

    # Relationships
    car: Mapped["Car"] = relationship(back_populates="noise_files", lazy="selectin")
