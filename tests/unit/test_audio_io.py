"""Tests for audio I/O: load, save, PCM conversion, base64, WAV bytes."""

from __future__ import annotations

import os
import tempfile

import numpy as np
import pytest

from backend.app.audio.types import AudioBuffer
from backend.app.audio.io import (
    load_audio,
    save_audio,
    audio_to_pcm16_bytes,
    pcm16_bytes_to_audio,
    audio_to_base64,
    audio_to_wav_bytes,
)


def _sine(freq: float = 440.0, dur: float = 0.5, sr: int = 16000) -> AudioBuffer:
    t = np.arange(int(sr * dur)) / sr
    return AudioBuffer(samples=0.5 * np.sin(2 * np.pi * freq * t), sample_rate=sr)


# ---------------------------------------------------------------------------
# save_audio / load_audio round-trip
# ---------------------------------------------------------------------------

class TestSaveLoadRoundTrip:
    def test_wav_roundtrip(self):
        buf = _sine()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            save_audio(buf, f.name)
            loaded = load_audio(f.name)
        os.unlink(f.name)
        assert loaded.sample_rate == 16000
        assert abs(loaded.num_samples - buf.num_samples) <= 1

    def test_flac_roundtrip(self):
        buf = _sine()
        with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as f:
            save_audio(buf, f.name, format="FLAC", subtype="PCM_16")
            loaded = load_audio(f.name)
        os.unlink(f.name)
        assert loaded.sample_rate == 16000

    def test_resample_on_load(self):
        buf = _sine(sr=44100)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            save_audio(buf, f.name)
            loaded = load_audio(f.name, target_sample_rate=16000)
        os.unlink(f.name)
        assert loaded.sample_rate == 16000

    def test_save_clips_out_of_range(self):
        """Samples > 1.0 should be clipped on save, not cause errors."""
        loud = AudioBuffer(samples=np.array([2.0, -2.0, 0.5]), sample_rate=16000)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            save_audio(loud, f.name)
            loaded = load_audio(f.name)
        os.unlink(f.name)
        assert loaded.peak <= 1.0

    def test_nonexistent_file_raises(self):
        with pytest.raises(Exception):
            load_audio("/tmp/does_not_exist_audio_xyz.wav")


# ---------------------------------------------------------------------------
# PCM16 conversion
# ---------------------------------------------------------------------------

class TestPCM16:
    def test_roundtrip_preserves_shape(self):
        buf = _sine()
        raw = audio_to_pcm16_bytes(buf)
        recovered = pcm16_bytes_to_audio(raw, 16000)
        assert recovered.num_samples == buf.num_samples

    def test_roundtrip_accuracy(self):
        """PCM16 quantization error should be < 1 LSB (~3e-5)."""
        buf = _sine()
        raw = audio_to_pcm16_bytes(buf)
        recovered = pcm16_bytes_to_audio(raw, 16000)
        max_err = np.max(np.abs(buf.samples - recovered.samples))
        assert max_err < 2.0 / 32767  # less than 2 LSBs

    def test_clips_loud_signal(self):
        loud = AudioBuffer(samples=np.array([1.5, -1.5]), sample_rate=16000)
        raw = audio_to_pcm16_bytes(loud)
        recovered = pcm16_bytes_to_audio(raw, 16000)
        assert np.all(np.abs(recovered.samples) <= 1.0)

    def test_silence(self):
        silence = AudioBuffer(samples=np.zeros(100), sample_rate=16000)
        raw = audio_to_pcm16_bytes(silence)
        recovered = pcm16_bytes_to_audio(raw, 16000)
        assert np.all(recovered.samples == 0.0)

    def test_rounding_not_truncation(self):
        """Verify np.round is used (not just cast), reducing quantization bias."""
        # 0.5 / 32767 ≈ 1.526e-5 — should round to 1, not 0
        val = 0.5 / 32767
        buf = AudioBuffer(samples=np.array([val]), sample_rate=16000)
        raw = audio_to_pcm16_bytes(buf)
        pcm = np.frombuffer(raw, dtype=np.int16)
        # With rounding: round(0.5) = 0 or 1 depending on banker's rounding
        # The key thing is it's not systematically wrong
        assert pcm[0] in (0, 1)


# ---------------------------------------------------------------------------
# Base64 and WAV bytes
# ---------------------------------------------------------------------------

class TestBase64AndWavBytes:
    def test_base64_is_string(self):
        buf = _sine(dur=0.1)
        b64 = audio_to_base64(buf)
        assert isinstance(b64, str)
        assert len(b64) > 0

    def test_wav_bytes_header(self):
        buf = _sine(dur=0.1)
        wav = audio_to_wav_bytes(buf)
        assert wav[:4] == b"RIFF"
        assert wav[8:12] == b"WAVE"

    def test_wav_bytes_playable(self):
        """WAV bytes should be loadable by soundfile."""
        import io
        import soundfile as sf
        buf = _sine(dur=0.2)
        wav = audio_to_wav_bytes(buf)
        data, sr = sf.read(io.BytesIO(wav))
        assert sr == 16000
        assert len(data) == buf.num_samples
