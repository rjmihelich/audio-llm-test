"""Bark TTS provider — Suno's open-source text-to-audio model (offline, free).

Requires: pip install suno-bark
First run downloads models (~5 GB). GPU strongly recommended.
"""

from __future__ import annotations

import numpy as np

from ..audio.types import AudioBuffer
from .tts_base import VoiceInfo

_BARK_SAMPLE_RATE = 24000

# Bark speaker presets — v2/ prefix for the newer models.
# tuple: (preset, display_name, gender, age_group, accent, language)
_PRESET_MAP: list[tuple[str, str, str, str, str, str]] = [
    ("v2/en_speaker_0", "English Speaker 0", "male", "adult", "american", "en"),
    ("v2/en_speaker_1", "English Speaker 1", "male", "young_adult", "american", "en"),
    ("v2/en_speaker_2", "English Speaker 2", "male", "adult", "american", "en"),
    ("v2/en_speaker_3", "English Speaker 3", "male", "adult", "american", "en"),
    ("v2/en_speaker_4", "English Speaker 4", "female", "adult", "american", "en"),
    ("v2/en_speaker_5", "English Speaker 5", "female", "adult", "american", "en"),
    ("v2/en_speaker_6", "English Speaker 6", "female", "young_adult", "american", "en"),
    ("v2/en_speaker_7", "English Speaker 7", "male", "senior", "american", "en"),
    ("v2/en_speaker_8", "English Speaker 8", "female", "adult", "american", "en"),
    ("v2/en_speaker_9", "English Speaker 9", "female", "adult", "american", "en"),
    ("v2/de_speaker_0", "German Speaker 0", "male", "adult", "german", "de"),
    ("v2/de_speaker_3", "German Speaker 3", "female", "adult", "german", "de"),
    ("v2/fr_speaker_0", "French Speaker 0", "male", "adult", "french", "fr"),
    ("v2/fr_speaker_3", "French Speaker 3", "female", "adult", "french", "fr"),
    ("v2/es_speaker_0", "Spanish Speaker 0", "male", "adult", "spanish", "es"),
    ("v2/es_speaker_3", "Spanish Speaker 3", "female", "adult", "spanish", "es"),
    ("v2/ja_speaker_0", "Japanese Speaker 0", "male", "adult", "japanese", "ja"),
    ("v2/zh_speaker_0", "Chinese Speaker 0", "male", "adult", "mandarin", "zh"),
    ("v2/ko_speaker_0", "Korean Speaker 0", "female", "adult", "korean", "ko"),
]


class BarkTTSProvider:
    """TTS provider using Suno Bark for expressive speech generation."""

    provider_name: str = "bark"

    def __init__(self, use_gpu: bool = False, use_small: bool = False) -> None:
        self._use_gpu = use_gpu
        self._use_small = use_small
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            from bark import preload_models
            preload_models(
                text_use_gpu=self._use_gpu,
                coarse_use_gpu=self._use_gpu,
                fine_use_gpu=self._use_gpu,
                text_use_small=self._use_small,
                coarse_use_small=self._use_small,
                fine_use_small=self._use_small,
            )
            self._loaded = True

    async def synthesize(self, text: str, voice_id: str) -> AudioBuffer:
        """Synthesize text using Bark.

        voice_id is a Bark speaker preset (e.g. 'v2/en_speaker_6').
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._synthesize_sync, text, voice_id)

    def _synthesize_sync(self, text: str, voice_id: str) -> AudioBuffer:
        self._ensure_loaded()
        from bark import generate_audio

        audio_array = generate_audio(text, history_prompt=voice_id)

        # Bark outputs float32 numpy array at 24 kHz
        samples_f64 = audio_array.astype(np.float64)

        # Normalize to [-1, 1] if needed
        peak = np.max(np.abs(samples_f64))
        if peak > 1.0:
            samples_f64 /= peak

        return AudioBuffer(samples=samples_f64, sample_rate=_BARK_SAMPLE_RATE)

    async def list_voices(self) -> list[VoiceInfo]:
        """Return Bark speaker presets."""
        return [
            VoiceInfo(
                provider=self.provider_name,
                voice_id=preset,
                name=name,
                gender=gender,
                age_group=age_group,
                accent=accent,
                language=lang,
            )
            for preset, name, gender, age_group, accent, lang in _PRESET_MAP
        ]
