"""ElevenLabs TTS provider implementation (REST API via httpx)."""

from __future__ import annotations

import numpy as np
import httpx

from ..audio.types import AudioBuffer
from ..config import settings
from .tts_base import VoiceInfo

_BASE_URL = "https://api.elevenlabs.io"
_OUTPUT_FORMAT = "pcm_16000"
_SAMPLE_RATE = 16000


def _map_gender(labels: dict[str, str]) -> str:
    """Extract gender from ElevenLabs voice label metadata."""
    gender = labels.get("gender", "").lower()
    if gender in ("male", "female"):
        return gender
    return "neutral"


def _map_age_group(labels: dict[str, str]) -> str:
    """Map ElevenLabs age label to our canonical age groups."""
    age = labels.get("age", "").lower()
    mapping = {
        "young": "young_adult",
        "middle aged": "adult",
        "middle-aged": "adult",
        "old": "senior",
    }
    return mapping.get(age, "adult")


def _map_accent(labels: dict[str, str]) -> str:
    return labels.get("accent", "american").lower()


class ElevenLabsTTSProvider:
    """TTS provider backed by the ElevenLabs REST API."""

    provider_name: str = "elevenlabs"

    def __init__(
        self,
        api_key: str | None = None,
        model_id: str = "eleven_monolingual_v1",
    ) -> None:
        self._api_key = api_key or settings.elevenlabs_api_key
        self._model_id = model_id
        self._http = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={
                "xi-api-key": self._api_key,
                "Accept": "application/json",
            },
            timeout=60.0,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def synthesize(self, text: str, voice_id: str) -> AudioBuffer:
        """Synthesize *text* using the specified ElevenLabs voice.

        Returns an :class:`AudioBuffer` at 16 kHz (``pcm_16000`` output format).
        """
        url = f"/v1/text-to-speech/{voice_id}"
        payload = {
            "text": text,
            "model_id": self._model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }
        params = {"output_format": _OUTPUT_FORMAT}

        response = await self._http.post(
            url,
            json=payload,
            params=params,
            headers={"Accept": "audio/pcm"},
        )
        response.raise_for_status()

        # pcm_16000 returns signed 16-bit little-endian mono PCM at 16 kHz.
        samples_int16 = np.frombuffer(response.content, dtype=np.int16)
        samples_f64 = samples_int16.astype(np.float64) / 32768.0

        return AudioBuffer(samples=samples_f64, sample_rate=_SAMPLE_RATE)

    async def list_voices(self) -> list[VoiceInfo]:
        """Fetch the available voices from the ElevenLabs API."""
        response = await self._http.get("/v1/voices")
        response.raise_for_status()

        data = response.json()
        voices: list[VoiceInfo] = []
        for v in data.get("voices", []):
            labels: dict[str, str] = v.get("labels", {})
            voices.append(
                VoiceInfo(
                    provider=self.provider_name,
                    voice_id=v["voice_id"],
                    name=v.get("name", v["voice_id"]),
                    gender=_map_gender(labels),
                    age_group=_map_age_group(labels),
                    accent=_map_accent(labels),
                    language=labels.get("language", "en"),
                )
            )
        return voices

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()
