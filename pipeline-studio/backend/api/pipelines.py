"""Pipeline CRUD API — create, read, update, delete, validate, preview, node-types."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import get_session
from ..models.pipeline import Pipeline
from ..engine.graph_executor import validate_graph
from ..engine.node_registry import registry_to_dict

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class PipelineCreate(BaseModel):
    name: str
    description: str = ""
    graph_json: dict[str, Any]
    is_template: bool = False


class PipelineUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    graph_json: dict[str, Any] | None = None


class PipelineResponse(BaseModel):
    id: str
    name: str
    description: str | None
    graph_json: dict[str, Any]
    is_template: bool
    version: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class ValidationResponse(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_response(p: Pipeline) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "description": p.description,
        "graph_json": p.graph_json,
        "is_template": p.is_template,
        "version": p.version,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/node-types")
async def get_node_types():
    """Return the full node registry for the frontend palette."""
    return registry_to_dict()


@router.get("")
async def list_pipelines(
    is_template: bool | None = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Pipeline).order_by(Pipeline.updated_at.desc())
    if is_template is not None:
        stmt = stmt.where(Pipeline.is_template == is_template)
    result = await session.execute(stmt)
    pipelines = result.scalars().all()
    return [_to_response(p) for p in pipelines]


@router.get("/{pipeline_id}")
async def get_pipeline(
    pipeline_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Pipeline).where(Pipeline.id == uuid.UUID(pipeline_id))
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")
    return _to_response(pipeline)


@router.post("", status_code=201)
async def create_pipeline(
    body: PipelineCreate,
    session: AsyncSession = Depends(get_session),
):
    # Validate the graph before saving
    validation = validate_graph(body.graph_json)
    if not validation.valid:
        raise HTTPException(422, {"errors": validation.errors})

    pipeline = Pipeline(
        name=body.name,
        description=body.description,
        graph_json=body.graph_json,
        is_template=body.is_template,
    )
    session.add(pipeline)
    await session.commit()
    await session.refresh(pipeline)
    return _to_response(pipeline)


@router.put("/{pipeline_id}")
async def update_pipeline(
    pipeline_id: str,
    body: PipelineUpdate,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Pipeline).where(Pipeline.id == uuid.UUID(pipeline_id))
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    if body.graph_json is not None:
        validation = validate_graph(body.graph_json)
        if not validation.valid:
            raise HTTPException(422, {"errors": validation.errors})
        pipeline.graph_json = body.graph_json
        pipeline.version += 1

    if body.name is not None:
        pipeline.name = body.name
    if body.description is not None:
        pipeline.description = body.description

    await session.commit()
    await session.refresh(pipeline)
    return _to_response(pipeline)


@router.delete("/{pipeline_id}", status_code=204)
async def delete_pipeline(
    pipeline_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Pipeline).where(Pipeline.id == uuid.UUID(pipeline_id))
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    await session.execute(
        sa_delete(Pipeline).where(Pipeline.id == uuid.UUID(pipeline_id))
    )
    await session.commit()


@router.post("/{pipeline_id}/validate")
async def validate_pipeline(
    pipeline_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Pipeline).where(Pipeline.id == uuid.UUID(pipeline_id))
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    validation = validate_graph(pipeline.graph_json)
    return {
        "valid": validation.valid,
        "errors": validation.errors,
        "warnings": validation.warnings,
    }


@router.post("/validate-graph")
async def validate_graph_inline(body: dict[str, Any]):
    """Validate a graph without saving it."""
    validation = validate_graph(body)
    return {
        "valid": validation.valid,
        "errors": validation.errors,
        "warnings": validation.warnings,
    }


@router.post("/{pipeline_id}/execute-preview")
async def execute_preview(
    pipeline_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Execute the pipeline once with a sample input for preview."""
    result = await session.execute(
        select(Pipeline).where(Pipeline.id == uuid.UUID(pipeline_id))
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    # Build a sample PipelineInput
    import numpy as np
    from backend.app.audio.types import AudioBuffer
    from backend.app.pipeline.base import PipelineInput
    from ..engine.graph_executor import GraphPipeline

    # Generate a short sine wave as sample speech
    sample_rate = 16000
    duration = 2.0
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    samples = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float64)
    sample_audio = AudioBuffer(samples=samples, sample_rate=sample_rate)

    sample_input = PipelineInput(
        clean_speech=sample_audio,
        original_text="Navigate to the nearest gas station",
        expected_intent="navigation",
        expected_action="navigate_nearest_gas_station",
    )

    try:
        graph_pipeline = GraphPipeline(pipeline.graph_json)
        pipeline_result = await graph_pipeline.execute(sample_input)
        return {
            "success": True,
            "pipeline_type": pipeline_result.pipeline_type,
            "total_latency_ms": pipeline_result.total_latency_ms,
            "has_degraded_audio": pipeline_result.degraded_audio is not None,
            "has_llm_response": pipeline_result.llm_response is not None,
            "has_transcription": pipeline_result.transcription is not None,
            "llm_response_text": pipeline_result.llm_response.text if pipeline_result.llm_response else None,
            "error": pipeline_result.error,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
        }
