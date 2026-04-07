"""Piper TTS provider — fast local neural TTS (offline, free).

Requires: pip install piper-tts
Models are downloaded automatically on first use to ~/.local/share/piper-models/.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from ..audio.types import AudioBuffer
from .tts_base import VoiceInfo

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "en_US-lessac-medium"
_MODEL_DIR = Path.home() / ".local" / "share" / "piper-models"

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


def _ensure_model(voice_id: str) -> Path:
    """Download model if not already on disk. Returns path to .onnx file."""
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)

    onnx_path = _MODEL_DIR / f"{voice_id}.onnx"
    json_path = _MODEL_DIR / f"{voice_id}.onnx.json"

    if onnx_path.exists() and json_path.exists():
        return onnx_path

    logger.info("Downloading Piper model '%s' to %s ...", voice_id, _MODEL_DIR)
    try:
        from piper.download_voices import download_voice

        download_voice(voice_id, _MODEL_DIR)
    except Exception as e:
        raise RuntimeError(
            f"Failed to download Piper model '{voice_id}': {e}. "
            f"You can manually download from https://huggingface.co/rhasspy/piper-voices"
        ) from e

    if not onnx_path.exists():
        raise FileNotFoundError(
            f"Model file not found after download: {onnx_path}"
        )
    return onnx_path


class PiperTTSProvider:
    """TTS provider using Piper for fast local neural synthesis."""

    provider_name: str = "piper"

    # Class-level model cache — survives across calls and provider instances
    _voice_cache: dict[str, object] = {}

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self._default_model = model

    async def synthesize(self, text: str, voice_id: str) -> AudioBuffer:
        """Synthesize text using a Piper voice model.

        voice_id should be a Piper model name (e.g. 'en_US-lessac-medium').
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._synthesize_sync, text, voice_id)

    def _get_voice(self, voice_id: str):
        """Load a PiperVoice, caching it so the ONNX model is only parsed once."""
        if voice_id not in self._voice_cache:
            from piper import PiperVoice

            # Auto-download if needed
            model_path = _ensure_model(voice_id)
            self._voice_cache[voice_id] = PiperVoice.load(str(model_path))
            logger.info("Piper model '%s' loaded and cached.", voice_id)
        return self._voice_cache[voice_id]

    def _synthesize_sync(self, text: str, voice_id: str) -> AudioBuffer:
        voice = self._get_voice(voice_id)

        # Piper's synthesize yields AudioChunk objects with float32 arrays
        chunks = []
        sample_rate = 22050  # will be overwritten
        for chunk in voice.synthesize(text):
            sample_rate = chunk.sample_rate
            chunks.append(chunk.audio_float_array)

        if not chunks:
            raise RuntimeError(f"Piper produced no audio for: {text[:50]}")

        samples = np.concatenate(chunks).astype(np.float64)
        return AudioBuffer(samples=samples, sample_rate=sample_rate)

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
