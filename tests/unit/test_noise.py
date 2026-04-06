"""Tests for noise generation."""

import numpy as np
import pytest

from backend.app.audio.noise import white_noise, pink_noise, pink_noise_filtered


class TestWhiteNoise:
    def test_duration(self):
        noise = white_noise(1.0, sample_rate=16000)
        assert noise.num_samples == 16000
        assert noise.sample_rate == 16000

    def test_seed_reproducibility(self):
        n1 = white_noise(1.0, seed=42)
        n2 = white_noise(1.0, seed=42)
        np.testing.assert_array_equal(n1.samples, n2.samples)

    def test_different_seeds(self):
        n1 = white_noise(1.0, seed=42)
        n2 = white_noise(1.0, seed=99)
        assert not np.allclose(n1.samples, n2.samples)

    def test_approximate_unit_rms(self):
        # White Gaussian noise with unit variance has RMS ≈ 1.0
        noise = white_noise(10.0, seed=42)
        assert noise.rms == pytest.approx(1.0, abs=0.05)


class TestPinkNoise:
    def test_duration(self):
        noise = pink_noise(1.0, sample_rate=16000)
        assert noise.num_samples == 16000

    def test_unit_rms(self):
        noise = pink_noise(10.0, seed=42)
        assert noise.rms == pytest.approx(1.0, abs=0.05)

    def test_spectral_slope(self):
        """Pink noise should have ~1/f power spectrum (3 dB/octave rolloff)."""
        noise = pink_noise(10.0, sample_rate=16000, seed=42)
        fft = np.abs(np.fft.rfft(noise.samples))
        freqs = np.fft.rfftfreq(noise.num_samples, 1 / 16000)

        # Compare power at 500 Hz vs 1000 Hz (one octave)
        # For 1/f spectrum, power ratio should be ~2 (3 dB)
        idx_500 = np.argmin(np.abs(freqs - 500))
        idx_1000 = np.argmin(np.abs(freqs - 1000))

        # Average over a band to reduce variance
        band_width = 50
        power_500 = np.mean(fft[idx_500 - band_width:idx_500 + band_width] ** 2)
        power_1000 = np.mean(fft[idx_1000 - band_width:idx_1000 + band_width] ** 2)

        ratio_db = 10 * np.log10(power_500 / power_1000)
        # Should be approximately 3 dB (1/f means power doubles per octave down)
        assert ratio_db == pytest.approx(3.0, abs=2.0)


class TestPinkNoiseFiltered:
    def test_lpf_reduces_high_freq(self):
        """Filtered pink noise should have even less high-frequency content."""
        unfiltered = pink_noise(5.0, sample_rate=16000, seed=42)
        filtered = pink_noise_filtered(5.0, lpf_cutoff_hz=100.0, lpf_order=2,
                                       sample_rate=16000, seed=42)

        fft_unf = np.abs(np.fft.rfft(unfiltered.samples))
        fft_flt = np.abs(np.fft.rfft(filtered.samples))
        freqs = np.fft.rfftfreq(unfiltered.num_samples, 1 / 16000)

        # Energy above 500 Hz should be negligible in filtered version
        high_mask = freqs > 500
        high_energy_unf = np.mean(fft_unf[high_mask] ** 2)
        high_energy_flt = np.mean(fft_flt[high_mask] ** 2)

        assert high_energy_flt < high_energy_unf * 0.01

    def test_unit_rms_after_filter(self):
        filtered = pink_noise_filtered(10.0, seed=42)
        assert filtered.rms == pytest.approx(1.0, abs=0.05)
