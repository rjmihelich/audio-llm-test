"""Acoustic Echo Canceller (AEC) residual simulation for telephony testing.

Real AEC processors never remove echo perfectly. This module simulates:
  - Partial echo suppression (not full removal)
  - Non-linear distortion (NLD) artifacts introduced by over-aggressive AEC
  - Residual echo that leaks through the canceller

Works with the EchoPath output from echo.py: the echo reference signal
(what the AEC knows about) is attenuated by suppression_db, and NLD
artifacts are added to represent the distortion caused by the AEC itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from .types import AudioBuffer


class ResidualType(str, Enum):
    """Type of AEC residual pattern."""
    partial = "partial"        # Attenuated echo leaks through
    nonlinear = "nonlinear"    # Heavy NLD from over-aggressive AEC
    mixed = "mixed"            # Both partial residual + NLD (most realistic)


@dataclass(frozen=True)
class AECResidualConfig:
    """Configuration for AEC residual simulation.

    Attributes:
        suppression_db: How much the AEC suppresses echo (negative dB).
            -40 dB = very good AEC (only 1% of echo leaks through).
            -10 dB = poor AEC (31% of echo leaks through).
        residual_type: Pattern of residual artifacts.
        nonlinear_distortion: Strength of NLD clipping distortion [0.0, 1.0].
            0.0 = no NLD. 1.0 = maximum distortion.
        seed: Random seed for reproducible noise.
    """

    suppression_db: float = -25.0
    residual_type: ResidualType = ResidualType.mixed
    nonlinear_distortion: float = 0.3
    seed: int | None = None

    def __post_init__(self):
        if not (-60 <= self.suppression_db <= 0):
            raise ValueError(f"suppression_db must be -60 to 0, got {self.suppression_db}")
        if not (0.0 <= self.nonlinear_distortion <= 1.0):
            raise ValueError(f"nonlinear_distortion must be 0-1, got {self.nonlinear_distortion}")


def apply_aec_residual(
    mic_audio: AudioBuffer,
    echo_ref: AudioBuffer | None,
    config: AECResidualConfig,
) -> AudioBuffer:
    """Simulate imperfect AEC by mixing attenuated residual echo + NLD artifacts.

    Args:
        mic_audio: The mic signal already containing acoustic echo (output of
            EchoPath.apply()). The AEC will partially clean this.
        echo_ref: The echo reference signal (the speaker output that the AEC
            uses as its reference). If None, NLD-only mode is used.
        config: AEC residual configuration.

    Returns:
        Audio with realistic AEC residual: partially cleaned (some echo
        remaining) + optional NLD distortion artifacts.
    """
    if len(mic_audio.samples) == 0:
        return mic_audio

    samples = mic_audio.samples.copy()

    if echo_ref is not None and config.residual_type in (
        ResidualType.partial, ResidualType.mixed
    ):
        # The AEC suppresses the echo reference by suppression_db.
        # Whatever is not suppressed leaks back as residual.
        suppression_linear = 10 ** (config.suppression_db / 20.0)

        # Resample and align echo reference to mic length
        ref = echo_ref
        if ref.sample_rate != mic_audio.sample_rate:
            ref = ref.resample(mic_audio.sample_rate)

        ref_len = ref.num_samples
        mic_len = len(samples)
        if ref_len >= mic_len:
            ref_samples = ref.samples[:mic_len]
        else:
            ref_samples = np.zeros(mic_len, dtype=np.float64)
            ref_samples[:ref_len] = ref.samples

        # Residual = echo_ref × (1 - suppression) × suppression_linear
        # The AEC removes most of the echo, leaving just the residual fraction
        residual = ref_samples * suppression_linear
        samples = samples + residual

    if config.nonlinear_distortion > 0.0 and config.residual_type in (
        ResidualType.nonlinear, ResidualType.mixed
    ):
        samples = _apply_nld(samples, config.nonlinear_distortion, config.seed)

    return AudioBuffer(samples=samples, sample_rate=mic_audio.sample_rate)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _apply_nld(samples: np.ndarray, strength: float, seed: int | None) -> np.ndarray:
    """Apply non-linear distortion artifacts mimicking over-aggressive AEC.

    Combines soft clipping (simulates AEC-induced saturation) with a small
    amount of harmonic distortion and sporadic suppression bursts (the AEC
    briefly over-suppresses legitimate speech).
    """
    rng = np.random.default_rng(seed)

    # 1. Soft clipping — tanh with adjustable threshold
    # Higher strength = lower threshold = more distortion
    clip_threshold = 1.0 - 0.7 * strength
    clipped = clip_threshold * np.tanh(samples / (clip_threshold + 1e-8))

    # 2. Sporadic suppression bursts (AEC over-suppression)
    # At strength=1.0: ~5% of 20ms frames get suppressed by up to -12dB
    frame_len = int(samples.shape[0] / max(len(samples) // 320, 1)) or 320
    num_frames = max(len(clipped) // frame_len, 1)
    burst_prob = 0.05 * strength
    output = clipped.copy()
    for i in range(num_frames):
        if rng.random() < burst_prob:
            start = i * frame_len
            end = min(start + frame_len, len(output))
            suppress_db = rng.uniform(-12.0 * strength, -3.0 * strength)
            output[start:end] *= 10 ** (suppress_db / 20.0)

    return output
