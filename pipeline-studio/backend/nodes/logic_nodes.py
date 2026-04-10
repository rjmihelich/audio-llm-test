"""Logic node executors — routing, switching, and control flow."""

from __future__ import annotations

import re
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


# ---------------------------------------------------------------------------
# Triage classifier — keyword/regex binary classifier for vehicle commands
# ---------------------------------------------------------------------------

_VEHICLE_PATTERNS = [
    r"\b(temperature|ac|a/c|air conditioning|heater|heat|defrost|defroster|fan speed|climate|warmer|cooler|colder)\b",
    r"\b(window|windows|sunroof)\b",
    r"\b(seat|seats|heated seat|seat warmer|recline)\b",
    r"\b(mirror|mirrors)\b",
    r"\b(wiper|wipers|windshield wiper)\b",
    r"\b(headlight|headlights|high beam|high beams|interior light|interior lights|fog light|dome light)\b",
    r"\b(lock|unlock|tailgate|trunk|hood)\b",
    r"\b(honk|horn)\b",
    r"\b(start the engine|stop the engine|turn.{0,6}engine|engine on|engine off|ignition)\b",
    r"\b(sport mode|eco mode|comfort mode|cruise control|lane assist|parking sensor|drive mode)\b",
    r"\b(heated steering|steering wheel heater)\b",
    r"\b(navigate|navigation|take me to|take me home|drive to|route to|directions to|find nearest|find a .{0,30} nearby|show .{0,20} route|avoid highways)\b",
    r"\b(call |dial |answer the phone|hang up|pick up the call|send a text|send message)\b",
]

_MEDIA_PATTERNS = [
    r"\b(volume up|volume down|turn.{0,6}volume|mute the speaker|mute the speakers|unmute)\b",
    r"\b(next track|previous track|skip track|shuffle|repeat)\b",
    r"\b(pause the music|resume the music|stop the music|turn off the radio|turn on the radio)\b",
    r"\b(play my|play the|play some|play a |play something)\b",
]

_ACTION_VERB_RE = re.compile(
    r"\b(turn on|turn off|turn up|turn down|switch on|switch off|open|close|set|adjust|"
    r"enable|disable|activate|deactivate|start|stop|increase|decrease|raise|lower|dim|brighten)\b"
)
_VEHICLE_NOUN_RE = re.compile(
    r"\b(ac|a/c|heater|fan|defroster|defrost|window|sunroof|seat|mirror|wiper|headlight|"
    r"light|lights|trunk|door|doors|hood|tailgate|engine|car|radio|speaker|speakers|"
    r"steering wheel|cruise control|parking|beam|beams)\b"
)

_GENERAL_SIGNALS = [
    r"\b(what is|what are|what was|what does|what did|who is|who was|who invented|when was|when did|where is|where was|why is|why do|why does|how does|how do|how many|how much|how long|how old|how far)\b",
    r"\b(explain|define|describe|summarize|translate|convert|calculate)\b",
    r"\b(tell me a|tell me about|tell me something|give me a)\b",
    r"\b(meaning of|definition of|capital of|population of|president of)\b",
    r"\b(recommend|suggest|should I)\b",
    r"\b(joke|poem|story|fun fact|interesting)\b",
    r"\b(remind me|set a timer|set an alarm|what time)\b",
    r"\b(weather|forecast|rain|snow|temperature outside)\b",
    r"\b(calories|cost|price|how much does)\b",
    r"\b(good morning|good night|how are you|thank you)\b",
]


def _classify_triage(utterance: str, default_class: int = 1) -> int:
    """Classify utterance as vehicle command (0) or general (1)."""
    text = utterance.lower().strip()

    vehicle_score = 0
    general_score = 0

    for pattern in _VEHICLE_PATTERNS:
        if re.search(pattern, text):
            vehicle_score += 2

    for pattern in _MEDIA_PATTERNS:
        if re.search(pattern, text):
            vehicle_score += 2

    if _ACTION_VERB_RE.search(text) and _VEHICLE_NOUN_RE.search(text):
        vehicle_score += 3

    for pattern in _GENERAL_SIGNALS:
        if re.search(pattern, text):
            general_score += 1

    if vehicle_score >= 2:
        return 0
    if general_score >= 1:
        return 1
    return default_class


async def execute_triage_classifier(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Binary triage: 0 = vehicle control command, 1 = general LLM request."""
    text_in = str(inputs.get("text_in", "")).strip()
    default_class = int(config.get("default_class", 1))

    result = _classify_triage(text_in, default_class)
    result_str = str(result)

    return {
        "text_out": result_str,
        "control": result_str,
    }


async def execute_histogram(
    node: GraphNode, inputs: dict[str, Any], config: dict, ctx: ExecutionContext
) -> dict[str, Any]:
    """Histogram sink — captures the value for frontend accumulation."""
    value = inputs.get("value_in", "")
    return {"_value": str(value).strip()}
