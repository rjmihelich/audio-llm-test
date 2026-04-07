"""Built-in pipeline templates matching the 5 whiteboard diagrams."""

from __future__ import annotations

import uuid


def _id() -> str:
    return str(uuid.uuid4())[:8]


def _node(type_id: str, x: float, y: float, config: dict | None = None, label: str = "") -> dict:
    nid = f"{type_id}_{_id()}"
    return {
        "id": nid,
        "type": type_id,
        "position": {"x": x, "y": y},
        "data": {
            "type_id": type_id,
            "label": label or type_id,
            "config": config or {},
        },
    }


def _edge(src_id: str, src_handle: str, tgt_id: str, tgt_handle: str,
          edge_type: str = "normal") -> dict:
    return {
        "id": f"e_{_id()}",
        "source": src_id,
        "sourceHandle": src_handle,
        "target": tgt_id,
        "targetHandle": tgt_handle,
        "data": {"edge_type": edge_type},
    }


# ---------------------------------------------------------------------------
# Template 1: Direct Realtime
# Speech + 3 Noise Gens → Mixer → LLM Realtime → Eval & Analysis
# ---------------------------------------------------------------------------

def template_direct_realtime() -> dict:
    speech = _node("speech_source", 0, 100, label="Speech")
    babble = _node("noise_generator", 0, 250, {"noise_type": "babble"}, "Babble Noise")
    road = _node("noise_generator", 0, 400, {"noise_type": "traffic"}, "Road Noise")
    wind = _node("noise_generator", 0, 550, {"noise_type": "wind"}, "Wind Noise")
    mixer = _node("mixer", 300, 300, {"snr_db": 15, "mixing_mode": "snr"}, "Audio Mixer")
    llm = _node("llm_realtime", 600, 300, {
        "model": "gpt-4o-realtime-preview",
        "voice": "alloy",
        "system_prompt": "You are a helpful in-car voice assistant.",
    }, "GPT Realtime")
    evaluator = _node("eval_analysis", 900, 300, {
        "evaluators": "all",
        "enable_latency_tracking": True,
    }, "Evaluation & Analysis")
    eval_out = _node("eval_output", 1200, 300, {"label": "Results"}, "Results")

    nodes = [speech, babble, road, wind, mixer, llm, evaluator, eval_out]
    edges = [
        _edge(speech["id"], "audio_out", mixer["id"], "audio_in_0"),
        _edge(babble["id"], "audio_out", mixer["id"], "audio_in_1"),
        _edge(road["id"], "audio_out", mixer["id"], "audio_in_2"),
        _edge(wind["id"], "audio_out", mixer["id"], "audio_in_3"),
        _edge(mixer["id"], "audio_out", llm["id"], "audio_in"),
        _edge(llm["id"], "text_out", evaluator["id"], "text_in"),
        _edge(llm["id"], "audio_out", evaluator["id"], "audio_in"),
        _edge(evaluator["id"], "eval_out", eval_out["id"], "eval_in"),
    ]

    return {"nodes": nodes, "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": 0.8}}


# ---------------------------------------------------------------------------
# Template 2: Network Simulation
# Sources → Mixer → Network Sim → LLM → Network Sim → Eval
# ---------------------------------------------------------------------------

