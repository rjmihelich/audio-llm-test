"""Demo script: generate degraded audio samples at various SNR/echo settings.

Usage:
    python scripts/demo_audio.py [input.wav]

If no input WAV is provided, generates a synthetic speech-like tone.
Outputs files to storage/demo/ for listening and inspection.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.audio.types import AudioBuffer, FilterSpec
from backend.app.audio.noise import pink_noise_filtered, white_noise
from backend.app.audio.mixer import mix_at_snr
from backend.app.audio.echo import EchoConfig, EchoPath
from backend.app.audio.io import save_audio, load_audio

OUTPUT_DIR = Path("storage/demo")


def generate_synthetic_speech(duration_s: float = 3.0, sr: int = 16000) -> AudioBuffer:
    """Generate a synthetic signal that exercises the audio pipeline.

    Uses a multi-tone signal with amplitude modulation to simulate
    speech-like dynamics (not actual speech, but good enough to hear
    the effects of noise and echo).
    """
    t = np.arange(int(sr * duration_s)) / sr

    # Fundamental + harmonics (vocal-like)
    signal = (
        0.3 * np.sin(2 * np.pi * 150 * t)   # F0
        + 0.2 * np.sin(2 * np.pi * 300 * t)  # 2nd harmonic
        + 0.1 * np.sin(2 * np.pi * 450 * t)  # 3rd harmonic
        + 0.05 * np.sin(2 * np.pi * 1200 * t)  # Formant-like
    )

    # Amplitude modulation (syllable-like rhythm at ~4 Hz)
    envelope = 0.5 + 0.5 * np.sin(2 * np.pi * 4 * t)
    signal *= envelope

    return AudioBuffer(samples=signal, sample_rate=sr)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load or generate speech
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        print(f"Loading speech from: {input_file}")
        speech = load_audio(input_file, target_sample_rate=16000)
    else:
        print("No input file provided, generating synthetic speech...")
        speech = generate_synthetic_speech()

    sr = speech.sample_rate
    print(f"  Duration: {speech.duration_s:.2f}s, Sample rate: {sr} Hz, RMS: {speech.rms:.4f}")

    # Save clean speech
    save_audio(speech, OUTPUT_DIR / "00_clean.wav")
    print(f"  Saved: {OUTPUT_DIR / '00_clean.wav'}")

    # === Noise demos ===
    print("\n--- Noise at various SNR levels ---")
    noise = pink_noise_filtered(speech.duration_s, lpf_cutoff_hz=100.0, lpf_order=2,
                                 sample_rate=sr, seed=42)

    for snr_db in [20, 10, 5, 0, -5, -10]:
        mixed = mix_at_snr(speech, noise, snr_db)
        filename = f"01_noise_snr_{snr_db:+d}dB.wav"
        save_audio(mixed, OUTPUT_DIR / filename)
        print(f"  SNR {snr_db:+d} dB → {filename}  (RMS: {mixed.rms:.4f})")

    # === White noise comparison ===
    print("\n--- White noise vs pink noise at 0 dB SNR ---")
    white = white_noise(speech.duration_s, sr, seed=42)
    mixed_white = mix_at_snr(speech, white, 0.0)
    save_audio(mixed_white, OUTPUT_DIR / "02_white_noise_0dB.wav")
    print(f"  White noise → 02_white_noise_0dB.wav")

    # === Echo demos ===
    print("\n--- Echo at various delay/gain settings ---")

    # Simulate a previous LLM response (just use the speech itself as the echo source)
    echo_source = speech

    echo_configs = [
        ("03_echo_50ms_-10dB", EchoConfig(delay_ms=50, gain_db=-10)),
        ("04_echo_100ms_-20dB", EchoConfig(delay_ms=100, gain_db=-20)),
        ("05_echo_200ms_-6dB", EchoConfig(delay_ms=200, gain_db=-6)),
        ("06_echo_500ms_-10dB", EchoConfig(delay_ms=500, gain_db=-10)),
    ]

    for filename, cfg in echo_configs:
        echo_path = EchoPath(cfg, sr)
        result = echo_path.apply(speech, echo_source)
        save_audio(result, OUTPUT_DIR / f"{filename}.wav")
        print(f"  Delay {cfg.delay_ms}ms, Gain {cfg.gain_db}dB → {filename}.wav")

    # === Echo with EQ (car cabin simulation) ===
    print("\n--- Echo with car cabin EQ ---")
    cabin_eq = [
        FilterSpec("hpf", 80.0, Q=0.7071),        # Speaker rolloff
        FilterSpec("lpf", 6000.0, Q=0.7071),       # Air absorption
        FilterSpec("peaking", 2500.0, Q=2.0, gain_db=4.0),  # Cabin resonance
    ]
    cfg = EchoConfig(delay_ms=100, gain_db=-10, eq_chain=cabin_eq)
    echo_path = EchoPath(cfg, sr)
    result = echo_path.apply(speech, echo_source)
    save_audio(result, OUTPUT_DIR / "07_echo_cabin_eq.wav")
    print(f"  Cabin EQ (HPF 80Hz + LPF 6kHz + peak 2.5kHz) → 07_echo_cabin_eq.wav")

    # === Combined: noise + echo ===
    print("\n--- Combined: noise + echo ---")
    for snr_db in [10, 0, -5]:
        noisy = mix_at_snr(speech, noise, snr_db)
        cfg = EchoConfig(delay_ms=100, gain_db=-10, eq_chain=cabin_eq)
        echo_path = EchoPath(cfg, sr)
        combined = echo_path.apply(noisy, echo_source)
        filename = f"08_combined_snr_{snr_db:+d}dB.wav"
        save_audio(combined, OUTPUT_DIR / filename)
        print(f"  SNR {snr_db:+d}dB + echo → {filename}")

    print(f"\nAll files saved to: {OUTPUT_DIR.resolve()}")
    print("Open them in any audio player to hear the degradation effects.")


if __name__ == "__main__":
    main()
