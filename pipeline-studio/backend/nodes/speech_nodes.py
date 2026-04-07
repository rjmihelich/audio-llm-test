"""Speech node executors — TTS and STT wrapping existing providers."""

from __future__ import annotations

from typing import Any

from ..engine.graph_executor import ExecutionContext, GraphNode


async def execute_tts(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Text-to-Speech: convert text input to audio."""
    text_in = inputs.get("text_in")
    if not text_in:
        raise ValueError("TTS node: text_in is required")

    provider_name = config.get("provider", "edge")
    voice_id = config.get("voice_id", "")

    # Get TTS provider from existing catalog
    from backend.app.speech.catalog import get_tts_provider
    provider = get_tts_provider(provider_name)

    audio = await provider.synthesize(text_in, voice_id)
    return {"audio_out": audio}


async def execute_stt(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Speech-to-Text: transcribe audio to text."""
    audio_in = inputs.get("audio_in")
    if audio_in is None:
        raise ValueError("STT node: audio_in is required")

    backend_name = config.get("backend", "whisper_local")

    from backend.app.config import settings

    if backend_name == "whisper_local":
        from backend.app.llm.whisper import WhisperLocalBackend
        asr = WhisperLocalBackend(model_size=config.get("model_size", "base"))
    elif backend_name == "whisper_api":
        from backend.app.llm.whisper import WhisperAPIBackend
        asr = WhisperAPIBackend(api_key=settings.openai_api_key)
    elif backend_name == "deepgram":
        from backend.app.llm.deepgram_stt import DeepgramSTTBackend
        asr = DeepgramSTTBackend(api_key=settings.deepgram_api_key)
    else:
        raise ValueError(f"Unknown STT backend: {backend_name}")

    transcription = await asr.transcribe(audio_in)
    return {
        "text_out": transcription.text,
        "_language": transcription.language,
        "_confidence": transcription.confidence,
    }
