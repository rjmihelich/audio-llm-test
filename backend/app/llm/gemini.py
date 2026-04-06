"""Google Gemini backend — supports direct audio input."""

from __future__ import annotations

import time

import google.generativeai as genai

from ..audio.types import AudioBuffer
from ..audio.io import audio_to_wav_bytes
from .base import LLMResponse, RateLimitConfig


class GeminiBackend:
    """Google Gemini with audio input support."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        rate_limit: RateLimitConfig | None = None,
    ):
        genai.configure(api_key=api_key)
        self._model_name = model
        self._model = genai.GenerativeModel(model)
        self._rate_limit = rate_limit or RateLimitConfig(
            requests_per_minute=100, tokens_per_minute=200_000, max_concurrent=20
        )

    @property
    def name(self) -> str:
        return f"gemini:{self._model_name}"

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
        wav_bytes = audio_to_wav_bytes(audio)

        parts = []
        if context:
            parts.append(context)
        parts.append({
            "mime_type": "audio/wav",
            "data": wav_bytes,
        })

        t0 = time.monotonic()
        response = await self._model.generate_content_async(
            parts,
            generation_config=genai.GenerationConfig(
                temperature=0.1,
            ),
            system_instruction=system_prompt,
        )
        latency_ms = (time.monotonic() - t0) * 1000

        text = response.text if response.text else ""
        usage = getattr(response, "usage_metadata", None)

        return LLMResponse(
            text=text,
            latency_ms=latency_ms,
            input_tokens=getattr(usage, "prompt_token_count", 0) if usage else 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) if usage else 0,
            model=self._model_name,
            raw_response={"text": text},
        )

    async def query_with_text(
        self,
        text: str,
        system_prompt: str,
        context: str | None = None,
    ) -> LLMResponse:
        prompt = f"{context}\n\n{text}" if context else text

        t0 = time.monotonic()
        response = await self._model.generate_content_async(
            prompt,
            generation_config=genai.GenerationConfig(temperature=0.1),
            system_instruction=system_prompt,
        )
        latency_ms = (time.monotonic() - t0) * 1000

        resp_text = response.text if response.text else ""
        usage = getattr(response, "usage_metadata", None)

        return LLMResponse(
            text=resp_text,
            latency_ms=latency_ms,
            input_tokens=getattr(usage, "prompt_token_count", 0) if usage else 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) if usage else 0,
            model=self._model_name,
            raw_response={"text": resp_text},
        )
