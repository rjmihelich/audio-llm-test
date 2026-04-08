"""Full telephony signal chain for automotive BT HFP path simulation.

Models a complete 2-way phone conversation in a car cabin:

  UPLINK (near-end → network → far-end listener / LLM):
    1. Near-end speech level gain     -- whisper vs. normal vs. shout
    2. Cabin noise mix                -- road noise, HVAC, etc.
    3. Far-end echo via car speakers  -- far-end speech through echo path into mic
    4. AEC residual                   -- imperfect echo cancellation + NLD artifacts
    5. AGC                            -- gain normalization + pumping
    6. BT codec (encode)              -- CVSD / mSBC bandwidth limiting + quant noise
    7. Network degradation            -- jitter, packet loss, codec switching

  DOWNLINK (far-end → network → car speaker → occupant):
    1. BT codec (encode/decode)       -- codec degradation on far-end speech
    2. Network degradation            -- same impairments as uplink

  DOUBLETALK:
    When far_end_speech is provided, both speakers are active.  The overlap
    timing is controlled by far_end_offset_ms.  Signal-level doubletalk
    metrics (ERLE, near-end distortion, DT ratio) are computed automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .types import AudioBuffer
from .echo import EchoConfig, EchoPath
from .mixer import mix_with_gain, mix_at_relative_level
from .noise import generate_noise
from .aec import AECResidualConfig, apply_aec_residual
from .agc import AGCConfig, AGC_MILD, apply_agc
from .codec import CodecConfig, CodecType, apply_codec
from .network import NetworkConfig, apply_network_degradation
from .doubletalk import (
    DoubletalkConfig,
    DoubletalkMetrics,
    compute_doubletalk_metrics,
    mix_with_overlap,
)


@dataclass
class TelephonyChainConfig:
    """Aggregate configuration for the full telephony signal chain.

    Attributes:
        noise_level_db: Gain applied to noise in dB. 0 = natural level.
        noise_type: Noise source identifier (matches generate_noise() types).
        noise_file: Path to noise file (for "car_file:<path>" noise_type).
        speech_level_db: Digital gain applied to near-end speech before mixing (dB).
        echo_config: Acoustic echo path parameters. None = no echo.
        aec_config: AEC residual simulation parameters. None = no AEC sim.
        agc_config: AGC parameters. None = no AGC.
        codec_config: BT codec parameters. None = no codec degradation.
        network_config: Network degradation parameters. None = no network impairment.
        interferer: Pre-loaded secondary voice / babble audio. None = no interferer.
        interferer_level_db: Level for interferer relative to speech RMS.
        far_end_speech: Far-end caller's audio (played through car speakers).
            When provided, this is used as the echo source instead of near-end speech.
        far_end_speech_level_db: Digital gain on far-end speech (dB). 0 = original.
        far_end_offset_ms: Timing offset for far-end relative to near-end.
            Negative = far-end starts first (near-end interrupts).
            Positive = far-end starts after near-end.
            Zero = simultaneous start.
        compute_doubletalk_metrics: Whether to compute DT signal metrics.
        sample_rate: Target sample rate for processing.
        seed: Base random seed (offsets applied per stage for independence).
    """

    noise_level_db: float = 0.0
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
    far_end_speech: AudioBuffer | None = None
    far_end_speech_level_db: float = 0.0
    far_end_offset_ms: float = 0.0
    compute_doubletalk_metrics: bool = True
    sample_rate: int = 16000
    seed: int | None = None


@dataclass
class TelephonyChainResult:
    """Intermediate and final outputs from the telephony chain."""

    # Uplink: degraded near-end audio after full chain (what the LLM receives)
    degraded_audio: AudioBuffer

    # Downlink: degraded far-end audio after codec + network (what car occupant hears)
    downlink_audio: AudioBuffer | None = None

    # Echo component (before AEC), for metadata / evaluation
    echo_audio: AudioBuffer | None = None

    # Clean reference signals (for metric computation)
    near_end_clean: AudioBuffer | None = None   # Near-end after level gain, before mixing
    far_end_clean: AudioBuffer | None = None     # Far-end after level gain

    # Signal after AEC (before AGC/codec), for DT metric reference
    aec_output: AudioBuffer | None = None

    # Mic signal before AEC (near-end + noise + echo), for DT metric reference
    mic_signal: AudioBuffer | None = None

    # Doubletalk signal-level metrics
    doubletalk_metrics: DoubletalkMetrics | None = None

    # Processing metadata
    stages_applied: list[str] = field(default_factory=list)
    has_far_end: bool = False
    far_end_offset_ms: float = 0.0


class TelephonyChain:
    """Executes the full telephony processing chain for 2-way phone call simulation."""

    def __init__(self, config: TelephonyChainConfig):
        self.config = config

    def process(self, clean_speech: AudioBuffer) -> TelephonyChainResult:
        """Run all telephony stages in physically-motivated order.

        Args:
            clean_speech: The near-end speech (person in the car).

        Returns:
            TelephonyChainResult with uplink audio, downlink audio, and metrics.
        """
        cfg = self.config
        stages: list[str] = []
        has_far_end = cfg.far_end_speech is not None

        # --- Stage 0: Resample and apply speech level gains ---
        near_end = clean_speech.resample(cfg.sample_rate)
        if cfg.speech_level_db != 0.0:
            gain_linear = 10 ** (cfg.speech_level_db / 20.0)
            gained = near_end.samples * gain_linear
            gained = np.clip(gained, -1.0, 1.0)
            near_end = AudioBuffer(samples=gained, sample_rate=cfg.sample_rate)
            stages.append("speech_level_gain")

        # Prepare far-end speech if provided
        far_end: AudioBuffer | None = None
        if has_far_end:
            far_end = cfg.far_end_speech.resample(cfg.sample_rate)
            if cfg.far_end_speech_level_db != 0.0:
                fe_gain = 10 ** (cfg.far_end_speech_level_db / 20.0)
                fe_gained = far_end.samples * fe_gain
                fe_gained = np.clip(fe_gained, -1.0, 1.0)
                far_end = AudioBuffer(samples=fe_gained, sample_rate=cfg.sample_rate)
                stages.append("far_end_level_gain")

            # Time-align near-end and far-end with overlap offset
            if cfg.far_end_offset_ms != 0.0:
                near_end, far_end = mix_with_overlap(
                    near_end, far_end, cfg.far_end_offset_ms
                )
                stages.append("far_end_overlap_align")

        # Save clean references for doubletalk metrics
        near_end_clean = AudioBuffer(
            samples=near_end.samples.copy(), sample_rate=cfg.sample_rate
        )
        far_end_clean = (
            AudioBuffer(samples=far_end.samples.copy(), sample_rate=cfg.sample_rate)
            if far_end is not None
            else None
        )

        # --- Stage 1: Mix cabin noise ---
        noise = generate_noise(
            noise_type=cfg.noise_type,
            duration_s=near_end.duration_s,
            num_samples=near_end.num_samples,
            sample_rate=cfg.sample_rate,
            seed=cfg.seed,
            noise_file=cfg.noise_file,
        )
        mixed = mix_with_gain(near_end, noise, cfg.noise_level_db)
        stages.append("noise_mix")

        # --- Stage 1b: Mix interferer (secondary voice / babble) ---
        if cfg.interferer is not None and cfg.interferer_level_db is not None:
            mixed = mix_at_relative_level(mixed, cfg.interferer, cfg.interferer_level_db)
            stages.append("interferer_mix")

        # --- Stage 2: Acoustic echo from far-end through car speakers ---
        echo_audio: AudioBuffer | None = None
        if cfg.echo_config is not None:
            echo_path = EchoPath(cfg.echo_config, cfg.sample_rate)
            # Echo SOURCE = far-end speech (what plays through the car speakers)
            # If no far-end speech, fall back to near-end (legacy behavior)
            echo_source = far_end if far_end is not None else near_end
            echo_audio = echo_path.process_echo(echo_source)
            mixed = echo_path.apply(mixed, echo_source)
            stages.append("acoustic_echo")

        # Save mic signal (before AEC) for doubletalk metrics
        mic_signal = AudioBuffer(
            samples=mixed.samples.copy(), sample_rate=cfg.sample_rate
        )

        # --- Stage 3: AEC residual ---
        if cfg.aec_config is not None:
            mixed = apply_aec_residual(
                mic_audio=mixed,
                echo_ref=echo_audio,
                config=cfg.aec_config,
            )
            stages.append("aec_residual")

        # Save AEC output for doubletalk metrics (before AGC/codec alter it further)
        aec_output = AudioBuffer(
            samples=mixed.samples.copy(), sample_rate=cfg.sample_rate
        )

        # --- Stage 4: AGC ---
        if cfg.agc_config is not None:
            mixed = apply_agc(mixed, cfg.agc_config)
            stages.append("agc")

        # --- Stage 5: BT codec simulation (uplink encode) ---
        if cfg.codec_config is not None and cfg.codec_config.codec_type != CodecType.none:
            mixed = apply_codec(mixed, cfg.codec_config)
            stages.append(f"codec_{cfg.codec_config.codec_type.value}")

        # --- Stage 6: Network degradation (uplink) ---
        if cfg.network_config is not None:
            has_loss = cfg.network_config.packet_loss_pct > 0
            has_jitter = cfg.network_config.jitter_ms > 0
            has_switching = cfg.network_config.codec_switching
            if has_loss or has_jitter or has_switching:
                mixed = apply_network_degradation(mixed, cfg.network_config)
                stages.append("network_degradation")

        # --- Downlink path: far-end → codec → network → car speaker ---
        downlink_audio: AudioBuffer | None = None
        if far_end is not None:
            downlink = far_end
            # Apply codec to downlink (same codec for both directions in BT HFP)
            if cfg.codec_config is not None and cfg.codec_config.codec_type != CodecType.none:
                downlink = apply_codec(downlink, cfg.codec_config)
                stages.append("downlink_codec")
            # Apply network degradation to downlink
            if cfg.network_config is not None:
                has_loss = cfg.network_config.packet_loss_pct > 0
                has_jitter = cfg.network_config.jitter_ms > 0
                has_switching = cfg.network_config.codec_switching
                if has_loss or has_jitter or has_switching:
                    # Use a different seed for downlink to get independent impairments
                    dl_net_cfg = NetworkConfig(
                        packet_loss_pct=cfg.network_config.packet_loss_pct,
                        packet_loss_pattern=cfg.network_config.packet_loss_pattern,
                        burst_length_ms=cfg.network_config.burst_length_ms,
                        jitter_ms=cfg.network_config.jitter_ms,
                        codec_switching=cfg.network_config.codec_switching,
                        seed=(cfg.network_config.seed + 1000) if cfg.network_config.seed else None,
                    )
                    downlink = apply_network_degradation(downlink, dl_net_cfg)
                    stages.append("downlink_network")
            downlink_audio = downlink

        # --- Doubletalk metrics ---
        dt_metrics: DoubletalkMetrics | None = None
        if has_far_end and far_end_clean is not None and cfg.compute_doubletalk_metrics:
            try:
                dt_metrics = compute_doubletalk_metrics(
                    near_end_clean=near_end_clean,
                    far_end_clean=far_end_clean,
                    mic_signal=mic_signal,
                    aec_output=aec_output,
                    echo_ref=echo_audio,
                )
                stages.append("doubletalk_metrics")
            except Exception:
                pass  # Don't fail the chain if metrics computation errors

        return TelephonyChainResult(
            degraded_audio=mixed,
            downlink_audio=downlink_audio,
            echo_audio=echo_audio,
            near_end_clean=near_end_clean,
            far_end_clean=far_end_clean,
            aec_output=aec_output,
            mic_signal=mic_signal,
            doubletalk_metrics=dt_metrics,
            stages_applied=stages,
            has_far_end=has_far_end,
            far_end_offset_ms=cfg.far_end_offset_ms,
        )
