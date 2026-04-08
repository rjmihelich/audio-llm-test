"""Noise reduction / suppression algorithms.

Implements spectral subtraction and Wiener filtering for speech enhancement.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import get_window

from .types import AudioBuffer


def _stft(samples: np.ndarray, fft_size: int, hop_size: int, window: np.ndarray):
    """Short-Time Fourier Transform."""
    n_frames = 1 + (len(samples) - fft_size) // hop_size
    frames = np.zeros((n_frames, fft_size), dtype=np.float64)
    for i in range(n_frames):
        start = i * hop_size
        frames[i] = samples[start:start + fft_size] * window
    return np.fft.rfft(frames, axis=1)


def _istft(stft_matrix: np.ndarray, fft_size: int, hop_size: int, window: np.ndarray, length: int):
    """Inverse STFT with overlap-add."""
    n_frames = stft_matrix.shape[0]
    output = np.zeros(length, dtype=np.float64)
    window_sum = np.zeros(length, dtype=np.float64)

    for i in range(n_frames):
        start = i * hop_size
        end = min(start + fft_size, length)
        frame = np.fft.irfft(stft_matrix[i], n=fft_size)
        seg_len = end - start
        output[start:end] += frame[:seg_len] * window[:seg_len]
        window_sum[start:end] += window[:seg_len] ** 2

    # Normalize by window sum (avoid divide-by-zero)
    nonzero = window_sum > 1e-10
    output[nonzero] /= window_sum[nonzero]
    return output


def spectral_subtraction(
    audio: AudioBuffer,
    *,
    noise_ref: AudioBuffer | None = None,
    suppression_db: float = 12.0,
    noise_floor_db: float = -60.0,
    smoothing_factor: float = 0.9,
    fft_size: int = 1024,
    hop_size: int = 256,
) -> AudioBuffer:
    """Spectral subtraction noise reduction.

    Estimates noise spectrum from either a reference signal or the first
    few frames of the input, then subtracts it from each frame's magnitude
    spectrum.

    Args:
        audio: Noisy input signal.
        noise_ref: Optional noise-only reference for profile estimation.
            If None, uses the first 10 frames of the input.
        suppression_db: Maximum suppression applied (dB).
        noise_floor_db: Spectral floor to prevent musical noise (dB).
        smoothing_factor: Exponential smoothing for noise estimate update.
        fft_size: FFT window size in samples.
        hop_size: Hop size in samples.
    """
    samples = audio.samples.astype(np.float64)
    window = get_window("hann", fft_size)

    # Compute STFT of input
    X = _stft(samples, fft_size, hop_size, window)
    mag = np.abs(X)
    phase = np.angle(X)

    # Estimate noise profile
    if noise_ref is not None:
        noise_samples = noise_ref.samples.astype(np.float64)
        if len(noise_samples) >= fft_size:
            N = _stft(noise_samples, fft_size, hop_size, window)
            noise_profile = np.mean(np.abs(N) ** 2, axis=0)
        else:
            noise_profile = np.mean(mag[:10] ** 2, axis=0)
    else:
        # Use first 10 frames as noise estimate
        n_noise_frames = min(10, mag.shape[0])
        noise_profile = np.mean(mag[:n_noise_frames] ** 2, axis=0)

    # Suppression parameters
    max_suppression = 10 ** (-suppression_db / 20)
    floor = 10 ** (noise_floor_db / 20)

    # Process each frame
    output_mag = np.zeros_like(mag)
    running_noise = noise_profile.copy()

    for i in range(mag.shape[0]):
        frame_power = mag[i] ** 2

        # SNR estimate per bin
        snr = frame_power / (running_noise + 1e-10)

        # Spectral subtraction gain
        gain = np.sqrt(np.maximum(1.0 - 1.0 / (snr + 1e-10), max_suppression ** 2))

        # Apply floor
        gain = np.maximum(gain, floor)

        output_mag[i] = mag[i] * gain

        # Update noise estimate for bins with low SNR (likely noise-only)
        noise_mask = snr < 2.0  # bins where noise dominates
        running_noise[noise_mask] = (
            smoothing_factor * running_noise[noise_mask]
            + (1 - smoothing_factor) * frame_power[noise_mask]
        )

    # Reconstruct
    Y = output_mag * np.exp(1j * phase)
    output = _istft(Y, fft_size, hop_size, window, len(samples))

    return AudioBuffer(samples=output.astype(np.float32), sample_rate=audio.sample_rate)


def wiener_filter(
    audio: AudioBuffer,
    *,
    noise_ref: AudioBuffer | None = None,
    suppression_db: float = 12.0,
    noise_floor_db: float = -60.0,
    smoothing_factor: float = 0.9,
    fft_size: int = 1024,
    hop_size: int = 256,
) -> AudioBuffer:
    """Wiener filter noise reduction.

    Applies the optimal minimum mean square error (MMSE) spectral gain:
        G(f) = S(f) / (S(f) + N(f))
    where S is speech power and N is noise power estimate.

    Args:
        audio: Noisy input signal.
        noise_ref: Optional noise-only reference for profile estimation.
        suppression_db: Maximum suppression applied (dB).
        noise_floor_db: Spectral floor (dB).
        smoothing_factor: Noise estimate smoothing.
        fft_size: FFT window size.
        hop_size: Hop size.
    """
    samples = audio.samples.astype(np.float64)
    window = get_window("hann", fft_size)

    X = _stft(samples, fft_size, hop_size, window)
    mag = np.abs(X)
    phase = np.angle(X)

    # Noise profile
    if noise_ref is not None:
        noise_samples = noise_ref.samples.astype(np.float64)
        if len(noise_samples) >= fft_size:
            N = _stft(noise_samples, fft_size, hop_size, window)
            noise_profile = np.mean(np.abs(N) ** 2, axis=0)
        else:
            noise_profile = np.mean(mag[:10] ** 2, axis=0)
    else:
        n_noise_frames = min(10, mag.shape[0])
        noise_profile = np.mean(mag[:n_noise_frames] ** 2, axis=0)

    floor = 10 ** (noise_floor_db / 20)
    max_suppression = 10 ** (-suppression_db / 20)

    output_mag = np.zeros_like(mag)
    running_noise = noise_profile.copy()

    for i in range(mag.shape[0]):
        frame_power = mag[i] ** 2

        # Wiener gain: G = max(1 - N/P, floor)
        # Equivalent to S/(S+N) where S = P - N
        speech_power = np.maximum(frame_power - running_noise, 0)
        gain = speech_power / (frame_power + 1e-10)

        # Clamp
        gain = np.maximum(gain, max_suppression)
        gain = np.maximum(gain, floor)

        output_mag[i] = mag[i] * gain

        # Update noise estimate
        snr = frame_power / (running_noise + 1e-10)
        noise_mask = snr < 2.0
        running_noise[noise_mask] = (
            smoothing_factor * running_noise[noise_mask]
            + (1 - smoothing_factor) * frame_power[noise_mask]
        )

    Y = output_mag * np.exp(1j * phase)
    output = _istft(Y, fft_size, hop_size, window, len(samples))

    return AudioBuffer(samples=output.astype(np.float32), sample_rate=audio.sample_rate)


def apply_noise_reduction(
    audio: AudioBuffer,
    *,
    method: str = "spectral_subtraction",
    noise_ref: AudioBuffer | None = None,
    suppression_db: float = 12.0,
    noise_floor_db: float = -60.0,
    smoothing_factor: float = 0.9,
) -> AudioBuffer:
    """Dispatch to the chosen noise reduction method.

    Args:
        method: One of "spectral_subtraction" or "wiener".
    """
    kwargs = dict(
        noise_ref=noise_ref,
        suppression_db=suppression_db,
        noise_floor_db=noise_floor_db,
        smoothing_factor=smoothing_factor,
    )
    if method == "spectral_subtraction":
        return spectral_subtraction(audio, **kwargs)
    elif method == "wiener":
        return wiener_filter(audio, **kwargs)
    else:
        raise ValueError(f"Unknown noise reduction method: {method!r}. Use 'spectral_subtraction' or 'wiener'.")
