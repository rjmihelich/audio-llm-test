"""Full telephony signal chain for automotive BT HFP path simulation.

Composes all telephony processing stages in physically-motivated order,
mirroring what a real Bluetooth hands-free call looks like from the phone
microphone through to the ASR / LLM inference:

  1. Speech level gain      -- adjust speaker amplitude (existing)
  2. Noise mix at SNR       -- road noise, HVAC fan, etc. (existing mixer.py)
  3. Acoustic echo          -- cabin speaker-to-mic feedback (existing echo.py)
  4. AEC residual           -- partial echo removal + NLD artifacts (aec.py)
  5. AGC                    -- gain normalization + pumping (agc.py)
  6. BT codec simulation    -- bandwidth limiting + quantization (codec.py)
  7. Network degradation    -- jitter, packet loss, codec switch (network.py)

The output is a degraded AudioBuffer ready to be fed to an LLM pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import AudioBuffer
from .echo import EchoConfig, EchoPath
from .mixer import mix_at_snr, mix_at_relative_level
from .noise import generate_noise
from .aec import AECResidualConfig, apply_aec_residual
from .agc import AGCConfig, AGC_MILD, apply_agc
from .codec import CodecConfig, CodecType, apply_codec
from .network import NetworkConfig, apply_network_degradation


@dataclass
class TelephonyChainConfig:
    """Aggregate configuration for the full telephony signal chain.

    All sub-configs are optional. Defaults produce minimal degradation so
    that you can selectively enable stages during testing.

    Attributes:
        snr_db: Background noise SNR (dB). None = no noise.
        noise_type: Noise source identifier (matches generate_noise() types).
        noise_file: Path to noise file (for "car_file:<path>" noise_type).
        speech_level_db: Digital gain applied to speech before mixing (dB).
        echo_config: Acoustic echo path parameters. None = no echo.
        aec_config: AEC residual simulation parameters. None = no AEC sim.
        agc_config: AGC parameters. None = no AGC.
        codec_config: BT codec parameters. None = no codec degradation.
        network_config: Network degradation parameters. None = no network impairment.
        interferer: Pre-loaded secondary voice / babble audio. None = no interferer.
        interferer_level_db: Level for interferer relative to speech RMS.
        sample_rate: Target sample rate for processing.
        seed: Base random seed (offsets applied per stage for independence).
    """

    snr_db: float | None = 10.0
    noise_type: str = "pink_lpf"
    noise_file: str | None = None
    speech_level_db: float = 0.0
    echo_config: EchoConfig | None = None
    aec_config: AECResidualConfig | None = None
    agc_config: AGCConfig | None = None
    codec_config: CodecConfig | None = None
    network_config: NetworkConfig | None = None
    interferer: AudioBuffer | None = None
    interferer_level_db: float | None = None
    sample_rate: int = 16000
    seed: int | None = None


@dataclass
class TelephonyChainResult:
    """Intermediate and final outputs from the telephony chain."""

    degraded_audio: AudioBuffer       # Final output after all processing stages
    echo_audio: AudioBuffer | None    # Echo component (before AEC), for metadata
    stages_applied: list[str] = field(default_factory=list)


class TelephonyChain:
    """Executes the full telephony processing chain on a clean speech buffer."""

    def __init__(self, config: TelephonyChainConfig):
        self.config = config

    def process(self, clean_speech: AudioBuffer) -> TelephonyChainResult:
        """Run all telephony stages in physically-motivated order.

        Returns TelephonyChainResult with degraded audio and metadata.
        """
        cfg = self.config
        stages: list[str] = []

        # --- Stage 0: Speech level gain ---
        speech = clean_speech.resample(cfg.sample_rate)
        if cfg.speech_level_db != 0.0:
            import numpy as np
            gain_linear = 10 ** (cfg.speech_level_db / 20.0)
            gained = speech.samples * gain_linear
            gained = np.clip(gained, -1.0, 1.0)
            speech = AudioBuffer(samples=gained, sample_rate=cfg.sample_rate)
            stages.append("speech_level_gain")

        # --- Stage 1: Mix noise at SNR ---
        noise = generate_noise(
            noise_type=cfg.noise_type,
            duration_s=speech.duration_s,
            num_samples=speech.num_samples,
            sample_rate=cfg.sample_rate,
            seed=cfg.seed,
            noise_file=cfg.noise_file,
        )
        if cfg.snr_db is not None:
            mixed = mix_at_snr(speech, noise, cfg.snr_db)
        else:
            mixed = mix_at_snr(speech, noise, None)
        stages.append("noise_mix")

        # --- Stage 1b: Mix interferer (secondary voice / babble) ---
        if cfg.interferer is not None and cfg.interferer_level_db is not None:
            mixed = mix_at_relative_level(mixed, cfg.interferer, cfg.interferer_level_db)
            stages.append("interferer_mix")

        # --- Stage 2: Acoustic echo ---
        echo_audio: AudioBuffer | None = None
        if cfg.echo_config is not None:
            echo_path = EchoPath(cfg.echo_config, cfg.sample_rate)
            # We use speech as the "speaker output" (what the LLM is playing)
            echo_audio = echo_path.process_echo(speech)
            mixed = echo_path.apply(mixed, speech)
            stages.append("acoustic_echo")

        # --- Stage 3: AEC residual ---
        if cfg.aec_config is not None:
            mixed = apply_aec_residual(
                mic_audio=mixed,
                echo_ref=echo_audio,
                config=cfg.aec_config,
            )
            stages.append("aec_residual")

        # --- Stage 4: AGC ---
        if cfg.agc_config is not None:
            mixed = apply_agc(mixed, cfg.agc_config)
            stages.append("agc")

        # --- Stage 5: BT codec simulation ---
        if cfg.codec_config is not None and cfg.codec_config.codec_type != CodecType.none:
            mixed = apply_codec(mixed, cfg.codec_config)
            stages.append(f"codec_{cfg.codec_config.codec_type.value}")

        # --- Stage 6: Network degradation ---
        if cfg.network_config is not None:
            has_loss = cfg.network_config.packet_loss_pct > 0
            has_jitter = cfg.network_config.jitter_ms > 0
            has_switching = cfg.network_config.codec_switching
            if has_loss or has_jitter or has_switching:
                mixed = apply_network_degradation(mixed, cfg.network_config)
                stages.append("network_degradation")

        return TelephonyChainResult(
            degraded_audio=mixed,
            echo_audio=echo_audio,
            stages_applied=stages,
        )
