"""Automatic Gain Control (AGC) simulation for telephony path testing.

Models the gain normalization and characteristic artifacts (pumping, breathing)
introduced by AGC circuits in Bluetooth hands-free units and phone microphone
processing stacks.

The envelope-follower model uses attack/release time constants to produce
realistic gain modulation, including audible pumping when the AGC responds
to silence or quieter passages.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .types import AudioBuffer


@dataclass(frozen=True)
class AGCConfig:
    """Configuration for AGC simulation.

    Attributes:
        target_rms_db: Target RMS level the AGC drives towards (dBFS).
        attack_ms: Time constant for gain increase when signal drops (ms).
            Shorter = faster "breathing" / pumping artefacts.
        release_ms: Time constant for gain decrease when signal rises (ms).
            Shorter = faster gain reduction, can cause clipping artifacts.
        max_gain_db: Maximum gain the AGC will apply (dB).
            Limits noise amplification during silence.
        compression_ratio: Gain reduction ratio above threshold (e.g. 4.0 = 4:1).
            Higher = more aggressive compression / more pumping.
    """

    target_rms_db: float = -18.0
    attack_ms: float = 50.0
    release_ms: float = 200.0
    max_gain_db: float = 30.0
    compression_ratio: float = 4.0


# Pre-defined presets matching real-world AGC behaviour profiles
AGC_OFF = AGCConfig(
    target_rms_db=-18.0,
    attack_ms=10000.0,   # Extremely slow = effectively off
    release_ms=10000.0,
    max_gain_db=0.0,     # No gain boost allowed
    compression_ratio=1.0,
)

AGC_MILD = AGCConfig(
    target_rms_db=-18.0,
    attack_ms=100.0,
    release_ms=500.0,
    max_gain_db=20.0,
    compression_ratio=2.0,
)

AGC_AGGRESSIVE = AGCConfig(
    target_rms_db=-12.0,
    attack_ms=20.0,
    release_ms=100.0,
    max_gain_db=30.0,
    compression_ratio=8.0,
)

AGC_PRESETS: dict[str, AGCConfig] = {
    "off": AGC_OFF,
    "mild": AGC_MILD,
    "aggressive": AGC_AGGRESSIVE,
}


def apply_agc(audio: AudioBuffer, config: AGCConfig) -> AudioBuffer:
    """Apply envelope-follower AGC with realistic pumping/breathing artifacts.

    Algorithm:
      1. Compute per-sample envelope via first-order IIR with attack/release
         time constants derived from config.
      2. Derive desired gain from envelope vs. target level, clamped to
         max_gain_db.
      3. Apply compression above threshold using compression_ratio.
      4. Multiply signal by gain envelope (produces pumping/breathing when
         gain changes are audible).
    """
    if len(audio.samples) == 0:
        return audio

    sr = audio.sample_rate
    samples = audio.samples.copy()

    target_rms = 10 ** (config.target_rms_db / 20.0)
    max_gain = 10 ** (config.max_gain_db / 20.0)

    # Time constants → per-sample coefficients (first-order IIR)
    attack_coef = np.exp(-1.0 / (config.attack_ms * sr / 1000.0))
    release_coef = np.exp(-1.0 / (config.release_ms * sr / 1000.0))

    # Compute rectified envelope
    abs_samples = np.abs(samples)

    envelope = np.zeros(len(samples), dtype=np.float64)
    env = 0.0
    for i, s in enumerate(abs_samples):
        if s > env:
            env = attack_coef * env + (1.0 - attack_coef) * s
        else:
            env = release_coef * env + (1.0 - release_coef) * s
        envelope[i] = env

    # Compute desired gain at each sample
    # Avoid division by zero in silence
    safe_envelope = np.where(envelope > 1e-7, envelope, 1e-7)

    # Base gain to reach target RMS from envelope
    base_gain = target_rms / safe_envelope

    # Apply compression: above threshold, reduce gain by compression ratio
    # Threshold = target_rms (unity gain point)
    threshold = target_rms
    # Compression: in log domain, reduce excess gain by 1/ratio
    # For signals louder than threshold, the gain is reduced
    base_gain_db = 20.0 * np.log10(np.clip(base_gain, 1e-12, None))
    excess_db = np.maximum(base_gain_db, 0.0)  # only positive gain (louder-than-target)
    compressed_gain_db = base_gain_db - excess_db * (1.0 - 1.0 / config.compression_ratio)
    gain_linear = 10 ** (compressed_gain_db / 20.0)

    # Clamp to max_gain
    gain_linear = np.minimum(gain_linear, max_gain)

    # Apply gain and soft-clip to prevent hard clipping
    output = samples * gain_linear
    output = np.tanh(output)  # Soft saturation

    return AudioBuffer(samples=output, sample_rate=audio.sample_rate)
