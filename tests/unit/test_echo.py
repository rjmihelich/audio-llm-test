"""Tests for echo path simulation."""

import numpy as np
import pytest

from backend.app.audio.types import AudioBuffer, FilterSpec
from backend.app.audio.echo import EchoConfig, EchoPath


class TestEchoConfig:
    def test_valid_config(self):
        cfg = EchoConfig(delay_ms=100.0, gain_db=-20.0)
        assert cfg.delay_ms == 100.0
        assert cfg.gain_db == -20.0

    def test_delay_out_of_range(self):
        with pytest.raises(ValueError, match="delay_ms"):
            EchoConfig(delay_ms=600.0, gain_db=-20.0)

    def test_gain_out_of_range(self):
        with pytest.raises(ValueError, match="gain_db"):
            EchoConfig(delay_ms=100.0, gain_db=5.0)

    def test_default_values(self):
        cfg = EchoConfig()
        assert cfg.delay_ms == 50.0
        assert cfg.gain_db == -20.0
        assert cfg.eq_chain == []


class TestEchoPath:
    def _impulse(self, num_samples=16000, sr=16000):
        """Create an impulse signal (1.0 at sample 0, rest zeros)."""
        samples = np.zeros(num_samples, dtype=np.float64)
        samples[0] = 1.0
        return AudioBuffer(samples=samples, sample_rate=sr)

    def _tone(self, freq=440, duration=1.0, sr=16000, amplitude=0.5):
        t = np.arange(int(sr * duration)) / sr
        return AudioBuffer(samples=amplitude * np.sin(2 * np.pi * freq * t), sample_rate=sr)

    def test_delay_accuracy(self):
        """Echo should appear at exactly the specified delay."""
        delay_ms = 100.0
        sr = 16000
        cfg = EchoConfig(delay_ms=delay_ms, gain_db=0.0)
        echo_path = EchoPath(cfg, sr)

        impulse = self._impulse(sr=sr)
        echo = echo_path.process_echo(impulse)

        expected_delay_samples = int(delay_ms * sr / 1000)
        # The echo of the impulse should appear at the delay offset
        peak_idx = np.argmax(np.abs(echo.samples))
        assert peak_idx == expected_delay_samples

    def test_zero_delay(self):
        """With zero delay, echo should be immediate."""
        cfg = EchoConfig(delay_ms=0.0, gain_db=0.0)
        echo_path = EchoPath(cfg, 16000)
        impulse = self._impulse()
        echo = echo_path.process_echo(impulse)
        assert np.argmax(np.abs(echo.samples)) == 0

    def test_gain_accuracy(self):
        """Echo gain should match the specified dB value."""
        gain_db = -20.0
        cfg = EchoConfig(delay_ms=0.0, gain_db=gain_db)
        echo_path = EchoPath(cfg, 16000)

        impulse = self._impulse()
        echo = echo_path.process_echo(impulse)

        expected_gain_linear = 10 ** (gain_db / 20.0)
        assert echo.samples[0] == pytest.approx(expected_gain_linear, rel=1e-6)

    def test_minus_100db_effectively_silent(self):
        """At -100 dB gain, echo should be essentially zero."""
        cfg = EchoConfig(delay_ms=50.0, gain_db=-100.0)
        echo_path = EchoPath(cfg, 16000)

        tone = self._tone()
        echo = echo_path.process_echo(tone)

        assert echo.peak < 1e-4

    def test_apply_adds_echo_to_mic(self):
        """apply() should sum the echo with the mic input."""
        sr = 16000
        cfg = EchoConfig(delay_ms=0.0, gain_db=0.0)
        echo_path = EchoPath(cfg, sr)

        mic = AudioBuffer(samples=np.ones(sr, dtype=np.float64) * 0.3, sample_rate=sr)
        speaker = AudioBuffer(samples=np.ones(sr, dtype=np.float64) * 0.2, sample_rate=sr)

        result = echo_path.apply(mic, speaker)
        # Should be mic + echo = 0.3 + 0.2 = 0.5
        assert result.samples[0] == pytest.approx(0.5, rel=1e-6)

    def test_echo_with_eq(self):
        """Echo with EQ should filter the echo signal."""
        specs = [FilterSpec("lpf", 500.0)]
        cfg = EchoConfig(delay_ms=0.0, gain_db=0.0, eq_chain=specs)
        echo_path = EchoPath(cfg, 16000)

        # Use white noise as speaker signal
        rng = np.random.default_rng(42)
        speaker = AudioBuffer(samples=rng.standard_normal(16000), sample_rate=16000)
        mic = AudioBuffer(samples=np.zeros(16000, dtype=np.float64), sample_rate=16000)

        result = echo_path.apply(mic, speaker)

        # The result should have reduced high-frequency content
        fft = np.abs(np.fft.rfft(result.samples))
        freqs = np.fft.rfftfreq(16000, 1 / 16000)
        high_mask = freqs > 2000
        low_mask = (freqs > 10) & (freqs < 200)

        high_energy = np.mean(fft[high_mask] ** 2)
        low_energy = np.mean(fft[low_mask] ** 2)
        assert high_energy < low_energy * 0.01

    def test_echo_length_alignment(self):
        """Echo output should be truncated/padded to match mic input length."""
        sr = 16000
        cfg = EchoConfig(delay_ms=200.0, gain_db=-10.0)
        echo_path = EchoPath(cfg, sr)

        mic = AudioBuffer(samples=np.zeros(sr, dtype=np.float64), sample_rate=sr)
        speaker = AudioBuffer(samples=np.ones(sr, dtype=np.float64) * 0.5, sample_rate=sr)

        result = echo_path.apply(mic, speaker)
        assert result.num_samples == mic.num_samples
