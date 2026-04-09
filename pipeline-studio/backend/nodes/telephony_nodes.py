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


async def execute_far_end_source(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Load far-end caller audio with optional level and offset adjustments."""
    import numpy as np

    audio: AudioBuffer | None = None

    source_mode = config.get("source_mode", "pipeline_input")

    if source_mode == "pipeline_input":
        # Pull from pipeline context (far_end_speech from test case)
        audio = ctx.pipeline_input.get("far_end_speech") if hasattr(ctx, "pipeline_input") and ctx.pipeline_input else None
        if audio is None:
            raise ValueError("far_end_source: no far-end speech in pipeline input")
    elif source_mode == "file":
        import soundfile as sf
        file_path = config.get("file_path", "")
        if not file_path:
            raise ValueError("far_end_source: file_path is required")
        data, sr = sf.read(file_path, dtype="float32")
        if data.ndim > 1:
            data = data[:, 0]
        audio = AudioBuffer(samples=data, sample_rate=sr)
    elif source_mode == "corpus_entry":
        corpus_id = config.get("corpus_entry_id", "")
        if not corpus_id:
            raise ValueError("far_end_source: corpus_entry_id is required")
        from backend.app.config import settings
        import soundfile as sf
        # Look up speech sample file
        from backend.app.models.base import async_session
        from backend.app.models.speech import SpeechSample
        from sqlalchemy import select as sa_select
        import uuid
        async with async_session() as session:
            stmt = sa_select(SpeechSample).where(SpeechSample.id == uuid.UUID(corpus_id))
            row = (await session.execute(stmt)).scalar_one_or_none()
            if not row:
                raise ValueError(f"far_end_source: corpus entry {corpus_id} not found")
            fpath = settings.audio_storage_path / row.file_path
        data, sr = sf.read(str(fpath), dtype="float32")
        if data.ndim > 1:
            data = data[:, 0]
        audio = AudioBuffer(samples=data, sample_rate=sr)

    # Apply level adjustment
    level_db = config.get("level_db", 0.0)
    if level_db != 0.0 and audio is not None:
        gain = 10 ** (level_db / 20.0)
        audio = AudioBuffer(samples=audio.samples * gain, sample_rate=audio.sample_rate)

    # Apply timing offset by zero-padding
    offset_ms = config.get("offset_ms", 0.0)
    if offset_ms != 0.0 and audio is not None:
        offset_samples = int(abs(offset_ms) / 1000.0 * audio.sample_rate)
        if offset_ms < 0:
            # Negative offset: far-end starts first → prepend silence (delay near-end relative)
            # In practice, we pad the *front* so far-end is early
            pass  # No padding needed - the offset is metadata for downstream mixing
        # Store offset as metadata for downstream nodes that do the actual mixing
        # For standalone use, pad with zeros
        if offset_ms > 0:
            # Far-end starts late → prepend silence to far-end
            pad = np.zeros(offset_samples, dtype=np.float32)
            audio = AudioBuffer(
                samples=np.concatenate([pad, audio.samples]),
                sample_rate=audio.sample_rate,
            )
        elif offset_ms < 0:
            # Far-end starts early → append silence (far-end plays first, then near-end catches up)
            pad = np.zeros(offset_samples, dtype=np.float32)
            audio = AudioBuffer(
                samples=np.concatenate([audio.samples, pad]),
                sample_rate=audio.sample_rate,
            )

    return {"audio_out": audio}


async def execute_telephony_judge(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """LLM-based telephony quality evaluation with multi-judge majority voting."""
    from backend.app.evaluation.telephony_judge import (
        TelephonyJudgeEvaluator,
        TelephonyJudgeMode,
    )
    from backend.app.execution.worker import _init_backend
    from backend.app.pipeline.base import PipelineInput, PipelineResult

    # Resolve judge LLM backend
    judge_backend_str = config.get("judge_backend", "openai:gpt-4o-audio-preview")
    judge_backend = _init_backend(judge_backend_str)

    # Resolve modes
    modes_str = config.get("modes", "auto")
    modes: list[TelephonyJudgeMode] | None = None
    if modes_str == "all":
        modes = list(TelephonyJudgeMode)
    elif modes_str != "auto":
        modes = [TelephonyJudgeMode(modes_str)]
    # None = auto-detect

    evaluator = TelephonyJudgeEvaluator(
        judge_backend=judge_backend,
        modes=modes,
        num_judges=config.get("num_judges", 3),
        pass_threshold=config.get("pass_threshold", 0.6),
    )

    # Build PipelineInput / PipelineResult from available inputs
    text_response = inputs.get("text_in", "")
    audio_in = inputs.get("audio_in")
    near_end_ref = inputs.get("near_end_ref")
    far_end_ref = inputs.get("far_end_ref")

    # Construct PipelineInput with available audio references
    # PipelineInput requires clean_speech, original_text, expected_intent
    clean_speech = near_end_ref or audio_in
    if clean_speech is None:
        # Create a silent placeholder if no audio provided
        import numpy as np
        clean_speech = AudioBuffer(samples=np.zeros(16000, dtype=np.float32), sample_rate=16000)

    pipeline_input = PipelineInput(
        clean_speech=clean_speech,
        original_text="",
        expected_intent="",
        far_end_speech=far_end_ref,
    )

    pipeline_result = PipelineResult(
        degraded_audio=audio_in,
        llm_response=None,
    )
    # Attach transcription text if available
    if text_response:
        from backend.app.llm.base import Transcription
        pipeline_result.transcription = Transcription(
            text=text_response if isinstance(text_response, str) else str(text_response),
        )

    result = await evaluator.evaluate(pipeline_input, pipeline_result)

    # Serialize result
    eval_data = result.to_dict() if hasattr(result, "to_dict") else vars(result)
    return {"eval_out": eval_data}
