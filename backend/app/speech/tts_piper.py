"""Piper TTS provider — fast local neural TTS (offline, free).

Requires: pip install piper-tts
Models are downloaded automatically on first use.
"""

from __future__ import annotations

import io
import tempfile
import wave

import numpy as np

from ..audio.types import AudioBuffer
from .tts_base import VoiceInfo

_DEFAULT_MODEL = "en_US-lessac-medium"

# Curated voice list — Piper ships many ONNX models.
# Each tuple: (model_name, display_name, gender, age_group, accent, language)
_VOICE_MAP: list[tuple[str, str, str, str, str, str]] = [
    ("en_US-lessac-medium", "Lessac", "female", "adult", "american", "en"),
    ("en_US-amy-medium", "Amy", "female", "adult", "american", "en"),
    ("en_US-ryan-medium", "Ryan", "male", "adult", "american", "en"),
    ("en_US-arctic-medium", "Arctic", "male", "adult", "american", "en"),
    ("en_US-libritts-high", "LibriTTS", "neutral", "adult", "american", "en"),
    ("en_GB-alan-medium", "Alan", "male", "adult", "british", "en-GB"),
    ("en_GB-cori-medium", "Cori", "female", "adult", "british", "en-GB"),
    ("de_DE-thorsten-medium", "Thorsten", "male", "adult", "german", "de"),
    ("de_DE-eva_k-x_low", "Eva", "female", "adult", "german", "de"),
    ("fr_FR-upmc-medium", "UPMC", "male", "adult", "french", "fr"),
    ("es_ES-davefx-medium", "DaveFX", "male", "adult", "spanish", "es"),
    ("es_MX-ald-medium", "Ald", "male", "adult", "mexican", "es-MX"),
    ("it_IT-riccardo-x_low", "Riccardo", "male", "adult", "italian", "it"),
    ("pt_BR-edresson-low", "Edresson", "male", "adult", "brazilian", "pt-BR"),
    ("zh_CN-huayan-x_low", "Huayan", "female", "adult", "mandarin", "zh"),
    ("ja_JP-kokoro-medium-v1.0", "Kokoro", "female", "adult", "japanese", "ja"),
    ("ko_KR-x_low", "Korean", "female", "adult", "korean", "ko"),
    ("ru_RU-irina-medium", "Irina", "female", "adult", "russian", "ru"),
]


class PiperTTSProvider:
    """TTS provider using Piper for fast local neural synthesis."""

    provider_name: str = "piper"

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self._default_model = model

    async def synthesize(self, text: str, voice_id: str) -> AudioBuffer:
        """Synthesize text using a Piper voice model.

        voice_id should be a Piper model name (e.g. 'en_US-lessac-medium').
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._synthesize_sync, text, voice_id)

    def _synthesize_sync(self, text: str, voice_id: str) -> AudioBuffer:
        from piper import PiperVoice

        voice = PiperVoice.load(voice_id, download_dir=None, update=False)

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            voice.synthesize(text, wav)

        buf.seek(0)
        with wave.open(buf, "rb") as wav:
            sample_rate = wav.getframerate()
            n_frames = wav.getnframes()
            raw = wav.readframes(n_frames)

        samples_int16 = np.frombuffer(raw, dtype=np.int16)
        samples_f64 = samples_int16.astype(np.float64) / 32768.0
        return AudioBuffer(samples=samples_f64, sample_rate=sample_rate)

    async def list_voices(self) -> list[VoiceInfo]:
        """Return curated set of Piper voices."""
        return [
            VoiceInfo(
                provider=self.provider_name,
                voice_id=model,
                name=name,
                gender=gender,
                age_group=age_group,
                accent=accent,
                language=lang,
            )
            for model, name, gender, age_group, accent, lang in _VOICE_MAP
        ]
