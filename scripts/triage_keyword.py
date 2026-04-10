"""Rule-based keyword/regex classifier for vehicle command triage.

Returns 0 for vehicle control commands, 1 for general LLM requests.
"""

import re

# Vehicle-control patterns — if ANY of these match, lean toward label 0.
_VEHICLE_PATTERNS = [
    # Climate
    r"\b(temperature|ac|a/c|air conditioning|heater|heat|defrost|defroster|fan speed|climate|warmer|cooler|colder)\b",
    # Windows / sunroof
    r"\b(window|windows|sunroof)\b",
    # Seats
    r"\b(seat|seats|heated seat|seat warmer|recline)\b",
    # Mirrors
    r"\b(mirror|mirrors)\b",
    # Wipers
    r"\b(wiper|wipers|windshield wiper)\b",
    # Lights
    r"\b(headlight|headlights|high beam|high beams|interior light|interior lights|fog light|dome light)\b",
    # Locks / doors / trunk
    r"\b(lock|unlock|tailgate|trunk|hood)\b",
    # Horn
    r"\b(honk|horn)\b",
    # Engine — require action context to avoid "how does an engine work"
    r"\b(start the engine|stop the engine|turn.{0,6}engine|engine on|engine off|ignition)\b",
    # Drive modes
    r"\b(sport mode|eco mode|comfort mode|cruise control|lane assist|parking sensor|drive mode)\b",
    # Steering
    r"\b(heated steering|steering wheel heater)\b",
    # Navigation action verbs
    r"\b(navigate|navigation|take me to|take me home|drive to|route to|directions to|find nearest|find a .{0,30} nearby|show .{0,20} route|avoid highways)\b",
    # Phone
    r"\b(call |dial |answer the phone|hang up|pick up the call|send a text|send message)\b",
]

# Media-control patterns — these need extra care to avoid false positives.
_MEDIA_PATTERNS = [
    r"\b(volume up|volume down|turn.{0,6}volume|mute the speaker|mute the speakers|unmute)\b",
    r"\b(next track|previous track|skip track|shuffle|repeat)\b",
    r"\b(pause the music|resume the music|stop the music|turn off the radio|turn on the radio)\b",
    r"\b(play my|play the|play some|play a |play something)\b",
]

# Action verbs that signal a vehicle command when paired with vehicle nouns
_ACTION_VERB_PATTERN = r"\b(turn on|turn off|turn up|turn down|switch on|switch off|open|close|set|adjust|enable|disable|activate|deactivate|start|stop|increase|decrease|raise|lower|dim|brighten)\b"

# Vehicle nouns that confirm a vehicle command when preceded by action verbs
_VEHICLE_NOUN_PATTERN = r"\b(ac|a/c|heater|fan|defroster|defrost|window|sunroof|seat|mirror|wiper|headlight|light|lights|trunk|door|doors|hood|tailgate|engine|car|radio|speaker|speakers|steering wheel|cruise control|parking|beam|beams)\b"

# Patterns that indicate general/non-vehicle queries
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


def classify_keyword(utterance: str) -> int:
    """Classify an utterance as vehicle command (0) or general (1)."""
    text = utterance.lower().strip()

    # Score-based: accumulate vehicle and general signals
    vehicle_score = 0
    general_score = 0

    # Check direct vehicle patterns
    for pattern in _VEHICLE_PATTERNS:
        if re.search(pattern, text):
            vehicle_score += 2

    # Check media patterns
    for pattern in _MEDIA_PATTERNS:
        if re.search(pattern, text):
            vehicle_score += 2

    # Check action verb + vehicle noun combo
    if re.search(_ACTION_VERB_PATTERN, text) and re.search(_VEHICLE_NOUN_PATTERN, text):
        vehicle_score += 3

    # Check general signals
    for pattern in _GENERAL_SIGNALS:
        if re.search(pattern, text):
            general_score += 1

    # Vehicle keywords override question framing
    # e.g. "can you turn on the AC" — has question structure but is a command
    if vehicle_score >= 2:
        return 0

    if general_score >= 1:
        return 1

    # Default to general
    return 1
