"""Tests for biquad filter chain."""

import numpy as np
import pytest
from scipy.signal import freqz

from backend.app.audio.types import AudioBuffer, FilterSpec
from backend.app.audio.filters import (
    FilterChain,
    filter_spec_to_sos,
    butterworth_lpf_sos,
)


class TestButterworth:
    def test_lpf_passband(self):
        """Signal well below cutoff should pass through with minimal attenuation."""
        sr = 16000
        sos = butterworth_lpf_sos(2, 100.0, sr)

        # Check frequency response at 10 Hz (well in passband)
        w, h = freqz(sos[0, :3], sos[0, 3:], worN=[2 * np.pi * 10 / sr])
        gain_db = 20 * np.log10(np.abs(h[0]))
        assert gain_db == pytest.approx(0.0, abs=0.5)

    def test_lpf_stopband(self):
        """Signal well above cutoff should be heavily attenuated."""
        sr = 16000
        sos = butterworth_lpf_sos(2, 100.0, sr)

        # 2nd-order Butterworth: -12 dB/octave above cutoff
        # At 1000 Hz (10x cutoff = ~3.3 octaves), expect ~-40 dB
        # Use the full SOS chain for multi-section filters
        from scipy.signal import sosfreqz
        w, h = sosfreqz(sos, worN=[2 * np.pi * 1000 / sr])
        gain_db = 20 * np.log10(np.abs(h[0]))
        assert gain_db < -30  # Should be significantly attenuated

    def test_lpf_cutoff_frequency(self):
        """At the cutoff frequency, gain should be approximately -3 dB."""
        sr = 16000
        sos = butterworth_lpf_sos(2, 100.0, sr)
        from scipy.signal import sosfreqz
        w, h = sosfreqz(sos, worN=[2 * np.pi * 100 / sr])
        gain_db = 20 * np.log10(np.abs(h[0]))
        assert gain_db == pytest.approx(-3.0, abs=0.5)


class TestFilterSpecs:
    def test_lpf_sos_shape(self):
        spec = FilterSpec(filter_type="lpf", frequency=1000.0)
        sos = filter_spec_to_sos(spec, 16000)
        assert sos.shape == (1, 6)

    def test_hpf_sos_shape(self):
        spec = FilterSpec(filter_type="hpf", frequency=80.0)
        sos = filter_spec_to_sos(spec, 16000)
        assert sos.shape == (1, 6)

    def test_peaking_sos_shape(self):
        spec = FilterSpec(filter_type="peaking", frequency=2000.0, Q=2.0, gain_db=6.0)
        sos = filter_spec_to_sos(spec, 16000)
        assert sos.shape == (1, 6)

    def test_peaking_boost(self):
        """Peaking EQ with positive gain should boost at center frequency."""
        spec = FilterSpec(filter_type="peaking", frequency=1000.0, Q=1.0, gain_db=12.0)
        sos = filter_spec_to_sos(spec, 16000)
        from scipy.signal import sosfreqz
        w, h = sosfreqz(sos, worN=[2 * np.pi * 1000 / 16000])
        gain_db = 20 * np.log10(np.abs(h[0]))
        assert gain_db == pytest.approx(12.0, abs=1.0)

    def test_peaking_cut(self):
        """Peaking EQ with negative gain should cut at center frequency."""
        spec = FilterSpec(filter_type="peaking", frequency=1000.0, Q=1.0, gain_db=-12.0)
        sos = filter_spec_to_sos(spec, 16000)
        from scipy.signal import sosfreqz
        w, h = sosfreqz(sos, worN=[2 * np.pi * 1000 / 16000])
        gain_db = 20 * np.log10(np.abs(h[0]))
        assert gain_db == pytest.approx(-12.0, abs=1.0)

    def test_invalid_type(self):
        spec = FilterSpec(filter_type="notch", frequency=1000.0)  # type: ignore
        with pytest.raises(ValueError, match="Unknown filter type"):
            filter_spec_to_sos(spec, 16000)


class TestFilterChain:
    def test_empty_chain(self):
        chain = FilterChain([], 16000)
        samples = np.random.default_rng(42).standard_normal(16000)
        buf = AudioBuffer(samples=samples, sample_rate=16000)
        result = chain.apply(buf)
        np.testing.assert_array_equal(result.samples, buf.samples)

    def test_single_filter(self):
        chain = FilterChain([FilterSpec("lpf", 100.0)], 16000)
        assert chain.num_stages == 1

        # White noise through LPF should have reduced high-frequency energy
        rng = np.random.default_rng(42)
        white = AudioBuffer(samples=rng.standard_normal(16000), sample_rate=16000)
        filtered = chain.apply(white)

        # Check that high-freq energy is reduced
        fft_white = np.abs(np.fft.rfft(white.samples))
        fft_filtered = np.abs(np.fft.rfft(filtered.samples))
        # Energy above 500 Hz should be much lower in filtered
        freq_bins = np.fft.rfftfreq(16000, 1 / 16000)
        high_mask = freq_bins > 500
        assert fft_filtered[high_mask].mean() < fft_white[high_mask].mean() * 0.1

    def test_cascade(self):
        """Cascading two LPFs should give steeper rolloff."""
        specs = [
            FilterSpec("lpf", 1000.0),
            FilterSpec("lpf", 1000.0),
        ]
        chain = FilterChain(specs, 16000)
        assert chain.num_stages == 2

    def test_car_cabin_eq(self):
        """Typical car cabin EQ: HPF + LPF + resonance peak."""
        specs = [
            FilterSpec("hpf", 80.0, Q=0.7071),
            FilterSpec("lpf", 8000.0, Q=0.7071),
            FilterSpec("peaking", 3000.0, Q=2.0, gain_db=4.0),
        ]
        chain = FilterChain(specs, 16000)
        assert chain.num_stages == 3

        # Should be able to process audio without error
        buf = AudioBuffer(samples=np.random.default_rng(42).standard_normal(16000), sample_rate=16000)
        result = chain.apply(buf)
        assert result.num_samples == buf.num_samples
