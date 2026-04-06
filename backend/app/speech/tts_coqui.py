"""Coqui TTS provider — open-source multi-model TTS (offline, free).

Requires: pip install TTS
Models are downloaded automatically on first use (~200 MB–1.5 GB per model).
"""

from __future__ import annotations

import tempfile

import numpy as np

from ..audio.types import AudioBuffer
from .tts_base import VoiceInfo

_DEFAULT_MODEL = "tts_models/en/ljspeech/tacotron2-DDC"

# Curated model list — each is a full Coqui TTS model path.
# tuple: (model_name, display_name, gender, age_group, accent, language)
_MODEL_MAP: list[tuple[str, str, str, str, str, str]] = [
    ("tts_models/en/ljspeech/tacotron2-DDC", "LJSpeech Tacotron2", "female", "adult", "american", "en"),
    ("tts_models/en/ljspeech/vits", "LJSpeech VITS", "female", "adult", "american", "en"),
    ("tts_models/en/ljspeech/glow-tts", "LJSpeech GlowTTS", "female", "adult", "american", "en"),
    ("tts_models/en/vctk/vits", "VCTK VITS (multi)", "neutral", "adult", "british", "en"),
    ("tts_models/en/jenny/jenny", "Jenny", "female", "young_adult", "american", "en"),
    ("tts_models/de/thorsten/tacotron2-DDC", "Thorsten DE", "male", "adult", "german", "de"),
    ("tts_models/fr/mai/tacotron2-DDC", "Mai FR", "female", "adult", "french", "fr"),
    ("tts_models/es/css10/vits", "CSS10 ES", "female", "adult", "spanish", "es"),
    ("tts_models/ja/kokoro/tacotron2-DDC", "Kokoro JA", "female", "adult", "japanese", "ja"),
    ("tts_models/zh-CN/baker/tacotron2-DDC-GST", "Baker ZH", "female", "adult", "mandarin", "zh"),
    ("tts_models/multilingual/multi-dataset/xtts_v2", "XTTS v2 (multilingual)", "neutral", "adult", "american", "en"),
]


class CoquiTTSProvider:
    """TTS provider using Coqui TTS for open-source synthesis."""

    provider_name: str = "coqui"

    def __init__(self, model: str = _DEFAULT_MODEL, gpu: bool = False) -> None:
        self._model_name = model
        self._gpu = gpu
        self._tts = None  # Lazy init

    def _get_tts(self):
        if self._tts is None:
            from TTS.api import TTS
            self._tts = TTS(model_name=self._model_name, gpu=self._gpu)
        return self._tts

    async def synthesize(self, text: str, voice_id: str) -> AudioBuffer:
        """Synthesize text using a Coqui TTS model.

        voice_id is the full Coqui model path.
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._synthesize_sync, text, voice_id)

    def _synthesize_sync(self, text: str, voice_id: str) -> AudioBuffer:
        from TTS.api import TTS

        tts = TTS(model_name=voice_id, gpu=self._gpu)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
            tts.tts_to_file(text=text, file_path=f.name)

            import wave
            with wave.open(f.name, "rb") as wav:
                sample_rate = wav.getframerate()
                raw = wav.readframes(wav.getnframes())

        samples_int16 = np.frombuffer(raw, dtype=np.int16)
        samples_f64 = samples_int16.astype(np.float64) / 32768.0
        return AudioBuffer(samples=samples_f64, sample_rate=sample_rate)

    async def list_voices(self) -> list[VoiceInfo]:
        """Return curated set of Coqui TTS models as voices."""
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
            for model, name, gender, age_group, accent, lang in _MODEL_MAP
        ]
