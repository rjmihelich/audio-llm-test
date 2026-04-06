"""Google Cloud TTS provider implementation."""

from __future__ import annotations

import numpy as np
from google.cloud import texttospeech_v1 as tts

from ..audio.types import AudioBuffer
from .tts_base import VoiceInfo

# Map the API's SsmlVoiceGender enum values to simple strings.
_GENDER_MAP = {
    tts.SsmlVoiceGender.MALE: "male",
    tts.SsmlVoiceGender.FEMALE: "female",
    tts.SsmlVoiceGender.NEUTRAL: "neutral",
    tts.SsmlVoiceGender.SSML_VOICE_GENDER_UNSPECIFIED: "neutral",
}


def _language_from_voice_name(name: str) -> str:
    """Extract the language tag from a voice name like ``en-US-Neural2-A``."""
    parts = name.split("-")
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return name


def _accent_from_language(language_code: str) -> str:
    """Derive a human-readable accent label from a BCP-47 language code."""
    mapping = {
        "en-US": "american",
        "en-GB": "british",
        "en-AU": "australian",
        "en-IN": "indian",
    }
    return mapping.get(language_code, language_code)


class GoogleTTSProvider:
    """TTS provider backed by Google Cloud Text-to-Speech."""

    provider_name: str = "google"

    def __init__(self, sample_rate: int = 24000) -> None:
        self._client = tts.TextToSpeechAsyncClient()
        self._sample_rate = sample_rate

    async def synthesize(
        self,
        text: str,
        voice_id: str,
        *,
        ssml: bool = False,
    ) -> AudioBuffer:
        """Synthesize speech for *text* using the given Google voice name.

        Parameters
        ----------
        text:
            Plain text or SSML markup.
        voice_id:
            Full Google voice name, e.g. ``en-US-Neural2-A``.
        ssml:
            If ``True``, *text* is treated as SSML.
        """
        language_code = _language_from_voice_name(voice_id)

        if ssml:
            synthesis_input = tts.SynthesisInput(ssml=text)
        else:
            synthesis_input = tts.SynthesisInput(text=text)

        voice_params = tts.VoiceSelectionParams(
            language_code=language_code,
            name=voice_id,
        )

        audio_config = tts.AudioConfig(
            audio_encoding=tts.AudioEncoding.LINEAR16,
            sample_rate_hertz=self._sample_rate,
        )

        response = await self._client.synthesize_speech(
            input=synthesis_input,
            voice=voice_params,
            audio_config=audio_config,
        )

        # LINEAR16 is signed 16-bit little-endian PCM.
        # The first 44 bytes may be a WAV header; Google returns raw PCM for
        # LINEAR16 so we read directly.
        samples_int16 = np.frombuffer(response.audio_content, dtype=np.int16)
        samples_f64 = samples_int16.astype(np.float64) / 32768.0

        return AudioBuffer(samples=samples_f64, sample_rate=self._sample_rate)

    async def list_voices(self, language_code: str = "en") -> list[VoiceInfo]:
        """Query the Google TTS API for available voices.

        Parameters
        ----------
        language_code:
            BCP-47 prefix used to filter voices (default ``"en"``).
        """
        response = await self._client.list_voices(language_code=language_code)

        voices: list[VoiceInfo] = []
        for voice in response.voices:
            gender_str = _GENDER_MAP.get(voice.ssml_gender, "neutral")
            lang = voice.language_codes[0] if voice.language_codes else language_code
            voices.append(
                VoiceInfo(
                    provider=self.provider_name,
                    voice_id=voice.name,
                    name=voice.name,
                    gender=gender_str,
                    age_group="adult",
                    accent=_accent_from_language(lang),
                    language=lang,
                )
            )
        return voices
