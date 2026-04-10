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


@router.post("/preview-node")
async def preview_node(
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
):
    """Execute a single source node and return audio as WAV.

    For speech_source in corpus_entry mode: queries the corpus DB for a random
    entry matching the selected category, synthesizes via TTS, returns audio.
    For noise_generator: generates noise audio directly.
    """
    import io
    import logging

    import numpy as np
    import soundfile as sf
    from sqlalchemy.sql.expression import func

    from backend.app.audio.types import AudioBuffer
    from backend.app.models.speech import CorpusEntry, SpeechSample
    from starlette.responses import Response

    log = logging.getLogger(__name__)

    type_id = body.get("type_id", "")
    config = body.get("config", {})

    audio: AudioBuffer | None = None

    # ---- speech_source ----
    if type_id in ("speech_source", "far_end_source"):
        mode = config.get("source_mode", "corpus_entry")

        if mode == "file":
            path = config.get("file_path", "")
            if not path:
                raise HTTPException(422, "file_path is required for file mode")
            from backend.app.audio.io import load_audio
            audio = load_audio(path, target_sample_rate=16000)

        elif mode == "speech_sample":
            # Load a pre-recorded speech sample by ID
            sample_id = config.get("speech_sample_id", "")
            if not sample_id:
                raise HTTPException(422, "speech_sample_id is required")
            result = await session.execute(
                select(SpeechSample).where(
                    SpeechSample.id == uuid.UUID(sample_id),
                    SpeechSample.status == "ready",
                )
            )
            sample = result.scalar_one_or_none()
            if not sample:
                raise HTTPException(404, "Speech sample not found or not ready")
            from backend.app.audio.io import load_audio
            audio = load_audio(sample.file_path, target_sample_rate=16000)

        else:
            # corpus_entry mode (default) — pick text from corpus, synthesize
            category = config.get("corpus_category", "")
            entry_id = config.get("corpus_entry_id", "")

            # Get the text to speak
            text: str | None = None
            if entry_id:
                result = await session.execute(
                    select(CorpusEntry).where(CorpusEntry.id == uuid.UUID(entry_id))
                )
                entry = result.scalar_one_or_none()
                if entry:
                    text = entry.text
            if not text and category:
                # Random English entry from this category
                result = await session.execute(
                    select(CorpusEntry)
                    .where(CorpusEntry.category == category, CorpusEntry.language == "en")
                    .order_by(func.random())
                    .limit(1)
                )
                entry = result.scalar_one_or_none()
                if entry:
                    text = entry.text
            if not text:
                # Any random English entry
                result = await session.execute(
                    select(CorpusEntry)
                    .where(CorpusEntry.language == "en")
                    .order_by(func.random())
                    .limit(1)
                )
                entry = result.scalar_one_or_none()
                if entry:
                    text = entry.text
            if not text:
                text = "The quick brown fox jumps over the lazy dog"

            # Synthesize via TTS
            provider_name = config.get("tts_provider", "edge")
            voice_id = config.get("voice_id", "")
            try:
                from backend.app.api.speech import _load_tts_provider
                tts = _load_tts_provider(provider_name)
                if tts is None:
                    raise ValueError(f"TTS provider '{provider_name}' not available")
                # Pick a default voice if none specified
                if not voice_id:
                    voices = await tts.list_voices()
                    voice_id = voices[0].voice_id if voices else "en-US-AriaNeural"
                audio = await tts.synthesize(text, voice_id)
                log.info("Preview TTS: '%s' via %s/%s → %.1fs", text, provider_name, voice_id, audio.duration_s)
            except Exception as e:
                log.warning("TTS preview failed (%s), falling back to silence: %s", provider_name, e)
                raise HTTPException(500, f"TTS synthesis failed: {e}")

    # ---- noise_generator ----
    elif type_id == "noise_generator":
        from backend.app.audio.noise import (
            white_noise, pink_noise, pink_noise_filtered, babble_noise,
        )

        noise_type = config.get("noise_type", "pink_lpf")
        seed = config.get("seed")
        if seed is not None:
            seed = int(seed)
        duration_s = float(config.get("duration_s", 3))
        if duration_s <= 0:
            duration_s = 3.0
        sample_rate = 16000

        noise_fns = {
            "white": lambda: white_noise(duration_s, sample_rate=sample_rate, seed=seed),
            "pink": lambda: pink_noise(duration_s, sample_rate=sample_rate, seed=seed),
            "pink_lpf": lambda: pink_noise_filtered(duration_s, sample_rate=sample_rate, seed=seed),
            "babble": lambda: babble_noise(duration_s, sample_rate=sample_rate, seed=seed),
        }
        fn = noise_fns.get(noise_type, noise_fns["pink_lpf"])
        audio = fn()

    else:
        raise HTTPException(422, f"Preview not supported for node type '{type_id}'")

    if audio is None:
        raise HTTPException(500, "No audio generated")

    # Encode as WAV
    buf = io.BytesIO()
    sf.write(buf, audio.samples, audio.sample_rate, format="WAV", subtype="PCM_16")
    buf.seek(0)

    return Response(
        content=buf.read(),
        media_type="audio/wav",
        headers={"Content-Disposition": f'inline; filename="preview_{type_id}.wav"'},
    )


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

        # Serialize audio as base64 WAV if present
        audio_wav_base64 = None
        if pipeline_result.degraded_audio is not None:
            import base64
            import io
            import soundfile as sf
            buf = io.BytesIO()
            sf.write(
                buf,
                pipeline_result.degraded_audio.samples,
                pipeline_result.degraded_audio.sample_rate,
                format="WAV",
                subtype="PCM_16",
            )
            audio_wav_base64 = base64.b64encode(buf.getvalue()).decode("ascii")

        return {
            "success": True,
            "pipeline_type": pipeline_result.pipeline_type,
            "total_latency_ms": pipeline_result.total_latency_ms,
            "has_degraded_audio": pipeline_result.degraded_audio is not None,
            "has_llm_response": pipeline_result.llm_response is not None,
            "has_transcription": pipeline_result.transcription is not None,
            "llm_response_text": pipeline_result.llm_response.text if pipeline_result.llm_response else None,
            "transcription_text": pipeline_result.transcription.text if pipeline_result.transcription else None,
            "audio_wav_base64": audio_wav_base64,
            "error": pipeline_result.error,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
        }
