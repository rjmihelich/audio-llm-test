"""Noise generation: road noise, HVAC fan, secondary voice, and file-based noise sources."""

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


def hvac_fan_noise(
    duration_s: float,
    fan_freq_hz: float = 120.0,
    num_harmonics: int = 4,
    tonal_mix: float = 0.4,
    sample_rate: int = 16000,
    seed: int | None = None,
) -> AudioBuffer:
    """Generate HVAC fan noise: tonal blade-pass harmonics + broadband airflow.

    Combines:
    - Tonal component: fan blade-pass frequency and harmonics (simulates
      the periodic whine/hum of a blower motor)
    - Broadband component: band-limited noise (200-2000 Hz) simulating
      turbulent airflow through ducts/vents

    Result is RMS-normalized to 1.0.
    """
    rng = np.random.default_rng(seed)
    num_samples = int(duration_s * sample_rate)
    t = np.arange(num_samples) / sample_rate

    # Tonal component: fundamental + harmonics with slight frequency jitter
    tonal = np.zeros(num_samples, dtype=np.float64)
    for h in range(1, num_harmonics + 1):
        freq = fan_freq_hz * h
        # Random phase and slight amplitude decay for higher harmonics
        phase = rng.uniform(0, 2 * np.pi)
        amplitude = 1.0 / (h ** 0.5)
        # Add slight frequency wobble (fan speed variation)
        wobble = 1.0 + 0.005 * np.sin(2 * np.pi * 0.3 * t + rng.uniform(0, 2 * np.pi))
        tonal += amplitude * np.sin(2 * np.pi * freq * wobble * t + phase)

    # Broadband airflow component: band-limited noise (200-2000 Hz)
    white = rng.standard_normal(num_samples)
    X = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(num_samples, d=1.0 / sample_rate)
    # Band-pass: 200-2000 Hz with smooth rolloff
    bp_mask = np.exp(-0.5 * ((freqs - 800) / 500) ** 2)  # Gaussian centered at 800 Hz
    bp_mask[freqs < 50] = 0
    X *= bp_mask
    broadband = np.fft.irfft(X, n=num_samples)

    # Normalize components individually
    tonal_rms = np.sqrt(np.mean(tonal**2))
    if tonal_rms > 0:
        tonal /= tonal_rms
    broad_rms = np.sqrt(np.mean(broadband**2))
    if broad_rms > 0:
        broadband /= broad_rms

    # Mix tonal + broadband
    mixed = tonal_mix * tonal + (1.0 - tonal_mix) * broadband

    # Normalize to unit RMS
    rms = np.sqrt(np.mean(mixed**2))
    if rms > 0:
        mixed /= rms

    return AudioBuffer(samples=mixed, sample_rate=sample_rate)