def template_network_sim() -> dict:
    speech = _node("speech_source", 0, 100, label="Speech")
    noise = _node("noise_generator", 0, 300, {"noise_type": "pink_lpf"}, "Noise")
    mixer = _node("mixer", 250, 200, {"snr_db": 20}, "Audio Mixer")
    buf = _node("audio_buffer", 500, 200, {"chunk_ms": 20}, "Audio Buffering")
    net_in = _node("network_sim", 700, 200, {
        "latency_ms": 80, "jitter_ms": 15, "packet_loss_pct": 1,
    }, "Network Sim (Ingress)")
    llm = _node("llm", 950, 200, {
        "backend": "openai:gpt-4o-audio-preview",
    }, "LLM")
    net_out = _node("network_sim", 1200, 200, {
        "latency_ms": 50, "jitter_ms": 10,
    }, "Network Sim (Egress)")
    evaluator = _node("eval_analysis", 1450, 200, {"evaluators": "all"}, "Evaluation & Analysis")
    eval_out = _node("eval_output", 1700, 200, {"label": "Results"}, "Results")

    nodes = [speech, noise, mixer, buf, net_in, llm, net_out, evaluator, eval_out]
    edges = [
        _edge(speech["id"], "audio_out", mixer["id"], "audio_in_0"),
        _edge(noise["id"], "audio_out", mixer["id"], "audio_in_1"),
        _edge(mixer["id"], "audio_out", buf["id"], "audio_in"),
        _edge(buf["id"], "audio_out", net_in["id"], "audio_in"),
        _edge(net_in["id"], "audio_out", llm["id"], "audio_in"),
        _edge(llm["id"], "text_out", net_out["id"], "text_in"),
        _edge(net_out["id"], "text_out", evaluator["id"], "text_in"),
        _edge(evaluator["id"], "eval_out", eval_out["id"], "eval_in"),
    ]

    return {"nodes": nodes, "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": 0.7}}


# ---------------------------------------------------------------------------
# Template 3: Echo + Network
# Sources → Mixer → Echo Sim → Network Sim → LLM → Network Sim → Eval
# With acoustic echo coupling feedback
# ---------------------------------------------------------------------------

def template_echo_network() -> dict:
    speech = _node("speech_source", 0, 100, label="Speech")
    noise = _node("noise_generator", 0, 300, {"noise_type": "babble"}, "Babble Noise")
    mixer = _node("mixer", 250, 200, {"snr_db": 15}, "Audio Mixer")
    echo = _node("echo_simulator", 500, 200, {
        "delay_ms": 120, "gain_db": -10,
    }, "Echo Simulator")
    net_in = _node("network_sim", 750, 200, {
        "latency_ms": 80, "jitter_ms": 15,
    }, "Network Sim (Ingress)")
    llm = _node("llm", 1000, 200, {
        "backend": "openai:gpt-4o-audio-preview",
    }, "LLM")
    net_out = _node("network_sim", 1250, 200, {
        "latency_ms": 50, "jitter_ms": 10,
    }, "Network Sim (Egress)")
    evaluator = _node("eval_analysis", 1500, 200, {"evaluators": "all"}, "Evaluation & Analysis")
    eval_out = _node("eval_output", 1750, 200, {"label": "Results"}, "Results")

    nodes = [speech, noise, mixer, echo, net_in, llm, net_out, evaluator, eval_out]
    edges = [
        _edge(speech["id"], "audio_out", mixer["id"], "audio_in_0"),
        _edge(noise["id"], "audio_out", mixer["id"], "audio_in_1"),
        _edge(mixer["id"], "audio_out", echo["id"], "mic_in"),
        _edge(echo["id"], "audio_out", net_in["id"], "audio_in"),
        _edge(net_in["id"], "audio_out", llm["id"], "audio_in"),
        _edge(llm["id"], "text_out", net_out["id"], "text_in"),
        _edge(net_out["id"], "text_out", evaluator["id"], "text_in"),
        # Feedback: LLM audio output → echo simulator speaker_in
        _edge(net_out["id"], "audio_out", echo["id"], "speaker_in", edge_type="feedback"),
        _edge(evaluator["id"], "eval_out", eval_out["id"], "eval_in"),
    ]

    return {"nodes": nodes, "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": 0.65}}


# ---------------------------------------------------------------------------
# Template 4: Full Audio Processing
# Sources → Mixer → Echo → Net → Pre-proc → LLM → Post-proc → Net → Eval
# ---------------------------------------------------------------------------

