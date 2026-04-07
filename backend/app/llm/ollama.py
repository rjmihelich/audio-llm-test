"""Ollama backend for local LLM inference — text-only, always Pipeline B."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from ..audio.types import AudioBuffer
from .base import LLMResponse, RateLimitConfig

logger = logging.getLogger(__name__)

# Delays between retries: 2s, 4s, 8s (3 retries after the initial attempt)
_RETRY_DELAYS = (2.0, 4.0, 8.0)

# Exceptions that are safe to retry
_RETRYABLE = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    asyncio.TimeoutError,
)


class OllamaBackend:
    """Local LLM via Ollama HTTP API. Text-only."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1",
        rate_limit: RateLimitConfig | None = None,
        request_timeout: float = 90.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._request_timeout = request_timeout
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(
                connect=10.0,
                read=request_timeout,
                write=10.0,
                pool=5.0,
            ),
        )
        self._rate_limit = rate_limit or RateLimitConfig(
            requests_per_minute=1000,  # Local, effectively unlimited
            tokens_per_minute=1_000_000,
            max_concurrent=8,  # Match OLLAMA_NUM_PARALLEL for full GPU utilization
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
        payload = {
            "model": self._model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
        }

        last_exc: Exception | None = None
        for attempt in range(len(_RETRY_DELAYS) + 1):
            if attempt > 0:
                delay = _RETRY_DELAYS[attempt - 1]
                logger.warning(
                    f"Ollama retry {attempt}/{len(_RETRY_DELAYS)} for model {self._model} "
                    f"after {delay}s — last error: {type(last_exc).__name__}: {last_exc}"
                )
                await asyncio.sleep(delay)

            try:
                t0 = time.monotonic()
                response = await asyncio.wait_for(
                    self._client.post("/api/generate", json=payload),
                    timeout=self._request_timeout,
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

            except _RETRYABLE as e:
                last_exc = e
                continue

            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500:
                    last_exc = e
                    continue
                raise

        raise last_exc or RuntimeError(
            f"Ollama request failed after {len(_RETRY_DELAYS) + 1} attempts"
        )

    async def close(self):
        await self._client.aclose()
