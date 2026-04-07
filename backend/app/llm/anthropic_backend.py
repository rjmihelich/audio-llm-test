"""Anthropic Claude backend — text-only, always uses Pipeline B (ASR first)."""

from __future__ import annotations

import time

import anthropic

from ..audio.types import AudioBuffer
from .base import LLMResponse, RateLimitConfig


class AnthropicBackend:
    """Claude via Anthropic API. Text-only — does not support direct audio input."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5-20251001",
        rate_limit: RateLimitConfig | None = None,
    ):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._rate_limit = rate_limit or RateLimitConfig(
            requests_per_minute=50, tokens_per_minute=100_000, max_concurrent=10
        )

    @property
    def name(self) -> str:
        return f"anthropic:{self._model}"

    @property
    def supports_audio_input(self) -> bool:
        return False

    @property
    def rate_limit(self) -> RateLimitConfig:
        return self._rate_limit

    async def query_with_audio(
        self,
        audio: AudioBuffer,
        system_prompt: str,
        context: str | None = None,
    ) -> LLMResponse:
        raise NotImplementedError(
            "Claude does not support direct audio input. Use Pipeline B (ASR → text → LLM)."
        )

    async def query_with_text(
        self,
        text: str,
        system_prompt: str,
        context: str | None = None,
    ) -> LLMResponse:
        messages = []
        if context:
            messages.append({"role": "user", "content": context})
            messages.append({"role": "assistant", "content": "Understood. I'll consider that context."})
        messages.append({"role": "user", "content": text})

        t0 = time.monotonic()
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )
        latency_ms = (time.monotonic() - t0) * 1000

        text_out = ""
        for block in response.content:
            if block.type == "text":
                text_out += block.text

        return LLMResponse(
            text=text_out,
            latency_ms=latency_ms,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=self._model,
            raw_response=response.model_dump(),
        )
