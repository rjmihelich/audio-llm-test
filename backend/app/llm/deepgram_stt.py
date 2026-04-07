"""Deepgram Nova-2 ASR backend — low-latency speech-to-text."""

from __future__ import annotations

import time
import io

import httpx

from ..audio.types import AudioBuffer
from ..audio.io import audio_to_wav_bytes
from .base import Transcription


class DeepgramSTTBackend:
    """Speech-to-text via Deepgram Nova-2 REST API.

    Optimized for low latency (~100-300ms). Preferred over Whisper
    for real-time voice assistant applications.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "nova-2",
        language: str = "en",
    ):
        self._api_key = api_key
        self._model = model
        self._language = language
        self._http = httpx.AsyncClient(
            base_url="https://api.deepgram.com",
            headers={
                "Authorization": f"Token {api_key}",
            },
            timeout=30.0,
        )

    @property
    def name(self) -> str:
        return f"deepgram:{self._model}"

    async def transcribe(self, audio: AudioBuffer) -> Transcription:
        """Transcribe audio using Deepgram Nova-2."""
        wav_bytes = audio_to_wav_bytes(audio)

        params = {
            "model": self._model,
            "language": self._language,
            "punctuate": "true",
            "smart_format": "true",
        }

        t0 = time.monotonic()
        response = await self._http.post(
            "/v1/listen",
            content=wav_bytes,
            params=params,
            headers={"Content-Type": "audio/wav"},
        )
        response.raise_for_status()
        latency_ms = (time.monotonic() - t0) * 1000

        data = response.json()
        results = data.get("results", {})
        channels = results.get("channels", [])

        text = ""
        confidence = 0.0
        word_timestamps = []

        if channels:
            alternatives = channels[0].get("alternatives", [])
            if alternatives:
                best = alternatives[0]
                text = best.get("transcript", "")
                confidence = best.get("confidence", 0.0)

                for word in best.get("words", []):
                    word_timestamps.append({
                        "start": word.get("start", 0.0),
                        "end": word.get("end", 0.0),
                        "text": word.get("word", ""),
                        "confidence": word.get("confidence", 0.0),
                    })

        language = ""
        detected = results.get("channels", [{}])[0].get("detected_language", "")
        if detected:
            language = detected

        return Transcription(
            text=text.strip(),
            language=language or self._language,
            confidence=confidence,
            word_timestamps=word_timestamps if word_timestamps else None,
            latency_ms=latency_ms,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()
