"""Node type registry — defines all available node types, their ports, and config schemas."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class PortType(str, enum.Enum):
    audio = "audio"
    text = "text"
    evaluation = "evaluation"


# Colors for the frontend
PORT_COLORS = {
    PortType.audio: "#3B82F6",       # blue
    PortType.text: "#22C55E",        # green
    PortType.evaluation: "#F97316",  # orange
}


@dataclass
class PortDef:
    """Definition of a single input or output port."""
    name: str
    port_type: PortType
    required: bool = True
    description: str = ""


@dataclass
class ConfigField:
    """Definition of a configuration field for a node."""
    name: str
    field_type: str  # "string", "number", "select", "slider", "boolean", "json"
    label: str = ""
    default: object = None
    options: list[dict] | None = None  # for "select" type: [{"value": ..., "label": ...}]
    min_val: float | None = None
    max_val: float | None = None
    step: float | None = None
    description: str = ""
    multiline: bool = False  # render "string" fields as textarea


@dataclass
class NodeTypeDef:
    """Full definition of a node type."""
    type_id: str
    label: str
    category: str
    description: str
    inputs: list[PortDef] = field(default_factory=list)
    outputs: list[PortDef] = field(default_factory=list)
    config_fields: list[ConfigField] = field(default_factory=list)
    dynamic_inputs: bool = False  # mixer: auto-add input handles
    color: str = "#64748B"  # node header color


# ---------------------------------------------------------------------------
# Node type definitions
# ---------------------------------------------------------------------------

CATEGORIES = {
    "sources": {"label": "Audio Sources", "color": "#A3E635"},
    "processing": {"label": "Audio Processing", "color": "#FBBF24"},
    "telephony": {"label": "Telephony", "color": "#E879F9"},
    "network": {"label": "Network", "color": "#F87171"},
    "speech": {"label": "Speech", "color": "#818CF8"},
    "llm": {"label": "LLM", "color": "#34D399"},
    "evaluation": {"label": "Evaluation", "color": "#FB923C"},
    "output": {"label": "Output", "color": "#94A3B8"},
}


def _build_registry() -> dict[str, NodeTypeDef]:
    """Build the complete node type registry."""
    nodes: list[NodeTypeDef] = []

    # -----------------------------------------------------------------------
    # SOURCE BLOCKS
    # -----------------------------------------------------------------------
    nodes.append(NodeTypeDef(
        type_id="speech_source",
        label="Speech Source",
        category="sources",
        description="Clean speech audio from corpus or PipelineInput",
        inputs=[],
        outputs=[PortDef("audio_out", PortType.audio)],
        config_fields=[
            ConfigField("source_mode", "select", "Source", "pipeline_input",
                        options=[
                            {"value": "pipeline_input", "label": "From Test Case"},
                            {"value": "corpus_entry", "label": "Corpus Entry"},
                            {"value": "file", "label": "Audio File"},
                        ]),
            ConfigField("corpus_entry_id", "string", "Corpus Entry ID", ""),
            ConfigField("voice_id", "string", "Voice ID", ""),
            ConfigField("file_path", "string", "File Path", ""),
        ],
        color="#A3E635",
    ))

    nodes.append(NodeTypeDef(
        type_id="noise_generator",
        label="Noise Generator",
        category="sources",
        description="Generate noise: white, pink, babble, traffic, wind",
        inputs=[],
        outputs=[PortDef("audio_out", PortType.audio)],
        config_fields=[
            ConfigField("noise_type", "select", "Noise Type", "pink_lpf",
                        options=[
                            {"value": "white", "label": "White Noise"},
                            {"value": "pink", "label": "Pink Noise"},
                            {"value": "pink_lpf", "label": "Pink (LPF)"},
                            {"value": "babble", "label": "Babble"},
                            {"value": "traffic", "label": "Traffic"},
                            {"value": "wind", "label": "Wind"},
                            {"value": "hvac_fan", "label": "HVAC Fan"},
                            {"value": "secondary_voice", "label": "Secondary Voice"},
                            {"value": "silence", "label": "Silence"},
                        ]),
            ConfigField("seed", "number", "Random Seed", None,
                        description="Leave empty for random"),
            ConfigField("duration_s", "number", "Duration (s)", 0,
                        description="0 = match speech source length"),
        ],
        color="#A3E635",
    ))

    nodes.append(NodeTypeDef(
        type_id="audio_file",
        label="Audio File",
        category="sources",
        description="Load audio from a WAV file",
        inputs=[],
        outputs=[PortDef("audio_out", PortType.audio)],
        config_fields=[
            ConfigField("file_path", "string", "File Path", ""),
        ],
        color="#A3E635",
    ))

    # -----------------------------------------------------------------------
    # AUDIO PROCESSING BLOCKS
    # -----------------------------------------------------------------------
    nodes.append(NodeTypeDef(
        type_id="mixer",
        label="Audio Mixer",
        category="processing",
        description="Mix N audio inputs at specified SNR levels",
        inputs=[
            PortDef("audio_in_0", PortType.audio, required=True, description="Primary (speech)"),
            PortDef("audio_in_1", PortType.audio, required=False, description="Noise 1"),
        ],
        outputs=[PortDef("audio_out", PortType.audio)],
        config_fields=[
            ConfigField("snr_db", "slider", "SNR (dB)", 20.0,
                        min_val=-10, max_val=40, step=1),
            ConfigField("mixing_mode", "select", "Mode", "snr",
                        options=[
                            {"value": "snr", "label": "SNR-calibrated"},
                            {"value": "equal", "label": "Equal gain"},
                        ]),
        ],
        dynamic_inputs=True,
        color="#FBBF24",
    ))

    nodes.append(NodeTypeDef(
        type_id="echo_simulator",
        label="Echo Simulator",
        category="processing",
        description="Simulate acoustic echo coupling path",
        inputs=[
            PortDef("mic_in", PortType.audio, required=True, description="Mic input"),
            PortDef("speaker_in", PortType.audio, required=False, description="Speaker feedback (echo coupling)"),
        ],
        outputs=[PortDef("audio_out", PortType.audio)],
        config_fields=[
            ConfigField("delay_ms", "slider", "Delay (ms)", 100,
                        min_val=0, max_val=500, step=10),
            ConfigField("gain_db", "slider", "Gain (dB)", -6,
                        min_val=-60, max_val=0, step=1),
            ConfigField("eq_config", "json", "EQ Chain", [],
                        description="Array of filter specs"),
        ],
        color="#FBBF24",
    ))

    nodes.append(NodeTypeDef(
        type_id="eq_filter",
        label="EQ Filter",
        category="processing",
        description="Biquad filter chain (LPF, HPF, peaking, shelf)",
        inputs=[PortDef("audio_in", PortType.audio)],
        outputs=[PortDef("audio_out", PortType.audio)],
        config_fields=[
            ConfigField("filters", "json", "Filter Chain", [],
                        description='[{"type":"lpf","freq":8000,"q":0.707}]'),
        ],
        color="#FBBF24",
    ))

    nodes.append(NodeTypeDef(
        type_id="gain",
        label="Gain",
        category="processing",
        description="Simple volume adjustment",
        inputs=[PortDef("audio_in", PortType.audio)],
        outputs=[PortDef("audio_out", PortType.audio)],
        config_fields=[
            ConfigField("gain_db", "slider", "Gain (dB)", 0,
                        min_val=-60, max_val=24, step=0.5),
        ],
        color="#FBBF24",
    ))

    nodes.append(NodeTypeDef(
        type_id="audio_preprocess",
        label="Audio Pre-Processing",
        category="processing",
        description="AEC, AGC, noise gate, VAD",
        inputs=[PortDef("audio_in", PortType.audio)],
        outputs=[PortDef("audio_out", PortType.audio)],
        config_fields=[
            ConfigField("enable_agc", "boolean", "Auto Gain Control", True),
            ConfigField("agc_target_db", "slider", "AGC Target (dB)", -3,
                        min_val=-20, max_val=0, step=1),
            ConfigField("enable_noise_gate", "boolean", "Noise Gate", False),
            ConfigField("noise_gate_threshold_db", "slider", "Gate Threshold (dB)", -40,
                        min_val=-80, max_val=0, step=1),
            ConfigField("enable_vad", "boolean", "Voice Activity Detection", False),
        ],
        color="#FBBF24",
    ))

    nodes.append(NodeTypeDef(
        type_id="audio_postprocess",
        label="Audio Post-Processing",
        category="processing",
        description="Normalization, limiting, format conversion",
        inputs=[PortDef("audio_in", PortType.audio)],
        outputs=[PortDef("audio_out", PortType.audio)],
        config_fields=[
            ConfigField("normalize", "boolean", "Normalize", True),
            ConfigField("normalize_target_db", "slider", "Target (dB)", -1,
                        min_val=-20, max_val=0, step=0.5),
            ConfigField("enable_limiter", "boolean", "Limiter", True),
            ConfigField("limiter_threshold_db", "slider", "Limiter Threshold (dB)", -1,
                        min_val=-12, max_val=0, step=0.5),
        ],
        color="#FBBF24",
    ))

    nodes.append(NodeTypeDef(
        type_id="audio_buffer",
        label="Audio Buffer",
        category="processing",
        description="Chunk/buffer audio for streaming simulation",
        inputs=[PortDef("audio_in", PortType.audio)],
        outputs=[PortDef("audio_out", PortType.audio)],
        config_fields=[
            ConfigField("chunk_ms", "slider", "Chunk Size (ms)", 20,
                        min_val=5, max_val=200, step=5),
            ConfigField("overlap_ms", "slider", "Overlap (ms)", 0,
                        min_val=0, max_val=50, step=5),
        ],
        color="#FBBF24",
    ))

    # -----------------------------------------------------------------------
    # NETWORK SIMULATION
    # -----------------------------------------------------------------------
    nodes.append(NodeTypeDef(
        type_id="network_sim",
        label="Network Simulator",
        category="network",
        description="Simulate network latency, jitter, packet loss",
        inputs=[
            PortDef("audio_in", PortType.audio, required=False),
            PortDef("text_in", PortType.text, required=False),
        ],
        outputs=[
            PortDef("audio_out", PortType.audio),
            PortDef("text_out", PortType.text),
        ],
        config_fields=[
            ConfigField("latency_ms", "slider", "Latency (ms)", 50,
                        min_val=0, max_val=2000, step=10),
            ConfigField("jitter_ms", "slider", "Jitter (ms)", 10,
                        min_val=0, max_val=500, step=5),
            ConfigField("packet_loss_pct", "slider", "Packet Loss (%)", 0,
                        min_val=0, max_val=50, step=0.5),
            ConfigField("bandwidth_kbps", "number", "Bandwidth (kbps)", 0,
                        description="0 = unlimited"),
        ],
        color="#F87171",
    ))

    # -----------------------------------------------------------------------
    # SPEECH BLOCKS
    # -----------------------------------------------------------------------
    nodes.append(NodeTypeDef(
        type_id="tts",
        label="Text-to-Speech",
        category="speech",
        description="Convert text to audio using a TTS provider",
        inputs=[PortDef("text_in", PortType.text)],
        outputs=[PortDef("audio_out", PortType.audio)],
        config_fields=[
            ConfigField("provider", "select", "Provider", "edge",
                        options=[
                            {"value": "openai", "label": "OpenAI"},
                            {"value": "google", "label": "Google"},
                            {"value": "elevenlabs", "label": "ElevenLabs"},
                            {"value": "edge", "label": "Edge (Free)"},
                            {"value": "gtts", "label": "gTTS (Free)"},
                            {"value": "piper", "label": "Piper (Local)"},
                        ]),
            ConfigField("voice_id", "string", "Voice ID", ""),
        ],
        color="#818CF8",
    ))

    nodes.append(NodeTypeDef(
        type_id="stt",
        label="Speech-to-Text",
        category="speech",
        description="Transcribe audio to text",
        inputs=[PortDef("audio_in", PortType.audio)],
        outputs=[PortDef("text_out", PortType.text)],
        config_fields=[
            ConfigField("backend", "select", "Backend", "whisper_local",
                        options=[
                            {"value": "whisper_local", "label": "Whisper (Local)"},
                            {"value": "whisper_api", "label": "Whisper (API)"},
                            {"value": "deepgram", "label": "Deepgram"},
                        ]),
            ConfigField("model_size", "select", "Model Size", "base",
                        options=[
                            {"value": "tiny", "label": "Tiny"},
                            {"value": "base", "label": "Base"},
                            {"value": "small", "label": "Small"},
                            {"value": "medium", "label": "Medium"},
                            {"value": "large", "label": "Large"},
                        ]),
        ],
        color="#818CF8",
    ))

    # -----------------------------------------------------------------------
    # LLM BLOCKS
    # -----------------------------------------------------------------------
    nodes.append(NodeTypeDef(
        type_id="llm",
        label="LLM",
        category="llm",
        description="Request/response LLM (GPT-4o, Gemini, Claude, Ollama)",
        inputs=[
            PortDef("audio_in", PortType.audio, required=False, description="Audio input (multimodal)"),
            PortDef("text_in", PortType.text, required=False, description="Text input"),
        ],
        outputs=[
            PortDef("text_out", PortType.text),
            PortDef("audio_out", PortType.audio),
        ],
        config_fields=[
            ConfigField("backend", "select", "Backend", "openai:gpt-4o-audio-preview",
                        options=[
                            {"value": "openai:gpt-4o-audio-preview", "label": "GPT-4o Audio"},
                            {"value": "openai:gpt-4o-mini-audio-preview", "label": "GPT-4o Mini Audio"},
                            {"value": "gemini:gemini-2.0-flash", "label": "Gemini 2.0 Flash"},
                            {"value": "anthropic:claude-haiku-4-5-20251001", "label": "Claude Haiku"},
                            {"value": "anthropic:claude-sonnet-4-6", "label": "Claude Sonnet"},
                            {"value": "ollama:mistral", "label": "Ollama Mistral"},
                        ]),
            ConfigField("system_prompt", "string", "System Prompt",
                        "You are a helpful in-car voice assistant.", multiline=True),
            ConfigField("temperature", "slider", "Temperature", 0.7,
                        min_val=0, max_val=2, step=0.1),
        ],
        color="#34D399",
    ))

    nodes.append(NodeTypeDef(
        type_id="llm_realtime",
        label="LLM Realtime",
        category="llm",
        description="Streaming WebSocket LLM (OpenAI Realtime API)",
        inputs=[
            PortDef("audio_in", PortType.audio, required=True, description="Streaming audio input"),
        ],
        outputs=[
            PortDef("text_out", PortType.text),
            PortDef("audio_out", PortType.audio),
        ],
        config_fields=[
            ConfigField("model", "select", "Model", "gpt-4o-realtime-preview",
                        options=[
                            {"value": "gpt-4o-realtime-preview", "label": "GPT-4o Realtime"},
                            {"value": "gpt-4o-mini-realtime-preview", "label": "GPT-4o Mini Realtime"},
                        ]),
            ConfigField("voice", "select", "Voice", "alloy",
                        options=[
                            {"value": "alloy", "label": "Alloy"},
                            {"value": "echo", "label": "Echo"},
                            {"value": "shimmer", "label": "Shimmer"},
                            {"value": "ash", "label": "Ash"},
                            {"value": "ballad", "label": "Ballad"},
                            {"value": "coral", "label": "Coral"},
                            {"value": "sage", "label": "Sage"},
                            {"value": "verse", "label": "Verse"},
                        ]),
            ConfigField("modalities", "select", "Modalities", "text_and_audio",
                        options=[
                            {"value": "text_and_audio", "label": "Text + Audio"},
                            {"value": "text_only", "label": "Text Only"},
                        ]),
            ConfigField("turn_detection", "select", "Turn Detection", "server_vad",
                        options=[
                            {"value": "server_vad", "label": "Server VAD"},
                            {"value": "manual", "label": "Manual"},
                        ]),
            ConfigField("temperature", "slider", "Temperature", 0.8,
                        min_val=0, max_val=2, step=0.1),
            ConfigField("system_prompt", "string", "Instructions",
                        "You are a helpful in-car voice assistant.", multiline=True),
            ConfigField("chunk_ms", "slider", "Stream Chunk (ms)", 20,
                        min_val=5, max_val=100, step=5,
                        description="Audio chunk size for streaming"),
        ],
        color="#34D399",
    ))

    # -----------------------------------------------------------------------
    # TELEPHONY BLOCKS
    # -----------------------------------------------------------------------
    nodes.append(NodeTypeDef(
        type_id="telephony_codec",
        label="BT Codec",
        category="telephony",
        description="Bluetooth codec simulation (CVSD narrowband / mSBC wideband)",
        inputs=[PortDef("audio_in", PortType.audio)],
        outputs=[PortDef("audio_out", PortType.audio)],
        config_fields=[
            ConfigField("codec_type", "select", "Codec", "msbc",
                        options=[
                            {"value": "cvsd", "label": "CVSD (8 kHz narrowband)"},
                            {"value": "msbc", "label": "mSBC (16 kHz wideband)"},
                            {"value": "none", "label": "None (bypass)"},
                        ]),
            ConfigField("cvsd_snr_db", "slider", "CVSD SNR (dB)", 27.0,
                        min_val=20, max_val=35, step=1,
                        description="Quantization noise floor for CVSD"),
            ConfigField("msbc_snr_db", "slider", "mSBC SNR (dB)", 37.0,
                        min_val=30, max_val=45, step=1,
                        description="Quantization noise floor for mSBC"),
            ConfigField("seed", "number", "Random Seed", None,
                        description="Leave empty for random"),
        ],
        color="#E879F9",
    ))

    nodes.append(NodeTypeDef(
        type_id="aec",
        label="Echo Canceller",
        category="telephony",
        description="Adaptive acoustic echo canceller (NLMS / RLS / Kalman)",
        inputs=[
            PortDef("mic_in", PortType.audio, required=True, description="Mic signal (near-end + echo)"),
            PortDef("ref_in", PortType.audio, required=True, description="Far-end reference (speaker signal)"),
        ],
        outputs=[
            PortDef("audio_out", PortType.audio, description="Echo-cancelled signal"),
            PortDef("echo_est", PortType.audio, description="Estimated echo component"),
        ],
        config_fields=[
            ConfigField("algorithm", "select", "Algorithm", "nlms",
                        options=[
                            {"value": "nlms", "label": "NLMS"},
                            {"value": "rls", "label": "RLS"},
                            {"value": "kalman", "label": "Kalman"},
                        ]),
            ConfigField("filter_length_ms", "slider", "Filter Length (ms)", 200,
                        min_val=50, max_val=500, step=10,
                        description="Adaptive filter tap length"),
            ConfigField("step_size", "slider", "Step Size (mu)", 0.1,
                        min_val=0.01, max_val=1.0, step=0.01,
                        description="NLMS learning rate"),
            ConfigField("forgetting_factor", "slider", "Forgetting Factor", 0.999,
                        min_val=0.9, max_val=1.0, step=0.001,
                        description="RLS lambda (memory length)"),
            ConfigField("process_noise", "number", "Process Noise (Q)", 0.0001,
                        description="Kalman process noise covariance"),
            ConfigField("measurement_noise", "number", "Measurement Noise (R)", 0.01,
                        description="Kalman measurement noise covariance"),
            ConfigField("regularization", "number", "Regularization", 0.000001,
                        description="Diagonal loading"),
        ],
        color="#E879F9",
    ))

    nodes.append(NodeTypeDef(
        type_id="aec_residual",
        label="AEC Residual",
        category="telephony",
        description="Simulate imperfect AEC: residual echo leakage + NLD artifacts",
        inputs=[
            PortDef("mic_in", PortType.audio, required=True, description="Mic / AEC output signal"),
            PortDef("echo_ref", PortType.audio, required=False, description="Echo reference for residual"),
        ],
        outputs=[PortDef("audio_out", PortType.audio)],
        config_fields=[
            ConfigField("suppression_db", "slider", "Suppression (dB)", -25,
                        min_val=-60, max_val=0, step=1,
                        description="-40=excellent AEC, -10=poor AEC"),
            ConfigField("residual_type", "select", "Residual Type", "mixed",
                        options=[
                            {"value": "partial", "label": "Partial (attenuated echo)"},
                            {"value": "nonlinear", "label": "Non-linear (NLD artifacts)"},
                            {"value": "mixed", "label": "Mixed (most realistic)"},
                        ]),
            ConfigField("nonlinear_distortion", "slider", "NLD Strength", 0.3,
                        min_val=0, max_val=1, step=0.05),
            ConfigField("seed", "number", "Random Seed", None),
        ],
        color="#E879F9",
    ))

    nodes.append(NodeTypeDef(
        type_id="agc",
        label="AGC",
        category="telephony",
        description="Automatic gain control with envelope follower and compression",
        inputs=[PortDef("audio_in", PortType.audio)],
        outputs=[PortDef("audio_out", PortType.audio)],
        config_fields=[
            ConfigField("preset", "select", "Preset", "mild",
                        options=[
                            {"value": "off", "label": "Off"},
                            {"value": "mild", "label": "Mild"},
                            {"value": "aggressive", "label": "Aggressive"},
                            {"value": "custom", "label": "Custom"},
                        ]),
            ConfigField("target_rms_db", "slider", "Target RMS (dB)", -18,
                        min_val=-30, max_val=0, step=1),
            ConfigField("attack_ms", "slider", "Attack (ms)", 50,
                        min_val=5, max_val=500, step=5),
            ConfigField("release_ms", "slider", "Release (ms)", 200,
                        min_val=20, max_val=2000, step=10),
            ConfigField("max_gain_db", "slider", "Max Gain (dB)", 30,
                        min_val=0, max_val=40, step=1),
            ConfigField("compression_ratio", "slider", "Compression Ratio", 4.0,
                        min_val=1, max_val=20, step=0.5),
        ],
        color="#E879F9",
    ))

    nodes.append(NodeTypeDef(
        type_id="noise_reduction",
        label="Noise Reduction",
        category="telephony",
        description="Speech enhancement via spectral subtraction or Wiener filtering",
        inputs=[
            PortDef("audio_in", PortType.audio, required=True, description="Noisy input"),
            PortDef("noise_ref", PortType.audio, required=False, description="Noise-only reference (optional)"),
        ],
        outputs=[PortDef("audio_out", PortType.audio)],
        config_fields=[
            ConfigField("method", "select", "Method", "spectral_subtraction",
                        options=[
                            {"value": "spectral_subtraction", "label": "Spectral Subtraction"},
                            {"value": "wiener", "label": "Wiener Filter"},
                        ]),
            ConfigField("suppression_db", "slider", "Max Suppression (dB)", 12,
                        min_val=0, max_val=30, step=1),
            ConfigField("noise_floor_db", "slider", "Noise Floor (dB)", -60,
                        min_val=-80, max_val=-20, step=1),
            ConfigField("smoothing_factor", "slider", "Smoothing", 0.9,
                        min_val=0, max_val=1, step=0.05),
        ],
        color="#E879F9",
    ))

    nodes.append(NodeTypeDef(
        type_id="sample_rate_converter",
        label="Sample Rate Converter",
        category="telephony",
        description="Polyphase sample rate conversion",
        inputs=[PortDef("audio_in", PortType.audio)],
        outputs=[PortDef("audio_out", PortType.audio)],
        config_fields=[
            ConfigField("target_sample_rate", "select", "Target Rate", 16000,
                        options=[
                            {"value": 8000, "label": "8 kHz (narrowband)"},
                            {"value": 16000, "label": "16 kHz (wideband)"},
                            {"value": 22050, "label": "22.05 kHz"},
                            {"value": 44100, "label": "44.1 kHz (CD)"},
                            {"value": 48000, "label": "48 kHz"},
                        ]),
        ],
        color="#E879F9",
    ))

    nodes.append(NodeTypeDef(
        type_id="time_delay",
        label="Time Delay",
        category="telephony",
        description="Standalone delay line",
        inputs=[PortDef("audio_in", PortType.audio)],
        outputs=[PortDef("audio_out", PortType.audio)],
        config_fields=[
            ConfigField("delay_ms", "slider", "Delay (ms)", 0,
                        min_val=0, max_val=2000, step=1),
            ConfigField("pad_mode", "select", "Mode", "zero",
                        options=[
                            {"value": "zero", "label": "Zero-pad (extends length)"},
                            {"value": "truncate", "label": "Truncate (maintain length)"},
                        ]),
        ],
        color="#E879F9",
    ))

    nodes.append(NodeTypeDef(
        type_id="doubletalk_metrics",
        label="Doubletalk Metrics",
        category="telephony",
        description="Compute ERLE, near-end distortion, and activity ratios",
        inputs=[
            PortDef("near_end_clean", PortType.audio, required=True, description="Clean near-end reference"),
            PortDef("far_end_clean", PortType.audio, required=False, description="Clean far-end reference"),
            PortDef("mic_signal", PortType.audio, required=True, description="Mic signal (with echo)"),
            PortDef("aec_output", PortType.audio, required=False, description="AEC output signal"),
            PortDef("echo_ref", PortType.audio, required=False, description="Echo reference"),
        ],
        outputs=[PortDef("eval_out", PortType.evaluation)],
        config_fields=[
            ConfigField("frame_ms", "slider", "Frame Size (ms)", 20,
                        min_val=10, max_val=40, step=5),
            ConfigField("vad_threshold_db", "slider", "VAD Threshold (dB)", -40,
                        min_val=-60, max_val=-20, step=1),
        ],
        color="#E879F9",
    ))

    nodes.append(NodeTypeDef(
        type_id="far_end_source",
        label="Far-End Speech Source",
        category="sources",
        description="Far-end caller audio with timing offset for 2-way telephony",
        inputs=[],
        outputs=[PortDef("audio_out", PortType.audio, description="Far-end speech signal")],
        config_fields=[
            ConfigField("source_mode", "select", "Source", "pipeline_input",
                        options=[
                            {"value": "pipeline_input", "label": "From Test Case"},
                            {"value": "corpus_entry", "label": "Corpus Entry"},
                            {"value": "file", "label": "Audio File"},
                        ]),
            ConfigField("corpus_entry_id", "string", "Corpus Entry ID", ""),
            ConfigField("file_path", "string", "File Path", ""),
            ConfigField("level_db", "slider", "Level (dB)", 0.0,
                        min_val=-30, max_val=12, step=0.5,
                        description="Gain applied to far-end speech. 0=original level."),
            ConfigField("offset_ms", "slider", "Offset (ms)", 0.0,
                        min_val=-5000, max_val=5000, step=50,
                        description="Timing offset. Negative=far-end starts first (barge-in)."),
        ],
        color="#A3E635",
    ))

    # -----------------------------------------------------------------------
    # EVALUATION BLOCKS
    # -----------------------------------------------------------------------
    nodes.append(NodeTypeDef(
        type_id="telephony_judge",
        label="Telephony Judge",
        category="evaluation",
        description="LLM-based telephony quality evaluation with multi-judge voting",
        inputs=[
            PortDef("text_in", PortType.text, required=False, description="LLM response text"),
            PortDef("audio_in", PortType.audio, required=False, description="Processed audio"),
            PortDef("near_end_ref", PortType.audio, required=False, description="Clean near-end reference"),
            PortDef("far_end_ref", PortType.audio, required=False, description="Clean far-end reference"),
        ],
        outputs=[PortDef("eval_out", PortType.evaluation)],
        config_fields=[
            ConfigField("modes", "select", "Evaluation Mode", "auto",
                        options=[
                            {"value": "auto", "label": "Auto-detect"},
                            {"value": "uplink_quality", "label": "Uplink Quality"},
                            {"value": "downlink_quality", "label": "Downlink Quality"},
                            {"value": "speaker_attribution", "label": "Speaker Attribution"},
                            {"value": "barge_in", "label": "Barge-in Detection"},
                            {"value": "conversational", "label": "Conversational Quality"},
                            {"value": "all", "label": "All Modes"},
                        ]),
            ConfigField("judge_backend", "select", "Judge LLM", "openai:gpt-4o-audio-preview",
                        options=[
                            {"value": "openai:gpt-4o-audio-preview", "label": "GPT-4o Audio"},
                            {"value": "openai:gpt-4o-mini-audio-preview", "label": "GPT-4o Mini Audio"},
                            {"value": "gemini:gemini-2.0-flash", "label": "Gemini 2.0 Flash"},
                            {"value": "anthropic:claude-sonnet-4-6", "label": "Claude Sonnet"},
                        ]),
            ConfigField("num_judges", "slider", "Number of Judges", 3,
                        min_val=1, max_val=7, step=2,
                        description="Odd number for majority voting"),
            ConfigField("pass_threshold", "slider", "Pass Threshold", 0.6,
                        min_val=0, max_val=1, step=0.05),
            ConfigField("system_prompt_override", "string", "System Prompt Override", "",
                        multiline=True,
                        description="Override default telephony judge prompt (leave empty for default)"),
        ],
        color="#FB923C",
    ))

    nodes.append(NodeTypeDef(
        type_id="eval_analysis",
        label="Evaluation & Analysis",
        category="evaluation",
        description="Combined evaluation engine: command match, LLM judge, WER, latency, barge-in",
        inputs=[
            PortDef("text_in", PortType.text, required=True, description="LLM response text"),
            PortDef("audio_in", PortType.audio, required=False, description="LLM response audio"),
        ],
        outputs=[PortDef("eval_out", PortType.evaluation)],
        config_fields=[
            ConfigField("evaluators", "select", "Evaluators", "command_match",
                        options=[
                            {"value": "command_match", "label": "Command Match"},
                            {"value": "llm_judge", "label": "LLM Judge"},
                            {"value": "wer", "label": "WER"},
                            {"value": "all", "label": "All"},
                        ]),
            ConfigField("pass_threshold", "slider", "Pass Threshold", 0.6,
                        min_val=0, max_val=1, step=0.05),
            ConfigField("enable_self_transcription", "boolean", "Self-Transcription", False,
                        description="Re-run STT on output audio to verify"),
            ConfigField("enable_latency_tracking", "boolean", "Track Latency", True),
            ConfigField("enable_barge_in_detection", "boolean", "Barge-in Detection", False),
        ],
        color="#FB923C",
    ))

    # -----------------------------------------------------------------------
    # CONTENT SAFETY EVALUATION BLOCKS
    # -----------------------------------------------------------------------
    _judge_backend_options = [
        {"value": "openai:gpt-4o", "label": "GPT-4o"},
        {"value": "openai:gpt-4o-mini", "label": "GPT-4o Mini"},
        {"value": "gemini:gemini-2.0-flash", "label": "Gemini 2.0 Flash"},
        {"value": "anthropic:claude-sonnet-4-6", "label": "Claude Sonnet"},
        {"value": "ollama:mistral", "label": "Ollama Mistral"},
    ]

    nodes.append(NodeTypeDef(
        type_id="safety_critical_eval",
        label="Safety-Critical Eval",
        category="evaluation",
        description="Agentic safety evaluation: vehicle safety, personal safety, child safety, emergency protocol",
        inputs=[
            PortDef("text_in", PortType.text, required=True, description="LLM response text to evaluate"),
            PortDef("audio_in", PortType.audio, required=False, description="Original audio (for context)"),
        ],
        outputs=[PortDef("eval_out", PortType.evaluation)],
        config_fields=[
            ConfigField("judge_backend", "select", "Judge LLM", "openai:gpt-4o",
                        options=_judge_backend_options),
            ConfigField("pass_threshold", "slider", "Pass Threshold", 0.6,
                        min_val=0, max_val=1, step=0.05,
                        description="Weighted average score threshold for pass"),
            ConfigField("weakest_link_threshold", "slider", "Weakest Link Threshold", 0.4,
                        min_val=0, max_val=1, step=0.05,
                        description="Any sub-agent below this = automatic fail"),
            ConfigField("user_query", "string", "User Query Context", "",
                        description="Original user query for context (optional)",
                        multiline=True),
        ],
        color="#FB923C",
    ))

    nodes.append(NodeTypeDef(
        type_id="compliance_eval",
        label="Compliance Eval",
        category="evaluation",
        description="Agentic compliance evaluation: legal, privacy, regulatory",
        inputs=[
            PortDef("text_in", PortType.text, required=True, description="LLM response text to evaluate"),
            PortDef("audio_in", PortType.audio, required=False, description="Original audio (for context)"),
        ],
        outputs=[PortDef("eval_out", PortType.evaluation)],
        config_fields=[
            ConfigField("judge_backend", "select", "Judge LLM", "openai:gpt-4o",
                        options=_judge_backend_options),
            ConfigField("pass_threshold", "slider", "Pass Threshold", 0.6,
                        min_val=0, max_val=1, step=0.05),
            ConfigField("weakest_link_threshold", "slider", "Weakest Link Threshold", 0.4,
                        min_val=0, max_val=1, step=0.05),
            ConfigField("user_query", "string", "User Query Context", "",
                        multiline=True),
        ],
        color="#FB923C",
    ))

    nodes.append(NodeTypeDef(
        type_id="trust_brand_eval",
        label="Trust & Brand Eval",
        category="evaluation",
        description="Agentic trust evaluation: misinformation, ethics/bias, brand safety",
        inputs=[
            PortDef("text_in", PortType.text, required=True, description="LLM response text to evaluate"),
            PortDef("audio_in", PortType.audio, required=False, description="Original audio (for context)"),
        ],
        outputs=[PortDef("eval_out", PortType.evaluation)],
        config_fields=[
            ConfigField("judge_backend", "select", "Judge LLM", "openai:gpt-4o",
                        options=_judge_backend_options),
            ConfigField("pass_threshold", "slider", "Pass Threshold", 0.6,
                        min_val=0, max_val=1, step=0.05),
            ConfigField("weakest_link_threshold", "slider", "Weakest Link Threshold", 0.4,
                        min_val=0, max_val=1, step=0.05),
            ConfigField("user_query", "string", "User Query Context", "",
                        multiline=True),
        ],
        color="#FB923C",
    ))

    nodes.append(NodeTypeDef(
        type_id="ux_quality_eval",
        label="UX Quality Eval",
        category="evaluation",
        description="Agentic UX evaluation: driver cognitive load, emotional intelligence",
        inputs=[
            PortDef("text_in", PortType.text, required=True, description="LLM response text to evaluate"),
            PortDef("audio_in", PortType.audio, required=False, description="Original audio (for context)"),
        ],
        outputs=[PortDef("eval_out", PortType.evaluation)],
        config_fields=[
            ConfigField("judge_backend", "select", "Judge LLM", "openai:gpt-4o",
                        options=_judge_backend_options),
            ConfigField("pass_threshold", "slider", "Pass Threshold", 0.6,
                        min_val=0, max_val=1, step=0.05),
            ConfigField("weakest_link_threshold", "slider", "Weakest Link Threshold", 0.4,
                        min_val=0, max_val=1, step=0.05),
            ConfigField("user_query", "string", "User Query Context", "",
                        multiline=True),
        ],
        color="#FB923C",
    ))

    # -----------------------------------------------------------------------
    # OUTPUT / SINK BLOCKS
    # -----------------------------------------------------------------------
    nodes.append(NodeTypeDef(
        type_id="text_output",
        label="Text Output",
        category="output",
        description="Display or capture text result",
        inputs=[PortDef("text_in", PortType.text)],
        outputs=[],
        config_fields=[
            ConfigField("label", "string", "Label", "Output"),
        ],
        color="#94A3B8",
    ))

    nodes.append(NodeTypeDef(
        type_id="audio_output",
        label="Audio Output",
        category="output",
        description="Save or play audio result",
        inputs=[PortDef("audio_in", PortType.audio)],
        outputs=[],
        config_fields=[
            ConfigField("label", "string", "Label", "Output"),
            ConfigField("save_to_file", "boolean", "Save to File", False),
            ConfigField("file_path", "string", "File Path", ""),
        ],
        color="#94A3B8",
    ))

    nodes.append(NodeTypeDef(
        type_id="eval_output",
        label="Eval Output",
        category="output",
        description="Display evaluation results",
        inputs=[PortDef("eval_in", PortType.evaluation)],
        outputs=[],
        config_fields=[
            ConfigField("label", "string", "Label", "Results"),
        ],
        color="#94A3B8",
    ))

    return {n.type_id: n for n in nodes}


# The global registry
NODE_REGISTRY: dict[str, NodeTypeDef] = _build_registry()


def get_node_type(type_id: str) -> NodeTypeDef:
    """Get a node type definition by ID. Raises KeyError if not found."""
    return NODE_REGISTRY[type_id]


def get_port_type(node_type_id: str, port_name: str, direction: str) -> PortType:
    """Get the PortType for a specific port on a node type.

    direction: "input" or "output"
    """
    node_def = NODE_REGISTRY[node_type_id]
    ports = node_def.inputs if direction == "input" else node_def.outputs
    for port in ports:
        if port.name == port_name:
            return port.port_type
    # Handle dynamic mixer inputs
    if node_def.dynamic_inputs and port_name.startswith("audio_in_"):
        return PortType.audio
    raise KeyError(f"Port {port_name!r} not found on {node_type_id} ({direction})")


def registry_to_dict() -> dict:
    """Serialize the registry for the frontend /node-types endpoint."""
    result = {"categories": CATEGORIES, "node_types": {}}
    for type_id, node_def in NODE_REGISTRY.items():
        result["node_types"][type_id] = {
            "type_id": node_def.type_id,
            "label": node_def.label,
            "category": node_def.category,
            "description": node_def.description,
            "color": node_def.color,
            "dynamic_inputs": node_def.dynamic_inputs,
            "inputs": [
                {"name": p.name, "type": p.port_type.value, "required": p.required, "description": p.description}
                for p in node_def.inputs
            ],
            "outputs": [
                {"name": p.name, "type": p.port_type.value, "description": p.description}
                for p in node_def.outputs
            ],
            "config_fields": [
                {
                    "name": f.name, "type": f.field_type, "label": f.label or f.name,
                    "default": f.default, "options": f.options,
                    "min": f.min_val, "max": f.max_val, "step": f.step,
                    "description": f.description, "multiline": f.multiline,
                }
                for f in node_def.config_fields
            ],
        }
    return result
