"""DSP node executors — noise reduction, sample rate conversion, time delay."""

from __future__ import annotations

from typing import Any

import numpy as np

from backend.app.audio.types import AudioBuffer

from ..engine.graph_executor import ExecutionContext, GraphNode


async def execute_noise_reduction(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Noise suppression via spectral subtraction or Wiener filter."""
    from backend.app.audio.noise_reduction import apply_noise_reduction

    audio = inputs.get("audio_in")
    if audio is None:
        raise ValueError("noise_reduction: audio_in is required")

    noise_ref = inputs.get("noise_ref")  # optional

    result = apply_noise_reduction(
        audio,
        method=config.get("method", "spectral_subtraction"),
        noise_ref=noise_ref,
        suppression_db=config.get("suppression_db", 12.0),
        noise_floor_db=config.get("noise_floor_db", -60.0),
        smoothing_factor=config.get("smoothing_factor", 0.9),
    )
    return {"audio_out": result}


async def execute_sample_rate_converter(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Polyphase sample rate conversion."""
    audio = inputs.get("audio_in")
    if audio is None:
        raise ValueError("sample_rate_converter: audio_in is required")

    target_sr = int(config.get("target_sample_rate", 16000))
    if audio.sample_rate == target_sr:
        return {"audio_out": audio}

    result = audio.resample(target_sr)
    return {"audio_out": result}


async def execute_time_delay(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Standalone delay line."""
    audio = inputs.get("audio_in")
    if audio is None:
        raise ValueError("time_delay: audio_in is required")

    delay_ms = config.get("delay_ms", 0)
    if delay_ms <= 0:
        return {"audio_out": audio}

    delay_samples = int(delay_ms * audio.sample_rate / 1000)
    pad_mode = config.get("pad_mode", "zero")

    samples = audio.samples
    if pad_mode == "zero":
        # Zero-pad at the start, extending total length
        delayed = np.concatenate([np.zeros(delay_samples, dtype=samples.dtype), samples])
    else:
        # Truncate: maintain original length, drop the tail
        delayed = np.zeros_like(samples)
        if delay_samples < len(samples):
            delayed[delay_samples:] = samples[:len(samples) - delay_samples]

    return {"audio_out": AudioBuffer(samples=delayed, sample_rate=audio.sample_rate)}
