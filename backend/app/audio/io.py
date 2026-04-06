"""Audio file I/O: load and save WAV/FLAC files."""

from __future__ import annotations

import io
import base64
from pathlib import Path

import numpy as np
import soundfile as sf

from .types import AudioBuffer


def load_audio(file_path: Path | str, target_sample_rate: int | None = None) -> AudioBuffer:
    """Load an audio file and return an AudioBuffer.

    Supports WAV, FLAC, OGG, and other formats via libsndfile.
    Converts to mono float64 in [-1, 1] range.
    """
    data, sr = sf.read(str(file_path), dtype="float64", always_2d=False)
    buf = AudioBuffer(samples=data, sample_rate=sr)
    if target_sample_rate and sr != target_sample_rate:
        buf = buf.resample(target_sample_rate)
    return buf


def save_audio(audio: AudioBuffer, file_path: Path | str, format: str = "WAV", subtype: str = "PCM_16"):
    """Save an AudioBuffer to a file."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Clip to [-1, 1] before saving
    samples = np.clip(audio.samples, -1.0, 1.0)
    sf.write(str(path), samples, audio.sample_rate, format=format, subtype=subtype)


def audio_to_pcm16_bytes(audio: AudioBuffer) -> bytes:
    """Convert audio to raw PCM16 bytes (for API transport)."""
    samples = np.clip(audio.samples, -1.0, 1.0)
    pcm16 = (samples * 32767).astype(np.int16)
    return pcm16.tobytes()


def pcm16_bytes_to_audio(data: bytes, sample_rate: int) -> AudioBuffer:
    """Convert raw PCM16 bytes back to an AudioBuffer."""
    pcm16 = np.frombuffer(data, dtype=np.int16)
    samples = pcm16.astype(np.float64) / 32767.0
    return AudioBuffer(samples=samples, sample_rate=sample_rate)


def audio_to_base64(audio: AudioBuffer) -> str:
    """Convert audio to base64-encoded PCM16 (for OpenAI audio API)."""
    return base64.b64encode(audio_to_pcm16_bytes(audio)).decode("ascii")


def audio_to_wav_bytes(audio: AudioBuffer) -> bytes:
    """Convert audio to WAV file bytes (for APIs that accept file uploads)."""
    buf = io.BytesIO()
    samples = np.clip(audio.samples, -1.0, 1.0)
    sf.write(buf, samples, audio.sample_rate, format="WAV", subtype="PCM_16")
    buf.seek(0)
    return buf.read()
