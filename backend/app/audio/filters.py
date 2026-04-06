"""Biquad filter chain using SOS form for numerical stability.

Filter coefficient formulas from the Audio EQ Cookbook by Robert Bristow-Johnson.
All filters are implemented as second-order sections (SOS) and cascaded via sosfilt.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import sosfilt, butter

from .types import AudioBuffer, FilterSpec


def _peaking_eq_sos(fc: float, Q: float, gain_db: float, fs: float) -> np.ndarray:
    """Peaking EQ biquad coefficients in SOS form."""
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * fc / fs
    alpha = np.sin(w0) / (2 * Q)

    b0 = 1 + alpha * A
    b1 = -2 * np.cos(w0)
    b2 = 1 - alpha * A
    a0 = 1 + alpha / A
    a1 = -2 * np.cos(w0)
    a2 = 1 - alpha / A

    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])


def _lowshelf_sos(fc: float, Q: float, gain_db: float, fs: float) -> np.ndarray:
    """Low shelf biquad coefficients in SOS form."""
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * fc / fs
    alpha = np.sin(w0) / (2 * Q)
    cos_w0 = np.cos(w0)
    two_sqrt_A_alpha = 2 * np.sqrt(A) * alpha

    b0 = A * ((A + 1) - (A - 1) * cos_w0 + two_sqrt_A_alpha)
    b1 = 2 * A * ((A - 1) - (A + 1) * cos_w0)
    b2 = A * ((A + 1) - (A - 1) * cos_w0 - two_sqrt_A_alpha)
    a0 = (A + 1) + (A - 1) * cos_w0 + two_sqrt_A_alpha
    a1 = -2 * ((A - 1) + (A + 1) * cos_w0)
    a2 = (A + 1) + (A - 1) * cos_w0 - two_sqrt_A_alpha

    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])


def _highshelf_sos(fc: float, Q: float, gain_db: float, fs: float) -> np.ndarray:
    """High shelf biquad coefficients in SOS form."""
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * fc / fs
    alpha = np.sin(w0) / (2 * Q)
    cos_w0 = np.cos(w0)
    two_sqrt_A_alpha = 2 * np.sqrt(A) * alpha

    b0 = A * ((A + 1) + (A - 1) * cos_w0 + two_sqrt_A_alpha)
    b1 = -2 * A * ((A - 1) + (A + 1) * cos_w0)
    b2 = A * ((A + 1) + (A - 1) * cos_w0 - two_sqrt_A_alpha)
    a0 = (A + 1) - (A - 1) * cos_w0 + two_sqrt_A_alpha
    a1 = 2 * ((A - 1) - (A + 1) * cos_w0)
    a2 = (A + 1) - (A - 1) * cos_w0 - two_sqrt_A_alpha

    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])


def _lpf_sos(fc: float, Q: float, fs: float) -> np.ndarray:
    """2nd-order low-pass filter biquad coefficients in SOS form."""
    w0 = 2 * np.pi * fc / fs
    alpha = np.sin(w0) / (2 * Q)
    cos_w0 = np.cos(w0)

    b0 = (1 - cos_w0) / 2
    b1 = 1 - cos_w0
    b2 = (1 - cos_w0) / 2
    a0 = 1 + alpha
    a1 = -2 * cos_w0
    a2 = 1 - alpha

    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])


def _hpf_sos(fc: float, Q: float, fs: float) -> np.ndarray:
    """2nd-order high-pass filter biquad coefficients in SOS form."""
    w0 = 2 * np.pi * fc / fs
    alpha = np.sin(w0) / (2 * Q)
    cos_w0 = np.cos(w0)

    b0 = (1 + cos_w0) / 2
    b1 = -(1 + cos_w0)
    b2 = (1 + cos_w0) / 2
    a0 = 1 + alpha
    a1 = -2 * cos_w0
    a2 = 1 - alpha

    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])


def filter_spec_to_sos(spec: FilterSpec, sample_rate: int) -> np.ndarray:
    """Convert a FilterSpec to SOS coefficients (1x6 array)."""
    nyquist = sample_rate / 2.0
    if spec.frequency > nyquist:
        raise ValueError(
            f"Filter frequency {spec.frequency} Hz exceeds Nyquist "
            f"frequency {nyquist} Hz (sample rate {sample_rate})"
        )
    if spec.filter_type == "lpf":
        return _lpf_sos(spec.frequency, spec.Q, sample_rate)
    elif spec.filter_type == "hpf":
        return _hpf_sos(spec.frequency, spec.Q, sample_rate)
    elif spec.filter_type == "peaking":
        return _peaking_eq_sos(spec.frequency, spec.Q, spec.gain_db, sample_rate)
    elif spec.filter_type == "lowshelf":
        return _lowshelf_sos(spec.frequency, spec.Q, spec.gain_db, sample_rate)
    elif spec.filter_type == "highshelf":
        return _highshelf_sos(spec.frequency, spec.Q, spec.gain_db, sample_rate)
    else:
        raise ValueError(f"Unknown filter type: {spec.filter_type}")


def butterworth_lpf_sos(order: int, cutoff_hz: float, sample_rate: int) -> np.ndarray:
    """Butterworth low-pass filter as SOS sections (for noise shaping)."""
    return butter(order, cutoff_hz, btype="low", fs=sample_rate, output="sos")


class FilterChain:
    """A cascade of biquad filters applied as a single SOS matrix."""

    def __init__(self, specs: list[FilterSpec], sample_rate: int):
        self.sample_rate = sample_rate
        self.specs = specs
        if specs:
            sections = [filter_spec_to_sos(s, sample_rate) for s in specs]
            self._sos = np.vstack(sections)
        else:
            self._sos = None

    def apply(self, audio: AudioBuffer) -> AudioBuffer:
        """Apply the filter chain to an audio buffer."""
        if self._sos is None or len(audio.samples) == 0:
            return audio
        filtered = sosfilt(self._sos, audio.samples)
        return AudioBuffer(samples=filtered, sample_rate=audio.sample_rate)

    @property
    def num_stages(self) -> int:
        return len(self.specs)
