"""LLM node executors — standard request/response and realtime streaming."""

from __future__ import annotations

import time
from typing import Any

from backend.app.audio.types import AudioBuffer

from ..engine.graph_executor import ExecutionContext, GraphNode


async def execute_llm(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Standard request/response LLM execution."""
    audio_in = inputs.get("audio_in")
    text_in = inputs.get("text_in")

    if audio_in is None and text_in is None:
        raise ValueError("LLM node: at least one of audio_in or text_in required")

    backend_str = config.get("backend", "openai:gpt-4o-audio-preview")
    system_prompt = config.get("system_prompt", "You are a helpful in-car voice assistant.")
    temperature = config.get("temperature", 0.7)

    # Parse backend string
    provider, _, model = backend_str.partition(":")

    from backend.app.config import settings

    backend = _get_llm_backend(provider, model, settings)

    start = time.monotonic()

    if audio_in is not None and isinstance(audio_in, AudioBuffer):
        response = await backend.query_with_audio(
            audio=audio_in,
            system_prompt=system_prompt,
        )
    elif text_in:
        response = await backend.query_with_text(
            text=text_in,
            system_prompt=system_prompt,
        )
    else:
        raise ValueError("LLM node: no valid input")

    latency_ms = (time.monotonic() - start) * 1000

    return {
        "text_out": response.text,
        "audio_out": response.audio if hasattr(response, "audio") else None,
        "_latency_ms": latency_ms,
    }


async def execute_llm_realtime(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """OpenAI Realtime API streaming execution."""
    audio_in = inputs.get("audio_in")
    if audio_in is None:
        raise ValueError("LLM Realtime node: audio_in is required")

    from ..realtime.openai_realtime import OpenAIRealtimeSession

    model = config.get("model", "gpt-4o-realtime-preview")
    voice = config.get("voice", "alloy")
    modalities = config.get("modalities", "text_and_audio")
    turn_detection = config.get("turn_detection", "server_vad")
    temperature = config.get("temperature", 0.8)
    system_prompt = config.get("system_prompt", "You are a helpful in-car voice assistant.")
    chunk_ms = config.get("chunk_ms", 20)

    session_config = {
        "model": model,
        "voice": voice,
        "modalities": ["text", "audio"] if modalities == "text_and_audio" else ["text"],
        "turn_detection": turn_detection,
        "temperature": temperature,
        "instructions": system_prompt,
    }

    start = time.monotonic()

    async with OpenAIRealtimeSession(session_config) as session:
        # Stream audio in chunks with real-time pacing
        chunk_samples = int(chunk_ms * audio_in.sample_rate / 1000)

        for i in range(0, len(audio_in.samples), chunk_samples):
            chunk = audio_in.samples[i:i + chunk_samples]
            await session.send_audio(chunk, audio_in.sample_rate)
            # Await to not be faster than real time
            import asyncio
            await asyncio.sleep(chunk_ms / 1000)

        # Signal end of input
        await session.signal_turn_end()

        # Collect response
        response = await session.receive_response()

    latency_ms = (time.monotonic() - start) * 1000
    first_byte_ms = response.get("first_byte_ms", 0)

    return {
        "text_out": response.get("transcript", ""),
        "audio_out": response.get("audio"),
        "_latency_ms": latency_ms,
        "_first_byte_ms": first_byte_ms,
    }


def _get_llm_backend(provider: str, model: str, settings):
    """Instantiate an LLM backend from provider string."""
    if provider == "openai":
        from backend.app.llm.openai_audio import OpenAIAudioBackend
        return OpenAIAudioBackend(api_key=settings.openai_api_key, model=model)
    elif provider == "gemini":
        from backend.app.llm.gemini import GeminiBackend
        return GeminiBackend(api_key=settings.google_api_key, model=model)
    elif provider == "anthropic":
        from backend.app.llm.anthropic_backend import AnthropicBackend
        return AnthropicBackend(api_key=settings.anthropic_api_key, model=model)
    elif provider == "ollama":
        from backend.app.llm.ollama import OllamaBackend
        return OllamaBackend(base_url=settings.ollama_base_url, model=model)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
