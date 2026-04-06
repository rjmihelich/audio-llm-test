"""SNR-calibrated audio mixing."""

from __future__ import annotations

import numpy as np

from .types import AudioBuffer


def _soft_clip(samples: np.ndarray, threshold: float = 0.95) -> np.ndarray:
    """Soft-clip samples using a piece-wise approach.

    Samples with |x| <= threshold pass through unchanged.
    Samples with |x| > threshold are compressed into (threshold, 1.0]
    using a tanh curve, keeping the output strictly within [-1, 1].
    This preserves the true SNR for well-behaved signals while
    preventing hard-clipping artefacts for loud ones.
    """
    peak = np.max(np.abs(samples))
    if peak <= threshold:
        return samples

    out = samples.copy()
    headroom = 1.0 - threshold          # 0.05 by default
    over_pos = samples > threshold
    over_neg = samples < -threshold

    if np.any(over_pos):
        excess = samples[over_pos] - threshold
        out[over_pos] = threshold + headroom * np.tanh(excess / headroom)

    if np.any(over_neg):
        excess = -(samples[over_neg] + threshold)
        out[over_neg] = -(threshold + headroom * np.tanh(excess / headroom))

    return out


def mix_at_snr(speech: AudioBuffer, noise: AudioBuffer, snr_db: float) -> AudioBuffer:
    """Mix noise into speech at the specified SNR.

    SNR = 20 * log10(rms_speech / rms_noise)
    => rms_noise_target = rms_speech / 10^(snr_db/20)

    The noise is scaled to achieve the target SNR relative to the speech RMS.
    Soft-clipping is applied only when the mixed signal exceeds +/-0.95,
    preserving the true SNR for well-behaved signals.

    Args:
        speech: Clean speech audio (reference signal).
        noise: Noise audio (must be same length and sample rate as speech).
        snr_db: Target signal-to-noise ratio in dB. Lower values = more noise.
    """
    if speech.sample_rate != noise.sample_rate:
        noise = noise.resample(speech.sample_rate)

    # Ensure same length
    noise_samples = noise.loop_to_length(speech.num_samples).samples

    speech_rms = speech.rms
    noise_rms = np.sqrt(np.mean(noise_samples**2))

    if noise_rms <= 0 or speech_rms <= 0:
        return speech

    # Scale noise to target SNR
    target_noise_rms = speech_rms / (10 ** (snr_db / 20.0))
    scale = target_noise_rms / noise_rms

    mixed = speech.samples + scale * noise_samples

    # Soft-clip only if samples actually exceed bounds
    mixed = _soft_clip(mixed)

    return AudioBuffer(samples=mixed, sample_rate=speech.sample_rate)


def mix_signals(signals: list[AudioBuffer], gains_db: list[float] | None = None) -> AudioBuffer:
    """Mix multiple audio signals with optional per-signal gain.

    All signals are resampled to the first signal's sample rate and
    padded/truncated to the longest duration.
    """
    if not signals:
        raise ValueError("No signals to mix")

    target_sr = signals[0].sample_rate
    max_len = max(s.num_samples for s in signals)

    if gains_db is None:
        gains_db = [0.0] * len(signals)

    mixed = np.zeros(max_len, dtype=np.float64)

    for sig, gain_db in zip(signals, gains_db):
        s = sig.resample(target_sr).loop_to_length(max_len)
        gain_linear = 10 ** (gain_db / 20.0)
        mixed += s.samples * gain_linear

    mixed = _soft_clip(mixed)
    return AudioBuffer(samples=mixed, sample_rate=target_sr)
