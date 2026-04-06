"""OpenAI TTS provider implementation."""

from __future__ import annotations

import numpy as np
from openai import AsyncOpenAI

from ..audio.types import AudioBuffer
from ..config import settings
from .tts_base import VoiceInfo

# Voice metadata: (voice_id, display_name, gender, age_group)
_VOICE_MAP: list[tuple[str, str, str, str]] = [
    ("alloy", "Alloy", "neutral", "young_adult"),
    ("echo", "Echo", "male", "adult"),
    ("fable", "Fable", "neutral", "adult"),
    ("onyx", "Onyx", "male", "adult"),
    ("nova", "Nova", "female", "young_adult"),
    ("shimmer", "Shimmer", "female", "adult"),
]

OPENAI_NATIVE_SAMPLE_RATE = 24000


class OpenAITTSProvider:
    """TTS provider backed by the OpenAI audio API."""

    provider_name: str = "openai"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "tts-1",
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
        self._model = model

    async def synthesize(self, text: str, voice_id: str) -> AudioBuffer:
        """Synthesize *text* with the given OpenAI voice.

        Returns an :class:`AudioBuffer` at 24 kHz (OpenAI native rate).
        The consumer can call ``buf.resample(target_sr)`` if needed.
        """
        response = await self._client.audio.speech.create(
            model=self._model,
            voice=voice_id,
            input=text,
            response_format="pcm",
        )

        raw_bytes = response.content
        # OpenAI PCM format: signed 16-bit little-endian mono at 24 kHz
        samples_int16 = np.frombuffer(raw_bytes, dtype=np.int16)
        samples_f64 = samples_int16.astype(np.float64) / 32768.0

        return AudioBuffer(samples=samples_f64, sample_rate=OPENAI_NATIVE_SAMPLE_RATE)

    async def list_voices(self) -> list[VoiceInfo]:
        """Return the fixed set of OpenAI TTS voices."""
        return [
            VoiceInfo(
                provider=self.provider_name,
                voice_id=vid,
                name=name,
                gender=gender,
                age_group=age_group,
                accent="american",
                language="en",
            )
            for vid, name, gender, age_group in _VOICE_MAP
        ]
