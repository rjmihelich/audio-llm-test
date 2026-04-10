"""Node executors — each function wraps existing backend modules."""

from __future__ import annotations

from typing import Any, Callable, Coroutine

# Lazy import to avoid circular deps
_EXECUTOR_MAP: dict[str, str] = {
    # audio sources
    "speech_source": "audio_sources",
    "noise_generator": "audio_sources",
    "audio_file": "audio_sources",
    # audio processing
    "mixer": "audio_processing",
    "echo_simulator": "audio_processing",
    "eq_filter": "audio_processing",
    "gain": "audio_processing",
    "audio_buffer": "audio_processing",
    # network
    "network_sim": "network_sim",
    # telephony
    "telephony_codec": "telephony_nodes",
    "aec": "telephony_nodes",
    "aec_residual": "telephony_nodes",
    "agc": "telephony_nodes",
    "doubletalk_metrics": "telephony_nodes",
    "far_end_source": "telephony_nodes",
    "telephony_judge": "telephony_nodes",
    # dsp
    "noise_reduction": "dsp_nodes",
    "sample_rate_converter": "dsp_nodes",
    "time_delay": "dsp_nodes",
    # speech
    "tts": "speech_nodes",
    "stt": "speech_nodes",
    # llm
    "llm": "llm_nodes",
    "llm_realtime": "llm_nodes",
    # logic
    "router": "logic_nodes",
    "histogram": "logic_nodes",
    # evaluation
    "eval_analysis": "eval_nodes",
    "safety_critical_eval": "content_safety_nodes",
    "compliance_eval": "content_safety_nodes",
    "trust_brand_eval": "content_safety_nodes",
    "ux_quality_eval": "content_safety_nodes",
    # outputs
    "text_output": "eval_nodes",
    "audio_output": "eval_nodes",
    "eval_output": "eval_nodes",
}

_loaded_modules: dict[str, Any] = {}


def get_default_executor(type_id: str) -> Callable[..., Coroutine]:
    """Get the default executor function for a node type."""
    module_name = _EXECUTOR_MAP.get(type_id)
    if not module_name:
        raise KeyError(f"No executor registered for node type '{type_id}'")

    if module_name not in _loaded_modules:
        import importlib
        _loaded_modules[module_name] = importlib.import_module(
            f".{module_name}", package=__package__
        )

    module = _loaded_modules[module_name]
    executor_fn = getattr(module, f"execute_{type_id}", None)
    if not executor_fn:
        raise KeyError(f"Executor function 'execute_{type_id}' not found in {module_name}")
    return executor_fn
