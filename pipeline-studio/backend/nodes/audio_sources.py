"""Source node executors — speech, noise, audio file."""

from __future__ import annotations

from typing import Any

import numpy as np

from backend.app.audio.types import AudioBuffer
from backend.app.audio.noise import white_noise, pink_noise, pink_noise_filtered, babble_noise
from backend.app.audio.io import load_audio

from ..engine.graph_executor import ExecutionContext, GraphNode


async def execute_speech_source(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Produce clean speech audio from PipelineInput or file."""
    mode = config.get("source_mode", "pipeline_input")

    if mode == "pipeline_input":
        return {"audio_out": ctx.pipeline_input.clean_speech}
    elif mode == "file":
        path = config.get("file_path", "")
        audio = load_audio(path, target_sample_rate=16000)
        return {"audio_out": audio}
    elif mode == "corpus_entry":
        # For corpus entries, we'd need DB access — fall back to pipeline input for now
        return {"audio_out": ctx.pipeline_input.clean_speech}
    else:
        return {"audio_out": ctx.pipeline_input.clean_speech}


async def execute_noise_generator(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Generate noise audio."""
    noise_type = config.get("noise_type", "pink_lpf")
    seed = config.get("seed")
    if seed is not None:
        seed = int(seed)
    sample_rate = 16000

    # Match duration to speech source if available
    duration_s = config.get("duration_s", 0)
    if not duration_s or float(duration_s) <= 0:
        duration_s = len(ctx.pipeline_input.clean_speech.samples) / ctx.pipeline_input.clean_speech.sample_rate
    duration_s = float(duration_s)

    if noise_type == "white":
        audio = white_noise(duration_s, sample_rate=sample_rate, seed=seed)
    elif noise_type == "pink":
        audio = pink_noise(duration_s, sample_rate=sample_rate, seed=seed)
    elif noise_type == "pink_lpf":
        audio = pink_noise_filtered(duration_s, sample_rate=sample_rate, seed=seed)
    elif noise_type == "babble":
        audio = babble_noise(duration_s, sample_rate=sample_rate, seed=seed)
    elif noise_type in ("traffic", "wind"):
        # Use filtered pink noise as approximation
        audio = pink_noise_filtered(duration_s, sample_rate=sample_rate, seed=seed)
    else:
        audio = pink_noise_filtered(duration_s, sample_rate=sample_rate, seed=seed)

    return {"audio_out": audio}


async def execute_audio_file(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Load audio from file."""
    path = config.get("file_path", "")
    if not path:
        raise ValueError("audio_file node: file_path is required")
    audio = load_audio(path, target_sample_rate=16000)
    return {"audio_out": audio}
