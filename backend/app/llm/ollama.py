"""Ollama backend for local LLM inference — text-only, always Pipeline B."""

from __future__ import annotations

import time

import httpx

from ..audio.types import AudioBuffer
from .base import LLMResponse, RateLimitConfig


class OllamaBackend:
    """Local LLM via Ollama HTTP API. Text-only."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1",
        rate_limit: RateLimitConfig | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=120.0)
        self._rate_limit = rate_limit or RateLimitConfig(
            requests_per_minute=1000,  # Local, effectively unlimited
            tokens_per_minute=1_000_000,
            max_concurrent=4,  # Limited by GPU memory
        )

    @property
    def name(self) -> str:
        return f"ollama:{self._model}"

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
            "Ollama does not support direct audio input. Use Pipeline B (ASR → text → LLM)."
        )

    async def query_with_text(
        self,
        text: str,
        system_prompt: str,
        context: str | None = None,
    ) -> LLMResponse:
        prompt = f"{context}\n\n{text}" if context else text

        t0 = time.monotonic()
        response = await self._client.post(
            "/api/generate",
            json={
                "model": self._model,
                "prompt": prompt,
                "system": system_prompt,
                "stream": False,
            },
        )
        response.raise_for_status()
        latency_ms = (time.monotonic() - t0) * 1000

        data = response.json()
        return LLMResponse(
            text=data.get("response", ""),
            latency_ms=latency_ms,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            model=self._model,
            raw_response=data,
        )

    async def close(self):
        await self._client.aclose()
