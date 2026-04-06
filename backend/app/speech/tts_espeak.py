"""eSpeak/pyttsx3 TTS provider — system-level speech synthesis (offline, free).

Requires: pip install pyttsx3
Uses the system's speech engine (eSpeak on Linux, NSSpeech on macOS, SAPI5 on Windows).
Quality is low (robotic) but works offline with zero setup.
"""

from __future__ import annotations

import tempfile
import wave

import numpy as np

from ..audio.types import AudioBuffer
from .tts_base import VoiceInfo


class ESpeakTTSProvider:
    """TTS provider using pyttsx3 (system speech engine)."""

    provider_name: str = "espeak"

    def __init__(self) -> None:
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            import pyttsx3
            self._engine = pyttsx3.init()
        return self._engine

    async def synthesize(self, text: str, voice_id: str) -> AudioBuffer:
        """Synthesize text using the system TTS engine.

        voice_id is a pyttsx3 voice ID string.
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._synthesize_sync, text, voice_id)

    def _synthesize_sync(self, text: str, voice_id: str) -> AudioBuffer:
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("voice", voice_id)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
            engine.save_to_file(text, f.name)
            engine.runAndWait()

            with wave.open(f.name, "rb") as wav:
                sample_rate = wav.getframerate()
                n_channels = wav.getnchannels()
                raw = wav.readframes(wav.getnframes())

        samples_int16 = np.frombuffer(raw, dtype=np.int16)
        # Mono downmix if stereo
        if n_channels == 2:
            samples_int16 = samples_int16.reshape(-1, 2).mean(axis=1).astype(np.int16)
        samples_f64 = samples_int16.astype(np.float64) / 32768.0

        return AudioBuffer(samples=samples_f64, sample_rate=sample_rate)

    async def list_voices(self) -> list[VoiceInfo]:
        """Query the system for available TTS voices."""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._list_voices_sync)

    def _list_voices_sync(self) -> list[VoiceInfo]:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            system_voices = engine.getProperty("voices")
        except Exception:
            return []

        voices = []
        for v in system_voices:
            # Extract language from voice ID or languages list
            lang = "en"
            if hasattr(v, "languages") and v.languages:
                raw_lang = v.languages[0]
                if isinstance(raw_lang, bytes):
                    raw_lang = raw_lang.decode("utf-8", errors="ignore")
                lang = raw_lang.strip("\x00").split("_")[0] if raw_lang else "en"

            # Guess gender from name
            name_lower = (v.name or "").lower()
            gender = "neutral"
            if any(w in name_lower for w in ("female", "woman", "girl")):
                gender = "female"
            elif any(w in name_lower for w in ("male", "man", "boy")):
                gender = "male"

            voices.append(
                VoiceInfo(
                    provider=self.provider_name,
                    voice_id=v.id,
                    name=v.name or v.id,
                    gender=gender,
                    age_group="adult",
                    accent="system",
                    language=lang,
                )
            )

        return voices
