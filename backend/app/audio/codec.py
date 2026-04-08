"""BT HFP codec simulation for telephony path testing.

Simulates the bandwidth limiting and quantization distortion introduced by
Bluetooth Hands-Free Profile codecs:
  - CVSD: 8 kHz narrowband, 25-30 dB SNR (original HFP codec)
  - mSBC: 16 kHz wideband, 35-40 dB SNR (HFP v1.6+)
  - none: No codec degradation (passthrough)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from .types import AudioBuffer, FilterSpec
from .filters import FilterChain


class CodecType(str, Enum):
    cvsd = "cvsd"
    msbc = "msbc"
    none = "none"


@dataclass(frozen=True)
class CodecConfig:
    """Configuration for codec simulation.

    Attributes:
        codec_type: Which codec to simulate.
        cvsd_snr_db: Quantization noise floor for CVSD (25-30 dB typical).
        msbc_snr_db: Quantization noise floor for mSBC (35-40 dB typical).
        seed: Random seed for reproducible quantization noise.
    """

    codec_type: CodecType = CodecType.none
    cvsd_snr_db: float = 27.0   # Mid-range of 25-30 dB CVSD spec
    msbc_snr_db: float = 37.0   # Mid-range of 35-40 dB mSBC spec
    seed: int | None = None


def simulate_cvsd(audio: AudioBuffer, config: CodecConfig) -> AudioBuffer:
    """Simulate CVSD (Continuously Variable Slope Delta) codec.

    CVSD is the original BT HFP codec: 8 kHz sample rate, 300-3400 Hz
    bandpass (PSTN telephone band), heavy quantization noise (~25-30 dB SNR).
    """
    # 1. Resample to 8 kHz
    resampled = audio.resample(8000)

    # 2. Bandpass 300-3400 Hz (telephone band)
    bp_chain = FilterChain(
        [
            FilterSpec(filter_type="hpf", frequency=300.0, Q=0.7071),
            FilterSpec(filter_type="lpf", frequency=3400.0, Q=0.7071),
        ],
        sample_rate=8000,
    )
    filtered = bp_chain.apply(resampled)

    # 3. Add quantization noise at target SNR
    filtered = _add_quantization_noise(filtered, config.cvsd_snr_db, config.seed)

    # 4. Resample back to original sample rate
    return filtered.resample(audio.sample_rate)


def simulate_msbc(audio: AudioBuffer, config: CodecConfig) -> AudioBuffer:
    """Simulate mSBC (modified Sub-Band Codec) — HFP wideband audio.

    mSBC is the wideband BT HFP codec: 16 kHz sample rate, 50-7000 Hz
    bandpass, lighter quantization noise (~35-40 dB SNR).
    """
    # 1. Resample to 16 kHz
    resampled = audio.resample(16000)

    # 2. Bandpass 50-7000 Hz (wideband telephone)
    bp_chain = FilterChain(
        [
            FilterSpec(filter_type="hpf", frequency=50.0, Q=0.5),
            FilterSpec(filter_type="lpf", frequency=7000.0, Q=0.7071),
        ],
        sample_rate=16000,
    )
    filtered = bp_chain.apply(resampled)

    # 3. Add quantization noise at target SNR
    filtered = _add_quantization_noise(filtered, config.msbc_snr_db, config.seed)

    # 4. Resample back to original sample rate
    return filtered.resample(audio.sample_rate)


def apply_codec(audio: AudioBuffer, config: CodecConfig) -> AudioBuffer:
    """Apply codec simulation to audio. Dispatcher for all codec types."""
    if config.codec_type == CodecType.cvsd:
        return simulate_cvsd(audio, config)
    elif config.codec_type == CodecType.msbc:
        return simulate_msbc(audio, config)
    else:
        return audio  # CodecType.none — passthrough


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _add_quantization_noise(audio: AudioBuffer, snr_db: float, seed: int | None) -> AudioBuffer:
    """Add white noise to simulate quantization distortion at the given SNR."""
    rng = np.random.default_rng(seed)
    signal_rms = audio.rms
    if signal_rms <= 0:
        return audio
    # Desired noise RMS from SNR: SNR = 20 log10(signal_rms / noise_rms)
    noise_rms = signal_rms / (10 ** (snr_db / 20.0))
    noise = rng.normal(0.0, noise_rms, size=len(audio.samples))
    degraded = audio.samples + noise
    return AudioBuffer(samples=degraded, sample_rate=audio.sample_rate)
