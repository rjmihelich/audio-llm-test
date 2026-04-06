"""Whisper ASR backend — both local and API modes."""

from __future__ import annotations

import time
import io

from ..audio.types import AudioBuffer
from ..audio.io import audio_to_wav_bytes
from .base import Transcription


class WhisperLocalBackend:
    """Local Whisper inference using openai-whisper package."""

    def __init__(self, model_size: str = "base"):
        self._model_size = model_size
        self._model = None  # Lazy load

    @property
    def name(self) -> str:
        return f"whisper-local:{self._model_size}"

    def _ensure_model(self):
        if self._model is None:
            import whisper
            self._model = whisper.load_model(self._model_size)

    async def transcribe(self, audio: AudioBuffer) -> Transcription:
        import asyncio
        self._ensure_model()

        # Whisper expects 16kHz
        audio_16k = audio.resample(16000)

        t0 = time.monotonic()
        # Run in executor since whisper is synchronous
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._model.transcribe(
                audio_16k.samples.astype("float32"),
                fp16=False,
            ),
        )
        latency_ms = (time.monotonic() - t0) * 1000

        segments = result.get("segments", [])
        word_timestamps = []
        for seg in segments:
            word_timestamps.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"],
            })

        return Transcription(
            text=result["text"].strip(),
            language=result.get("language", ""),
            confidence=1.0 - result.get("no_speech_prob", 0.0) if segments else 0.0,
            word_timestamps=word_timestamps,
            latency_ms=latency_ms,
        )


class WhisperAPIBackend:
    """Whisper via OpenAI API."""

    def __init__(self, api_key: str, model: str = "whisper-1"):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    @property
    def name(self) -> str:
        return f"whisper-api:{self._model}"

    async def transcribe(self, audio: AudioBuffer) -> Transcription:
        wav_bytes = audio_to_wav_bytes(audio)

        t0 = time.monotonic()
        response = await self._client.audio.transcriptions.create(
            model=self._model,
            file=("audio.wav", io.BytesIO(wav_bytes), "audio/wav"),
            response_format="verbose_json",
        )
        latency_ms = (time.monotonic() - t0) * 1000

        return Transcription(
            text=response.text.strip(),
            language=getattr(response, "language", ""),
            confidence=1.0,
            latency_ms=latency_ms,
        )
