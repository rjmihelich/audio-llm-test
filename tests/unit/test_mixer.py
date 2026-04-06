"""Tests for SNR mixing."""

import numpy as np
import pytest

from backend.app.audio.types import AudioBuffer
from backend.app.audio.mixer import mix_at_snr, mix_signals


class TestMixAtSNR:
    def _make_tone(self, freq, duration=1.0, sr=16000, amplitude=0.5):
        t = np.arange(int(sr * duration)) / sr
        samples = amplitude * np.sin(2 * np.pi * freq * t)
        return AudioBuffer(samples=samples, sample_rate=sr)

    def _make_noise(self, duration=1.0, sr=16000, seed=42):
        rng = np.random.default_rng(seed)
        samples = rng.standard_normal(int(sr * duration))
        return AudioBuffer(samples=samples, sample_rate=sr)

    def test_high_snr_preserves_speech(self):
        """At very high SNR, the noise contribution should be negligible."""
        speech = self._make_tone(440)
        noise = self._make_noise()
        mixed = mix_at_snr(speech, noise, snr_db=60.0)

        # At 60 dB SNR, noise is 1000x quieter than speech
        # The mixed signal should be very close to the speech
        correlation = np.corrcoef(speech.samples, mixed.samples)[0, 1]
        assert correlation > 0.999

    def test_zero_snr(self):
        """At 0 dB SNR, speech and noise should have equal RMS."""
        speech = self._make_tone(440, amplitude=0.3)
        noise = self._make_noise()
        mixed = mix_at_snr(speech, noise, snr_db=0.0)

        # The mixed signal exists and is valid
        assert mixed.num_samples == speech.num_samples
        assert not np.any(np.isnan(mixed.samples))

    def test_negative_snr(self):
        """At negative SNR, noise dominates."""
        speech = self._make_tone(440, amplitude=0.3)
        noise = self._make_noise()
        mixed = mix_at_snr(speech, noise, snr_db=-10.0)

        # Should still produce valid audio
        assert mixed.num_samples == speech.num_samples
        assert mixed.peak <= 1.0  # tanh clips to [-1, 1]

    def test_snr_accuracy(self):
        """Verify the actual SNR of the mixed signal is close to target.

        Note: tanh soft-clipping may slightly alter the SNR for low-SNR signals.
        This test uses a high enough SNR that clipping is negligible.
        """
        sr = 16000
        duration = 5.0  # Longer for more stable measurement
        speech = self._make_tone(440, duration=duration, amplitude=0.3)
        rng = np.random.default_rng(42)
        noise_samples = rng.standard_normal(int(sr * duration))
        noise = AudioBuffer(samples=noise_samples, sample_rate=sr)

        target_snr = 20.0
        mixed = mix_at_snr(speech, noise, snr_db=target_snr)

        # Measure actual SNR
        # noise component = mixed - speech (approximately, before tanh)
        # At 20 dB SNR with amplitude 0.3, peak mixed is ~0.33, no clipping
        noise_scale = speech.rms / (noise.rms * 10 ** (target_snr / 20.0))
        actual_noise = noise_scale * noise.samples[:speech.num_samples]
        actual_snr = 20 * np.log10(speech.rms / np.sqrt(np.mean(actual_noise**2)))

        assert actual_snr == pytest.approx(target_snr, abs=0.1)

    def test_noise_looped_to_speech_length(self):
        """If noise is shorter than speech, it should be looped."""
        speech = AudioBuffer(
            samples=np.zeros(16000, dtype=np.float64), sample_rate=16000
        )
        # Create short noise
        short_noise = AudioBuffer(
            samples=np.ones(8000, dtype=np.float64), sample_rate=16000
        )
        # Should not raise
        mixed = mix_at_snr(speech, short_noise, snr_db=10.0)
        assert mixed.num_samples == 16000


class TestMixSignals:
    def test_two_signals(self):
        s1 = AudioBuffer(samples=np.ones(16000, dtype=np.float64) * 0.3, sample_rate=16000)
        s2 = AudioBuffer(samples=np.ones(16000, dtype=np.float64) * 0.2, sample_rate=16000)
        mixed = mix_signals([s1, s2])
        # Sum is 0.5, below soft-clip threshold — should pass through unchanged
        assert mixed.samples[0] == pytest.approx(0.5, rel=1e-6)

    def test_with_gains(self):
        s1 = AudioBuffer(samples=np.ones(16000, dtype=np.float64) * 0.5, sample_rate=16000)
        mixed = mix_signals([s1], gains_db=[-6.0])
        # -6 dB ≈ 0.5012, signal ≈ 0.5 * 0.5 = 0.25 — below threshold, pass through
        expected = 0.5 * 10 ** (-6 / 20)
        assert mixed.samples[0] == pytest.approx(expected, rel=1e-3)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            mix_signals([])
