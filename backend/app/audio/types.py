"""Core audio types for the test system."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

import numpy as np
from scipy.signal import resample_poly
from math import gcd


@dataclass(frozen=True)
class AudioBuffer:
    """Immutable audio buffer with float64 samples in [-1.0, 1.0] range."""

    samples: np.ndarray  # float64, mono
    sample_rate: int

    def __post_init__(self):
        if self.samples.dtype != np.float64:
            object.__setattr__(self, "samples", self.samples.astype(np.float64))
        if self.samples.ndim > 1:
            # Convert to mono by averaging channels
            object.__setattr__(self, "samples", self.samples.mean(axis=1))

    @property
    def duration_s(self) -> float:
        return len(self.samples) / self.sample_rate

    @property
    def num_samples(self) -> int:
        return len(self.samples)

    @property
    def rms(self) -> float:
        if len(self.samples) == 0:
            return 0.0
        return float(np.sqrt(np.mean(self.samples**2)))

    @property
    def peak(self) -> float:
        if len(self.samples) == 0:
            return 0.0
        return float(np.max(np.abs(self.samples)))

    @property
    def rms_db(self) -> float:
        r = self.rms
        if r <= 0:
            return -np.inf
        return float(20.0 * np.log10(r))

    def resample(self, target_sr: int) -> AudioBuffer:
        """Resample to a new sample rate using polyphase filtering."""
        if target_sr == self.sample_rate:
            return self
        g = gcd(self.sample_rate, target_sr)
        up = target_sr // g
        down = self.sample_rate // g
        resampled = resample_poly(self.samples, up, down)
        return AudioBuffer(samples=resampled, sample_rate=target_sr)

    def normalize(self, target_rms: float | None = None, target_peak: float | None = None) -> AudioBuffer:
        """Normalize audio to target RMS or peak level."""
        if target_rms is not None:
            current_rms = self.rms
            if current_rms <= 0:
                return self
            scale = target_rms / current_rms
        elif target_peak is not None:
            current_peak = self.peak
            if current_peak <= 0:
                return self
            scale = target_peak / current_peak
        else:
            # Default: normalize peak to 1.0
            return self.normalize(target_peak=1.0)
        return AudioBuffer(samples=self.samples * scale, sample_rate=self.sample_rate)

    def trim_to_duration(self, duration_s: float) -> AudioBuffer:
        """Trim or zero-pad to exactly the specified duration."""
        target_samples = int(duration_s * self.sample_rate)
        if len(self.samples) >= target_samples:
            return AudioBuffer(samples=self.samples[:target_samples], sample_rate=self.sample_rate)
        padded = np.zeros(target_samples, dtype=np.float64)
        padded[: len(self.samples)] = self.samples
        return AudioBuffer(samples=padded, sample_rate=self.sample_rate)

    def loop_to_length(self, num_samples: int) -> AudioBuffer:
        """Loop audio to fill exactly num_samples."""
        if len(self.samples) == 0:
            return AudioBuffer(samples=np.zeros(num_samples, dtype=np.float64), sample_rate=self.sample_rate)
        if len(self.samples) >= num_samples:
            return AudioBuffer(samples=self.samples[:num_samples], sample_rate=self.sample_rate)
        repeats = (num_samples // len(self.samples)) + 1
        looped = np.tile(self.samples, repeats)[:num_samples]
        return AudioBuffer(samples=looped, sample_rate=self.sample_rate)


@dataclass(frozen=True)
class FilterSpec:
    """Specification for a single biquad filter stage."""

    filter_type: Literal["lpf", "hpf", "peaking", "lowshelf", "highshelf"]
    frequency: float  # Hz
    Q: float = 0.7071  # Butterworth default (1/sqrt(2))
    gain_db: float = 0.0  # Only used for peaking/shelf types