def secondary_voice_noise(
    duration_s: float,
    sample_rate: int = 16000,
    seed: int | None = None,
) -> AudioBuffer:
    """Generate a sporadic secondary voice (competing talker) noise.

    Simulates another person speaking intermittently in the background.
    Uses amplitude-modulated formant-like noise with speech-like spectral
    shape and random on/off gating to create a realistic competing talker.

    Result is RMS-normalized to 1.0.
    """
    rng = np.random.default_rng(seed)
    num_samples = int(duration_s * sample_rate)

    # Generate speech-shaped noise (emphasis around formant frequencies)
    white = rng.standard_normal(num_samples)
    X = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(num_samples, d=1.0 / sample_rate)

    # Speech spectral envelope: peaks at typical formant frequencies
    speech_shape = np.zeros_like(freqs)
    formants = [(300, 100), (900, 150), (2200, 200), (3500, 250)]
    for center, width in formants:
        speech_shape += np.exp(-0.5 * ((freqs - center) / width) ** 2)
    # Add overall spectral tilt (speech rolls off at high freq)
    freqs_safe = np.maximum(freqs, 1.0)
    speech_shape *= 1.0 / np.sqrt(freqs_safe / 300.0 + 1.0)
    X *= speech_shape
    voiced = np.fft.irfft(X, n=num_samples)

    # Apply speech-like amplitude modulation (syllable rhythm ~3-5 Hz)
    syllable_rate = rng.uniform(3.0, 5.0)
    envelope = np.abs(np.sin(2 * np.pi * syllable_rate * np.arange(num_samples) / sample_rate))
    envelope = np.power(envelope, 0.5)  # Soften the modulation
    voiced *= envelope

    # Apply sporadic gating: voice is only active 30-60% of the time
    gate = np.zeros(num_samples, dtype=np.float64)
    activity_ratio = rng.uniform(0.3, 0.6)
    # Create random speech bursts (0.5-3 seconds each)
    pos = 0
    while pos < num_samples:
        if rng.random() < activity_ratio:
            # Speaking burst
            burst_len = int(rng.uniform(0.5, 3.0) * sample_rate)
            end = min(pos + burst_len, num_samples)
            # Smooth onset/offset (50ms ramp)
            ramp_len = min(int(0.05 * sample_rate), (end - pos) // 2)
            gate[pos:end] = 1.0
            if ramp_len > 0:
                gate[pos:pos + ramp_len] = np.linspace(0, 1, ramp_len)
                gate[end - ramp_len:end] = np.linspace(1, 0, ramp_len)
            pos = end
        else:
            # Silence gap
            gap_len = int(rng.uniform(0.3, 2.0) * sample_rate)
            pos += gap_len

    voiced *= gate

    # Normalize to unit RMS (over active portions only, then scale full signal)
    rms = np.sqrt(np.mean(voiced**2))
    if rms > 0:
        voiced /= rms

    return AudioBuffer(samples=voiced, sample_rate=sample_rate)


def noise_from_file(
    file_path: Path | str,
    target_num_samples: int,
    target_sample_rate: int = 16000,
    preserve_level: bool = False,
) -> AudioBuffer:
    """Load noise from a WAV file, resample if needed, loop/truncate to target length.

    Args:
        preserve_level: If True, keep the original recorded level (for real car
            recordings that already contain the correct amplitude). If False,
            RMS-normalize to unit RMS for SNR-calibrated mixing.
    """
    audio = load_audio(file_path, target_sample_rate)
    audio = audio.loop_to_length(target_num_samples)

    if preserve_level:
        return audio

    # Normalize to unit RMS
    rms = audio.rms
    if rms > 0:
        return AudioBuffer(samples=audio.samples / rms, sample_rate=audio.sample_rate)
    return audio


def generate_noise(
    noise_type: str,
    duration_s: float,
    num_samples: int,
    sample_rate: int = 16000,
    seed: int | None = None,
    noise_file: str | None = None,
) -> AudioBuffer:
    """Dispatch noise generation by type.

    Centralized function so pipelines don't duplicate the switch logic.
    Returns an RMS-normalized AudioBuffer for synthetic types, or a
    level-preserved AudioBuffer for car noise files.

    Car noise format: "car_file:<path>" — loads the file at its recorded
    level (no RMS normalization). The mixer should add this signal
    directly rather than scaling it to an SNR target.
    """
    if noise_type.startswith("car_file:"):
        # Real car recording — preserve original level
        from backend.app.config import settings
        relative_path = noise_type.split(":", 1)[1]
        car_path = settings.audio_storage_path / relative_path
        return noise_from_file(car_path, num_samples, sample_rate, preserve_level=True)
    elif noise_type in ("road_noise", "pink_lpf"):
        return pink_noise_filtered(
            duration_s, lpf_cutoff_hz=100.0, lpf_order=2,
            sample_rate=sample_rate, seed=seed,
        )
    elif noise_type == "hvac_fan":
        return hvac_fan_noise(duration_s, sample_rate=sample_rate, seed=seed)
    elif noise_type == "secondary_voice":
        return secondary_voice_noise(duration_s, sample_rate=sample_rate, seed=seed)
    elif noise_type == "white":
        return white_noise(duration_s, sample_rate, seed=seed)
    elif noise_type == "pink":
        return pink_noise(duration_s, sample_rate, seed=seed)
    elif noise_type == "babble":
        return babble_noise(duration_s, sample_rate=sample_rate, seed=seed)
    elif noise_type == "silence":
        samples = np.zeros(num_samples, dtype=np.float64)
        return AudioBuffer(samples=samples, sample_rate=sample_rate)
    elif noise_type == "file" and noise_file:
        return noise_from_file(noise_file, num_samples, sample_rate)
    else:
        # Default: road noise
        return pink_noise_filtered(
            duration_s, sample_rate=sample_rate, seed=seed,
        )
