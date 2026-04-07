"""Azure Cognitive Services Speech TTS provider.

Requires: pip install azure-cognitiveservices-speech

Supports expressive speaking styles via SSML <mstts:express-as> including:
  whispering, shouting, cheerful, sad, angry, terrified, excited, friendly,
  unfriendly, hopeful, newscast, assistant, chat, customerservice.

Also supports fine-grained prosody control (rate, volume, pitch).

Set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION environment variables.
"""

from __future__ import annotations

import asyncio
import io
import logging
import struct
import tempfile
from typing import Literal

import numpy as np

from ..audio.types import AudioBuffer
from .tts_base import VoiceInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Voice catalog: voices that support expressive styles
# (voice_id, display_name, gender, age_group, accent, language, styles)
# ---------------------------------------------------------------------------

_AZURE_VOICES: list[tuple[str, str, str, str, str, str, list[str]]] = [
    # English - US
    (
        "en-US-JennyNeural", "Jenny (Azure)", "female", "adult", "american", "en",
        ["assistant", "chat", "customerservice", "newscast", "angry", "cheerful",
         "sad", "excited", "friendly", "terrified", "shouting", "unfriendly",
         "whispering", "hopeful"],
    ),
    (
        "en-US-GuyNeural", "Guy (Azure)", "male", "adult", "american", "en",
        ["newscast", "angry", "cheerful", "sad", "excited", "friendly",
         "terrified", "shouting", "unfriendly", "whispering", "hopeful"],
    ),
    (
        "en-US-AriaNeural", "Aria (Azure)", "female", "young_adult", "american", "en",
        ["chat", "customerservice", "narration-professional", "newscast-casual",
         "newscast-formal", "cheerful", "empathetic", "angry", "sad",
         "excited", "friendly", "terrified", "shouting", "unfriendly",
         "whispering", "hopeful"],
    ),
    (
        "en-US-DavisNeural", "Davis (Azure)", "male", "adult", "american", "en",
        ["chat", "angry", "cheerful", "excited", "friendly", "hopeful",
         "shouting", "terrified", "unfriendly", "whispering", "sad"],
    ),
    (
        "en-US-JasonNeural", "Jason (Azure)", "male", "adult", "american", "en",
        ["angry", "cheerful", "excited", "friendly", "hopeful", "sad",
         "shouting", "terrified", "unfriendly", "whispering"],
    ),
    (
        "en-US-SaraNeural", "Sara (Azure)", "female", "young_adult", "american", "en",
        ["angry", "cheerful", "excited", "friendly", "hopeful", "sad",
         "shouting", "terrified", "unfriendly", "whispering"],
    ),
    (
        "en-US-TonyNeural", "Tony (Azure)", "male", "adult", "american", "en",
        ["angry", "cheerful", "excited", "friendly", "hopeful", "sad",
         "shouting", "terrified", "unfriendly", "whispering"],
    ),
    (
        "en-US-NancyNeural", "Nancy (Azure)", "female", "adult", "american", "en",
        ["angry", "cheerful", "excited", "friendly", "hopeful", "sad",
         "shouting", "terrified", "unfriendly", "whispering"],
    ),
    # English - UK
    (
        "en-GB-SoniaNeural", "Sonia (Azure)", "female", "adult", "british", "en-GB",
        ["cheerful", "sad"],
    ),
    (
        "en-GB-RyanNeural", "Ryan (Azure)", "male", "adult", "british", "en-GB",
        ["cheerful", "chat"],
    ),
    # Multilingual
    (
        "zh-CN-XiaoxiaoNeural", "Xiaoxiao (Azure)", "female", "young_adult", "mandarin", "zh",
        ["assistant", "chat", "customerservice", "newscast", "affectionate",
         "angry", "calm", "cheerful", "disgruntled", "fearful", "gentle",
         "lyrical", "sad", "serious", "poetry-reading"],
    ),
    (
        "ja-JP-NanamiNeural", "Nanami (Azure)", "female", "adult", "japanese", "ja",
        ["chat", "cheerful", "customerservice"],
    ),
]


