"""Network degradation simulation for telephony path testing.

Models impairments that occur on the wireless/packet network path between
the phone and the Bluetooth hands-free unit:
  - Packet loss (random or bursty Gilbert-Elliott model)
  - Jitter (variable delay with interpolation)
  - Mid-call codec switching (CVSD ↔ mSBC transitions)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from .types import AudioBuffer


class PacketLossPattern(str, Enum):
    random = "random"   # Independent random frame losses (Bernoulli model)
    burst = "burst"     # Bursty losses (Gilbert-Elliott model)


@dataclass(frozen=True)
class NetworkConfig:
    """Configuration for network degradation simulation.

    Attributes:
        packet_loss_pct: Mean packet loss rate [0.0, 100.0].
        packet_loss_pattern: Distribution of losses — random or bursty.
        burst_length_ms: Mean burst duration for Gilbert-Elliott model (ms).
            Only used when packet_loss_pattern == "burst".
        jitter_ms: Maximum jitter offset (±jitter_ms/2) per frame (ms).
        codec_switching: If True, simulate a mid-call CVSD↔mSBC transition.
        seed: Random seed for reproducibility.
    """

    packet_loss_pct: float = 0.0
    packet_loss_pattern: PacketLossPattern = PacketLossPattern.random
    burst_length_ms: float = 80.0
    jitter_ms: float = 0.0
    codec_switching: bool = False
    seed: int | None = None

    def __post_init__(self):
        if not (0.0 <= self.packet_loss_pct <= 100.0):
            raise ValueError(f"packet_loss_pct must be 0-100, got {self.packet_loss_pct}")
        if self.jitter_ms < 0:
            raise ValueError(f"jitter_ms must be >= 0, got {self.jitter_ms}")


# Frame size for packet-based processing (20ms — standard RTP/HFP frame)
_FRAME_MS = 20


def apply_packet_loss(audio: AudioBuffer, config: NetworkConfig) -> AudioBuffer:
    """Apply packet loss by zeroing out dropped 20ms frames.

    Uses the Gilbert-Elliott two-state Markov model for burst mode:
      - Good state G: low loss probability (p_loss_good ≈ 0)
      - Bad state B: high loss probability (p_loss_bad ≈ 1)
    Transition probabilities derived from packet_loss_pct and burst_length_ms.

    In random mode, each frame is lost independently with probability
    packet_loss_pct/100.
    """
    if config.packet_loss_pct <= 0:
        return audio

    sr = audio.sample_rate
    frame_samples = int(_FRAME_MS * sr / 1000.0)
    samples = audio.samples.copy()
    n_frames = max(len(samples) // frame_samples, 1)

    loss_prob = config.packet_loss_pct / 100.0
    rng = np.random.default_rng(config.seed)

    if config.packet_loss_pattern == PacketLossPattern.random:
        lost_mask = rng.random(n_frames) < loss_prob
    else:
        # Gilbert-Elliott model
        # Mean burst length B: once in bad state, average B frames lost
        mean_burst_frames = max(config.burst_length_ms / _FRAME_MS, 1.0)
        # Transition out of bad state: p_gb = 1/B
        p_gb = 1.0 / mean_burst_frames
        # Overall loss rate: π_B = loss_prob = p_bg / (p_bg + p_gb)
        # → p_bg = loss_prob * p_gb / (1 - loss_prob)
        if loss_prob >= 1.0:
            p_bg = 1.0
        else:
            p_bg = loss_prob * p_gb / (1.0 - loss_prob)

        # Simulate Markov chain states (0=good, 1=bad)
        state = 0  # Start in good state
        lost_mask = np.zeros(n_frames, dtype=bool)
        for i in range(n_frames):
            if state == 0:
                if rng.random() < p_bg:
                    state = 1
            else:
                lost_mask[i] = True
                if rng.random() < p_gb:
                    state = 0

    # Zero out lost frames
    for i, lost in enumerate(lost_mask):
        if lost:
            start = i * frame_samples
            end = min(start + frame_samples, len(samples))
            samples[start:end] = 0.0

    return AudioBuffer(samples=samples, sample_rate=audio.sample_rate)


def apply_jitter(audio: AudioBuffer, config: NetworkConfig) -> AudioBuffer:
    """Apply random frame jitter with linear interpolation.

    Each 20ms frame is shifted by a random offset in [-jitter_ms/2, +jitter_ms/2],
    then the signal is reconstructed via interpolation to maintain continuity.
    """
    if config.jitter_ms <= 0:
        return audio

    sr = audio.sample_rate
    frame_samples = int(_FRAME_MS * sr / 1000.0)
    max_shift_samples = int(config.jitter_ms / 2 * sr / 1000.0)

    samples = audio.samples.copy()
    n_frames = len(samples) // frame_samples
    rng = np.random.default_rng(config.seed)

    output = np.zeros_like(samples)
    for i in range(n_frames):
        shift = int(rng.integers(-max_shift_samples, max_shift_samples + 1))
        src_start = i * frame_samples
        src_end = src_start + frame_samples
        dst_start = max(0, src_start + shift)
        dst_end = min(len(output), src_end + shift)
        if dst_start >= dst_end:
            continue
        copy_len = dst_end - dst_start
        output[dst_start:dst_end] = samples[src_start: src_start + copy_len]

    return AudioBuffer(samples=output, sample_rate=audio.sample_rate)


def apply_codec_switching(audio: AudioBuffer, config: NetworkConfig) -> AudioBuffer:
    """Simulate a mid-call codec switch from CVSD to mSBC (or vice versa).

    Creates an audible transition artifact near the midpoint of the audio:
    the first half is processed with CVSD degradation, the second half with
    mSBC degradation, with a brief (40ms) crossfade at the boundary.
    """
    if not config.codec_switching:
        return audio

    from .codec import CodecConfig, CodecType, simulate_cvsd, simulate_msbc

    mid = len(audio.samples) // 2
    xfade = int(0.04 * audio.sample_rate)  # 40ms crossfade

    cvsd_cfg = CodecConfig(codec_type=CodecType.cvsd, seed=config.seed)
    msbc_cfg = CodecConfig(codec_type=CodecType.msbc, seed=config.seed)

    cvsd_audio = simulate_cvsd(audio, cvsd_cfg)
    msbc_audio = simulate_msbc(audio, msbc_cfg)

    output = audio.samples.copy()
    # First half: CVSD
    output[:mid] = cvsd_audio.samples[:mid]
    # Crossfade region
    xfade_start = max(0, mid - xfade // 2)
    xfade_end = min(len(output), mid + xfade // 2)
    xlen = xfade_end - xfade_start
    if xlen > 0:
        fade_out = np.linspace(1.0, 0.0, xlen)
        fade_in = np.linspace(0.0, 1.0, xlen)
        output[xfade_start:xfade_end] = (
            cvsd_audio.samples[xfade_start:xfade_end] * fade_out
            + msbc_audio.samples[xfade_start:xfade_end] * fade_in
        )
    # Second half: mSBC
    output[xfade_end:] = msbc_audio.samples[xfade_end:]

    return AudioBuffer(samples=output, sample_rate=audio.sample_rate)


def apply_network_degradation(audio: AudioBuffer, config: NetworkConfig) -> AudioBuffer:
    """Apply all network degradation steps in sequence.

    Order: packet loss → jitter → codec switching.
    Codec switching is applied last so its boundary artifacts are not
    disrupted by frame zeroing.
    """
    audio = apply_packet_loss(audio, config)
    audio = apply_jitter(audio, config)
    audio = apply_codec_switching(audio, config)
    return audio
