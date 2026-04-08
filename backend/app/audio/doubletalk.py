"""Doubletalk detection and metrics for telephony testing.

In a 2-way phone call, "doubletalk" occurs when both the near-end speaker
(person in the car) and the far-end speaker (other caller, playing through
the car speakers) are active simultaneously.  This is the hardest scenario
for AEC: the canceller must suppress the far-end echo without distorting
the near-end speech.

This module provides:
  - Energy-based VAD for detecting speech activity
  - Doubletalk region detection (both speakers active)
  - Metrics:
      doubletalk_ratio   – fraction of near-end active time that overlaps far-end
      erle_singletalk_db – Echo Return Loss Enhancement when only far-end is active
      erle_doubletalk_db – ERLE during doubletalk (typically much worse)
      near_end_distortion_db – how much AEC damages near-end during doubletalk
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .types import AudioBuffer


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DoubletalkConfig:
    """Parameters for doubletalk detection and metric computation.

    Attributes:
        frame_ms: Analysis frame length in ms.
        vad_threshold_db: Energy threshold (dB below peak) for VAD.
            Frames with energy above this relative threshold are "active".
        min_active_frames: Minimum consecutive active frames to count as speech.
    """

    frame_ms: float = 20.0
    vad_threshold_db: float = -40.0
    min_active_frames: int = 3


# ---------------------------------------------------------------------------
# Metrics result
# ---------------------------------------------------------------------------

@dataclass
class DoubletalkMetrics:
    """Computed doubletalk metrics for a single test case."""

    doubletalk_ratio: float          # 0–1: fraction of near-end time overlapping far-end
    near_end_active_ratio: float     # 0–1: fraction of total time near-end is active
    far_end_active_ratio: float      # 0–1: fraction of total time far-end is active
    erle_singletalk_db: float | None  # ERLE when only far-end active (dB, higher = better)
    erle_doubletalk_db: float | None  # ERLE during doubletalk (dB)
    near_end_distortion_db: float | None  # Near-end damage during DT (dB, lower = less damage)
    total_frames: int
    doubletalk_frames: int
    singletalk_far_frames: int       # Frames where only far-end is active

    def to_dict(self) -> dict:
        return {
            "doubletalk_ratio": round(self.doubletalk_ratio, 4),
            "near_end_active_ratio": round(self.near_end_active_ratio, 4),
            "far_end_active_ratio": round(self.far_end_active_ratio, 4),
            "erle_singletalk_db": round(self.erle_singletalk_db, 2) if self.erle_singletalk_db is not None else None,
            "erle_doubletalk_db": round(self.erle_doubletalk_db, 2) if self.erle_doubletalk_db is not None else None,
            "near_end_distortion_db": round(self.near_end_distortion_db, 2) if self.near_end_distortion_db is not None else None,
            "total_frames": self.total_frames,
            "doubletalk_frames": self.doubletalk_frames,
            "singletalk_far_frames": self.singletalk_far_frames,
        }


# ---------------------------------------------------------------------------
# VAD (Voice Activity Detection) — energy-based
# ---------------------------------------------------------------------------

def _frame_energies(samples: np.ndarray, frame_len: int) -> np.ndarray:
    """Compute per-frame RMS energy in dB."""
    n_frames = len(samples) // frame_len
    if n_frames == 0:
        return np.array([])
    # Reshape into frames, compute RMS per frame
    frames = samples[: n_frames * frame_len].reshape(n_frames, frame_len)
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    return 20.0 * np.log10(rms + 1e-12)


def detect_vad(
    samples: np.ndarray,
    sample_rate: int,
    config: DoubletalkConfig,
) -> np.ndarray:
    """Return boolean array (per frame) indicating speech activity.

    Uses energy-based VAD: frames with energy within `vad_threshold_db` of
    the peak energy are considered active.  A minimum run-length filter
    removes isolated spikes.
    """
    frame_len = int(config.frame_ms * sample_rate / 1000.0)
    if frame_len == 0 or len(samples) < frame_len:
        return np.array([], dtype=bool)

    energies = _frame_energies(samples, frame_len)
    if len(energies) == 0:
        return np.array([], dtype=bool)

    peak_energy = np.max(energies)
    threshold = peak_energy + config.vad_threshold_db  # vad_threshold_db is negative
    active = energies >= threshold

    # Minimum run-length filter: require min_active_frames consecutive active
    if config.min_active_frames > 1:
        filtered = np.zeros_like(active)
        run = 0
        for i in range(len(active)):
            if active[i]:
                run += 1
                if run >= config.min_active_frames:
                    # Mark this run as active
                    filtered[i - config.min_active_frames + 1 : i + 1] = True
            else:
                run = 0
        active = filtered

    return active


# ---------------------------------------------------------------------------
# Doubletalk detection
# ---------------------------------------------------------------------------

def detect_doubletalk(
    near_end_vad: np.ndarray,
    far_end_vad: np.ndarray,
) -> np.ndarray:
    """Return boolean array where both near-end and far-end are active."""
    min_len = min(len(near_end_vad), len(far_end_vad))
    return near_end_vad[:min_len] & far_end_vad[:min_len]


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def compute_doubletalk_metrics(
    near_end_clean: AudioBuffer,
    far_end_clean: AudioBuffer,
    mic_signal: AudioBuffer,
    aec_output: AudioBuffer,
    echo_ref: AudioBuffer | None = None,
    config: DoubletalkConfig | None = None,
) -> DoubletalkMetrics:
    """Compute doubletalk metrics from signal chain intermediate signals.

    Args:
        near_end_clean: Clean near-end speech (before any mixing).
        far_end_clean: Clean far-end speech (before echo path).
        mic_signal: Microphone signal (near-end + noise + far-end echo).
        aec_output: Signal after AEC processing.
        echo_ref: The echo component in the mic signal (far-end through
            echo path, before AEC). If provided, used for ERLE computation.
        config: Detection parameters.

    Returns:
        DoubletalkMetrics with all computed values.
    """
    if config is None:
        config = DoubletalkConfig()

    sr = near_end_clean.sample_rate

    # Detect VAD for both speakers
    ne_vad = detect_vad(near_end_clean.samples, sr, config)
    fe_vad = detect_vad(far_end_clean.samples, sr, config)

    # Align lengths (signals may differ slightly due to echo delay padding)
    min_frames = min(len(ne_vad), len(fe_vad))
    if min_frames == 0:
        return DoubletalkMetrics(
            doubletalk_ratio=0.0,
            near_end_active_ratio=0.0,
            far_end_active_ratio=0.0,
            erle_singletalk_db=None,
            erle_doubletalk_db=None,
            near_end_distortion_db=None,
            total_frames=0,
            doubletalk_frames=0,
            singletalk_far_frames=0,
        )

    ne_vad = ne_vad[:min_frames]
    fe_vad = fe_vad[:min_frames]

    dt_mask = ne_vad & fe_vad
    st_far_mask = fe_vad & ~ne_vad  # singletalk far-end only

    total_frames = min_frames
    ne_active = int(np.sum(ne_vad))
    fe_active = int(np.sum(fe_vad))
    dt_frames = int(np.sum(dt_mask))
    st_far_frames = int(np.sum(st_far_mask))

    dt_ratio = dt_frames / ne_active if ne_active > 0 else 0.0

    # --- ERLE computation ---
    # ERLE = 10 * log10(E[echo_ref^2] / E[aec_residual_echo^2])
    # During singletalk-far, the AEC output should ideally be silence (no near-end),
    # so residual = aec_output during those frames.
    frame_len = int(config.frame_ms * sr / 1000.0)
    erle_st: float | None = None
    erle_dt: float | None = None
    ne_distortion: float | None = None

    if echo_ref is not None and frame_len > 0:
        echo_samples = echo_ref.samples
        aec_samples = aec_output.samples
        mic_samples = mic_signal.samples

        # Align all to min length
        sig_len = min(len(echo_samples), len(aec_samples), len(mic_samples))
        max_frame_samples = min_frames * frame_len
        sig_len = min(sig_len, max_frame_samples)

        echo_samples = echo_samples[:sig_len]
        aec_samples = aec_samples[:sig_len]

        def _erle_for_mask(mask: np.ndarray) -> float | None:
            """Compute ERLE over frames indicated by mask."""
            if np.sum(mask) == 0:
                return None
            echo_power = 0.0
            residual_power = 0.0
            for i in range(min(len(mask), sig_len // frame_len)):
                if mask[i]:
                    start = i * frame_len
                    end = min(start + frame_len, sig_len)
                    echo_power += np.sum(echo_samples[start:end] ** 2)
                    residual_power += np.sum(aec_samples[start:end] ** 2)
            if echo_power < 1e-12:
                return None
            if residual_power < 1e-12:
                return 60.0  # Cap at 60 dB (perfect suppression)
            return float(10.0 * np.log10(echo_power / residual_power))

        erle_st = _erle_for_mask(st_far_mask)
        erle_dt = _erle_for_mask(dt_mask)

    # --- Near-end distortion during doubletalk ---
    # Compare clean near-end to AEC output during DT frames.
    # Distortion = 10 * log10(E[error^2] / E[near_end^2])
    # where error = aec_output - near_end_clean (during DT frames only)
    if dt_frames > 0 and frame_len > 0:
        ne_samples = near_end_clean.samples
        aec_samples = aec_output.samples
        sig_len = min(len(ne_samples), len(aec_samples), min_frames * frame_len)

        ne_power = 0.0
        error_power = 0.0
        for i in range(min(len(dt_mask), sig_len // frame_len)):
            if dt_mask[i]:
                start = i * frame_len
                end = min(start + frame_len, sig_len)
                ne_frame = ne_samples[start:end] if start < len(ne_samples) else np.zeros(end - start)
                aec_frame = aec_samples[start:end] if start < len(aec_samples) else np.zeros(end - start)
                # Truncate to same length
                flen = min(len(ne_frame), len(aec_frame))
                ne_frame = ne_frame[:flen]
                aec_frame = aec_frame[:flen]
                ne_power += np.sum(ne_frame ** 2)
                error_power += np.sum((aec_frame - ne_frame) ** 2)

        if ne_power > 1e-12 and error_power > 1e-12:
            ne_distortion = float(10.0 * np.log10(error_power / ne_power))
        elif ne_power > 1e-12:
            ne_distortion = -60.0  # Perfect preservation

    return DoubletalkMetrics(
        doubletalk_ratio=dt_ratio,
        near_end_active_ratio=ne_active / total_frames if total_frames > 0 else 0.0,
        far_end_active_ratio=fe_active / total_frames if total_frames > 0 else 0.0,
        erle_singletalk_db=erle_st,
        erle_doubletalk_db=erle_dt,
        near_end_distortion_db=ne_distortion,
        total_frames=total_frames,
        doubletalk_frames=dt_frames,
        singletalk_far_frames=st_far_frames,
    )


# ---------------------------------------------------------------------------
# Utility: mix near-end and far-end with overlap timing
# ---------------------------------------------------------------------------

def mix_with_overlap(
    near_end: AudioBuffer,
    far_end: AudioBuffer,
    far_end_offset_ms: float = 0.0,
) -> tuple[AudioBuffer, AudioBuffer]:
    """Time-align near-end and far-end speech for 2-way conversation simulation.

    The far-end signal is offset relative to near-end by `far_end_offset_ms`.
    Negative offset = far-end starts before near-end (near-end interrupts).
    Positive offset = far-end starts after near-end.
    Zero = simultaneous start.

    Returns both signals zero-padded to the same total length so they can be
    used in the signal chain (near-end goes to mic, far-end goes to speakers).
    """
    sr = near_end.sample_rate
    if far_end.sample_rate != sr:
        far_end = far_end.resample(sr)

    offset_samples = int(far_end_offset_ms * sr / 1000.0)

    ne_len = near_end.num_samples
    fe_len = far_end.num_samples

    # Compute total duration needed
    if offset_samples >= 0:
        # Far-end starts at offset_samples after near-end
        total_len = max(ne_len, offset_samples + fe_len)
        ne_padded = np.zeros(total_len, dtype=np.float64)
        fe_padded = np.zeros(total_len, dtype=np.float64)
        ne_padded[:ne_len] = near_end.samples
        fe_padded[offset_samples : offset_samples + fe_len] = far_end.samples
    else:
        # Far-end starts before near-end (negative offset)
        abs_offset = abs(offset_samples)
        total_len = max(abs_offset + ne_len, fe_len)
        ne_padded = np.zeros(total_len, dtype=np.float64)
        fe_padded = np.zeros(total_len, dtype=np.float64)
        ne_padded[abs_offset : abs_offset + ne_len] = near_end.samples
        fe_padded[:fe_len] = far_end.samples

    return (
        AudioBuffer(samples=ne_padded, sample_rate=sr),
        AudioBuffer(samples=fe_padded, sample_rate=sr),
    )
