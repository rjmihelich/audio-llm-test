"""Whisper ASR backend — both local and API modes."""

from __future__ import annotations

import time
import io

from ..audio.types import AudioBuffer
from ..audio.io import audio_to_wav_bytes
from .base import Transcription


class WhisperLocalBackend:
    """Local Whisper inference using faster-whisper (CTranslate2).

    Much lighter on memory than openai-whisper + torch.
    """

    def __init__(self, model_size: str = "base"):
        self._model_size = model_size
        self._model = None  # Lazy load

    @property
    def name(self) -> str:
        return f"whisper-local:{self._model_size}"

    def _ensure_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self._model_size,
                device="cpu",
                compute_type="int8",
            )

    async def transcribe(self, audio: AudioBuffer) -> Transcription:
        import asyncio
        import numpy as np
        self._ensure_model()

        # Whisper expects 16kHz float32
        audio_16k = audio.resample(16000)
        samples = audio_16k.samples.astype(np.float32)

        t0 = time.monotonic()
        loop = asyncio.get_event_loop()

        def _transcribe():
            segments_gen, info = self._model.transcribe(
                samples,
                beam_size=1,
                best_of=1,
                language="en",
            )
            segments = list(segments_gen)
            return segments, info

        segments, info = await loop.run_in_executor(None, _transcribe)
        latency_ms = (time.monotonic() - t0) * 1000

        text = " ".join(seg.text.strip() for seg in segments).strip()
        word_timestamps = []
        for seg in segments:
            word_timestamps.append({
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
            })

        avg_logprob = sum(seg.avg_logprob for seg in segments) / max(len(segments), 1)
        confidence = min(1.0, max(0.0, 1.0 + avg_logprob))

        return Transcription(
            text=text,
            language=info.language if info else "",
            confidence=confidence,
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