def template_full_audio_processing() -> dict:
    speech = _node("speech_source", 0, 100, label="Speech")
    noise = _node("noise_generator", 0, 300, {"noise_type": "babble"}, "Babble Noise")
    road = _node("noise_generator", 0, 450, {"noise_type": "traffic"}, "Road Noise")
    mixer = _node("mixer", 250, 200, {"snr_db": 15}, "Audio Mixer")
    echo = _node("echo_simulator", 450, 200, {
        "delay_ms": 100, "gain_db": -8,
    }, "Echo Simulator")
    net_in = _node("network_sim", 650, 200, {
        "latency_ms": 60, "jitter_ms": 10,
    }, "Network Sim (In)")
    preproc = _node("audio_preprocess", 850, 200, {
        "enable_agc": True, "agc_target_db": -3,
        "enable_noise_gate": True, "noise_gate_threshold_db": -40,
    }, "Audio Pre-Processing")
    llm = _node("llm", 1050, 200, {
        "backend": "openai:gpt-4o-audio-preview",
    }, "LLM")
    postproc = _node("audio_postprocess", 1250, 200, {
        "normalize": True, "enable_limiter": True,
    }, "Audio Post-Processing")
    net_out = _node("network_sim", 1450, 200, {
        "latency_ms": 50, "jitter_ms": 10,
    }, "Network Sim (Out)")
    evaluator = _node("eval_analysis", 1650, 200, {"evaluators": "all"}, "Evaluation & Analysis")
    eval_out = _node("eval_output", 1900, 200, {"label": "Results"}, "Results")

    nodes = [speech, noise, road, mixer, echo, net_in, preproc, llm,
             postproc, net_out, evaluator, eval_out]
    edges = [
        _edge(speech["id"], "audio_out", mixer["id"], "audio_in_0"),
        _edge(noise["id"], "audio_out", mixer["id"], "audio_in_1"),
        _edge(road["id"], "audio_out", mixer["id"], "audio_in_2"),
        _edge(mixer["id"], "audio_out", echo["id"], "mic_in"),
        _edge(echo["id"], "audio_out", net_in["id"], "audio_in"),
        _edge(net_in["id"], "audio_out", preproc["id"], "audio_in"),
        _edge(preproc["id"], "audio_out", llm["id"], "audio_in"),
        _edge(llm["id"], "text_out", evaluator["id"], "text_in"),
        _edge(llm["id"], "audio_out", postproc["id"], "audio_in"),
        _edge(postproc["id"], "audio_out", net_out["id"], "audio_in"),
        # Feedback: post-processed audio → echo coupling
        _edge(net_out["id"], "audio_out", echo["id"], "speaker_in", edge_type="feedback"),
        _edge(evaluator["id"], "eval_out", eval_out["id"], "eval_in"),
    ]

    return {"nodes": nodes, "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": 0.55}}


# ---------------------------------------------------------------------------
# Template 5: Full STT/LLM/TTS Loop
# Sources → Mixer → Echo → Pre → STT → Net → LLM → Net → TTS → Post → Eval
# ---------------------------------------------------------------------------

