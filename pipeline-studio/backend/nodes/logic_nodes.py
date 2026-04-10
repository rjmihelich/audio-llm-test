"""Logic node executors — routing, switching, and control flow."""

from __future__ import annotations

from typing import Any

import numpy as np

from backend.app.audio.types import AudioBuffer

from ..engine.graph_executor import ExecutionContext, GraphNode


async def execute_router(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Route audio/text to one of N outputs based on a control signal.

    Control input should be a string containing a route index (0, 1, 2, ...).
    Both audio_in and text_in are routed to the matching output index.
    """
    num_routes = int(config.get("num_routes", 2))
    default_route = int(config.get("default_route", 0))
    pass_silence = bool(config.get("pass_silence", False))

    audio_in = inputs.get("audio_in")
    text_in = inputs.get("text_in")
    control = inputs.get("control", "")

    # Parse control signal to route index
    try:
        route = int(str(control).strip())
    except (ValueError, TypeError):
        route = default_route

    # Clamp to valid range
    route = max(0, min(route, num_routes - 1))

    outputs: dict[str, Any] = {"_active_route": route}

    for i in range(num_routes):
        if i == route:
            # Active route gets the signal
            if audio_in is not None:
                outputs[f"audio_out_{i}"] = audio_in
            if text_in is not None:
                outputs[f"text_out_{i}"] = text_in
        elif pass_silence:
            # Inactive routes get silence/empty
            if audio_in is not None and isinstance(audio_in, AudioBuffer):
                outputs[f"audio_out_{i}"] = AudioBuffer(
                    samples=np.zeros_like(audio_in.samples),
                    sample_rate=audio_in.sample_rate,
                )
            if text_in is not None:
                outputs[f"text_out_{i}"] = ""

    return outputs


async def execute_histogram(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Histogram sink — captures the value for frontend accumulation."""
    value = inputs.get("value_in", "")
    return {"_value": str(value).strip()}
