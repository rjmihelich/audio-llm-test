"""OpenAI GPT-4o audio backend — supports direct audio input and audio output."""

from __future__ import annotations

import time
import base64

from openai import AsyncOpenAI

from ..audio.types import AudioBuffer
from ..audio.io import audio_to_base64, pcm16_bytes_to_audio
from .base import LLMResponse, RateLimitConfig


class OpenAIAudioBackend:
    """GPT-4o with audio modality via Chat Completions API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-audio-preview",
        rate_limit: RateLimitConfig | None = None,
    ):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._rate_limit = rate_limit or RateLimitConfig(
            requests_per_minute=50, tokens_per_minute=100_000, max_concurrent=10
        )

    @property
    def name(self) -> str:
        return f"openai:{self._model}"

    @property
    def supports_audio_input(self) -> bool:
        return True

    @property
    def rate_limit(self) -> RateLimitConfig:
        return self._rate_limit

    async def query_with_audio(
        self,
        audio: AudioBuffer,
        system_prompt: str,
        context: str | None = None,
    ) -> LLMResponse:
        # GPT-4o audio expects 24kHz PCM16
        audio_24k = audio.resample(24000)
        audio_b64 = audio_to_base64(audio_24k)

        messages = [{"role": "system", "content": system_prompt}]
        if context:
            messages.append({"role": "user", "content": context})

        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": audio_b64,
                        "format": "pcm16",
                    },
                }
            ],
        })

        t0 = time.monotonic()
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            modalities=["text", "audio"],
            audio={"voice": "alloy", "format": "pcm16"},
        )
        latency_ms = (time.monotonic() - t0) * 1000

        choice = response.choices[0]
        text = choice.message.content or ""
        response_audio = None

        # Extract audio response if present
        if hasattr(choice.message, "audio") and choice.message.audio:
            audio_data = base64.b64decode(choice.message.audio.data)
            response_audio = pcm16_bytes_to_audio(audio_data, sample_rate=24000)
            if not text and choice.message.audio.transcript:
                text = choice.message.audio.transcript

        return LLMResponse(
            text=text,
            audio=response_audio,
            latency_ms=latency_ms,
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            model=self._model,
            raw_response=response.model_dump(),
        )

    async def query_with_text(
        self,
        text: str,
        system_prompt: str,
        context: str | None = None,
    ) -> LLMResponse:
        messages = [{"role": "system", "content": system_prompt}]
        if context:
            messages.append({"role": "user", "content": context})
        messages.append({"role": "user", "content": text})

        t0 = time.monotonic()
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
        )
        latency_ms = (time.monotonic() - t0) * 1000

        choice = response.choices[0]
        return LLMResponse(
            text=choice.message.content or "",
            latency_ms=latency_ms,
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            model=self._model,
            raw_response=response.model_dump(),
        )
