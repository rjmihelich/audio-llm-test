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
            provider_name = config.get("tts_provider", "edge")
            voice_id = config.get("voice_id", "")

            from backend.app.api.speech import _load_tts_provider
            tts = _load_tts_provider(provider_name)
            if tts is None:
                raise HTTPException(500, f"TTS provider '{provider_name}' not available")

            # Build voice lookup by language prefix for auto-matching
            all_voices = await tts.list_voices()
            voices_by_lang: dict[str, list] = {}
            for v in all_voices:
                lang_key = v.language.split("-")[0]  # "en-GB" → "en"
                voices_by_lang.setdefault(lang_key, []).append(v)

            # Map corpus language codes to Edge voice language prefixes
            _LANG_VOICE_MAP = {
                "en": "en", "de": "de", "fr": "fr", "es": "es",
                "it": "it", "ja": "ja", "ko": "ko", "zh": "zh",
                "pt": "pt", "ru": "ru", "ar": "ar", "hi": "hi",
            }

            async def _pick_entry(cat: str | None) -> CorpusEntry | None:
                stmt = select(CorpusEntry)
                if cat:
                    stmt = stmt.where(CorpusEntry.category == cat)
                return (await session.execute(
                    stmt.order_by(func.random()).limit(1)
                )).scalar_one_or_none()

            async def _try_synthesize(entry: CorpusEntry) -> AudioBuffer | None:
                """Try to synthesize an entry, matching voice to entry language."""
                vid = voice_id  # user-specified voice takes priority
                if not vid:
                    lang = _LANG_VOICE_MAP.get(entry.language, "en")
                    candidates = voices_by_lang.get(lang, voices_by_lang.get("en", []))
                    vid = candidates[0].voice_id if candidates else "en-US-AriaNeural"
                try:
                    buf = await tts.synthesize(entry.text, vid)
                    log.info("Preview TTS: '%s' [%s] via %s/%s → %.1fs",
                             entry.text[:60], entry.language, provider_name, vid, buf.duration_s)
                    return buf
                except Exception as e:
                    log.warning("TTS failed for '%s' [%s]: %s", entry.text[:40], entry.language, e)
                    return None

            # If a specific entry ID was given, use it directly
            if entry_id:
                result = await session.execute(
                    select(CorpusEntry).where(CorpusEntry.id == uuid.UUID(entry_id))
                )
                entry = result.scalar_one_or_none()
                if entry:
                    audio = await _try_synthesize(entry)

            # Otherwise pick random entries, retrying up to 3 times on TTS failure
            if audio is None:
                for attempt in range(3):
                    entry = await _pick_entry(category if category else None)
                    if not entry:
                        break
                    audio = await _try_synthesize(entry)
                    if audio is not None:
                        break

            if audio is None:
                raise HTTPException(500, "TTS synthesis failed after retries")

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


