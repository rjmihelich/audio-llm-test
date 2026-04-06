"""Noise generation: pink noise, white noise, and file-based noise sources."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.signal import sosfilt

from .types import AudioBuffer
from .filters import butterworth_lpf_sos
from .io import load_audio


def white_noise(duration_s: float, sample_rate: int = 16000, seed: int | None = None) -> AudioBuffer:
    """Generate white Gaussian noise."""
    rng = np.random.default_rng(seed)
    num_samples = int(duration_s * sample_rate)
    samples = rng.standard_normal(num_samples)
    return AudioBuffer(samples=samples, sample_rate=sample_rate)


def pink_noise(duration_s: float, sample_rate: int = 16000, seed: int | None = None) -> AudioBuffer:
    """Generate pink noise (1/f spectrum) via spectral shaping.

    Method: Generate white noise in frequency domain, scale magnitudes by 1/sqrt(f),
    then IFFT back to time domain.
    """
    rng = np.random.default_rng(seed)
    num_samples = int(duration_s * sample_rate)

    # Generate white noise
    white = rng.standard_normal(num_samples)

    # FFT
    X = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(num_samples, d=1.0 / sample_rate)

    # Scale by 1/sqrt(f) for pink spectrum, skip DC
    freqs[0] = 1.0  # Avoid division by zero at DC
    X *= 1.0 / np.sqrt(freqs)

    # IFFT back to time domain
    samples = np.fft.irfft(X, n=num_samples)

    # Normalize to unit RMS
    rms = np.sqrt(np.mean(samples**2))
    if rms > 0:
        samples /= rms

    return AudioBuffer(samples=samples, sample_rate=sample_rate)


def pink_noise_filtered(
    duration_s: float,
    lpf_cutoff_hz: float = 100.0,
    lpf_order: int = 2,
    sample_rate: int = 16000,
    seed: int | None = None,
) -> AudioBuffer:
    """Generate pink noise with a low-pass Butterworth filter applied.

    Default: 2nd-order LPF at 100 Hz — simulates low-frequency rumble
    typical of car cabin noise (road, engine, wind).
    """
    noise = pink_noise(duration_s, sample_rate, seed)
    sos = butterworth_lpf_sos(lpf_order, lpf_cutoff_hz, sample_rate)
    filtered = sosfilt(sos, noise.samples)

    # Re-normalize to unit RMS after filtering
    rms = np.sqrt(np.mean(filtered**2))
    if rms > 0:
        filtered /= rms

    return AudioBuffer(samples=filtered, sample_rate=sample_rate)


def babble_noise(
    duration_s: float,
    num_talkers: int = 6,
    sample_rate: int = 16000,
    seed: int | None = None,
) -> AudioBuffer:
    """Generate babble noise by summing multiple independent pink noise streams.

    Each "talker" is a pink noise stream with random amplitude modulation
    to simulate overlapping speech-like energy. The result is normalized
    to unit RMS.
    """
    rng = np.random.default_rng(seed)
    num_samples = int(duration_s * sample_rate)
    mixed = np.zeros(num_samples, dtype=np.float64)

    for i in range(num_talkers):
        talker_seed = rng.integers(0, 2**31)
        talker = pink_noise(duration_s, sample_rate, seed=int(talker_seed))
        mixed += talker.samples

    # Normalize to unit RMS
    rms = np.sqrt(np.mean(mixed**2))
    if rms > 0:
        mixed /= rms

    return AudioBuffer(samples=mixed, sample_rate=sample_rate)


def noise_from_file(
    file_path: Path | str,
    target_num_samples: int,
    target_sample_rate: int = 16000,
) -> AudioBuffer:
    """Load noise from a WAV file, resample if needed, loop/truncate to target length.

    The noise is RMS-normalized to unit RMS for consistent SNR mixing.
    """
    audio = load_audio(file_path, target_sample_rate)
    audio = audio.loop_to_length(target_num_samples)

    # Normalize to unit RMS
    rms = audio.rms
    if rms > 0:
        return AudioBuffer(samples=audio.samples / rms, sample_rate=audio.sample_rate)
    return audio
