"""OpenAI Realtime API backend — WebSocket-based audio-in/audio-out via the Realtime API."""

from __future__ import annotations

import asyncio
import base64
import logging
import time

from openai import AsyncOpenAI

from ..audio.types import AudioBuffer
from ..audio.io import audio_to_pcm16_bytes, pcm16_bytes_to_audio
from .base import LLMResponse, RateLimitConfig

logger = logging.getLogger(__name__)

# Realtime API expects 24 kHz PCM16 mono
_REALTIME_SAMPLE_RATE = 24000

# Max chunk size when streaming audio into the session (base64 ~128 KB chunks)
_CHUNK_BYTES = 96_000  # 96 KB of raw PCM16 → ~2 seconds at 24 kHz mono


class OpenAIRealtimeBackend:
    """OpenAI Realtime API backend (batch-compatible wrapper).

    Opens a WebSocket session, sends the full audio buffer, collects the
    complete response, then closes the session.  This lets us slot into the
    existing pipeline / evaluation / checkpoint machinery unchanged.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-realtime-preview",
        voice: str = "alloy",
        rate_limit: RateLimitConfig | None = None,
    ):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._voice = voice
        self._rate_limit = rate_limit or RateLimitConfig(
            requests_per_minute=15,
            tokens_per_minute=100_000,
            max_concurrent=5,
        )

    # -- LLMBackend protocol properties --

    @property
    def name(self) -> str:
        return f"openai-realtime:{self._model}"

    @property
    def supports_audio_input(self) -> bool:
        return True

    @property
    def rate_limit(self) -> RateLimitConfig:
        return self._rate_limit

    # -- LLMBackend protocol methods --

    async def query_with_audio(
        self,
        audio: AudioBuffer,
        system_prompt: str,
        context: str | None = None,
    ) -> LLMResponse:
        audio_24k = audio.resample(_REALTIME_SAMPLE_RATE)
        pcm_bytes = audio_to_pcm16_bytes(audio_24k)

        t0 = time.monotonic()

        async with self._client.beta.realtime.connect(model=self._model) as conn:
            # Configure the session
            await conn.session.update(
                session={
                    "modalities": ["text", "audio"],
                    "instructions": system_prompt,
                    "voice": self._voice,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "turn_detection": None,  # manual turn management
                },
            )

            # If there's additional context, send it as a text message first
            if context:
                await conn.conversation.item.create(
                    item={
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": context}],
                    },
                )

            # Stream audio in chunks
            for offset in range(0, len(pcm_bytes), _CHUNK_BYTES):
                chunk = pcm_bytes[offset : offset + _CHUNK_BYTES]
                chunk_b64 = base64.b64encode(chunk).decode("ascii")
                await conn.input_audio_buffer.append(audio=chunk_b64)

            # Signal that we're done sending audio and request a response
            await conn.input_audio_buffer.commit()
            await conn.response.create()

            # Collect the full response
            response_text = ""
            audio_transcript = ""
            audio_chunks: list[bytes] = []
            input_tokens = 0
            output_tokens = 0

            async for event in conn:
                etype = event.type

                if etype == "response.audio_transcript.delta":
                    audio_transcript += event.delta

                elif etype == "response.text.delta":
                    response_text += event.delta

                elif etype == "response.audio.delta":
                    audio_chunks.append(base64.b64decode(event.delta))

                elif etype == "response.done":
                    resp = event.response
                    if resp.usage:
                        input_tokens = resp.usage.input_tokens or 0
                        output_tokens = resp.usage.output_tokens or 0
                    break

                elif etype == "error":
                    error_msg = getattr(event, "error", {})
                    raise RuntimeError(
                        f"Realtime API error: {error_msg}"
                    )

        latency_ms = (time.monotonic() - t0) * 1000

        # Use transcript as text if no explicit text was returned
        text = response_text or audio_transcript

        # Reassemble audio response
        response_audio = None
        if audio_chunks:
            all_audio = b"".join(audio_chunks)
            response_audio = pcm16_bytes_to_audio(all_audio, sample_rate=_REALTIME_SAMPLE_RATE)

        return LLMResponse(
            text=text,
            audio=response_audio,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self._model,
            raw_response={"api": "realtime", "voice": self._voice},
        )

    async def query_with_text(
        self,
        text: str,
        system_prompt: str,
        context: str | None = None,
    ) -> LLMResponse:
        t0 = time.monotonic()

        async with self._client.beta.realtime.connect(model=self._model) as conn:
            await conn.session.update(
                session={
                    "modalities": ["text"],
                    "instructions": system_prompt,
                    "turn_detection": None,
                },
            )

            content = []
            if context:
                content.append({"type": "input_text", "text": context})
            content.append({"type": "input_text", "text": text})

            await conn.conversation.item.create(
                item={
                    "type": "message",
                    "role": "user",
                    "content": content,
                },
            )
            await conn.response.create()

            response_text = ""
            input_tokens = 0
            output_tokens = 0

            async for event in conn:
                etype = event.type

                if etype == "response.text.delta":
                    response_text += event.delta

                elif etype == "response.done":
                    resp = event.response
                    if resp.usage:
                        input_tokens = resp.usage.input_tokens or 0
                        output_tokens = resp.usage.output_tokens or 0
                    break

                elif etype == "error":
                    error_msg = getattr(event, "error", {})
                    raise RuntimeError(
                        f"Realtime API error: {error_msg}"
                    )

        latency_ms = (time.monotonic() - t0) * 1000

        return LLMResponse(
            text=response_text,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self._model,
            raw_response={"api": "realtime"},
        )
