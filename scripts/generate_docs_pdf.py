#!/usr/bin/env python3
"""Generate comprehensive PDF documentation for the Audio LLM Test Platform."""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    KeepTogether, HRFlowable, ListFlowable, ListItem
)
from reportlab.lib import colors
import os
import datetime

# ── Colors ──────────────────────────────────────────────────────────────────

DARK_BG = HexColor("#1a1a2e")
ACCENT = HexColor("#0f3460")
HIGHLIGHT = HexColor("#e94560")
LIGHT_BG = HexColor("#f5f5f5")
TABLE_HEADER = HexColor("#16213e")
TABLE_ALT = HexColor("#eef2f7")
BORDER = HexColor("#c0c0c0")
LINK_BLUE = HexColor("#2563eb")
METRIC_GREEN = HexColor("#059669")
METRIC_RED = HexColor("#dc2626")
METRIC_AMBER = HexColor("#d97706")

# ── Styles ──────────────────────────────────────────────────────────────────

styles = getSampleStyleSheet()

styles.add(ParagraphStyle(
    "CoverTitle", parent=styles["Title"],
    fontSize=32, leading=40, textColor=DARK_BG,
    spaceAfter=6, alignment=TA_CENTER, fontName="Helvetica-Bold",
))
styles.add(ParagraphStyle(
    "CoverSubtitle", parent=styles["Normal"],
    fontSize=14, leading=20, textColor=ACCENT,
    spaceAfter=30, alignment=TA_CENTER, fontName="Helvetica",
))
styles.add(ParagraphStyle(
    "SectionHead", parent=styles["Heading1"],
    fontSize=20, leading=26, textColor=DARK_BG,
    spaceBefore=24, spaceAfter=10, fontName="Helvetica-Bold",
    borderWidth=0, borderPadding=0,
))
styles.add(ParagraphStyle(
    "SubHead", parent=styles["Heading2"],
    fontSize=15, leading=20, textColor=ACCENT,
    spaceBefore=16, spaceAfter=8, fontName="Helvetica-Bold",
))
styles.add(ParagraphStyle(
    "Sub3", parent=styles["Heading3"],
    fontSize=12, leading=16, textColor=HexColor("#374151"),
    spaceBefore=12, spaceAfter=6, fontName="Helvetica-Bold",
))
styles.add(ParagraphStyle(
    "Body", parent=styles["Normal"],
    fontSize=10, leading=14, textColor=HexColor("#1f2937"),
    spaceAfter=8, alignment=TA_JUSTIFY, fontName="Helvetica",
))
styles.add(ParagraphStyle(
    "BodySmall", parent=styles["Normal"],
    fontSize=9, leading=12, textColor=HexColor("#374151"),
    spaceAfter=4, fontName="Helvetica",
))
styles.add(ParagraphStyle(
    "CodeBlock", parent=styles["Normal"],
    fontSize=8.5, leading=11, textColor=HexColor("#1e293b"),
    fontName="Courier", backColor=LIGHT_BG,
    leftIndent=12, rightIndent=12,
    spaceBefore=4, spaceAfter=4,
    borderWidth=0.5, borderColor=BORDER, borderPadding=6,
))
styles.add(ParagraphStyle(
    "BulletBody", parent=styles["Normal"],
    fontSize=10, leading=14, textColor=HexColor("#1f2937"),
    spaceAfter=3, fontName="Helvetica",
    leftIndent=20, bulletIndent=8,
))
styles.add(ParagraphStyle(
    "TableCell", parent=styles["Normal"],
    fontSize=8.5, leading=11, fontName="Helvetica",
))
styles.add(ParagraphStyle(
    "TableHeader", parent=styles["Normal"],
    fontSize=8.5, leading=11, fontName="Helvetica-Bold", textColor=white,
))
styles.add(ParagraphStyle(
    "MetricLabel", parent=styles["Normal"],
    fontSize=9, leading=12, textColor=HexColor("#6b7280"),
    fontName="Helvetica",
))
styles.add(ParagraphStyle(
    "MetricValue", parent=styles["Normal"],
    fontSize=16, leading=20, textColor=DARK_BG,
    fontName="Helvetica-Bold",
))
styles.add(ParagraphStyle(
    "FooterStyle", parent=styles["Normal"],
    fontSize=8, textColor=HexColor("#9ca3af"),
    fontName="Helvetica", alignment=TA_CENTER,
))


def hr():
    return HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=10, spaceBefore=6)


def bullet(text):
    return Paragraph(f"<bullet>&bull;</bullet> {text}", styles["BulletBody"])


def make_table(headers, rows, col_widths=None):
    """Create a styled table."""
    header_cells = [Paragraph(h, styles["TableHeader"]) for h in headers]
    data = [header_cells]
    for row in rows:
        data.append([Paragraph(str(c), styles["TableCell"]) for c in row])

    t = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), TABLE_ALT))
    t.setStyle(TableStyle(style_cmds))
    return t


def metric_box(label, value, color=DARK_BG):
    """Create a mini metric display."""
    return [
        Paragraph(label, styles["MetricLabel"]),
        Paragraph(f'<font color="{color}">{value}</font>', styles["MetricValue"]),
    ]


# ── Page Template ───────────────────────────────────────────────────────────

def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(HexColor("#9ca3af"))
    canvas.drawCentredString(
        letter[0] / 2, 0.5 * inch,
        f"Audio LLM Test Platform  |  Technical Documentation  |  Page {doc.page}"
    )
    canvas.restoreState()


# ── Build Document ──────────────────────────────────────────────────────────

