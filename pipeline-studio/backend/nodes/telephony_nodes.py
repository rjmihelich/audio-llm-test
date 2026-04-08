"""Telephony node executors — codec, AEC, AEC residual, AGC, doubletalk metrics."""

from __future__ import annotations

from typing import Any

from backend.app.audio.types import AudioBuffer

from ..engine.graph_executor import ExecutionContext, GraphNode


async def execute_telephony_codec(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Apply Bluetooth codec simulation (CVSD/mSBC)."""
    from backend.app.audio.codec import CodecConfig, CodecType, apply_codec

    audio = inputs.get("audio_in")
    if audio is None:
        raise ValueError("telephony_codec: audio_in is required")

    codec_type_str = config.get("codec_type", "msbc")
    if codec_type_str == "none":
        return {"audio_out": audio}

    codec_type = CodecType(codec_type_str)
    codec_config = CodecConfig(
        codec_type=codec_type,
        cvsd_snr_db=config.get("cvsd_snr_db", 27.0),
        msbc_snr_db=config.get("msbc_snr_db", 37.0),
        seed=config.get("seed"),
    )
    result = apply_codec(audio, codec_config)
    return {"audio_out": result}


async def execute_aec(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Adaptive acoustic echo cancellation (NLMS/RLS/Kalman)."""
    from backend.app.audio.aec_algo import apply_aec

    mic = inputs.get("mic_in")
    ref = inputs.get("ref_in")
    if mic is None:
        raise ValueError("aec: mic_in is required")
    if ref is None:
        raise ValueError("aec: ref_in is required")

    result = apply_aec(
        mic, ref,
        algorithm=config.get("algorithm", "nlms"),
        filter_length_ms=config.get("filter_length_ms", 200),
        step_size=config.get("step_size", 0.1),
        forgetting_factor=config.get("forgetting_factor", 0.999),
        process_noise=config.get("process_noise", 1e-4),
        measurement_noise=config.get("measurement_noise", 0.01),
        regularization=config.get("regularization", 1e-6),
    )
    return {"audio_out": result.output, "echo_est": result.echo_estimate}


async def execute_aec_residual(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Simulate imperfect AEC residual leakage + NLD."""
    from backend.app.audio.aec import AECResidualConfig, apply_aec_residual

    mic = inputs.get("mic_in")
    if mic is None:
        raise ValueError("aec_residual: mic_in is required")

    echo_ref = inputs.get("echo_ref")

    aec_config = AECResidualConfig(
        suppression_db=config.get("suppression_db", -25),
        residual_type=config.get("residual_type", "mixed"),
        nonlinear_distortion=config.get("nonlinear_distortion", 0.3),
        seed=config.get("seed"),
    )

    if echo_ref is not None:
        result = apply_aec_residual(mic, echo_ref, aec_config)
    else:
        # No echo reference — pass through
        result = mic

    return {"audio_out": result}


async def execute_agc(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Automatic gain control with envelope follower."""
    from backend.app.audio.agc import AGCConfig, AGC_AGGRESSIVE, AGC_MILD, AGC_OFF, apply_agc

    audio = inputs.get("audio_in")
    if audio is None:
        raise ValueError("agc: audio_in is required")

    preset = config.get("preset", "mild")
    if preset == "off":
        agc_config = AGC_OFF
    elif preset == "mild":
        agc_config = AGC_MILD
    elif preset == "aggressive":
        agc_config = AGC_AGGRESSIVE
    else:
        agc_config = AGCConfig(
            target_rms_db=config.get("target_rms_db", -18),
            attack_ms=config.get("attack_ms", 50),
            release_ms=config.get("release_ms", 200),
            max_gain_db=config.get("max_gain_db", 30),
            compression_ratio=config.get("compression_ratio", 4.0),
        )

    result = apply_agc(audio, agc_config)
    return {"audio_out": result}


async def execute_doubletalk_metrics(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Compute doubletalk metrics: ERLE, distortion, activity ratios."""
    from backend.app.audio.doubletalk import DoubletalkConfig, compute_doubletalk_metrics

    near_end_clean = inputs.get("near_end_clean")
    if near_end_clean is None:
        raise ValueError("doubletalk_metrics: near_end_clean is required")

    mic_signal = inputs.get("mic_signal")
    if mic_signal is None:
        raise ValueError("doubletalk_metrics: mic_signal is required")

    dt_config = DoubletalkConfig(
        frame_ms=config.get("frame_ms", 20),
        vad_threshold_db=config.get("vad_threshold_db", -40),
    )

    metrics = compute_doubletalk_metrics(
        near_end_clean=near_end_clean,
        far_end_clean=inputs.get("far_end_clean"),
        mic_signal=mic_signal,
        aec_output=inputs.get("aec_output"),
        echo_ref=inputs.get("echo_ref"),
        config=dt_config,
    )

    return {"eval_out": metrics.to_dict() if hasattr(metrics, "to_dict") else vars(metrics)}
