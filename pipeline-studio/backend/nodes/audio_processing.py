"""Audio processing node executors — mixer, echo, EQ, gain, pre/post-process, buffer."""

from __future__ import annotations

from typing import Any

import numpy as np

from backend.app.audio.types import AudioBuffer
from backend.app.audio.mixer import mix_at_snr, mix_signals
from backend.app.audio.echo import EchoConfig, EchoPath
from backend.app.audio.filters import FilterSpec, FilterChain

from ..engine.graph_executor import ExecutionContext, GraphNode


async def execute_mixer(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Mix N audio inputs with per-channel gain and master output."""
    master_gain_db = float(config.get("master_gain_db", 0))

    # Collect audio inputs
    audio_inputs = inputs.get("_audio_inputs", [])
    if not audio_inputs:
        # Try explicit inputs
        for key in sorted(inputs.keys()):
            if key.startswith("audio_in") and isinstance(inputs[key], AudioBuffer):
                audio_inputs.append(inputs[key])

    if not audio_inputs:
        raise ValueError("Mixer node: no audio inputs connected")

    if len(audio_inputs) == 1:
        gain_db = float(config.get("gain_0_db", 0)) + master_gain_db
        if gain_db != 0:
            gain_linear = 10 ** (gain_db / 20.0)
            return {"audio_out": AudioBuffer(
                samples=audio_inputs[0].samples * gain_linear,
                sample_rate=audio_inputs[0].sample_rate,
            )}
        return {"audio_out": audio_inputs[0]}

    # Build per-channel gain list from config
    gains_db = []
    for i in range(len(audio_inputs)):
        g = float(config.get(f"gain_{i}_db", 0))
        gains_db.append(g + master_gain_db)

    mixed = mix_signals(audio_inputs, gains_db)
    return {"audio_out": mixed}


async def execute_echo_simulator(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Simulate acoustic echo path."""
    mic_audio = inputs.get("mic_in")
    speaker_audio = inputs.get("speaker_in")

    if mic_audio is None:
        raise ValueError("Echo simulator: mic_in is required")

    delay_ms = config.get("delay_ms", 100)
    gain_db = config.get("gain_db", -6)
    eq_config_raw = config.get("eq_config", [])

    eq_specs = []
    for eq in (eq_config_raw or []):
        if isinstance(eq, dict):
            eq_specs.append(FilterSpec(**eq))

    echo_config = EchoConfig(
        delay_ms=delay_ms,
        gain_db=gain_db,
        eq_chain=eq_specs,
    )
    echo_path = EchoPath(echo_config)

    if speaker_audio is not None and isinstance(speaker_audio, AudioBuffer):
        # Apply echo from speaker to mic
        echo_signal = echo_path.apply(speaker_audio)
        # Mix echo into mic signal
        mixed_samples = mic_audio.samples + echo_signal.samples[:len(mic_audio.samples)]
        # Soft clip
        mixed_samples = np.tanh(mixed_samples)
        result = AudioBuffer(samples=mixed_samples, sample_rate=mic_audio.sample_rate)
    else:
        # No speaker input — pass through (first pass, no echo yet)
        result = mic_audio

    return {"audio_out": result}


async def execute_eq_filter(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Apply biquad filter chain."""
    audio = inputs.get("audio_in")
    if audio is None:
        raise ValueError("EQ filter: audio_in is required")

    filters_raw = config.get("filters", [])
    if not filters_raw:
        return {"audio_out": audio}

    specs = [FilterSpec(**f) if isinstance(f, dict) else f for f in filters_raw]
    chain = FilterChain(specs)
    filtered = chain.apply(audio)
    return {"audio_out": filtered}


async def execute_gain(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Simple volume adjustment."""
    audio = inputs.get("audio_in")
    if audio is None:
        raise ValueError("Gain: audio_in is required")

    gain_db = config.get("gain_db", 0)
    gain_linear = 10 ** (gain_db / 20)
    adjusted = AudioBuffer(
        samples=audio.samples * gain_linear,
        sample_rate=audio.sample_rate,
    )
    return {"audio_out": adjusted}


async def execute_audio_preprocess(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Audio pre-processing: AGC, noise gate."""
    audio = inputs.get("audio_in")
    if audio is None:
        raise ValueError("Audio preprocess: audio_in is required")

    samples = audio.samples.copy()

    # AGC
    if config.get("enable_agc", True):
        target_db = config.get("agc_target_db", -3)
        target_linear = 10 ** (target_db / 20)
        rms = np.sqrt(np.mean(samples ** 2))
        if rms > 1e-10:
            gain = target_linear / rms
            samples = samples * gain

    # Noise gate
    if config.get("enable_noise_gate", False):
        threshold_db = config.get("noise_gate_threshold_db", -40)
        threshold_linear = 10 ** (threshold_db / 20)
        envelope = np.abs(samples)
        # Simple gate: zero out samples below threshold
        samples[envelope < threshold_linear] = 0.0

    # Soft clip to prevent overflow
    samples = np.clip(samples, -1.0, 1.0)

    return {"audio_out": AudioBuffer(samples=samples, sample_rate=audio.sample_rate)}


async def execute_audio_postprocess(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Audio post-processing: normalization, limiting."""
    audio = inputs.get("audio_in")
    if audio is None:
        raise ValueError("Audio postprocess: audio_in is required")

    samples = audio.samples.copy()

    # Normalize
    if config.get("normalize", True):
        target_db = config.get("normalize_target_db", -1)
        target_linear = 10 ** (target_db / 20)
        peak = np.max(np.abs(samples))
        if peak > 1e-10:
            samples = samples * (target_linear / peak)

    # Limiter
    if config.get("enable_limiter", True):
        threshold_db = config.get("limiter_threshold_db", -1)
        threshold = 10 ** (threshold_db / 20)
        samples = np.where(
            np.abs(samples) > threshold,
            np.sign(samples) * (threshold + np.tanh(np.abs(samples) - threshold) * (1 - threshold)),
            samples,
        )

    return {"audio_out": AudioBuffer(samples=samples, sample_rate=audio.sample_rate)}


async def execute_audio_buffer(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Buffer audio into chunks (for streaming simulation).

    In batch mode this is essentially a pass-through, but it records
    the chunk configuration for downstream realtime nodes.
    """
    audio = inputs.get("audio_in")
    if audio is None:
        raise ValueError("Audio buffer: audio_in is required")

    chunk_ms = config.get("chunk_ms", 20)

    # Store chunk config in context metadata for downstream use
    ctx.metadata["chunk_ms"] = chunk_ms
    ctx.metadata["overlap_ms"] = config.get("overlap_ms", 0)

    return {"audio_out": audio}