class AzureTTSProvider:
    """TTS provider using Azure Cognitive Services Speech SDK.

    Supports speaking styles (whispering, shouting, etc.) via SSML
    ``<mstts:express-as>`` and prosody control.
    """

    provider_name: str = "azure"

    def __init__(
        self,
        speech_key: str = "",
        speech_region: str = "eastus",
        sample_rate: int = 24000,
    ) -> None:
        self._speech_key = speech_key
        self._speech_region = speech_region
        self._sample_rate = sample_rate

        if not self._speech_key:
            import os
            self._speech_key = os.environ.get("AZURE_SPEECH_KEY", "")
        if not self._speech_region:
            import os
            self._speech_region = os.environ.get("AZURE_SPEECH_REGION", "eastus")

    def _get_voice_styles(self, voice_id: str) -> list[str]:
        """Return available styles for a voice."""
        for vid, _, _, _, _, _, styles in _AZURE_VOICES:
            if vid == voice_id:
                return styles
        return []

    def _build_ssml(
        self,
        text: str,
        voice_id: str,
        style: str | None = None,
        style_degree: float = 1.0,
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
    ) -> str:
        """Build SSML with optional speaking style and prosody."""
        # Escape XML special chars
        escaped = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

        inner = escaped
        if style:
            # Wrap in mstts:express-as
            degree_attr = f' styledegree="{style_degree}"' if style_degree != 1.0 else ""
            inner = (
                f'<mstts:express-as style="{style}"{degree_attr}>'
                f"{escaped}"
                f"</mstts:express-as>"
            )

        ssml = (
            '<speak version="1.0" '
            'xmlns="http://www.w3.org/2001/10/synthesis" '
            'xmlns:mstts="https://www.w3.org/2001/mstts" '
            f'xml:lang="en-US">'
            f'<voice name="{voice_id}">'
            f'<prosody rate="{rate}" volume="{volume}" pitch="{pitch}">'
            f"{inner}"
            f"</prosody>"
            f"</voice>"
            f"</speak>"
        )
        return ssml

    async def synthesize(
        self,
        text: str,
        voice_id: str,
        style: str | None = None,
        style_degree: float = 1.0,
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
    ) -> AudioBuffer:
        """Synthesize speech using Azure Speech SDK.

        Args:
            text: Text to synthesize.
            voice_id: Azure voice name (e.g., 'en-US-JennyNeural').
            style: Speaking style (e.g., 'whispering', 'shouting', 'cheerful').
                   Only works with voices that support the style.
            style_degree: Intensity of the style, 0.01 to 2.0 (default 1.0).
            rate: Speech rate, e.g., '+20%', '-10%', 'slow', 'fast'.
            volume: Volume, e.g., '+10%', '-20%', 'soft', 'loud'.
            pitch: Pitch, e.g., '+5Hz', '-10Hz', 'high', 'low'.

        Returns:
            AudioBuffer with synthesized speech.
        """
        try:
            import azure.cognitiveservices.speech as speechsdk
        except ImportError:
            raise ImportError(
                "Azure Speech SDK not installed. Run: pip install azure-cognitiveservices-speech"
            )

        if not self._speech_key:
            raise RuntimeError(
                "AZURE_SPEECH_KEY not set. Provide it via environment variable "
                "or pass speech_key to AzureTTSProvider."
            )

        # Validate style if provided
        if style:
            available = self._get_voice_styles(voice_id)
            if available and style not in available:
                logger.warning(
                    f"Style '{style}' not in known styles for {voice_id}: {available}. "
                    f"Attempting anyway — Azure may ignore it."
                )

        ssml = self._build_ssml(
            text, voice_id,
            style=style,
            style_degree=style_degree,
            rate=rate,
            volume=volume,
            pitch=pitch,
        )

        # Run SDK call in thread since it's synchronous
        def _synthesize_sync() -> bytes:
            speech_config = speechsdk.SpeechConfig(
                subscription=self._speech_key,
                region=self._speech_region,
            )
            # Request raw PCM audio
            speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm
            )

            synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=speech_config,
                audio_config=None,  # We'll get the audio data directly
            )

            result = synthesizer.speak_ssml_async(ssml).get()

            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                return result.audio_data
            elif result.reason == speechsdk.ResultReason.Canceled:
                cancellation = result.cancellation_details
                raise RuntimeError(
                    f"Azure TTS canceled: {cancellation.reason}. "
                    f"Error: {cancellation.error_details}"
                )
            else:
                raise RuntimeError(f"Azure TTS failed: {result.reason}")

        loop = asyncio.get_running_loop()
        wav_data = await loop.run_in_executor(None, _synthesize_sync)

        # Parse WAV data — skip the 44-byte RIFF header
        samples = self._decode_wav_bytes(wav_data)
        return AudioBuffer(samples=samples, sample_rate=self._sample_rate)

    @staticmethod
    def _decode_wav_bytes(wav_bytes: bytes) -> np.ndarray:
        """Decode raw WAV bytes (RIFF PCM 16-bit mono) to float64 samples."""
        try:
            import soundfile as sf
            samples, _ = sf.read(io.BytesIO(wav_bytes), dtype="float64")
        except Exception:
            # Manual fallback: skip 44-byte header, parse int16
            if len(wav_bytes) <= 44:
                raise RuntimeError("Azure TTS returned empty audio")
            raw = wav_bytes[44:]
            n_samples = len(raw) // 2
            samples = np.array(
                struct.unpack(f"<{n_samples}h", raw[:n_samples * 2]),
                dtype=np.float64,
            ) / 32768.0

        if samples.ndim == 2:
            samples = samples.mean(axis=1)
        return samples

    async def list_voices(self) -> list[VoiceInfo]:
        """Return curated set of Azure voices with style support."""
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
            for vid, name, gender, age_group, accent, lang, _styles in _AZURE_VOICES
        ]

    def list_styles(self, voice_id: str) -> list[str]:
        """Return the available speaking styles for a given voice."""
        return self._get_voice_styles(voice_id)

    def list_all_styles(self) -> dict[str, list[str]]:
        """Return a mapping of voice_id → available styles."""
        return {
            vid: styles
            for vid, _, _, _, _, _, styles in _AZURE_VOICES
        }
