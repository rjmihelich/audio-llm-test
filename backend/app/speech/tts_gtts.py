"""gTTS provider — Google Translate TTS (free, no API key, online).

Requires: pip install gTTS
Uses Google Translate's undocumented TTS endpoint. No API key needed.
Audio quality is basic (MP3 → PCM conversion) but reliable and free.
"""

from __future__ import annotations

import io
import tempfile

import numpy as np

from ..audio.types import AudioBuffer
from .tts_base import VoiceInfo

# gTTS language → voice mapping.
# gTTS only exposes language, not individual voices, so we create one voice per language.
# tuple: (lang_code, display_name, accent, language_tag)
_LANG_MAP: list[tuple[str, str, str, str]] = [
    ("en", "English (US)", "american", "en"),
    ("en-gb", "English (UK)", "british", "en-GB"),
    ("en-au", "English (AU)", "australian", "en-AU"),
    ("en-in", "English (India)", "indian", "en-IN"),
    ("de", "German", "german", "de"),
    ("fr", "French", "french", "fr"),
    ("es", "Spanish", "spanish", "es"),
    ("it", "Italian", "italian", "it"),
    ("pt", "Portuguese", "portuguese", "pt"),
    ("pt-br", "Portuguese (BR)", "brazilian", "pt-BR"),
    ("ja", "Japanese", "japanese", "ja"),
    ("ko", "Korean", "korean", "ko"),
    ("zh-cn", "Chinese (Mandarin)", "mandarin", "zh"),
    ("zh-tw", "Chinese (Taiwan)", "taiwanese", "zh-TW"),
    ("ru", "Russian", "russian", "ru"),
    ("ar", "Arabic", "arabic", "ar"),
    ("hi", "Hindi", "indian", "hi"),
    ("nl", "Dutch", "dutch", "nl"),
    ("pl", "Polish", "polish", "pl"),
    ("sv", "Swedish", "swedish", "sv"),
    ("tr", "Turkish", "turkish", "tr"),
]


class GTTSProvider:
    """TTS provider using Google Translate's free text-to-speech."""

    provider_name: str = "gtts"

    def __init__(self, slow: bool = False) -> None:
        self._slow = slow

    async def synthesize(self, text: str, voice_id: str) -> AudioBuffer:
        """Synthesize text using gTTS.

        voice_id is a gTTS language code (e.g. 'en', 'de', 'fr').
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._synthesize_sync, text, voice_id)

    def _synthesize_sync(self, text: str, voice_id: str) -> AudioBuffer:
        from gtts import gTTS
        import soundfile as sf

        tts = gTTS(text=text, lang=voice_id, slow=self._slow)

        # gTTS writes MP3 — convert via soundfile
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as mp3_f:
            tts.write_to_fp(mp3_f)
            mp3_f.flush()
            mp3_f.seek(0)

            # soundfile can read MP3 if libsndfile supports it,
            # otherwise fall back to pydub
            try:
                samples, sample_rate = sf.read(mp3_f.name, dtype="float64")
            except Exception:
                samples, sample_rate = self._mp3_to_pcm_fallback(mp3_f.name)

        # Mono downmix if stereo
        if samples.ndim == 2:
            samples = samples.mean(axis=1)

        return AudioBuffer(samples=samples, sample_rate=sample_rate)

    @staticmethod
    def _mp3_to_pcm_fallback(mp3_path: str) -> tuple[np.ndarray, int]:
        """Fall back to pydub for MP3 decoding if soundfile can't handle it."""
        from pydub import AudioSegment

        seg = AudioSegment.from_mp3(mp3_path)
        seg = seg.set_channels(1)  # mono
        sample_rate = seg.frame_rate

        raw = np.array(seg.get_array_of_samples(), dtype=np.float64)
        raw /= 32768.0
        return raw, sample_rate

    async def list_voices(self) -> list[VoiceInfo]:
        """Return one voice per supported gTTS language."""
        return [
            VoiceInfo(
                provider=self.provider_name,
                voice_id=lang_code,
                name=name,
                gender="neutral",
                age_group="adult",
                accent=accent,
                language=lang_tag,
            )
            for lang_code, name, accent, lang_tag in _LANG_MAP
        ]