def build_pdf(output_path):
    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
        leftMargin=0.85 * inch, rightMargin=0.85 * inch,
        title="Audio LLM Test Platform - Technical Documentation",
        author="Audio LLM Test Team",
    )
    story = []

    # ════════════════════════════════════════════════════════════════════════
    # COVER PAGE
    # ════════════════════════════════════════════════════════════════════════
    story.append(Spacer(1, 2 * inch))
    story.append(Paragraph("Audio LLM Test Platform", styles["CoverTitle"]))
    story.append(Paragraph("Technical Documentation &amp; Performance Analysis Guide", styles["CoverSubtitle"]))
    story.append(hr())
    story.append(Spacer(1, 0.5 * inch))
    story.append(Paragraph(
        "A comprehensive platform for evaluating large language model speech understanding "
        "under realistic automotive cabin conditions. Supports multi-backend LLM evaluation, "
        "9 TTS providers, professional audio DSP, and rigorous statistical analysis.",
        styles["Body"]
    ))
    story.append(Spacer(1, 0.3 * inch))

    meta_data = [
        ["Version", "0.1.0"],
        ["Date", datetime.date.today().strftime("%B %d, %Y")],
        ["Stack", "FastAPI + React + PostgreSQL + Redis"],
        ["License", "Proprietary"],
    ]
    meta_table = Table(
        [[Paragraph(r[0], styles["TableCell"]),
          Paragraph(r[1], styles["TableCell"])] for r in meta_data],
        colWidths=[1.5 * inch, 3.5 * inch],
    )
    meta_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_BG),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(meta_table)
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # TABLE OF CONTENTS
    # ════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Table of Contents", styles["SectionHead"]))
    story.append(hr())
    toc_items = [
        "1. System Architecture Overview",
        "2. Audio DSP Pipeline",
        "3. Evaluation Pipelines",
        "4. LLM Backends",
        "5. Text-to-Speech Providers",
        "6. Evaluation System",
        "7. Test Execution Engine",
        "8. Statistical Analysis Framework",
        "9. Performance Metrics &amp; KPIs",
        "10. API Reference",
        "11. Database Schema",
        "12. Deployment &amp; Infrastructure",
        "13. Recommended Performance Statistics",
    ]
    for item in toc_items:
        story.append(Paragraph(item, ParagraphStyle(
            "TOC", parent=styles["Body"], fontSize=11, leading=18,
            leftIndent=20, textColor=ACCENT,
        )))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # 1. SYSTEM ARCHITECTURE
    # ════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("1. System Architecture Overview", styles["SectionHead"]))
    story.append(hr())
    story.append(Paragraph(
        "The Audio LLM Test Platform is a full-stack application designed to rigorously evaluate "
        "how large language models understand spoken commands under degraded acoustic conditions "
        "typical of automotive cabins (road noise, echo, frequency distortion).",
        styles["Body"]
    ))
    story.append(Paragraph("Core Components", styles["SubHead"]))

    arch_rows = [
        ["FastAPI Backend", "Async REST API + WebSocket, Pydantic validation, SQLAlchemy ORM"],
        ["React Frontend", "TypeScript SPA with Tailwind CSS, React Query, Recharts"],
        ["PostgreSQL 16", "Persistent storage for test suites, results, speech corpus"],
        ["Redis 7", "arq async task queue for background TTS synthesis and test execution"],
        ["Audio DSP Engine", "NumPy/SciPy signal processing: noise, filters, echo, mixing"],
        ["Evaluation Engine", "Command matching, LLM-as-judge, WER/CER metrics"],
        ["Statistics Module", "ANOVA, McNemar's test, Wilcoxon signed-rank, Holm-Bonferroni"],
    ]
    story.append(make_table(["Component", "Description"], arch_rows,
                            col_widths=[1.8 * inch, 4.7 * inch]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Data Flow", styles["SubHead"]))
    story.append(Paragraph(
        "1. <b>Corpus Seeding</b> - Text prompts (Harvard sentences, navigation/media/climate "
        "commands) are loaded into the database with expected intents and actions.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "2. <b>Speech Synthesis</b> - TTS providers generate audio samples from corpus entries "
        "across diverse voices (gender, accent, language).",
        styles["Body"]
    ))
    story.append(Paragraph(
        "3. <b>Test Suite Creation</b> - Sweep configurations define a Cartesian product of "
        "parameters: SNR levels, echo settings, noise types, pipelines, and LLM backends.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "4. <b>Test Execution</b> - The scheduler processes test cases with rate limiting, "
        "checkpointing, and bounded concurrency. Audio is degraded and sent to LLMs.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "5. <b>Evaluation</b> - Responses are scored via command matching or LLM judge. "
        "Results are stored with full diagnostic data.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "6. <b>Statistical Analysis</b> - ANOVA, pairwise comparisons, and effect-size "
        "calculations identify significant performance differences.",
        styles["Body"]
    ))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # 2. AUDIO DSP PIPELINE
    # ════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("2. Audio DSP Pipeline", styles["SectionHead"]))
    story.append(hr())
    story.append(Paragraph(
        "The DSP pipeline provides professional-grade audio signal processing to simulate "
        "realistic automotive cabin conditions. All audio is processed as mono float64 "
        "samples normalized to [-1.0, 1.0].",
        styles["Body"]
    ))

    story.append(Paragraph("2.1 AudioBuffer", styles["SubHead"]))
    story.append(Paragraph(
        "The immutable <font face='Courier'>AudioBuffer</font> dataclass is the fundamental "
        "unit of audio throughout the system. It stores float64 samples with a sample rate "
        "and provides methods for resampling (polyphase), normalization (RMS/peak), trimming, "
        "and looping. Stereo input is automatically downmixed to mono on construction.",
        styles["Body"]
    ))

    buf_props = [
        ["duration_s", "Duration in seconds (len(samples) / sample_rate)"],
        ["rms", "Root-mean-square amplitude"],
        ["peak", "Maximum absolute sample value"],
        ["rms_db", "RMS level in decibels (20 * log10(rms))"],
    ]
    story.append(make_table(["Property", "Description"], buf_props,
                            col_widths=[1.5 * inch, 5 * inch]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("2.2 Noise Generation", styles["SubHead"]))
    noise_rows = [
        ["white_noise()", "Gaussian white noise (flat spectrum)", "Baseline reference"],
        ["pink_noise()", "1/f spectrum via FFT shaping", "Broadband road noise"],
        ["pink_noise_filtered()", "Pink + Butterworth LPF (default 100 Hz)", "Car cabin rumble"],
        ["babble_noise()", "Sum of 6 pink streams, normalized", "Multi-talker babble"],
        ["noise_from_file()", "Load WAV/FLAC, resample &amp; loop", "Real-world recordings"],
    ]
    story.append(make_table(["Function", "Algorithm", "Use Case"], noise_rows,
                            col_widths=[1.8 * inch, 2.5 * inch, 2.2 * inch]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("2.3 Filtering (IIR Biquad)", styles["SubHead"]))
    story.append(Paragraph(
        "Filters use second-order sections (SOS) for numerical stability. "
        "Coefficients follow the Audio EQ Cookbook. A <font face='Courier'>FilterChain</font> "
        "cascades multiple filters via <font face='Courier'>scipy.signal.sosfilt</font>. "
        "Nyquist validation rejects filter frequencies above half the sample rate.",
        styles["Body"]
    ))
    filter_rows = [
        ["lpf / hpf", "Low-pass / high-pass (Butterworth)", "frequency, Q"],
        ["peaking", "Parametric EQ bell curve", "frequency, Q, gain_db"],
        ["lowshelf / highshelf", "Shelf filters", "frequency, Q, gain_db"],
    ]
    story.append(make_table(["Type", "Description", "Parameters"], filter_rows,
                            col_widths=[1.5 * inch, 3 * inch, 2 * inch]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("2.4 Echo Path Simulation", styles["SubHead"]))
    story.append(Paragraph(
        "The <font face='Courier'>EchoPath</font> models speaker-to-microphone acoustic "
        "feedback in a vehicle cabin. It applies a configurable delay (0-500 ms), gain "
        "(-100 to 0 dB), and an EQ filter chain representing the cabin frequency response. "
        "The processed echo signal is mixed into the microphone input at the correct time "
        "alignment.",
        styles["Body"]
    ))

    story.append(Paragraph("2.5 SNR Mixing &amp; Soft Clipping", styles["SubHead"]))
    story.append(Paragraph(
        "The mixer scales noise relative to speech to achieve the target SNR in dB "
        "(SNR = 20 * log10(RMS_speech / RMS_noise)). A piece-wise soft-clipping function "
        "prevents hard-clipping artifacts: samples below 0.95 pass through unchanged, "
        "while samples above 0.95 are compressed via tanh into the (0.95, 1.0] range. "
        "This preserves true SNR for well-behaved signals while preventing digital clipping.",
        styles["Body"]
    ))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # 3. EVALUATION PIPELINES
    # ════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("3. Evaluation Pipelines", styles["SectionHead"]))
    story.append(hr())

    story.append(Paragraph("Pipeline A: Direct Audio Input", styles["SubHead"]))
    story.append(Paragraph(
        "Clean speech is degraded with noise (at target SNR), echo is applied, and the "
        "resulting audio is sent directly to a multimodal LLM (GPT-4o or Gemini) as "
        "base64-encoded PCM16. The LLM processes the raw audio and returns a text response. "
        "This pipeline tests the LLM's native audio understanding capability.",
        styles["Body"]
    ))
    pipeline_a_flow = [
        ["1", "Load clean speech AudioBuffer from corpus"],
        ["2", "Generate noise (pink_lpf, white, babble, or file-based)"],
        ["3", "Mix at target SNR (e.g., -5 dB, 0 dB, 10 dB, 20 dB)"],
        ["4", "Apply echo path (delay + gain + EQ cascade)"],
        ["5", "Encode to base64 PCM16 (OpenAI) or WAV bytes (Gemini)"],
        ["6", "Send to multimodal LLM with system prompt"],
        ["7", "Receive and evaluate text response"],
    ]
    story.append(make_table(["Step", "Operation"], pipeline_a_flow,
                            col_widths=[0.5 * inch, 6 * inch]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Pipeline B: ASR then Text", styles["SubHead"]))
    story.append(Paragraph(
        "Same audio degradation as Pipeline A, but the audio is first transcribed via "
        "Whisper ASR. The transcript text is then sent to any LLM backend (including "
        "text-only models like Claude or Ollama). This pipeline measures the combined "
        "ASR + LLM performance and enables testing with non-audio LLMs.",
        styles["Body"]
    ))
    pipeline_b_flow = [
        ["1-4", "Same degradation as Pipeline A"],
        ["5", "Transcribe via Whisper (local or API mode)"],
        ["6", "Calculate Word Error Rate (WER) vs. original text"],
        ["7", "Send transcript to text-based LLM"],
        ["8", "Receive and evaluate text response"],
    ]
    story.append(make_table(["Step", "Operation"], pipeline_b_flow,
                            col_widths=[0.5 * inch, 6 * inch]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Pipeline Comparison Value", styles["Sub3"]))
    story.append(Paragraph(
        "Comparing Pipeline A vs. Pipeline B for the same audio conditions reveals whether "
        "native audio understanding outperforms the traditional ASR-then-NLU approach, and "
        "at which degradation levels one overtakes the other.",
        styles["Body"]
    ))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # 4. LLM BACKENDS
    # ════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("4. LLM Backends", styles["SectionHead"]))
    story.append(hr())
    story.append(Paragraph(
        "The platform supports four LLM backends through a common protocol interface. "
        "Each backend defines its rate limits, audio support capability, and query methods.",
        styles["Body"]
    ))

    llm_rows = [
        ["OpenAI GPT-4o", "Yes", "500 RPM / 50 conc.", "Native audio input, 24kHz PCM16"],
        ["Google Gemini", "Yes", "1000 RPM / 100 conc.", "WAV bytes input, high throughput"],
        ["Anthropic Claude", "No", "100 RPM / 20 conc.", "Text-only, requires Pipeline B"],
        ["Ollama (local)", "No", "10000 RPM / 100 conc.", "Local inference, any open model"],
    ]
    story.append(make_table(
        ["Backend", "Audio In", "Rate Limits", "Notes"], llm_rows,
        col_widths=[1.5 * inch, 0.8 * inch, 1.8 * inch, 2.4 * inch]
    ))
    story.append(Spacer(1, 10))

    story.append(Paragraph("LLM Response Structure", styles["Sub3"]))
    story.append(Paragraph(
        "Every LLM query returns an <font face='Courier'>LLMResponse</font> containing: "
        "response text, optional audio output (GPT-4o), latency in milliseconds, "
        "input/output token counts, and the raw API response for debugging.",
        styles["Body"]
    ))

    story.append(Paragraph("Whisper ASR Backend", styles["Sub3"]))
    story.append(Paragraph(
        "Whisper operates in two modes: <b>local</b> (openai-whisper package, runs on CPU/GPU) "
        "and <b>API</b> (OpenAI Whisper API endpoint). The local mode is preferred for "
        "high-throughput testing as it avoids API rate limits and latency.",
        styles["Body"]
    ))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # 5. TTS PROVIDERS
    # ════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("5. Text-to-Speech Providers", styles["SectionHead"]))
    story.append(hr())
    story.append(Paragraph(
        "Nine TTS providers are available, ranging from free local engines to premium "
        "cloud services. The <font face='Courier'>VoiceCatalog</font> aggregates voices "
        "across all providers and supports diverse voice set sampling (round-robin across "
        "gender, age, accent, and provider).",
        styles["Body"]
    ))

    tts_rows = [
        ["OpenAI TTS", "Cloud", "Yes", "24 kHz", "Premium", "6 voices (alloy, echo, fable, onyx, nova, shimmer)"],
        ["ElevenLabs", "Cloud", "Yes", "16 kHz", "Premium", "Neural voices, highest quality, expensive"],
        ["Google Cloud", "Cloud", "Yes", "24 kHz", "High", "Extensive language coverage"],
        ["Microsoft Edge", "Cloud", "No", "Variable", "High", "33 neural voices, free, multilingual"],
        ["Piper", "Local", "No", "22.05 kHz", "Medium", "Fast on-device, 18 voice presets"],
        ["Coqui TTS", "Local", "No", "Config.", "High", "Multi-speaker, XTTS v2, emotion control"],
        ["Bark (Suno)", "Local", "No", "24 kHz", "High", "19 speakers, 8 languages, sound effects"],
        ["gTTS", "Cloud", "No", "16 kHz", "Low", "Google Translate TTS, 21 languages, basic"],
        ["eSpeak", "Local", "No", "Variable", "Low", "System TTS via pyttsx3, robotic quality"],
    ]
    story.append(make_table(
        ["Provider", "Type", "API Key", "Rate", "Quality", "Notes"], tts_rows,
        col_widths=[1.1 * inch, 0.6 * inch, 0.7 * inch, 0.7 * inch, 0.7 * inch, 2.7 * inch]
    ))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Voice Diversity Sampling", styles["Sub3"]))
    story.append(Paragraph(
        "The <font face='Courier'>get_diverse_voice_set(count)</font> method ensures test "
        "coverage across demographic dimensions. It groups voices by (gender, age_group, accent) "
        "and samples round-robin to maximize diversity. This prevents bias toward any single "
        "voice characteristic in aggregate results.",
        styles["Body"]
    ))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # 6. EVALUATION SYSTEM
    # ════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("6. Evaluation System", styles["SectionHead"]))
    story.append(hr())

    story.append(Paragraph("6.1 Command Match Evaluator", styles["SubHead"]))
    story.append(Paragraph(
        "Used for structured commands with known expected actions (e.g., 'navigate to downtown'). "
        "Produces a score from 0.0 to 1.0 using three independent methods, taking the best:",
        styles["Body"]
    ))
    eval_methods = [
        ["Exact Match", "Word-boundary regex match after normalization", "1.0 or 0.0"],
        ["Fuzzy Match", "Levenshtein distance ratio (fuzz.ratio)", "0.0 - 1.0"],
        ["Keyword Match", "Expected keywords present (minus stop words)", "0.0 - 1.0"],
    ]
    story.append(make_table(["Method", "Algorithm", "Score Range"], eval_methods,
                            col_widths=[1.3 * inch, 3.5 * inch, 1.7 * inch]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "<b>Negation Detection:</b> Multi-language patterns (en, de, fr, es) detect negated "
        "responses (e.g., 'I cannot navigate'). Negated responses receive a penalty multiplier. "
        "<b>Stop Words:</b> Language-specific stop word lists (en, de, fr, es, ja) prevent "
        "articles and prepositions from inflating keyword scores.",
        styles["Body"]
    ))

    story.append(Paragraph("6.2 LLM Judge Evaluator", styles["SubHead"]))
    story.append(Paragraph(
        "For open-ended responses without a single correct answer, a separate LLM judges "
        "the quality on a 1-5 scale. Multiple independent judges (default: 3) vote, and the "
        "median score is used for robustness. Scores are normalized from [1, 5] to [0.0, 1.0]. "
        "The even-length median correctly averages the two middle values.",
        styles["Body"]
    ))

    judge_scale = [
        ["1", "Completely wrong or irrelevant response"],
        ["2", "Partially relevant but fundamentally incorrect"],
        ["3", "Acceptable - captures the gist but misses details"],
        ["4", "Good - correct response with minor imperfections"],
        ["5", "Perfect - exactly matches expected behavior"],
    ]
    story.append(make_table(["Score", "Meaning"], judge_scale,
                            col_widths=[0.8 * inch, 5.7 * inch]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("6.3 ASR Metrics", styles["SubHead"]))
    story.append(Paragraph(
        "<b>Word Error Rate (WER)</b> measures ASR transcript accuracy via Levenshtein "
        "distance on word sequences: WER = (S + D + I) / N, where S = substitutions, "
        "D = deletions, I = insertions, N = reference word count. "
        "<b>Character Error Rate (CER)</b> uses the same formula on individual characters, "
        "useful for languages without clear word boundaries (e.g., Japanese, Chinese).",
        styles["Body"]
    ))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # 7. TEST EXECUTION ENGINE
    # ════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("7. Test Execution Engine", styles["SectionHead"]))
    story.append(hr())

    story.append(Paragraph("7.1 Scheduler", styles["SubHead"]))
    story.append(Paragraph(
        "The <font face='Courier'>TestScheduler</font> orchestrates parallel test execution "
        "with per-backend rate limiting, bounded concurrency (default 50 workers), and "
        "configurable timeout (default 120s per test case). It uses asyncio semaphores for "
        "concurrency control and integrates with the rate limiter for API throttling.",
        styles["Body"]
    ))

    story.append(Paragraph("7.2 Checkpointing &amp; Resume", styles["SubHead"]))
    story.append(Paragraph(
        "The <font face='Courier'>CheckpointStore</font> persists completed test-case hashes "
        "to a JSONL file using append-only writes. On restart, the scheduler loads completed "
        "hashes and skips them. Each test case has a deterministic hash computed from all "
        "parameters (SNR, delay, backend, corpus entry, voice, pipeline), ensuring "
        "idempotent re-execution.",
        styles["Body"]
    ))

    story.append(Paragraph("7.3 Rate Limiting", styles["SubHead"]))
    story.append(Paragraph(
        "The <font face='Courier'>TokenBucketRateLimiter</font> enforces per-backend "
        "request rate limits using an async context manager. It maintains a token bucket "
        "with configurable requests-per-minute and maximum concurrent requests via an "
        "asyncio semaphore. Tokens are replenished at a constant interval to ensure "
        "smooth request distribution.",
        styles["Body"]
    ))

    story.append(Paragraph("7.4 Background Workers (arq)", styles["SubHead"]))
    story.append(Paragraph(
        "Two background job types run via the arq task queue: "
        "<b>run_test_suite</b> executes a complete test run (load config, initialize backends, "
        "run scheduler, persist results), and "
        "<b>synthesize_speech_batch</b> generates TTS audio for all pending speech samples. "
        "Workers broadcast progress via WebSocket for real-time frontend updates.",
        styles["Body"]
    ))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # 8. STATISTICAL ANALYSIS
    # ════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("8. Statistical Analysis Framework", styles["SectionHead"]))
    story.append(hr())
    story.append(Paragraph(
        "The statistics module provides rigorous analysis tools for comparing LLM performance "
        "across conditions. All tests account for multiple comparisons and report effect sizes.",
        styles["Body"]
    ))

    story.append(Paragraph("8.1 Group-Level Accuracy", styles["SubHead"]))
    story.append(Paragraph(
        "<font face='Courier'>accuracy_by_group()</font> computes mean score, pass rate, "
        "standard deviation, and count for any grouping dimension (backend, SNR, pipeline, etc.). "
        "Pass-rate confidence intervals use the Wilson score method, which is accurate even "
        "for small samples and extreme proportions (unlike the normal approximation).",
        styles["Body"]
    ))

    story.append(Paragraph("8.2 Pairwise Backend Comparison", styles["SubHead"]))
    story.append(Paragraph(
        "<font face='Courier'>pairwise_backend_comparison()</font> performs two statistical "
        "tests for every pair of backends:",
        styles["Body"]
    ))
    stat_tests = [
        ["McNemar's Test", "Binary (pass/fail)", "Whether two backends disagree significantly on which items they pass/fail", "Chi-squared"],
        ["Wilcoxon Signed-Rank", "Continuous (scores)", "Whether paired score distributions differ significantly", "Non-parametric"],
    ]
    story.append(make_table(
        ["Test", "Data Type", "Hypothesis", "Method"], stat_tests,
        col_widths=[1.5 * inch, 1.2 * inch, 2.5 * inch, 1.3 * inch]
    ))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "<b>Holm-Bonferroni Correction:</b> When comparing k backends, there are k*(k-1)/2 "
        "pairs. Raw p-values are adjusted using the Holm-Bonferroni step-down procedure to "
        "control the family-wise error rate. Adjusted p-values are reported in "
        "<font face='Courier'>mcnemar_p_adjusted</font> and "
        "<font face='Courier'>wilcoxon_p_adjusted</font> columns.",
        styles["Body"]
    ))

    story.append(Paragraph("8.3 ANOVA &amp; Effect Sizes", styles["SubHead"]))
    story.append(Paragraph(
        "<font face='Courier'>parameter_effects_anova()</font> runs one-way ANOVA for each "
        "experimental factor (SNR, noise type, echo delay, pipeline, backend) and reports "
        "the F-statistic, p-value, and eta-squared (effect size). Eta-squared indicates "
        "the proportion of variance explained by each factor:",
        styles["Body"]
    ))
    eta_rows = [
        ["Small", "< 0.01", "Factor has minimal practical impact"],
        ["Medium", "0.01 - 0.06", "Factor has moderate practical impact"],
        ["Large", "> 0.06", "Factor has substantial practical impact"],
    ]
    story.append(make_table(["Effect Size", "Eta-squared", "Interpretation"], eta_rows,
                            col_widths=[1.2 * inch, 1.3 * inch, 4 * inch]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("8.4 Data Export", styles["SubHead"]))
    story.append(Paragraph(
        "Results can be exported as CSV, Parquet (if pyarrow is installed), or JSON for "
        "external analysis in R, Julia, or other tools. The pivot heatmap endpoint generates "
        "2D aggregation tables for any pair of parameters.",
        styles["Body"]
    ))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # 9. PERFORMANCE METRICS & KPIs
    # ════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("9. Performance Metrics &amp; KPIs", styles["SectionHead"]))
    story.append(hr())
    story.append(Paragraph(
        "The following metrics and key performance indicators should be tracked to fully "
        "characterize system and model performance. These are organized into categories "
        "reflecting different dimensions of quality.",
        styles["Body"]
    ))

    story.append(Paragraph("9.1 Accuracy &amp; Correctness", styles["SubHead"]))
    acc_metrics = [
        ["Overall Pass Rate", "%", "Fraction of test cases scoring above threshold (0.6)", "Primary success metric"],
        ["Mean Evaluation Score", "0-1", "Average evaluator score across all test cases", "Continuous quality signal"],
        ["Command Match Accuracy", "%", "Pass rate for structured commands only", "Intent recognition quality"],
        ["LLM Judge Score", "1-5", "Median judge rating for open-ended responses", "Subjective quality"],
        ["Word Error Rate (WER)", "%", "ASR transcript accuracy (Pipeline B)", "Transcription fidelity"],
        ["Character Error Rate", "%", "Character-level accuracy (CJK languages)", "Fine-grained ASR quality"],
    ]
    story.append(make_table(
        ["Metric", "Unit", "Definition", "Purpose"], acc_metrics,
        col_widths=[1.6 * inch, 0.5 * inch, 2.7 * inch, 1.7 * inch]
    ))
    story.append(Spacer(1, 12))

    story.append(Paragraph("9.2 Robustness Under Degradation", styles["SubHead"]))
    robust_metrics = [
        ["SNR-50 (dB)", "The SNR level at which pass rate drops to 50%", "Noise tolerance threshold"],
        ["Degradation Slope", "Pass-rate change per dB of SNR reduction", "Graceful degradation rate"],
        ["Echo Tolerance", "Max echo delay/gain where pass rate stays above 80%", "Echo resilience"],
        ["Noise-Type Sensitivity", "Variance of pass rates across noise types at fixed SNR", "Noise-type robustness"],
        ["Pipeline A vs B Delta", "Score difference between direct audio and ASR pipeline", "Native audio advantage"],
    ]
    story.append(make_table(
        ["Metric", "Definition", "Purpose"], robust_metrics,
        col_widths=[1.7 * inch, 3 * inch, 1.8 * inch]
    ))
    story.append(Spacer(1, 12))

    story.append(Paragraph("9.3 Latency &amp; Throughput", styles["SubHead"]))
    lat_metrics = [
        ["LLM Latency (ms)", "Time from API request to response", "p50, p95, p99"],
        ["Total Latency (ms)", "End-to-end: audio encode + API + decode", "p50, p95, p99"],
        ["ASR Latency (ms)", "Whisper transcription time (Pipeline B)", "p50, p95, p99"],
        ["Throughput (tests/min)", "Test cases completed per minute", "Max sustained rate"],
        ["Token Usage (in/out)", "Input and output tokens per request", "Mean, total, cost est."],
        ["Timeout Rate (%)", "Fraction of test cases exceeding timeout", "Reliability indicator"],
    ]
    story.append(make_table(
        ["Metric", "Definition", "Recommended Aggregation"], lat_metrics,
        col_widths=[1.7 * inch, 2.8 * inch, 2 * inch]
    ))
    story.append(Spacer(1, 12))

    story.append(Paragraph("9.4 Voice &amp; Language Coverage", styles["SubHead"]))
    cov_metrics = [
        ["Voice Gender Parity", "Pass rate difference between male vs. female voices", "Detect gender bias"],
        ["Accent Sensitivity", "Score variance across accents at fixed SNR", "Accent fairness"],
        ["Language Coverage", "Pass rates per language (en, de, fr, es, ja, etc.)", "Multilingual readiness"],
        ["TTS Provider Effect", "Score variance attributable to TTS provider", "Isolate voice quality impact"],
        ["Age Group Sensitivity", "Score differences across young/middle/senior voices", "Age bias detection"],
    ]
    story.append(make_table(
        ["Metric", "Definition", "Purpose"], cov_metrics,
        col_widths=[1.7 * inch, 3 * inch, 1.8 * inch]
    ))
    story.append(PageBreak())

    story.append(Paragraph("9.5 Statistical Significance", styles["SubHead"]))
    sig_metrics = [
        ["ANOVA F-statistic", "Per-factor F-stat from one-way ANOVA", "Identifies factors with significant effect on scores"],
        ["ANOVA p-value", "Significance of each factor's effect", "Factors below alpha=0.05 are statistically significant"],
        ["Eta-squared", "Proportion of total variance explained by factor", "Practical importance of each factor"],
        ["McNemar p-adjusted", "Holm-Bonferroni adjusted pairwise p-value (binary)", "Controls family-wise error rate for backend comparisons"],
        ["Wilcoxon p-adjusted", "Holm-Bonferroni adjusted pairwise p-value (continuous)", "Non-parametric comparison with multiple-testing correction"],
        ["Wilson CI Width", "Width of 95% confidence interval on pass rate", "Precision of estimated pass rate"],
    ]
    story.append(make_table(
        ["Metric", "Source", "Interpretation"], sig_metrics,
        col_widths=[1.7 * inch, 2.5 * inch, 2.3 * inch]
    ))
    story.append(Spacer(1, 12))

    story.append(Paragraph("9.6 Cost &amp; Efficiency", styles["SubHead"]))
    cost_metrics = [
        ["Cost per Test Case", "Average API cost per individual test execution", "USD"],
        ["Cost per 1000 Tests", "Projected cost for a standard sweep", "USD"],
        ["Token Efficiency", "Score achieved per 1000 tokens consumed", "Score / kToken"],
        ["Quality-Cost Ratio", "Pass rate normalized by cost per test", "Quality per dollar"],
        ["TTS Cost per Hour", "Speech synthesis cost per hour of generated audio", "USD / hr"],
    ]
    story.append(make_table(
        ["Metric", "Definition", "Unit"], cost_metrics,
        col_widths=[1.7 * inch, 3.3 * inch, 1.5 * inch]
    ))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # 10. API REFERENCE
    # ════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("10. API Reference", styles["SectionHead"]))
    story.append(hr())

    api_groups = [
        ("Speech Corpus - /api/speech", [
            ["POST /voices/sync", "Sync voices from all active TTS providers into database"],
            ["GET /voices", "List voices (filter: provider, gender, language, accent)"],
            ["GET /corpus", "List corpus entries (filter: category, language)"],
            ["POST /corpus/seed", "Seed Harvard sentences + command templates"],
            ["POST /synthesize", "Queue batch TTS generation"],
            ["GET /samples/{id}/audio", "Stream generated speech audio file"],
        ]),
        ("Test Configuration - /api/tests", [
            ["POST /suites", "Create test suite from sweep config (Cartesian expansion)"],
            ["GET /suites", "List all test suites"],
            ["GET /suites/{id}", "Get suite details with test cases"],
            ["POST /suites/preview", "Preview case count without creating"],
            ["DELETE /suites/{id}", "Delete suite and all test cases"],
        ]),
        ("Execution - /api/runs", [
            ["POST /", "Launch test run (enqueue background worker)"],
            ["GET /", "List all runs"],
            ["GET /{id}", "Get run status and progress counters"],
            ["DELETE /{id}", "Cancel running test"],
        ]),
        ("Results - /api/results", [
            ["GET /", "Query results (filter: run, suite, backend, pipeline, SNR, pass)"],
            ["GET /{id}/stats", "Statistical analysis (accuracy, ANOVA, pairwise)"],
            ["GET /{id}/heatmap", "2D pivot table (row_param x col_param)"],
            ["GET /{id}/export", "Export CSV / Parquet / JSON"],
            ["GET /{id}/cases/{case_id}/audio", "Stream test audio (clean/degraded/echo)"],
        ]),
        ("WebSocket - /api/ws", [
            ["WS /runs/{id}", "Real-time progress, results, errors, heartbeat"],
        ]),
        ("Settings - /api/settings", [
            ["GET /", "Read masked API keys and configuration"],
            ["PATCH /", "Update API keys (persisted to .env file)"],
        ]),
    ]

    for group_name, endpoints in api_groups:
        story.append(Paragraph(group_name, styles["SubHead"]))
        story.append(make_table(
            ["Endpoint", "Description"], endpoints,
            col_widths=[2.2 * inch, 4.3 * inch]
        ))
        story.append(Spacer(1, 8))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # 11. DATABASE SCHEMA
    # ════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("11. Database Schema", styles["SectionHead"]))
    story.append(hr())

    story.append(Paragraph("Speech Corpus Tables", styles["SubHead"]))
    speech_tables = [
        ["voices", "id, provider, voice_id, name, gender, age_group, accent, language, sample_rate"],
        ["corpus_entries", "id, text, category, language, expected_intent, expected_action"],
        ["speech_samples", "id, voice_id, corpus_entry_id, file_path, status, duration_s, sample_rate"],
    ]
    story.append(make_table(["Table", "Key Columns"], speech_tables,
                            col_widths=[1.5 * inch, 5 * inch]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Test Configuration Tables", styles["SubHead"]))
    test_tables = [
        ["test_suites", "id, name, description, status, sweep_config_json, created_at"],
        ["sweep_configs", "id, suite_id, snr_levels, echo_configs, noise_types, pipelines, backends"],
        ["test_cases", "id, suite_id, corpus_entry_id, voice_id, snr_db, noise_type, pipeline, backend, case_hash"],
    ]
    story.append(make_table(["Table", "Key Columns"], test_tables,
                            col_widths=[1.5 * inch, 5 * inch]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Execution &amp; Results Tables", styles["SubHead"]))
    run_tables = [
        ["test_runs", "id, suite_id, status, total_cases, completed_cases, failed_cases, progress_pct"],
        ["test_results", "id, run_id, case_id, llm_response_text, asr_transcript, score, passed, llm_latency_ms, total_latency_ms, evaluation_details_json"],
    ]
    story.append(make_table(["Table", "Key Columns"], run_tables,
                            col_widths=[1.5 * inch, 5 * inch]))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # 12. DEPLOYMENT
    # ════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("12. Deployment &amp; Infrastructure", styles["SectionHead"]))
    story.append(hr())

    story.append(Paragraph("Docker Compose Architecture", styles["SubHead"]))
    docker_rows = [
        ["db", "PostgreSQL 16", "5432", "Persistent data, connection pool: 20 + 10 overflow"],
        ["redis", "Redis 7 Alpine", "6379", "arq task queue, ephemeral"],
        ["backend", "Python 3.12 + FastAPI", "8000", "API server, WebSocket, Uvicorn"],
        ["worker", "Python 3.12 + arq", "-", "Background jobs: TTS synthesis, test execution"],
        ["frontend", "Node 20 + Vite", "5173", "React dev server, HMR, host 0.0.0.0"],
    ]
    story.append(make_table(
        ["Container", "Image", "Port", "Purpose"], docker_rows,
        col_widths=[1 * inch, 1.5 * inch, 0.6 * inch, 3.4 * inch]
    ))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Configuration", styles["SubHead"]))
    story.append(Paragraph(
        "All configuration is managed via environment variables (loaded from <font face='Courier'>"
        ".env</font> file). The Settings API allows runtime updates that persist back to "
        "<font face='Courier'>.env</font>. Key settings include API keys for LLM and TTS "
        "providers, database URL, Redis URL, sample rate, and worker concurrency.",
        styles["Body"]
    ))

    config_rows = [
        ["OPENAI_API_KEY", "OpenAI GPT-4o + TTS + Whisper API"],
        ["ANTHROPIC_API_KEY", "Claude text-only backend"],
        ["GOOGLE_API_KEY", "Gemini multimodal backend"],
        ["ELEVENLABS_API_KEY", "ElevenLabs premium TTS"],
        ["OLLAMA_BASE_URL", "Local Ollama server endpoint"],
        ["DATABASE_URL", "PostgreSQL connection string"],
        ["REDIS_URL", "Redis connection string"],
        ["DEFAULT_SAMPLE_RATE", "Audio sample rate (default: 16000 Hz)"],
        ["MAX_CONCURRENT_WORKERS", "Parallel test execution limit (default: 50)"],
    ]
    story.append(make_table(["Variable", "Purpose"], config_rows,
                            col_widths=[2.2 * inch, 4.3 * inch]))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # 13. RECOMMENDED PERFORMANCE STATISTICS
    # ════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("13. Recommended Performance Statistics", styles["SectionHead"]))
    story.append(hr())
    story.append(Paragraph(
        "This section outlines a comprehensive set of statistics that should be gathered "
        "to fully characterize the performance of LLM speech understanding systems. These "
        "recommendations go beyond what the platform currently computes and represent "
        "best practices for automotive voice interface evaluation.",
        styles["Body"]
    ))

    story.append(Paragraph("13.1 Core Performance Dashboard", styles["SubHead"]))
    story.append(Paragraph(
        "Every test run should produce a top-level dashboard with these summary statistics. "
        "These provide a quick health check before deeper analysis.",
        styles["Body"]
    ))
    dashboard_stats = [
        ["Total Test Cases", "Count of all cases in the sweep"],
        ["Completion Rate", "% of cases that completed without error or timeout"],
        ["Overall Pass Rate", "% of completed cases scoring above threshold"],
        ["Mean Score +/- SD", "Average evaluation score with standard deviation"],
        ["Median Latency (p50)", "Typical response time"],
        ["Tail Latency (p99)", "Worst-case response time for reliability planning"],
        ["Total Token Usage", "Sum of input + output tokens across all cases"],
        ["Estimated API Cost", "Projected cost based on per-token pricing"],
        ["Error Breakdown", "Count by error type: timeout, API error, rate limit, parse failure"],
    ]
    story.append(make_table(["Statistic", "Description"], dashboard_stats,
                            col_widths=[2 * inch, 4.5 * inch]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("13.2 SNR Degradation Curves", styles["SubHead"]))
    story.append(Paragraph(
        "Plot pass rate and mean score vs. SNR (dB) for each backend and pipeline. "
        "Fit a logistic curve to estimate the <b>SNR-50</b> threshold (the SNR at which "
        "performance crosses 50%). Report the following per backend:",
        styles["Body"]
    ))
    snr_stats = [
        ["SNR-50 (dB)", "SNR at 50% pass rate (logistic fit)", "Lower is better (more noise tolerant)"],
        ["SNR-80 (dB)", "SNR at 80% pass rate", "Practical operating threshold"],
        ["Slope at SNR-50", "Steepness of the logistic curve", "Steeper = more brittle transition"],
        ["Floor Score", "Asymptotic score at very low SNR (-10 dB)", "Worst-case performance"],
        ["Ceiling Score", "Asymptotic score at high SNR (20+ dB)", "Best-case performance"],
        ["Usable Range", "SNR range where pass rate is in [20%, 80%]", "Width of transition zone"],
    ]
    story.append(make_table(["Statistic", "Definition", "Interpretation"], snr_stats,
                            col_widths=[1.4 * inch, 2.8 * inch, 2.3 * inch]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("13.3 Factor Importance Ranking", styles["SubHead"]))
    story.append(Paragraph(
        "Use the ANOVA eta-squared values to rank which experimental factors have the "
        "most impact on performance. This guides engineering effort toward the highest-impact "
        "improvements. Expected ranking (most to least impactful):",
        styles["Body"]
    ))
    factor_stats = [
        ["1. SNR Level", "Usually the dominant factor (eta-sq > 0.15)", "Invest in noise robustness"],
        ["2. LLM Backend", "Model choice is typically second most important", "Select best model for budget"],
        ["3. Pipeline Type", "A vs. B often shows significant difference", "Native audio vs. ASR path"],
        ["4. Noise Type", "Pink vs. white vs. babble effects vary", "Test against relevant noise"],
        ["5. Echo Config", "Usually smaller effect than noise level", "Matters for speakerphone use"],
        ["6. Voice / TTS", "Should be small if system is fair", "Large effect signals bias"],
    ]
    story.append(make_table(
        ["Factor", "Typical Finding", "Action"], factor_stats,
        col_widths=[1.4 * inch, 2.8 * inch, 2.3 * inch]
    ))
    story.append(PageBreak())

    story.append(Paragraph("13.4 Cross-Backend Comparison Matrix", styles["SubHead"]))
    story.append(Paragraph(
        "For every pair of backends, report a comparison card with:",
        styles["Body"]
    ))
    comparison_stats = [
        ["Win Rate", "% of cases where backend A scores higher than B"],
        ["Mean Score Delta", "Average (score_A - score_B) with 95% CI"],
        ["McNemar p-adjusted", "Significance of pass/fail disagreement"],
        ["Wilcoxon p-adjusted", "Significance of score distribution difference"],
        ["Cohen's d", "Standardized effect size of score difference"],
        ["Concordance Rate", "% of cases where both backends agree (both pass or both fail)"],
        ["Discordant Analysis", "Breakdown of cases where exactly one backend fails"],
    ]
    story.append(make_table(["Statistic", "Description"], comparison_stats,
                            col_widths=[1.8 * inch, 4.7 * inch]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("13.5 Bias &amp; Fairness Metrics", styles["SubHead"]))
    story.append(Paragraph(
        "These metrics detect whether the system unfairly penalizes certain voice "
        "characteristics. Report for each dimension with at least 30 samples per group:",
        styles["Body"]
    ))
    bias_stats = [
        ["Gender Parity Gap", "| pass_rate_male - pass_rate_female |", "< 5% = fair"],
        ["Accent Disparity Ratio", "min(pass_rate) / max(pass_rate) across accents", "> 0.85 = fair"],
        ["Language Equity Index", "Gini coefficient of pass rates across languages", "< 0.1 = equitable"],
        ["Age Group Variance", "Variance of pass rates across age groups", "Low = unbiased"],
        ["Provider Neutrality", "Eta-squared for TTS provider as factor", "< 0.01 = provider-neutral"],
    ]
    story.append(make_table(
        ["Metric", "Computation", "Target"], bias_stats,
        col_widths=[1.7 * inch, 3 * inch, 1.8 * inch]
    ))
    story.append(Spacer(1, 12))

    story.append(Paragraph("13.6 Reliability &amp; Consistency", styles["SubHead"]))
    reliability_stats = [
        ["Test-Retest Reliability", "Run the same sweep twice; compute ICC (intraclass correlation) between scores", "> 0.9 = excellent"],
        ["Score Variance (intra-condition)", "Variance of scores within identical conditions (same SNR, backend, etc.)", "Low = consistent"],
        ["Timeout Rate by Backend", "% of test cases that exceed timeout, per backend", "< 2% = reliable"],
        ["Error Rate by Category", "Breakdown: network errors, parse failures, rate limits, OOM", "Identifies systemic issues"],
        ["Recovery After Failure", "Pass rate of the test case immediately after a failed case", "Should equal baseline"],
    ]
    story.append(make_table(
        ["Metric", "Method", "Target"], reliability_stats,
        col_widths=[1.7 * inch, 3.3 * inch, 1.5 * inch]
    ))
    story.append(Spacer(1, 12))

    story.append(Paragraph("13.7 Operational Efficiency", styles["SubHead"]))
    ops_stats = [
        ["Sweep Duration", "Wall-clock time to complete an entire test suite", "Budget planning"],
        ["Backend Utilization", "% of time each backend is actively processing (vs. rate-limited)", "Identify bottlenecks"],
        ["Effective Throughput", "Completed tests per minute, excluding failures", "Capacity planning"],
        ["Checkpoint Overhead", "Time spent on JSONL checkpoint I/O vs. test execution", "Should be < 1%"],
        ["Cost per Insight", "API cost divided by number of statistically significant findings", "ROI of testing"],
    ]
    story.append(make_table(
        ["Metric", "Description", "Purpose"], ops_stats,
        col_widths=[1.7 * inch, 3.3 * inch, 1.5 * inch]
    ))
    story.append(PageBreak())

    story.append(Paragraph("13.8 Recommended Visualizations", styles["SubHead"]))
    story.append(Paragraph(
        "The following visualizations maximize insight extraction from test results:",
        styles["Body"]
    ))
    viz_items = [
        ["SNR Degradation Curves", "Line plot: pass rate vs. SNR, one line per backend, with 95% CI bands"],
        ["Performance Heatmap", "2D grid: SNR (rows) x Backend (cols), cell color = pass rate"],
        ["Pipeline Comparison Scatter", "Each dot = one test case, x = Pipeline A score, y = Pipeline B score"],
        ["Latency Distribution", "Violin/box plot per backend, showing p50/p95/p99 markers"],
        ["Factor Importance Bar Chart", "Horizontal bars: eta-squared per ANOVA factor, sorted descending"],
        ["Confusion Matrix", "For command match: predicted action vs. expected action grid"],
        ["Voice Fairness Radar", "Radar/spider chart: pass rate by gender, accent, age group, language"],
        ["Cost-Quality Pareto Front", "Scatter: x = cost per test, y = pass rate; identify Pareto-optimal backends"],
        ["Error Timeline", "Strip plot of errors over time during a run, colored by error type"],
        ["WER vs. Score Scatter", "Pipeline B only: x = WER, y = evaluation score; shows ASR quality impact"],
    ]
    story.append(make_table(
        ["Visualization", "Description"], viz_items,
        col_widths=[2.2 * inch, 4.3 * inch]
    ))

    story.append(Spacer(1, 20))
    story.append(hr())
    story.append(Paragraph(
        f"Document generated on {datetime.date.today().strftime('%B %d, %Y')}. "
        "For the latest version, regenerate from the project source.",
        styles["FooterStyle"]
    ))

    # ── Build ───────────────────────────────────────────────────────────────
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output_path


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                       "Audio_LLM_Test_Platform_Documentation.pdf")
    build_pdf(out)
    print(f"PDF generated: {out}")