async def _execute_graph(
    graph_json: dict[str, Any],
    session: AsyncSession,
) -> dict[str, Any]:
    """Shared logic: generate TTS from source nodes, execute graph, return result."""
    import base64
    import io
    import logging

    import numpy as np
    import soundfile as sf
    from sqlalchemy.sql.expression import func

    from backend.app.audio.types import AudioBuffer
    from backend.app.models.speech import CorpusEntry
    from backend.app.pipeline.base import PipelineInput
    from ..engine.graph_executor import GraphPipeline

    log = logging.getLogger(__name__)

    graph_nodes = graph_json.get("nodes", [])

    # Find speech_source / far_end_source nodes to generate real audio
    speech_audio: AudioBuffer | None = None
    speech_text = "The quick brown fox jumps over the lazy dog"

    for gn in graph_nodes:
        type_id = gn.get("type", gn.get("data", {}).get("type_id", ""))
        if type_id not in ("speech_source", "far_end_source"):
            continue
        config = gn.get("data", {}).get("config", {})
        mode = config.get("source_mode", "corpus_entry")

        if mode == "file":
            path = config.get("file_path", "")
            if path:
                from backend.app.audio.io import load_audio
                speech_audio = load_audio(path, target_sample_rate=16000)
                speech_text = f"(file: {path})"
            break

        # corpus_entry mode — pick from DB and synthesize
        category = config.get("corpus_category", "")
        entry_id = config.get("corpus_entry_id", "")
        provider_name = config.get("tts_provider", "edge")
        voice_id = config.get("voice_id", "")

        entry: CorpusEntry | None = None
        if entry_id:
            r = await session.execute(
                select(CorpusEntry).where(CorpusEntry.id == uuid.UUID(entry_id))
            )
            entry = r.scalar_one_or_none()
        if not entry and category:
            r = await session.execute(
                select(CorpusEntry)
                .where(CorpusEntry.category == category, CorpusEntry.language == "en")
                .order_by(func.random()).limit(1)
            )
            entry = r.scalar_one_or_none()
        if not entry:
            r = await session.execute(
                select(CorpusEntry)
                .where(CorpusEntry.language == "en")
                .order_by(func.random()).limit(1)
            )
            entry = r.scalar_one_or_none()

        if entry:
            speech_text = entry.text
            try:
                from backend.app.api.speech import _load_tts_provider
                tts = _load_tts_provider(provider_name)
                if tts:
                    if not voice_id:
                        voices = await tts.list_voices()
                        voice_id = voices[0].voice_id if voices else "en-US-AriaNeural"
                    speech_audio = await tts.synthesize(entry.text, voice_id)
                    log.info("Execute TTS: '%s' via %s/%s → %.1fs",
                             entry.text[:60], provider_name, voice_id, speech_audio.duration_s)
            except Exception as e:
                log.warning("Execute TTS failed: %s", e)
        break

    if speech_audio is None:
        sample_rate = 16000
        speech_audio = AudioBuffer(
            samples=np.zeros(int(sample_rate * 2.0), dtype=np.float64),
            sample_rate=sample_rate,
        )

    pipeline_input = PipelineInput(
        clean_speech=speech_audio,
        original_text=speech_text,
        expected_intent="preview",
        expected_action="preview",
    )

    try:
        graph_pipeline = GraphPipeline(graph_json)
        pipeline_result = await graph_pipeline.execute(pipeline_input)

        audio_wav_base64 = None
        if pipeline_result.degraded_audio is not None:
            buf = io.BytesIO()
            sf.write(
                buf,
                pipeline_result.degraded_audio.samples,
                pipeline_result.degraded_audio.sample_rate,
                format="WAV",
                subtype="PCM_16",
            )
            audio_wav_base64 = base64.b64encode(buf.getvalue()).decode("ascii")

        # Per-node state for the frontend
        text_outputs = getattr(pipeline_result, "_text_outputs", {})
        text_output_text = getattr(pipeline_result, "_text_output_text", None)
        router_states = getattr(pipeline_result, "_router_states", {})
        eval_states = getattr(pipeline_result, "_eval_states", {})
        histogram_values = getattr(pipeline_result, "_histogram_values", {})

        return {
            "success": True,
            "pipeline_type": pipeline_result.pipeline_type,
            "total_latency_ms": pipeline_result.total_latency_ms,
            "has_degraded_audio": pipeline_result.degraded_audio is not None,
            "has_llm_response": pipeline_result.llm_response is not None,
            "has_transcription": pipeline_result.transcription is not None,
            "llm_response_text": pipeline_result.llm_response.text if pipeline_result.llm_response else None,
            "transcription_text": pipeline_result.transcription.text if pipeline_result.transcription else None,
            "text_output_text": text_output_text,
            "text_outputs": text_outputs,
            "router_states": router_states,
            "eval_states": eval_states,
            "histogram_values": histogram_values,
            "audio_wav_base64": audio_wav_base64,
            "source_text": speech_text,
            "error": pipeline_result.error,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
        }


@router.post("/{pipeline_id}/execute-preview")
async def execute_preview(
    pipeline_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Execute a saved pipeline end-to-end."""
    result = await session.execute(
        select(Pipeline).where(Pipeline.id == uuid.UUID(pipeline_id))
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")
    return await _execute_graph(pipeline.graph_json, session)


@router.post("/execute-inline")
async def execute_inline(
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
):
    """Execute a graph directly from JSON without saving.

    Used by the continuous playback loop — sends the current graph state
    each iteration so parameter changes (mixer gains, etc.) take effect
    immediately without needing to save first.
    """
    graph_json = body.get("graph_json", body)
    return await _execute_graph(graph_json, session)


@router.post("/warmup-model")
async def warmup_model(body: dict[str, Any]):
    """Warm up an LLM model — forces loading into VRAM and returns timing.

    POST {"backend": "ollama:llama3.1"}
    Returns {"status": "ready", "model": "llama3.1:8b", "load_time_ms": 1234}
    """
    import time

    backend_str = body.get("backend", "")
    if not backend_str:
        raise HTTPException(400, "Missing 'backend' field")

    provider, _, model = backend_str.partition(":")
    if not provider or not model:
        raise HTTPException(400, f"Invalid backend format: {backend_str!r} — expected 'provider:model'")

    # Only Ollama needs warming (loads model into VRAM)
    if provider != "ollama":
        return {"status": "ready", "model": model, "load_time_ms": 0, "message": "Cloud provider — no warmup needed"}

    try:
        from backend.app.config import settings
        from backend.app.llm.ollama import OllamaBackend

        t0 = time.monotonic()
        backend = OllamaBackend(base_url=settings.ollama_base_url, model=model)

        # Resolve model name (e.g. llama3.1 → llama3.1:8b)
        await backend._resolve_model()
        resolved_model = backend._model

        # Tiny generate to force model loading into VRAM
        resp = await backend.query_with_text("Hi", "Reply with one word.")
        load_time_ms = (time.monotonic() - t0) * 1000

        await backend.close()

        return {
            "status": "ready",
            "model": resolved_model,
            "load_time_ms": round(load_time_ms),
        }
    except Exception as e:
        return {
            "status": "error",
            "model": model,
            "error": str(e),
        }
