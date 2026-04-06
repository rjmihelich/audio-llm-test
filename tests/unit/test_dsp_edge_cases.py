"""Edge case and stress tests for the full DSP chain.

Tests extreme SNR values, silent signals, very short/long audio,
filter stability, mixer clipping behavior, and noise generation
boundary conditions.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.app.audio.types import AudioBuffer, FilterSpec
from backend.app.audio.noise import white_noise, pink_noise, pink_noise_filtered, babble_noise
from backend.app.audio.mixer import mix_at_snr, mix_signals
from backend.app.audio.echo import EchoConfig, EchoPath
from backend.app.audio.filters import FilterChain, filter_spec_to_sos


def _sine(freq=300.0, dur=1.0, sr=16000, amp=0.5) -> AudioBuffer:
    t = np.arange(int(sr * dur)) / sr
    return AudioBuffer(samples=amp * np.sin(2 * np.pi * freq * t), sample_rate=sr)


def _silence(dur=1.0, sr=16000) -> AudioBuffer:
    return AudioBuffer(samples=np.zeros(int(sr * dur)), sample_rate=sr)


# ---------------------------------------------------------------------------
# Extreme SNR mixing
# ---------------------------------------------------------------------------

class TestExtremeSNR:
    def test_very_high_snr_noise_negligible(self):
        """At +60 dB SNR, noise should be inaudible."""
        speech = _sine()
        noise = white_noise(1.0, 16000, seed=1)
        mixed = mix_at_snr(speech, noise, 60.0)
        # Speech amplitude 0.5 is below soft-clip threshold, so pass-through
        diff = np.max(np.abs(mixed.samples - speech.samples))
        assert diff < 0.01

    def test_very_low_snr_speech_buried(self):
        """At -20 dB SNR, noise dominates."""
        speech = _sine(amp=0.3)
        noise = white_noise(1.0, 16000, seed=1)
        mixed = mix_at_snr(speech, noise, -20.0)
        # Mixed signal RMS should be much higher than speech
        assert mixed.rms > speech.rms * 0.5

    def test_zero_snr_equal_power(self):
        """At 0 dB, speech and noise have equal RMS before mixing."""
        speech = _sine()
        noise = white_noise(1.0, 16000, seed=1)
        mixed = mix_at_snr(speech, noise, 0.0)
        assert mixed.rms > 0

    def test_silent_speech_returns_speech(self):
        """If speech is silent, mixer returns it unchanged."""
        speech = _silence()
        noise = white_noise(1.0, 16000, seed=1)
        result = mix_at_snr(speech, noise, 10.0)
        np.testing.assert_array_equal(result.samples, speech.samples)

    def test_silent_noise_returns_speech(self):
        """If noise is silent, mixer returns speech unchanged."""
        speech = _sine()
        noise = _silence()
        result = mix_at_snr(speech, noise, 10.0)
        np.testing.assert_array_equal(result.samples, speech.samples)

    def test_no_nan_or_inf(self):
        """No NaN/Inf should appear at any SNR."""
        speech = _sine()
        noise = white_noise(1.0, 16000, seed=1)
        for snr in [-30, -10, 0, 10, 30, 60]:
            mixed = mix_at_snr(speech, noise, float(snr))
            assert not np.any(np.isnan(mixed.samples)), f"NaN at SNR={snr}"
            assert not np.any(np.isinf(mixed.samples)), f"Inf at SNR={snr}"

    def test_soft_clip_bounds_loud_signals(self):
        """Soft-clipping should keep loud signals within [-1, 1]."""
        speech = _sine(amp=0.8)
        noise = white_noise(1.0, 16000, seed=1)
        mixed = mix_at_snr(speech, noise, -20.0)
        assert np.all(mixed.samples >= -1.0)
        assert np.all(mixed.samples <= 1.0)
        assert not np.any(np.isnan(mixed.samples))


# ---------------------------------------------------------------------------
# Mix signals edge cases
# ---------------------------------------------------------------------------

class TestMixSignalsEdgeCases:
    def test_single_signal(self):
        sig = _sine()
        mixed = mix_signals([sig])
        assert mixed.num_samples == sig.num_samples

    def test_different_sample_rates(self):
        s1 = _sine(sr=16000)
        s2 = _sine(sr=8000)
        mixed = mix_signals([s1, s2])
        assert mixed.sample_rate == 16000

    def test_different_lengths(self):
        s1 = _sine(dur=1.0)
        s2 = _sine(dur=0.5)
        mixed = mix_signals([s1, s2])
        assert mixed.num_samples == s1.num_samples

    def test_high_gain_bounded(self):
        """High gain signals should be compressed within [-1, 1]."""
        sigs = [_sine(amp=0.5) for _ in range(5)]
        gains = [20.0] * 5
        mixed = mix_signals(sigs, gains)
        assert np.all(np.abs(mixed.samples) <= 1.0)
        assert not np.any(np.isnan(mixed.samples))


# ---------------------------------------------------------------------------
# Noise generation edge cases
# ---------------------------------------------------------------------------

class TestNoiseEdgeCases:
    def test_very_short_white_noise(self):
        n = white_noise(0.001, 16000, seed=0)  # 16 samples
        assert n.num_samples == 16
        assert n.rms > 0

    def test_very_short_pink_noise(self):
        n = pink_noise(0.01, 16000, seed=0)  # 160 samples
        assert n.num_samples == 160
        assert n.rms > 0

    def test_very_short_babble(self):
        n = babble_noise(0.05, num_talkers=2, sample_rate=16000, seed=0)
        assert n.num_samples == 800
        assert n.rms > 0

    def test_long_noise_no_error(self):
        """10 seconds of noise should work without memory issues."""
        n = white_noise(10.0, 16000, seed=0)
        assert n.num_samples == 160000

    def test_pink_noise_unit_rms(self):
        n = pink_noise(2.0, 16000, seed=42)
        assert abs(n.rms - 1.0) < 0.01

    def test_babble_single_talker(self):
        n = babble_noise(1.0, num_talkers=1, sample_rate=16000, seed=42)
        assert abs(n.rms - 1.0) < 0.01

    def test_babble_many_talkers(self):
        n = babble_noise(1.0, num_talkers=20, sample_rate=16000, seed=42)
        assert abs(n.rms - 1.0) < 0.01

    def test_white_noise_no_dc_bias(self):
        """White noise should have near-zero mean."""
        n = white_noise(5.0, 16000, seed=42)
        assert abs(np.mean(n.samples)) < 0.02

    def test_pink_filtered_below_cutoff_dominant(self):
        """After LPF at 100 Hz, most energy should be below 200 Hz."""
        n = pink_noise_filtered(2.0, lpf_cutoff_hz=100.0, sample_rate=16000, seed=42)
        fft_mag = np.abs(np.fft.rfft(n.samples))
        freqs = np.fft.rfftfreq(n.num_samples, d=1.0 / 16000)
        low_energy = np.sum(fft_mag[freqs <= 200] ** 2)
        high_energy = np.sum(fft_mag[freqs > 200] ** 2)
        assert low_energy > high_energy * 5  # Most energy below 200 Hz


# ---------------------------------------------------------------------------
# Echo edge cases
# ---------------------------------------------------------------------------

class TestEchoEdgeCases:
    def test_max_delay(self):
        """500 ms delay should work."""
        cfg = EchoConfig(delay_ms=500.0, gain_db=-10.0)
        ep = EchoPath(cfg, 16000)
        speech = _sine(dur=1.0)
        echo = ep.process_echo(speech)
        # Echo should be 8000 samples longer (500ms * 16kHz)
        assert echo.num_samples == speech.num_samples + 8000

    def test_zero_delay_no_shift(self):
        cfg = EchoConfig(delay_ms=0.0, gain_db=-6.0)
        ep = EchoPath(cfg, 16000)
        speech = _sine(dur=0.5)
        echo = ep.process_echo(speech)
        # With 0 delay, echo length equals speech length
        assert echo.num_samples == speech.num_samples

    def test_minus_100db_effectively_zero(self):
        cfg = EchoConfig(delay_ms=50.0, gain_db=-100.0)
        ep = EchoPath(cfg, 16000)
        speech = _sine(dur=0.5)
        echo = ep.process_echo(speech)
        assert echo.rms < 1e-4

    def test_echo_does_not_modify_mic_length(self):
        """apply() should return same-length audio as mic input."""
        cfg = EchoConfig(delay_ms=200.0, gain_db=-10.0)
        ep = EchoPath(cfg, 16000)
        mic = _sine(dur=1.0)
        speaker = _sine(dur=0.5)
        result = ep.apply(mic, speaker)
        assert result.num_samples == mic.num_samples

    def test_echo_with_eq_chain(self):
        cfg = EchoConfig(
            delay_ms=50.0, gain_db=-10.0,
            eq_chain=[
                FilterSpec("hpf", 80.0),
                FilterSpec("lpf", 6000.0),
            ],
        )
        ep = EchoPath(cfg, 16000)
        speech = _sine(dur=1.0)
        echo = ep.process_echo(speech)
        assert not np.any(np.isnan(echo.samples))

    def test_echo_separate_from_degraded(self):
        """Verify echo_audio is the isolated echo, not the full degraded signal."""
        from backend.app.pipeline.direct_audio import DirectAudioPipeline
        from backend.app.llm.base import LLMResponse, RateLimitConfig
        import asyncio

        class MockLLM:
            @property
            def name(self): return "mock"
            @property
            def supports_audio_input(self): return True
            @property
            def rate_limit(self): return RateLimitConfig()
            async def query_with_audio(self, audio, prompt, context=None):
                return LLMResponse(text="ok", latency_ms=1.0, model="mock")

        from backend.app.pipeline.base import PipelineInput
        from backend.app.audio.echo import EchoConfig

        llm = MockLLM()
        pipeline = DirectAudioPipeline(
            llm_backend=llm, snr_db=10.0,
            echo_config=EchoConfig(delay_ms=50.0, gain_db=-10.0),
        )
        inp = PipelineInput(
            clean_speech=_sine(), original_text="test",
            expected_intent="test", expected_action="test",
        )
        result = asyncio.get_event_loop().run_until_complete(pipeline.execute(inp))
        assert result.echo_audio is not None
        assert result.degraded_audio is not None
        # echo_audio should have LOWER RMS than degraded (it's just the echo component)
        assert result.echo_audio.rms < result.degraded_audio.rms


# ---------------------------------------------------------------------------
# Filter stability
# ---------------------------------------------------------------------------

class TestFilterStability:
    def test_nyquist_rejection(self):
        """Frequencies above Nyquist should be rejected."""
        spec = FilterSpec("lpf", 9000.0)  # > 8000 Hz Nyquist at 16 kHz
        with pytest.raises(ValueError, match="Nyquist"):
            filter_spec_to_sos(spec, 16000)

    def test_at_nyquist_allowed(self):
        """Exactly at Nyquist should be allowed (degenerate but valid)."""
        spec = FilterSpec("lpf", 8000.0)
        sos = filter_spec_to_sos(spec, 16000)
        assert sos.shape == (1, 6)

    def test_very_low_frequency(self):
        """1 Hz filter at 16 kHz should work."""
        spec = FilterSpec("hpf", 1.0)
        sos = filter_spec_to_sos(spec, 16000)
        assert not np.any(np.isnan(sos))

    def test_extreme_q_values(self):
        """Very high and very low Q should produce finite coefficients."""
        for q in [0.1, 0.5, 1.0, 10.0, 50.0]:
            spec = FilterSpec("peaking", 1000.0, Q=q, gain_db=6.0)
            sos = filter_spec_to_sos(spec, 16000)
            assert not np.any(np.isnan(sos)), f"NaN at Q={q}"
            assert not np.any(np.isinf(sos)), f"Inf at Q={q}"

    def test_extreme_gain(self):
        """Large gain values should produce finite coefficients."""
        for gain in [-40.0, -20.0, 0.0, 12.0, 24.0]:
            spec = FilterSpec("peaking", 1000.0, gain_db=gain)
            sos = filter_spec_to_sos(spec, 16000)
            assert not np.any(np.isnan(sos)), f"NaN at gain={gain}"

    def test_shelf_filters_stable(self):
        for ftype in ["lowshelf", "highshelf"]:
            spec = FilterSpec(ftype, 500.0, gain_db=12.0)
            sos = filter_spec_to_sos(spec, 16000)
            # Apply to random signal — should not diverge
            from scipy.signal import sosfilt
            signal = np.random.default_rng(42).standard_normal(16000)
            output = sosfilt(sos, signal)
            assert not np.any(np.isnan(output)), f"NaN with {ftype}"
            assert np.max(np.abs(output)) < 1e6, f"Divergence with {ftype}"

    def test_long_chain_no_divergence(self):
        """10 cascaded peaking filters should remain stable."""
        specs = [FilterSpec("peaking", 200 + i * 500, Q=2.0, gain_db=3.0) for i in range(10)]
        chain = FilterChain(specs, 16000)
        buf = AudioBuffer(
            samples=np.random.default_rng(0).standard_normal(16000),
            sample_rate=16000,
        )
        result = chain.apply(buf)
        assert not np.any(np.isnan(result.samples))
        assert np.max(np.abs(result.samples)) < 1e6


# ---------------------------------------------------------------------------
# AudioBuffer edge cases
# ---------------------------------------------------------------------------

class TestAudioBufferEdgeCases:
    def test_rms_db_silence(self):
        buf = _silence(dur=0.1)
        assert buf.rms_db == -np.inf

    def test_single_sample(self):
        buf = AudioBuffer(samples=np.array([0.5]), sample_rate=16000)
        assert buf.duration_s == pytest.approx(1 / 16000)
        assert buf.rms == 0.5
        assert buf.peak == 0.5

    def test_loop_empty_buffer(self):
        buf = AudioBuffer(samples=np.array([]), sample_rate=16000)
        looped = buf.loop_to_length(100)
        assert looped.num_samples == 100
        assert np.all(looped.samples == 0.0)

    def test_resample_preserves_duration(self):
        buf = _sine(dur=1.0, sr=16000)
        resampled = buf.resample(8000)
        assert abs(resampled.duration_s - 1.0) < 0.01

    def test_normalize_zero_signal(self):
        buf = _silence()
        normed = buf.normalize(target_rms=0.5)
        assert normed.rms == 0.0  # Can't normalize silence
