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
    """Local LLM via Ollama HTTP API. Text-only.

    Concurrency is adaptive: on first use, probes the Ollama server for
    GPU VRAM and model size, then computes optimal max_concurrent.
    Pass max_concurrent explicitly to override auto-detection.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1",
        rate_limit: RateLimitConfig | None = None,
        max_concurrent: int | None = None,
        request_timeout: float = 90.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._model_resolved = False
        self._request_timeout = request_timeout
        self._max_concurrent_override = max_concurrent
        self._probed = False
        self._hardware_info = None
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(
                connect=10.0,
                read=request_timeout,
                write=10.0,
                pool=5.0,
            ),
        )
        if rate_limit:
            self._rate_limit = rate_limit
        elif max_concurrent is not None:
            self._rate_limit = RateLimitConfig(
                requests_per_minute=1000,
                tokens_per_minute=1_000_000,
                max_concurrent=max_concurrent,
            )
        else:
            # Placeholder — will be updated by probe_and_configure()
            self._rate_limit = RateLimitConfig(
                requests_per_minute=1000,
                tokens_per_minute=1_000_000,
                max_concurrent=4,  # Conservative default until probed
            )

    async def probe_and_configure(self) -> None:
        """Probe Ollama server and set optimal concurrency. Safe to call multiple times."""
        if self._probed or self._max_concurrent_override is not None:
            return

        try:
            from .ollama_probe import probe_ollama
            self._hardware_info = await probe_ollama(
                base_url=self._base_url,
                model=self._model,
            )
            optimal = self._hardware_info.recommended_concurrency
            self._rate_limit = RateLimitConfig(
                requests_per_minute=1000,
                tokens_per_minute=1_000_000,
                max_concurrent=optimal,
            )
            logger.info(
                f"Ollama adaptive concurrency for {self._model}: "
                f"max_concurrent={optimal} "
                f"(vram={self._hardware_info.total_vram_bytes / 1e9:.1f}GB, "
                f"model={self._hardware_info.model_size_bytes / 1e9:.1f}GB)"
            )
        except Exception as e:
            logger.warning(f"Ollama probe failed, using default concurrency: {e}")
        finally:
            self._probed = True

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

    async def _resolve_model(self) -> None:
        """Resolve model name to an available tag if bare name doesn't exist.

        Ollama requires the full tag (e.g. llama3.1:8b). If the user specifies
        just 'llama3.1', look up available models and find the best match.
        """
        if self._model_resolved:
            return
        self._model_resolved = True

        # If model already has a tag, use as-is
        if ":" in self._model:
            return

        try:
            resp = await self._client.get("/api/tags", timeout=10)
            if resp.status_code != 200:
                return
            models = resp.json().get("models", [])
            names = [m["name"] for m in models]

            # Exact match (some models work without tag)
            if self._model in names:
                return

            # Find models that start with our base name
            candidates = [n for n in names if n.startswith(f"{self._model}:")]
            if candidates:
                # Prefer :latest first, then smallest parameter count
                def _sort_key(name: str) -> tuple:
                    tag = name.split(":", 1)[1] if ":" in name else ""
                    if tag == "latest":
                        return (0, 0)
                    # Extract numeric size (e.g. "8b" → 8, "70b" → 70)
                    import re
                    m = re.search(r"(\d+)[bB]", tag)
                    size = int(m.group(1)) if m else 999
                    return (1, size)
                candidates.sort(key=_sort_key)
                self._model = candidates[0]
                logger.info("Resolved model '%s' → '%s'", self._model.split(":")[0], self._model)
        except Exception as e:
            logger.debug("Model resolution failed: %s", e)

    async def query_with_text(
        self,
        text: str,
        system_prompt: str,
        context: str | None = None,
    ) -> LLMResponse:
        await self._resolve_model()
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
