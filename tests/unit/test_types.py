"""Tests for AudioBuffer and FilterSpec."""

import numpy as np
import pytest

from backend.app.audio.types import AudioBuffer, FilterSpec


class TestAudioBuffer:
    def test_creation(self):
        samples = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float64)
        buf = AudioBuffer(samples=samples, sample_rate=16000)
        assert buf.num_samples == 5
        assert buf.sample_rate == 16000

    def test_duration(self):
        samples = np.zeros(16000, dtype=np.float64)
        buf = AudioBuffer(samples=samples, sample_rate=16000)
        assert buf.duration_s == pytest.approx(1.0)

    def test_rms_sine(self):
        # RMS of a sine wave is amplitude / sqrt(2)
        sr = 16000
        t = np.arange(sr) / sr
        amplitude = 0.5
        samples = amplitude * np.sin(2 * np.pi * 440 * t)
        buf = AudioBuffer(samples=samples, sample_rate=sr)
        expected_rms = amplitude / np.sqrt(2)
        assert buf.rms == pytest.approx(expected_rms, rel=1e-3)

    def test_peak(self):
        samples = np.array([0.3, -0.7, 0.5], dtype=np.float64)
        buf = AudioBuffer(samples=samples, sample_rate=16000)
        assert buf.peak == pytest.approx(0.7)

    def test_auto_convert_to_float64(self):
        samples = np.array([0.5, -0.5], dtype=np.float32)
        buf = AudioBuffer(samples=samples, sample_rate=16000)
        assert buf.samples.dtype == np.float64

    def test_stereo_to_mono(self):
        stereo = np.array([[0.5, 0.3], [-0.5, -0.3]], dtype=np.float64)
        buf = AudioBuffer(samples=stereo, sample_rate=16000)
        assert buf.samples.ndim == 1
        assert buf.samples[0] == pytest.approx(0.4)

    def test_resample(self):
        sr = 16000
        duration = 1.0
        t = np.arange(int(sr * duration)) / sr
        samples = np.sin(2 * np.pi * 100 * t)
        buf = AudioBuffer(samples=samples, sample_rate=sr)

        resampled = buf.resample(24000)
        assert resampled.sample_rate == 24000
        assert resampled.num_samples == pytest.approx(24000, abs=10)
        assert resampled.duration_s == pytest.approx(1.0, abs=0.01)

    def test_resample_identity(self):
        samples = np.random.default_rng(42).standard_normal(16000)
        buf = AudioBuffer(samples=samples, sample_rate=16000)
        same = buf.resample(16000)
        assert same is buf  # Should return same object

    def test_normalize_peak(self):
        samples = np.array([0.3, -0.6, 0.2], dtype=np.float64)
        buf = AudioBuffer(samples=samples, sample_rate=16000)
        normalized = buf.normalize(target_peak=1.0)
        assert normalized.peak == pytest.approx(1.0, rel=1e-6)

    def test_normalize_rms(self):
        rng = np.random.default_rng(42)
        samples = rng.standard_normal(16000)
        buf = AudioBuffer(samples=samples, sample_rate=16000)
        normalized = buf.normalize(target_rms=0.1)
        assert normalized.rms == pytest.approx(0.1, rel=1e-6)

    def test_loop_to_length(self):
        samples = np.array([1.0, 2.0, 3.0], dtype=np.float64)
        buf = AudioBuffer(samples=samples, sample_rate=16000)
        looped = buf.loop_to_length(7)
        assert looped.num_samples == 7
        np.testing.assert_array_equal(looped.samples, [1, 2, 3, 1, 2, 3, 1])

    def test_loop_to_length_shorter(self):
        samples = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float64)
        buf = AudioBuffer(samples=samples, sample_rate=16000)
        truncated = buf.loop_to_length(3)
        assert truncated.num_samples == 3
        np.testing.assert_array_equal(truncated.samples, [1, 2, 3])

    def test_trim_to_duration_pad(self):
        samples = np.ones(8000, dtype=np.float64)
        buf = AudioBuffer(samples=samples, sample_rate=16000)
        padded = buf.trim_to_duration(1.0)
        assert padded.num_samples == 16000
        assert padded.samples[8000:].sum() == 0  # Padded with zeros

    def test_empty_buffer(self):
        buf = AudioBuffer(samples=np.array([], dtype=np.float64), sample_rate=16000)
        assert buf.rms == 0.0
        assert buf.peak == 0.0
        assert buf.duration_s == 0.0


class TestFilterSpec:
    def test_defaults(self):
        fs = FilterSpec(filter_type="lpf", frequency=100.0)
        assert fs.Q == pytest.approx(0.7071)
        assert fs.gain_db == 0.0

    def test_peaking(self):
        fs = FilterSpec(filter_type="peaking", frequency=1000.0, Q=2.0, gain_db=6.0)
        assert fs.filter_type == "peaking"
        assert fs.frequency == 1000.0