def template_full_stt_tts_loop() -> dict:
    speech = _node("speech_source", 0, 100, label="Speech")
    noise = _node("noise_generator", 0, 300, {"noise_type": "babble"}, "Babble Noise")
    road = _node("noise_generator", 0, 450, {"noise_type": "traffic"}, "Road Noise")
    mixer = _node("mixer", 200, 200, {"snr_db": 15}, "Audio Mixer")
    echo = _node("echo_simulator", 380, 200, {
        "delay_ms": 100, "gain_db": -8,
    }, "Echo Simulator")
    preproc = _node("audio_preprocess", 560, 200, {
        "enable_agc": True,
    }, "Audio Pre-Processing")
    stt = _node("stt", 740, 200, {
        "backend": "whisper_local", "model_size": "base",
    }, "STT")
    net_in = _node("network_sim", 920, 200, {
        "latency_ms": 60, "jitter_ms": 10,
    }, "Network Sim (In)")
    llm = _node("llm", 1100, 200, {
        "backend": "anthropic:claude-haiku-4-5-20251001",
    }, "LLM")
    net_out = _node("network_sim", 1280, 200, {
        "latency_ms": 50, "jitter_ms": 10,
    }, "Network Sim (Out)")
    tts = _node("tts", 1460, 200, {
        "provider": "edge", "voice_id": "",
    }, "TTS")
    postproc = _node("audio_postprocess", 1640, 200, {
        "normalize": True,
    }, "Audio Post-Processing")
    evaluator = _node("eval_analysis", 1820, 200, {"evaluators": "all"}, "Evaluation & Analysis")
    eval_out = _node("eval_output", 2050, 200, {"label": "Results"}, "Results")

    nodes = [speech, noise, road, mixer, echo, preproc, stt, net_in,
             llm, net_out, tts, postproc, evaluator, eval_out]
    edges = [
        _edge(speech["id"], "audio_out", mixer["id"], "audio_in_0"),
        _edge(noise["id"], "audio_out", mixer["id"], "audio_in_1"),
        _edge(road["id"], "audio_out", mixer["id"], "audio_in_2"),
        _edge(mixer["id"], "audio_out", echo["id"], "mic_in"),
        _edge(echo["id"], "audio_out", preproc["id"], "audio_in"),
        _edge(preproc["id"], "audio_out", stt["id"], "audio_in"),
        _edge(stt["id"], "text_out", net_in["id"], "text_in"),
        _edge(net_in["id"], "text_out", llm["id"], "text_in"),
        _edge(llm["id"], "text_out", net_out["id"], "text_in"),
        _edge(net_out["id"], "text_out", tts["id"], "text_in"),
        _edge(tts["id"], "audio_out", postproc["id"], "audio_in"),
        # Feedback: TTS audio → echo coupling
        _edge(postproc["id"], "audio_out", echo["id"], "speaker_in", edge_type="feedback"),
        # Evaluation gets the LLM text response
        _edge(llm["id"], "text_out", evaluator["id"], "text_in"),
        _edge(evaluator["id"], "eval_out", eval_out["id"], "eval_in"),
    ]

    return {"nodes": nodes, "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": 0.5}}


# ---------------------------------------------------------------------------
# Template seeding
# ---------------------------------------------------------------------------

TEMPLATES = [
    {
        "name": "Direct Realtime",
        "description": "Speech + noise → GPT Realtime → Evaluation. Simplest pipeline for testing multimodal LLMs with noise.",
        "graph_fn": template_direct_realtime,
    },
    {
        "name": "Network Simulation",
        "description": "Audio through network simulators on both sides of the LLM, modeling real-world latency and packet loss.",
        "graph_fn": template_network_sim,
    },
    {
        "name": "Echo + Network",
        "description": "Acoustic echo coupling path with network simulation. Tests LLM performance with echo feedback.",
        "graph_fn": template_echo_network,
    },
    {
        "name": "Full Audio Processing",
        "description": "Complete audio chain: mixer → echo → network → pre-processing → LLM → post-processing → network → eval.",
        "graph_fn": template_full_audio_processing,
    },
    {
        "name": "Full STT/LLM/TTS Loop",
        "description": "Full voice assistant loop: speech → STT → LLM → TTS with echo coupling, network sim, and pre/post processing.",
        "graph_fn": template_full_stt_tts_loop,
    },
]


async def seed_templates():
    """Seed built-in templates if they don't exist yet."""
    from backend.app.models.base import async_session
    from ..models.pipeline import Pipeline
    from sqlalchemy import select

    async with async_session() as session:
        # Check if templates already exist
        result = await session.execute(
            select(Pipeline).where(Pipeline.is_template == True)  # noqa: E712
        )
        existing = result.scalars().all()
        existing_names = {p.name for p in existing}

        for tmpl in TEMPLATES:
            if tmpl["name"] not in existing_names:
                graph_json = tmpl["graph_fn"]()
                pipeline = Pipeline(
                    name=tmpl["name"],
                    description=tmpl["description"],
                    graph_json=graph_json,
                    is_template=True,
                )
                session.add(pipeline)

        await session.commit()
