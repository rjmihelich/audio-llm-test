"""Microsoft Edge TTS provider — free cloud TTS, no API key required.

Requires: pip install edge-tts
Uses Microsoft Edge's online TTS service. High quality neural voices.
"""

from __future__ import annotations

import io
import tempfile

import numpy as np

from ..audio.types import AudioBuffer
from .tts_base import VoiceInfo

# Curated subset of Edge TTS voices.
# Full list available via `edge-tts --list-voices` CLI command.
# tuple: (short_name, display_name, gender, age_group, accent, language)
_VOICE_MAP: list[tuple[str, str, str, str, str, str]] = [
    ("en-US-GuyNeural", "Guy", "male", "adult", "american", "en"),
    ("en-US-JennyNeural", "Jenny", "female", "adult", "american", "en"),
    ("en-US-AriaNeural", "Aria", "female", "young_adult", "american", "en"),
    ("en-US-DavisNeural", "Davis", "male", "adult", "american", "en"),
    ("en-US-AmberNeural", "Amber", "female", "young_adult", "american", "en"),
    ("en-US-AnaNeural", "Ana", "female", "child", "american", "en"),
    ("en-US-AndrewNeural", "Andrew", "male", "adult", "american", "en"),
    ("en-US-BrandonNeural", "Brandon", "male", "young_adult", "american", "en"),
    ("en-US-ChristopherNeural", "Christopher", "male", "adult", "american", "en"),
    ("en-US-CoraNeural", "Cora", "female", "senior", "american", "en"),
    ("en-GB-SoniaNeural", "Sonia", "female", "adult", "british", "en-GB"),
    ("en-GB-RyanNeural", "Ryan", "male", "adult", "british", "en-GB"),
    ("en-AU-NatashaNeural", "Natasha", "female", "adult", "australian", "en-AU"),
    ("en-AU-WilliamNeural", "William", "male", "adult", "australian", "en-AU"),
    ("en-IN-NeerjaNeural", "Neerja", "female", "adult", "indian", "en-IN"),
    ("de-DE-ConradNeural", "Conrad", "male", "adult", "german", "de"),
    ("de-DE-KatjaNeural", "Katja", "female", "adult", "german", "de"),
    ("fr-FR-DeniseNeural", "Denise", "female", "adult", "french", "fr"),
    ("fr-FR-HenriNeural", "Henri", "male", "adult", "french", "fr"),
    ("es-ES-ElviraNeural", "Elvira", "female", "adult", "spanish", "es"),
    ("es-ES-AlvaroNeural", "Alvaro", "male", "adult", "spanish", "es"),
    ("es-MX-DaliaNeural", "Dalia", "female", "adult", "mexican", "es-MX"),
    ("it-IT-ElsaNeural", "Elsa", "female", "adult", "italian", "it"),
    ("it-IT-DiegoNeural", "Diego", "male", "adult", "italian", "it"),
    ("ja-JP-NanamiNeural", "Nanami", "female", "adult", "japanese", "ja"),
    ("ja-JP-KeitaNeural", "Keita", "male", "adult", "japanese", "ja"),
    ("ko-KR-SunHiNeural", "SunHi", "female", "adult", "korean", "ko"),
    ("zh-CN-XiaoxiaoNeural", "Xiaoxiao", "female", "young_adult", "mandarin", "zh"),
    ("zh-CN-YunxiNeural", "Yunxi", "male", "adult", "mandarin", "zh"),
    ("pt-BR-FranciscaNeural", "Francisca", "female", "adult", "brazilian", "pt-BR"),
    ("ru-RU-SvetlanaNeural", "Svetlana", "female", "adult", "russian", "ru"),
    ("ar-SA-ZariyahNeural", "Zariyah", "female", "adult", "arabic", "ar"),
    ("hi-IN-SwaraNeural", "Swara", "female", "adult", "indian", "hi"),
]


class EdgeTTSProvider:
    """TTS provider using Microsoft Edge's free neural TTS service."""

    provider_name: str = "edge"

    async def synthesize(self, text: str, voice_id: str) -> AudioBuffer:
        """Synthesize text using Edge TTS.

        voice_id is an Edge voice short name (e.g. 'en-US-JennyNeural').
        """
        import edge_tts

        communicate = edge_tts.Communicate(text, voice_id)

        # edge-tts streams MP3 chunks — collect them
        audio_chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])

        if not audio_chunks:
            raise RuntimeError(f"Edge TTS returned no audio for voice {voice_id}")

        mp3_data = b"".join(audio_chunks)

        # Decode MP3 to PCM
        samples, sample_rate = self._decode_mp3(mp3_data)
        return AudioBuffer(samples=samples, sample_rate=sample_rate)

    @staticmethod
    def _decode_mp3(mp3_bytes: bytes) -> tuple[np.ndarray, int]:
        """Decode MP3 bytes to float64 samples."""
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as f:
            f.write(mp3_bytes)
            f.flush()

            try:
                import soundfile as sf
                samples, sr = sf.read(f.name, dtype="float64")
            except Exception:
                from pydub import AudioSegment
                seg = AudioSegment.from_mp3(f.name).set_channels(1)
                sr = seg.frame_rate
                samples = np.array(seg.get_array_of_samples(), dtype=np.float64) / 32768.0

        if samples.ndim == 2:
            samples = samples.mean(axis=1)

        return samples, sr

    async def list_voices(self) -> list[VoiceInfo]:
        """Return curated set of Edge TTS voices."""
        return [
            VoiceInfo(
                provider=self.provider_name,
                voice_id=vid,
                name=name,
                gender=gender,
                age_group=age_group,
                accent=accent,
                language=lang,
            )
            for vid, name, gender, age_group, accent, lang in _VOICE_MAP
        ]
