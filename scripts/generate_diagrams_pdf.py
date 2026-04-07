#!/usr/bin/env python3
"""Generate block diagram documentation for the Audio LLM Test Platform."""

import datetime
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white, black, Color
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Flowable
)
from reportlab.graphics.shapes import (
    Drawing, Rect, String, Line, Group, Polygon, Circle, Ellipse,
    PolyLine,
)
from reportlab.graphics import renderPDF

# ── Color Palette ───────────────────────────────────────────────────────────

# Block categories
C_INPUT = HexColor("#3b82f6")       # Blue - inputs
C_INPUT_FILL = HexColor("#dbeafe")
C_DSP = HexColor("#8b5cf6")         # Purple - DSP/audio processing
C_DSP_FILL = HexColor("#ede9fe")
C_LLM = HexColor("#059669")         # Green - LLM backends
C_LLM_FILL = HexColor("#d1fae5")
C_EVAL = HexColor("#dc2626")        # Red - evaluation
C_EVAL_FILL = HexColor("#fee2e2")
C_TTS = HexColor("#d97706")         # Amber - TTS/STT
C_TTS_FILL = HexColor("#fef3c7")
C_STORE = HexColor("#6366f1")       # Indigo - storage/DB
C_STORE_FILL = HexColor("#e0e7ff")
C_CTRL = HexColor("#0891b2")        # Cyan - control/scheduler
C_CTRL_FILL = HexColor("#cffafe")
C_STAT = HexColor("#be185d")        # Pink - statistics
C_STAT_FILL = HexColor("#fce7f3")
C_ECHO = HexColor("#7c3aed")        # Violet - echo path
C_ECHO_FILL = HexColor("#f3e8ff")

C_ARROW = HexColor("#374151")       # Dark gray arrows
C_ARROW_DATA = HexColor("#2563eb")  # Blue data arrows
C_ARROW_CTRL = HexColor("#9ca3af")  # Light gray control arrows
C_BG = HexColor("#f8fafc")          # Page background
C_LABEL = HexColor("#1f2937")       # Label text
C_SUBLABEL = HexColor("#6b7280")    # Sub-label text
C_TITLE = HexColor("#1a1a2e")       # Title text
C_SECTION_BG = HexColor("#f1f5f9")  # Section background

# ── Drawing Helpers ─────────────────────────────────────────────────────────


def rounded_rect(g, x, y, w, h, fill, stroke, r=6, stroke_width=1.5):
    """Draw a rounded rectangle (approximated with regular rect + rounded corners)."""
    rect = Rect(x, y, w, h, rx=r, ry=r,
                fillColor=fill, strokeColor=stroke, strokeWidth=stroke_width)
    g.add(rect)


def block(g, x, y, w, h, label, sublabel=None, fill=C_INPUT_FILL, stroke=C_INPUT,
          font_size=9, sub_font_size=7, bold=True):
    """Draw a labeled block with optional sublabel (supports multi-line via \\n)."""
    rounded_rect(g, x, y, w, h, fill, stroke, stroke_width=1.8)
    font = "Helvetica-Bold" if bold else "Helvetica"

    # Split sublabel lines
    sub_lines = sublabel.split("\n") if sublabel else []
    total_lines = 1 + len(sub_lines)
    line_height = font_size + 3
    sub_line_height = sub_font_size + 2

    # Calculate vertical center
    total_text_height = line_height + len(sub_lines) * sub_line_height
    top_y = y + h / 2 + total_text_height / 2 - font_size

    g.add(String(x + w / 2, top_y, label,
                 fontName=font, fontSize=font_size,
                 fillColor=stroke, textAnchor="middle"))
    for i, line in enumerate(sub_lines):
        g.add(String(x + w / 2, top_y - (i + 1) * sub_line_height, line,
                     fontName="Helvetica", fontSize=sub_font_size,
                     fillColor=C_SUBLABEL, textAnchor="middle"))


def small_block(g, x, y, w, h, label, fill=C_INPUT_FILL, stroke=C_INPUT, font_size=7):
    """Draw a small labeled block."""
    rounded_rect(g, x, y, w, h, fill, stroke, r=4, stroke_width=1.2)
    g.add(String(x + w / 2, y + h / 2 - 3, label,
                 fontName="Helvetica", fontSize=font_size,
                 fillColor=stroke, textAnchor="middle"))


def diamond(g, cx, cy, size, label, fill=C_CTRL_FILL, stroke=C_CTRL, font_size=7):
    """Draw a diamond (decision) shape."""
    s = size
    points = [cx, cy + s, cx + s, cy, cx, cy - s, cx - s, cy]
    g.add(Polygon(points, fillColor=fill, strokeColor=stroke, strokeWidth=1.5))
    g.add(String(cx, cy - 3, label,
                 fontName="Helvetica-Bold", fontSize=font_size,
                 fillColor=stroke, textAnchor="middle"))


def arrow(g, x1, y1, x2, y2, color=C_ARROW, width=1.5, head_size=7, dashed=False):
    """Draw an arrow from (x1,y1) to (x2,y2)."""
    import math
    dash_array = [4, 3] if dashed else None
    g.add(Line(x1, y1, x2, y2, strokeColor=color, strokeWidth=width,
               strokeDashArray=dash_array))
    # Arrowhead
    angle = math.atan2(y2 - y1, x2 - x1)
    ax1 = x2 - head_size * math.cos(angle - 0.4)
    ay1 = y2 - head_size * math.sin(angle - 0.4)
    ax2 = x2 - head_size * math.cos(angle + 0.4)
    ay2 = y2 - head_size * math.sin(angle + 0.4)
    g.add(Polygon([x2, y2, ax1, ay1, ax2, ay2],
                  fillColor=color, strokeColor=color, strokeWidth=0.5))


def arrow_right(g, x1, y, x2, color=C_ARROW, width=1.5, label=None, label_above=True):
    """Horizontal arrow with optional label."""
    arrow(g, x1, y, x2, y, color, width)
    if label:
        ly = y + 6 if label_above else y - 10
        g.add(String((x1 + x2) / 2, ly, label,
                     fontName="Helvetica", fontSize=6.5,
                     fillColor=C_SUBLABEL, textAnchor="middle"))


def arrow_down(g, x, y1, y2, color=C_ARROW, width=1.5, label=None):
    """Vertical arrow with optional label."""
    arrow(g, x, y1, x, y2, color, width)
    if label:
        g.add(String(x + 5, (y1 + y2) / 2, label,
                     fontName="Helvetica", fontSize=6.5,
                     fillColor=C_SUBLABEL, textAnchor="start"))


def arrow_up(g, x, y1, y2, color=C_ARROW, width=1.5):
    """Vertical arrow going up."""
    arrow(g, x, y1, x, y2, color, width)


def bent_arrow_right_down(g, x1, y1, x2, y2, color=C_ARROW, width=1.5):
    """L-shaped arrow: right then down."""
    dash = None
    g.add(Line(x1, y1, x2, y1, strokeColor=color, strokeWidth=width, strokeDashArray=dash))
    arrow(g, x2, y1, x2, y2, color, width)


def bent_arrow_down_right(g, x1, y1, x2, y2, color=C_ARROW, width=1.5):
    """L-shaped arrow: down then right."""
    g.add(Line(x1, y1, x1, y2, strokeColor=color, strokeWidth=width))
    arrow(g, x1, y2, x2, y2, color, width)


def section_bg(g, x, y, w, h, label=None, fill=C_SECTION_BG):
    """Draw a section background with label in a tab above the content."""
    rounded_rect(g, x, y, w, h, fill, HexColor("#cbd5e1"), r=8, stroke_width=1)
    if label:
        # Draw label tab at top-left, outside the box
        lbl_w = len(label) * 5.5 + 16
        lbl_h = 14
        lbl_x = x + 1
        lbl_y = y + h - 1
        rounded_rect(g, lbl_x, lbl_y, lbl_w, lbl_h,
                     HexColor("#e2e8f0"), HexColor("#94a3b8"), r=3, stroke_width=0.8)
        g.add(String(lbl_x + 8, lbl_y + 2, label,
                     fontName="Helvetica-Bold", fontSize=7.5,
                     fillColor=HexColor("#475569"), textAnchor="start"))


def legend_item(g, x, y, fill, stroke, label):
    """Draw a legend color swatch + label."""
    rounded_rect(g, x, y, 12, 12, fill, stroke, r=2, stroke_width=1)
    g.add(String(x + 16, y + 2, label,
                 fontName="Helvetica", fontSize=7,
                 fillColor=C_LABEL, textAnchor="start"))


# ── Diagram Flowable Wrapper ────────────────────────────────────────────────

class DiagramFlowable(Flowable):
    """Wrap a reportlab Drawing as a Flowable for use in Platypus."""
    def __init__(self, drawing, h_padding=0):
        Flowable.__init__(self)
        self.drawing = drawing
        self.width = drawing.width
        self.height = drawing.height + h_padding

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        renderPDF.draw(self.drawing, self.canv, 0, 0)


# ── Styles ──────────────────────────────────────────────────────────────────

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    "DiagTitle", parent=styles["Title"],
    fontSize=28, leading=36, textColor=C_TITLE,
    spaceAfter=4, alignment=TA_CENTER, fontName="Helvetica-Bold",
))
styles.add(ParagraphStyle(
    "DiagSubtitle", parent=styles["Normal"],
    fontSize=12, leading=16, textColor=HexColor("#475569"),
    spaceAfter=20, alignment=TA_CENTER, fontName="Helvetica",
))
styles.add(ParagraphStyle(
    "SectionTitle", parent=styles["Heading1"],
    fontSize=18, leading=24, textColor=C_TITLE,
    spaceBefore=12, spaceAfter=8, fontName="Helvetica-Bold",
))
styles.add(ParagraphStyle(
    "DiagCaption", parent=styles["Normal"],
    fontSize=9, leading=13, textColor=HexColor("#475569"),
    spaceBefore=6, spaceAfter=4, alignment=TA_LEFT, fontName="Helvetica",
))
styles.add(ParagraphStyle(
    "DiagBody", parent=styles["Normal"],
    fontSize=10, leading=14, textColor=HexColor("#1f2937"),
    spaceAfter=8, fontName="Helvetica",
))
styles.add(ParagraphStyle(
    "FooterStyle", parent=styles["Normal"],
    fontSize=8, textColor=HexColor("#9ca3af"),
    fontName="Helvetica", alignment=TA_CENTER,
))


# ── Page Template ───────────────────────────────────────────────────────────

def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(HexColor("#9ca3af"))
    page_w = doc.pagesize[0]
    canvas.drawCentredString(
        page_w / 2, 0.4 * inch,
        f"Audio LLM Test Platform  |  Block Diagrams  |  Page {doc.page}"
    )
    canvas.restoreState()


# ════════════════════════════════════════════════════════════════════════════
# DIAGRAM 1: HIGH-LEVEL SYSTEM OVERVIEW
# ════════════════════════════════════════════════════════════════════════════

def diagram_system_overview():
    W, H = 700, 480
    d = Drawing(W, H)

    # Background
    d.add(Rect(0, 0, W, H, fillColor=white, strokeColor=None))

    g = Group()

    # ── Title ──
    g.add(String(W/2, H - 20, "System Overview", fontName="Helvetica-Bold",
                 fontSize=14, fillColor=C_TITLE, textAnchor="middle"))

    # ── Row 1: Inputs ──
    y1 = H - 80
    section_bg(g, 15, y1 - 10, 670, 55, "INPUTS")

    block(g, 25, y1 - 5, 95, 40, "Corpus Text", "Harvard / Commands",
          C_INPUT_FILL, C_INPUT)
    block(g, 135, y1 - 5, 95, 40, "TTS Providers", "9 engines",
          C_TTS_FILL, C_TTS)
    block(g, 245, y1 - 5, 95, 40, "Noise Sources", "pink/white/babble",
          C_DSP_FILL, C_DSP)
    block(g, 355, y1 - 5, 95, 40, "Echo Config", "delay/gain/EQ",
          C_ECHO_FILL, C_ECHO)
    block(g, 465, y1 - 5, 95, 40, "Sweep Config", "SNR/pipeline/backend",
          C_CTRL_FILL, C_CTRL)
    block(g, 575, y1 - 5, 100, 40, "API Keys", "Settings GUI",
          C_STORE_FILL, C_STORE)

    # ── Row 2: Processing ──
    y2 = H - 175
    section_bg(g, 15, y2 - 15, 670, 70, "PROCESSING")

    block(g, 30, y2 - 5, 130, 50, "Speech Synthesis", "TTS -> AudioBuffer",
          C_TTS_FILL, C_TTS)
    block(g, 180, y2 - 5, 150, 50, "Audio Degradation", "Noise + Echo + Filters",
          C_DSP_FILL, C_DSP)
    block(g, 350, y2 - 5, 130, 50, "Test Scheduler", "Rate limit / Checkpoint",
          C_CTRL_FILL, C_CTRL)
    block(g, 500, y2 - 5, 175, 50, "LLM Query", "GPT-4o / Gemini / Claude / Ollama",
          C_LLM_FILL, C_LLM)

    # Arrows row 1 -> row 2
    arrow_down(g, 72, y1 - 5, y2 + 45, C_ARROW, 1.2)
    arrow_down(g, 182, y1 - 5, y2 + 45, C_ARROW, 1.2)
    arrow_down(g, 292, y1 - 5, y2 + 45, C_ARROW, 1.2)
    arrow_down(g, 402, y1 - 5, y2 + 45, C_ARROW, 1.2)
    arrow_down(g, 512, y1 - 5, y2 + 45, C_ARROW, 1.2)
    # Arrows within row 2
    arrow_right(g, 160, y2 + 20, 180, C_ARROW_DATA, 1.5)
    arrow_right(g, 330, y2 + 20, 350, C_ARROW_DATA, 1.5)
    arrow_right(g, 480, y2 + 20, 500, C_ARROW_DATA, 1.5)

    # ── Row 3: Evaluation ──
    y3 = H - 280
    section_bg(g, 15, y3 - 15, 670, 70, "EVALUATION")

    block(g, 60, y3 - 5, 140, 50, "Command Match", "Exact/Fuzzy/Keyword",
          C_EVAL_FILL, C_EVAL)
    block(g, 230, y3 - 5, 140, 50, "LLM Judge", "Multi-judge median",
          C_EVAL_FILL, C_EVAL)
    block(g, 400, y3 - 5, 120, 50, "ASR Metrics", "WER / CER",
          C_EVAL_FILL, C_EVAL)
    block(g, 550, y3 - 5, 120, 50, "Score + Pass", "0.0-1.0 / threshold",
          C_EVAL_FILL, C_EVAL)

    # Arrows row 2 -> row 3
    arrow_down(g, 587, y2 - 5, y3 + 45, C_ARROW, 1.2, "response")
    arrow_right(g, 200, y3 + 20, 230, C_ARROW_DATA, 1.2)
    arrow_right(g, 370, y3 + 20, 400, C_ARROW_DATA, 1.2)
    arrow_right(g, 520, y3 + 20, 550, C_ARROW_DATA, 1.2)

    # ── Row 4: Output ──
    y4 = H - 385
    section_bg(g, 15, y4 - 15, 670, 70, "ANALYSIS & OUTPUT")

    block(g, 30, y4 - 5, 130, 50, "Statistical Tests", "ANOVA / McNemar",
          C_STAT_FILL, C_STAT)
    block(g, 180, y4 - 5, 130, 50, "Heatmaps", "SNR x Backend pivot",
          C_STAT_FILL, C_STAT)
    block(g, 330, y4 - 5, 130, 50, "Export", "CSV / Parquet / JSON",
          C_STORE_FILL, C_STORE)
    block(g, 480, y4 - 5, 100, 50, "WebSocket", "Live progress",
          C_CTRL_FILL, C_CTRL)
    block(g, 595, y4 - 5, 80, 50, "Frontend", "React UI",
          C_INPUT_FILL, C_INPUT)

    # Arrows row 3 -> row 4
    arrow_down(g, 610, y3 - 5, y4 + 45, C_ARROW, 1.2, "results")

    # Arrows within row 4
    arrow_right(g, 160, y4 + 20, 180, C_ARROW_DATA, 1.2)
    arrow_right(g, 310, y4 + 20, 330, C_ARROW_DATA, 1.2)
    arrow_right(g, 580, y4 + 20, 595, C_ARROW_DATA, 1.2)

    # ── Legend ──
    ly = 18
    legend_item(g, 25, ly, C_INPUT_FILL, C_INPUT, "Input/UI")
    legend_item(g, 105, ly, C_TTS_FILL, C_TTS, "TTS/STT")
    legend_item(g, 175, ly, C_DSP_FILL, C_DSP, "Audio DSP")
    legend_item(g, 260, ly, C_ECHO_FILL, C_ECHO, "Echo")
    legend_item(g, 315, ly, C_LLM_FILL, C_LLM, "LLM")
    legend_item(g, 370, ly, C_EVAL_FILL, C_EVAL, "Evaluation")
    legend_item(g, 455, ly, C_CTRL_FILL, C_CTRL, "Control")
    legend_item(g, 535, ly, C_STAT_FILL, C_STAT, "Statistics")
    legend_item(g, 615, ly, C_STORE_FILL, C_STORE, "Storage")

    d.add(g)
    return d


# ════════════════════════════════════════════════════════════════════════════
# DIAGRAM 2: AUDIO DSP PIPELINE (DETAILED)
# ════════════════════════════════════════════════════════════════════════════

def diagram_dsp_pipeline():
    W, H = 700, 500
    d = Drawing(W, H)
    d.add(Rect(0, 0, W, H, fillColor=white, strokeColor=None))
    g = Group()

    g.add(String(W/2, H - 20, "Audio DSP Pipeline - Signal Flow",
                 fontName="Helvetica-Bold", fontSize=14,
                 fillColor=C_TITLE, textAnchor="middle"))

    # ── Clean Speech Input ──
    block(g, 30, H - 80, 120, 45, "Clean Speech", "AudioBuffer (mono f64)",
          C_INPUT_FILL, C_INPUT)

    # ── Noise Generation Section ──
    section_bg(g, 180, H - 115, 200, 80, "Noise Generation")
    small_block(g, 190, H - 70, 55, 25, "White", C_DSP_FILL, C_DSP)
    small_block(g, 250, H - 70, 55, 25, "Pink", C_DSP_FILL, C_DSP)
    small_block(g, 310, H - 70, 60, 25, "Babble", C_DSP_FILL, C_DSP)
    small_block(g, 220, H - 105, 65, 25, "From File", C_DSP_FILL, C_DSP)
    small_block(g, 300, H - 105, 70, 25, "Pink+LPF", C_DSP_FILL, C_DSP)

    # ── SNR Mixer ──
    block(g, 410, H - 95, 120, 50, "SNR Mixer", "Target SNR (dB)",
          C_DSP_FILL, C_DSP)

    # Arrows to mixer
    arrow_right(g, 150, H - 57, 410, C_ARROW_DATA, 1.5, "speech")
    arrow_right(g, 370, H - 57, 410, C_ARROW_DATA, 1.5, "noise")

    # ── Soft Clip ──
    block(g, 560, H - 95, 110, 50, "Soft Clip", "tanh > 0.95",
          C_DSP_FILL, C_DSP)
    arrow_right(g, 530, H - 70, 560, C_ARROW_DATA, 1.5, "mixed")

    # ── Echo Path Section ──
    y_echo = H - 220
    section_bg(g, 30, y_echo - 30, 400, 100, "Acoustic Echo Simulator")

    block(g, 45, y_echo - 15, 100, 55, "Echo Config", "delay_ms\ngain_dB",
          C_ECHO_FILL, C_ECHO)

    block(g, 170, y_echo - 15, 90, 55, "Delay Line", "0-500 ms",
          C_ECHO_FILL, C_ECHO)

    block(g, 280, y_echo + 10, 70, 30, "Gain", "-100..0 dB",
          C_ECHO_FILL, C_ECHO)
    block(g, 280, y_echo - 25, 70, 30, "EQ Chain", "Biquad SOS",
          C_ECHO_FILL, C_ECHO)

    block(g, 370, y_echo - 5, 50, 40, "Mix", "",
          C_ECHO_FILL, C_ECHO)

    arrow_right(g, 145, y_echo + 12, 170, C_ARROW, 1.2)
    arrow_right(g, 260, y_echo + 25, 280, C_ARROW, 1.2)
    arrow_right(g, 260, y_echo - 10, 280, C_ARROW, 1.2)
    arrow_right(g, 350, y_echo + 25, 370, C_ARROW, 1.2)
    arrow_right(g, 350, y_echo - 10, 370, C_ARROW, 1.2)

    # Soft clip output -> echo mix
    bent_arrow_right_down(g, 615, H - 95, 615, y_echo + 15)
    g.add(Line(615, y_echo + 15, 420, y_echo + 15,
               strokeColor=C_ARROW_DATA, strokeWidth=1.5))
    # Echo output arrow
    arrow(g, 420, y_echo + 15, 420, y_echo - 50, C_ARROW_DATA, 1.5)

    # ── Filter Chain Section ──
    y_filt = y_echo - 100
    section_bg(g, 30, y_filt - 15, 400, 60, "Filter Chain (Biquad Cascade)")

    small_block(g, 50, y_filt, 70, 30, "LPF", C_DSP_FILL, C_DSP)
    small_block(g, 130, y_filt, 70, 30, "HPF", C_DSP_FILL, C_DSP)
    small_block(g, 210, y_filt, 75, 30, "Peaking", C_DSP_FILL, C_DSP)
    small_block(g, 295, y_filt, 70, 30, "Lo Shelf", C_DSP_FILL, C_DSP)
    small_block(g, 375, y_filt, 45, 30, "...", C_DSP_FILL, C_DSP)

    arrow_right(g, 120, y_filt + 15, 130, C_ARROW, 1)
    arrow_right(g, 200, y_filt + 15, 210, C_ARROW, 1)
    arrow_right(g, 285, y_filt + 15, 295, C_ARROW, 1)
    arrow_right(g, 365, y_filt + 15, 375, C_ARROW, 1)

    # Output
    y_out = y_filt - 70
    block(g, 460, y_out, 130, 45, "Degraded Audio", "AudioBuffer output",
          HexColor("#fef9c3"), HexColor("#a16207"))

    arrow_right(g, 420, y_filt + 15, 525, C_ARROW_DATA, 1.5)
    arrow_down(g, 525, y_filt, y_out + 45, C_ARROW_DATA, 1.5)

    # ── SNR Formula ──
    g.add(String(430, H - 120, "SNR = 20 * log10(RMS_s / RMS_n)",
                 fontName="Courier", fontSize=7, fillColor=C_SUBLABEL,
                 textAnchor="start"))

    # ── Soft Clip Detail ──
    g.add(String(560, H - 120, "|x| <= 0.95: pass",
                 fontName="Courier", fontSize=6.5, fillColor=C_SUBLABEL,
                 textAnchor="start"))
    g.add(String(560, H - 130, "|x| > 0.95: tanh",
                 fontName="Courier", fontSize=6.5, fillColor=C_SUBLABEL,
                 textAnchor="start"))

    # ── Legend ──
    legend_item(g, 25, 15, C_INPUT_FILL, C_INPUT, "Input")
    legend_item(g, 95, 15, C_DSP_FILL, C_DSP, "DSP Block")
    legend_item(g, 185, 15, C_ECHO_FILL, C_ECHO, "Echo Path")

    d.add(g)
    return d


# ════════════════════════════════════════════════════════════════════════════
# DIAGRAM 3: PIPELINE A vs PIPELINE B
# ════════════════════════════════════════════════════════════════════════════

def diagram_pipelines():
    W, H = 700, 520
    d = Drawing(W, H)
    d.add(Rect(0, 0, W, H, fillColor=white, strokeColor=None))
    g = Group()

    g.add(String(W/2, H - 20, "Evaluation Pipelines - A (Direct Audio) vs B (ASR + Text)",
                 fontName="Helvetica-Bold", fontSize=13,
                 fillColor=C_TITLE, textAnchor="middle"))

    # ── Common path (top) ──
    y_top = H - 70
    block(g, 30, y_top, 100, 40, "Corpus Entry", "text + expected",
          C_INPUT_FILL, C_INPUT)
    arrow_right(g, 130, y_top + 20, 155, C_ARROW_DATA)

    block(g, 155, y_top, 100, 40, "TTS Engine", "synthesize()",
          C_TTS_FILL, C_TTS)
    arrow_right(g, 255, y_top + 20, 280, C_ARROW_DATA, 1.5, "clean speech")

    block(g, 280, y_top, 100, 40, "Add Noise", "mix_at_snr()",
          C_DSP_FILL, C_DSP)
    arrow_right(g, 380, y_top + 20, 405, C_ARROW_DATA)

    block(g, 405, y_top, 100, 40, "Add Echo", "echo_path()",
          C_ECHO_FILL, C_ECHO)
    arrow_right(g, 505, y_top + 20, 530, C_ARROW_DATA, 1.5, "degraded audio")

    block(g, 530, y_top, 90, 40, "Apply Filters", "FilterChain",
          C_DSP_FILL, C_DSP)

    # ── Split point ──
    y_split = y_top - 50
    diamond(g, 575, y_split, 22, "Pipeline?", C_CTRL_FILL, C_CTRL, 6)

    arrow_down(g, 575, y_top, y_split + 22, C_ARROW)

    # ════ PIPELINE A (left) ════
    y_a = y_split - 80
    section_bg(g, 20, y_a - 20, 310, 105, "Pipeline A: Direct Audio")

    block(g, 35, y_a, 120, 45, "Encode Audio", "base64 PCM16 / WAV",
          C_DSP_FILL, C_DSP)
    arrow_right(g, 155, y_a + 22, 180, C_ARROW_DATA)
    block(g, 180, y_a, 135, 45, "Multimodal LLM", "GPT-4o / Gemini",
          C_LLM_FILL, C_LLM)

    # Arrow from split to pipeline A
    g.add(Line(553, y_split, 95, y_split,
               strokeColor=C_ARROW, strokeWidth=1.2))
    g.add(String(300, y_split + 4, "A", fontName="Helvetica-Bold",
                 fontSize=8, fillColor=C_CTRL, textAnchor="middle"))
    arrow_down(g, 95, y_split, y_a + 45, C_ARROW)

    # ════ PIPELINE B (right) ════
    y_b = y_split - 80
    section_bg(g, 365, y_b - 55, 320, 140, "Pipeline B: ASR + Text")

    block(g, 380, y_b, 120, 45, "Whisper ASR", "local / API",
          C_TTS_FILL, C_TTS)
    arrow_right(g, 500, y_b + 22, 530, C_ARROW_DATA, 1.5, "transcript")
    block(g, 530, y_b, 140, 45, "Compute WER", "vs. original text",
          C_EVAL_FILL, C_EVAL)

    # Text LLM below
    block(g, 440, y_b - 50, 165, 45, "Text LLM", "Claude / Ollama / GPT / Gemini",
          C_LLM_FILL, C_LLM)
    arrow_down(g, 530, y_b, y_b - 5, C_ARROW_DATA)

    # Arrow from split to pipeline B
    g.add(Line(597, y_split, 440, y_split,
               strokeColor=C_ARROW, strokeWidth=1.2))
    g.add(String(500, y_split + 4, "B", fontName="Helvetica-Bold",
                 fontSize=8, fillColor=C_CTRL, textAnchor="middle"))
    arrow_down(g, 440, y_split, y_b + 45, C_ARROW)

    # ── Merge: Evaluation ──
    y_eval = y_b - 120
    section_bg(g, 100, y_eval - 15, 500, 70, "Evaluation")

    block(g, 115, y_eval, 130, 45, "Command Match", "Exact/Fuzzy/Keyword",
          C_EVAL_FILL, C_EVAL)
    block(g, 260, y_eval, 130, 45, "LLM Judge", "3x median vote",
          C_EVAL_FILL, C_EVAL)
    block(g, 415, y_eval, 80, 45, "Score", "0.0 - 1.0",
          C_EVAL_FILL, C_EVAL)
    block(g, 510, y_eval, 75, 45, "Pass?", "> threshold",
          C_EVAL_FILL, C_EVAL)

    arrow_right(g, 245, y_eval + 22, 260, C_ARROW, 1)
    arrow_right(g, 390, y_eval + 22, 415, C_ARROW, 1)
    arrow_right(g, 495, y_eval + 22, 510, C_ARROW, 1)

    # Arrows from pipelines to evaluation
    # Pipeline A response
    arrow_down(g, 247, y_a, y_eval + 45, C_ARROW_DATA, 1.2)
    g.add(String(252, y_a - 15, "response", fontName="Helvetica",
                 fontSize=6.5, fillColor=C_SUBLABEL, textAnchor="start"))

    # Pipeline B response
    arrow_down(g, 522, y_b - 50, y_eval + 45, C_ARROW_DATA, 1.2)

    # ── Output ──
    y_out = y_eval - 60
    block(g, 230, y_out, 250, 40, "TestResult", "score + passed + latency + details -> DB",
          C_STORE_FILL, C_STORE)
    arrow_down(g, 455, y_eval, y_out + 40, C_ARROW_DATA, 1.5)

    # Legend
    ly = 10
    legend_item(g, 25, ly, C_INPUT_FILL, C_INPUT, "Input")
    legend_item(g, 95, ly, C_TTS_FILL, C_TTS, "TTS/ASR")
    legend_item(g, 175, ly, C_DSP_FILL, C_DSP, "Audio DSP")
    legend_item(g, 265, ly, C_ECHO_FILL, C_ECHO, "Echo")
    legend_item(g, 325, ly, C_LLM_FILL, C_LLM, "LLM")
    legend_item(g, 380, ly, C_EVAL_FILL, C_EVAL, "Evaluation")
    legend_item(g, 470, ly, C_CTRL_FILL, C_CTRL, "Control")
    legend_item(g, 545, ly, C_STORE_FILL, C_STORE, "Storage")

    d.add(g)
    return d


# ════════════════════════════════════════════════════════════════════════════
# DIAGRAM 4: TTS & STT SUBSYSTEM
# ════════════════════════════════════════════════════════════════════════════

def diagram_tts_stt():
    W, H = 700, 440
    d = Drawing(W, H)
    d.add(Rect(0, 0, W, H, fillColor=white, strokeColor=None))
    g = Group()

    g.add(String(W/2, H - 20, "Text-to-Speech & Speech-to-Text Subsystem",
                 fontName="Helvetica-Bold", fontSize=14,
                 fillColor=C_TITLE, textAnchor="middle"))

    # ── Corpus ──
    block(g, 30, H - 80, 110, 40, "Corpus Entry", "text + metadata",
          C_INPUT_FILL, C_INPUT)

    # ── Voice Catalog ──
    block(g, 30, H - 145, 110, 45, "Voice Catalog", "diversity sampling",
          C_CTRL_FILL, C_CTRL)

    # ── TTS Providers ──
    y_tts = H - 85
    section_bg(g, 185, y_tts - 105, 260, 140, "TTS Providers")

    # Cloud (API key needed)
    small_block(g, 200, y_tts - 5, 70, 24, "OpenAI", C_TTS_FILL, C_TTS)
    small_block(g, 275, y_tts - 5, 80, 24, "ElevenLabs", C_TTS_FILL, C_TTS)
    small_block(g, 360, y_tts - 5, 75, 24, "Google CL", C_TTS_FILL, C_TTS)
    # Cloud (free)
    small_block(g, 200, y_tts - 40, 80, 24, "Edge TTS", C_TTS_FILL, C_TTS)
    small_block(g, 290, y_tts - 40, 55, 24, "gTTS", C_TTS_FILL, C_TTS)
    # Local
    small_block(g, 200, y_tts - 75, 55, 24, "Piper", C_TTS_FILL, C_TTS)
    small_block(g, 260, y_tts - 75, 55, 24, "Coqui", C_TTS_FILL, C_TTS)
    small_block(g, 320, y_tts - 75, 55, 24, "Bark", C_TTS_FILL, C_TTS)
    small_block(g, 380, y_tts - 75, 55, 24, "eSpeak", C_TTS_FILL, C_TTS)

    # Labels
    g.add(String(440, y_tts + 2, "API key", fontName="Helvetica",
                 fontSize=6, fillColor=C_SUBLABEL, textAnchor="start"))
    g.add(String(350, y_tts - 33, "Free cloud", fontName="Helvetica",
                 fontSize=6, fillColor=C_SUBLABEL, textAnchor="start"))
    g.add(String(438, y_tts - 68, "Local", fontName="Helvetica",
                 fontSize=6, fillColor=C_SUBLABEL, textAnchor="start"))

    # Arrow corpus -> TTS
    arrow_right(g, 140, H - 60, 200, C_ARROW_DATA, 1.5, "text")
    # Arrow catalog -> TTS
    arrow_right(g, 140, H - 122, 200, C_ARROW, 1.2, "voice_id")

    # ── AudioBuffer output ──
    block(g, 480, H - 115, 100, 45, "AudioBuffer", "mono float64",
          HexColor("#fef9c3"), HexColor("#a16207"))
    arrow_right(g, 445, H - 92, 480, C_ARROW_DATA, 1.5, "PCM samples")

    # ── Speech Samples DB ──
    block(g, 600, H - 115, 80, 45, "Storage", "WAV files + DB",
          C_STORE_FILL, C_STORE)
    arrow_right(g, 580, H - 92, 600, C_ARROW, 1.2)

    # ═══ STT Section ═══
    y_stt = H - 250
    section_bg(g, 30, y_stt - 40, 400, 90, "Speech-to-Text (Pipeline B only)")

    block(g, 50, y_stt - 20, 110, 50, "Degraded Audio", "from DSP pipeline",
          C_DSP_FILL, C_DSP)
    arrow_right(g, 160, y_stt + 5, 195, C_ARROW_DATA, 1.5)

    block(g, 195, y_stt - 20, 105, 50, "Whisper ASR", "local or API",
          C_TTS_FILL, C_TTS)
    arrow_right(g, 300, y_stt + 5, 335, C_ARROW_DATA, 1.5, "transcript")

    block(g, 335, y_stt - 15, 80, 40, "WER Calc", "edit distance",
          C_EVAL_FILL, C_EVAL)

    # ── Whisper modes ──
    small_block(g, 460, y_stt + 10, 90, 22, "Local (GPU)", C_TTS_FILL, C_TTS)
    small_block(g, 460, y_stt - 18, 90, 22, "OpenAI API", C_TTS_FILL, C_TTS)
    arrow(g, 300, y_stt + 10, 460, y_stt + 21, C_ARROW, 1, dashed=True)
    arrow(g, 300, y_stt - 7, 460, y_stt - 7, C_ARROW, 1, dashed=True)

    # ── Data Flow annotation ──
    y_flow = y_stt - 80
    section_bg(g, 30, y_flow - 15, 650, 50, "End-to-End Data Flow")
    flow_items = [
        ("Corpus Text", C_INPUT), ("TTS", C_TTS), ("AudioBuffer", C_DSP),
        ("+ Noise/Echo", C_ECHO), ("Degraded Audio", C_DSP),
        ("LLM or ASR+LLM", C_LLM), ("Evaluation", C_EVAL),
        ("Results DB", C_STORE),
    ]
    fx = 45
    for i, (lbl, col) in enumerate(flow_items):
        small_block(g, fx, y_flow, 72, 22, lbl, HexColor("#f8fafc"), col, font_size=6)
        if i < len(flow_items) - 1:
            arrow_right(g, fx + 72, y_flow + 11, fx + 80, col, 1)
        fx += 80

    d.add(g)
    return d


# ════════════════════════════════════════════════════════════════════════════
# DIAGRAM 5: ECHO PATH DETAIL
# ════════════════════════════════════════════════════════════════════════════

def diagram_echo_detail():
    W, H = 700, 380
    d = Drawing(W, H)
    d.add(Rect(0, 0, W, H, fillColor=white, strokeColor=None))
    g = Group()

    g.add(String(W/2, H - 20, "Acoustic Echo Path Simulator - Detail",
                 fontName="Helvetica-Bold", fontSize=14,
                 fillColor=C_TITLE, textAnchor="middle"))

    # ── Speaker Output (TTS playback) ──
    y1 = H - 90
    block(g, 30, y1, 120, 45, "Speaker Output", "LLM audio response",
          C_INPUT_FILL, C_INPUT)

    # ── Cabin Acoustic Model ──
    section_bg(g, 180, y1 - 60, 350, 110, "Cabin Acoustic Model")

    # Delay
    block(g, 200, y1 - 5, 90, 40, "Delay Line", "0 - 500 ms",
          C_ECHO_FILL, C_ECHO)
    arrow_right(g, 150, y1 + 17, 200, C_ARROW_DATA, 1.5, "audio")

    # Gain
    block(g, 310, y1 - 5, 80, 40, "Gain", "-100 to 0 dB",
          C_ECHO_FILL, C_ECHO)
    arrow_right(g, 290, y1 + 17, 310, C_ARROW_DATA)

    # EQ Chain
    block(g, 410, y1 - 5, 100, 40, "EQ Filter Chain", "Biquad SOS cascade",
          C_ECHO_FILL, C_ECHO)
    arrow_right(g, 390, y1 + 17, 410, C_ARROW_DATA)

    # Cabin response annotation
    g.add(String(260, y1 - 45, "Simulates speaker -> microphone path",
                 fontName="Helvetica-Oblique", fontSize=7,
                 fillColor=C_SUBLABEL, textAnchor="start"))
    g.add(String(260, y1 - 55, "through vehicle cabin acoustics",
                 fontName="Helvetica-Oblique", fontSize=7,
                 fillColor=C_SUBLABEL, textAnchor="start"))

    # ── Echo signal out ──
    block(g, 555, y1, 110, 40, "Echo Signal", "processed echo",
          C_ECHO_FILL, C_ECHO)
    arrow_right(g, 510, y1 + 17, 555, C_ARROW_DATA, 1.5)

    # ── Microphone path ──
    y2 = y1 - 120
    block(g, 30, y2, 120, 45, "Microphone Input", "user's speech",
          C_INPUT_FILL, C_INPUT)

    # ── Adder (mix point) ──
    cx_add = 350
    cy_add = y2 + 22
    g.add(Circle(cx_add, cy_add, 18,
                 fillColor=HexColor("#fef3c7"), strokeColor=C_TTS, strokeWidth=2))
    g.add(String(cx_add, cy_add - 4, "+",
                 fontName="Helvetica-Bold", fontSize=16,
                 fillColor=C_TTS, textAnchor="middle"))

    arrow_right(g, 150, y2 + 22, cx_add - 18, C_ARROW_DATA, 1.5, "clean speech")

    # Echo signal down to adder
    arrow_down(g, 610, y1, cy_add + 18, C_ARROW_DATA, 1.5)
    g.add(Line(610, cy_add, cx_add + 18, cy_add,
               strokeColor=C_ARROW_DATA, strokeWidth=1.5))

    # ── Output: combined signal ──
    block(g, 430, y2, 130, 45, "Combined Signal", "speech + echo",
          HexColor("#fef9c3"), HexColor("#a16207"))
    arrow_right(g, cx_add + 18, cy_add, 430, C_ARROW_DATA, 1.5)

    # ── To DSP pipeline ──
    block(g, 590, y2, 85, 45, "To LLM", "via pipeline",
          C_LLM_FILL, C_LLM)
    arrow_right(g, 560, y2 + 22, 590, C_ARROW_DATA, 1.5)

    # ── Config block ──
    y3 = y2 - 75
    section_bg(g, 30, y3 - 10, 640, 55, "Configuration (EchoConfig)")
    config_items = [
        ("delay_ms: 0-500", 50),
        ("gain_db: -100..0", 180),
        ("eq_chain: List[FilterSpec]", 330),
        ("freq, Q, gain_db per filter", 530),
    ]
    for label, x in config_items:
        g.add(String(x, y3 + 8, label,
                     fontName="Courier", fontSize=8,
                     fillColor=C_ECHO, textAnchor="start"))

    d.add(g)
    return d


# ════════════════════════════════════════════════════════════════════════════
# DIAGRAM 6: STATISTICS & ANALYSIS PIPELINE
# ════════════════════════════════════════════════════════════════════════════

def diagram_statistics():
    W, H = 700, 480
    d = Drawing(W, H)
    d.add(Rect(0, 0, W, H, fillColor=white, strokeColor=None))
    g = Group()

    g.add(String(W/2, H - 20, "Statistics Gathering & Analysis Pipeline",
                 fontName="Helvetica-Bold", fontSize=14,
                 fillColor=C_TITLE, textAnchor="middle"))

    # ── Input: Raw Results ──
    y1 = H - 75
    block(g, 30, y1, 150, 40, "Test Results (DB)", "score, passed, latency, backend, SNR",
          C_STORE_FILL, C_STORE)

    # ── Group-by Analysis ──
    y2 = H - 150
    section_bg(g, 15, y2 - 20, 330, 80, "Group-Level Analysis")

    block(g, 30, y2 - 5, 90, 50, "Group By", "backend / SNR\npipeline / voice",
          C_CTRL_FILL, C_CTRL)
    block(g, 140, y2 - 5, 90, 50, "Aggregate", "mean, SD, count\npass rate",
          C_STAT_FILL, C_STAT)
    block(g, 245, y2 - 5, 85, 50, "Wilson CI", "95% confidence\nintervals",
          C_STAT_FILL, C_STAT)

    arrow_down(g, 105, y1, y2 + 45, C_ARROW_DATA, 1.2)
    arrow_right(g, 120, y2 + 20, 140, C_ARROW, 1.2)
    arrow_right(g, 230, y2 + 20, 245, C_ARROW, 1.2)

    # ── Pairwise Comparison ──
    y3 = H - 260
    section_bg(g, 15, y3 - 20, 330, 80, "Pairwise Backend Comparison")

    block(g, 30, y3 - 5, 90, 50, "McNemar", "binary pass/fail\nchi-squared",
          C_STAT_FILL, C_STAT)
    block(g, 135, y3 - 5, 90, 50, "Wilcoxon", "signed-rank\ncontinuous scores",
          C_STAT_FILL, C_STAT)
    block(g, 240, y3 - 5, 90, 50, "Holm-Bonf.", "p-value\nadjustment",
          C_STAT_FILL, C_STAT)

    arrow_down(g, 75, y2 - 20, y3 + 45, C_ARROW, 1.2)
    arrow_right(g, 120, y3 + 20, 135, C_ARROW, 1.2)
    arrow_right(g, 225, y3 + 20, 240, C_ARROW, 1.2)

    # ── ANOVA ──
    y4 = H - 370
    section_bg(g, 15, y4 - 20, 330, 80, "Factor Analysis (ANOVA)")

    block(g, 30, y4 - 5, 90, 50, "One-Way\nANOVA", "per factor",
          C_STAT_FILL, C_STAT)
    block(g, 135, y4 - 5, 90, 50, "F-Statistic\np-value", "significance",
          C_STAT_FILL, C_STAT)
    block(g, 240, y4 - 5, 90, 50, "Eta-Squared", "effect size\n(% variance)",
          C_STAT_FILL, C_STAT)

    arrow_down(g, 75, y3 - 20, y4 + 45, C_ARROW, 1.2)
    arrow_right(g, 120, y4 + 20, 135, C_ARROW, 1.2)
    arrow_right(g, 225, y4 + 20, 240, C_ARROW, 1.2)

    # ── Right side: Visualizations ──
    y_viz = H - 100
    section_bg(g, 370, y_viz - 330, 315, 370, "Outputs & Visualizations")

    viz_blocks = [
        ("SNR Degradation Curves", "pass rate vs SNR per backend"),
        ("Performance Heatmap", "SNR x Backend 2D grid"),
        ("Latency Distribution", "p50 / p95 / p99 per backend"),
        ("Factor Importance", "eta-squared bar chart"),
        ("Bias & Fairness", "gender/accent/age parity"),
        ("Cost Analysis", "$ per test, token efficiency"),
        ("Pipeline Comparison", "A vs B scatter plot"),
        ("Export", "CSV / Parquet / JSON"),
    ]
    vy = y_viz - 25
    for label, sublabel in viz_blocks:
        block(g, 385, vy, 145, 33, label, sublabel,
              HexColor("#f0fdf4"), HexColor("#166534"), font_size=8, sub_font_size=6)
        vy -= 40

    # WebSocket + Frontend
    block(g, 555, H - 145, 115, 40, "WebSocket", "real-time progress",
          C_CTRL_FILL, C_CTRL)
    block(g, 555, H - 210, 115, 45, "React Frontend", "Dashboard / Results\nRunMonitor",
          C_INPUT_FILL, C_INPUT)
    arrow_down(g, 612, H - 145, H - 165, C_ARROW, 1.2)

    # Arrows from analysis to outputs
    arrow_right(g, 330, y2 + 10, 385, C_ARROW_DATA, 1.2)
    arrow_right(g, 330, y3 + 10, 385, C_ARROW_DATA, 1.2)
    arrow_right(g, 330, y4 + 10, 385, C_ARROW_DATA, 1.2)

    d.add(g)
    return d


# ════════════════════════════════════════════════════════════════════════════
# DIAGRAM 7: EXECUTION & CONTROL FLOW
# ════════════════════════════════════════════════════════════════════════════

def diagram_execution():
    W, H = 700, 460
    d = Drawing(W, H)
    d.add(Rect(0, 0, W, H, fillColor=white, strokeColor=None))
    g = Group()

    g.add(String(W/2, H - 20, "Test Execution & Control Flow",
                 fontName="Helvetica-Bold", fontSize=14,
                 fillColor=C_TITLE, textAnchor="middle"))

    # ── User triggers run ──
    y1 = H - 70
    block(g, 30, y1, 100, 40, "User / API", "POST /api/runs",
          C_INPUT_FILL, C_INPUT)
    arrow_right(g, 130, y1 + 20, 165, C_ARROW_DATA, 1.5)

    block(g, 165, y1, 110, 40, "Redis Queue", "arq enqueue",
          C_STORE_FILL, C_STORE)
    arrow_right(g, 275, y1 + 20, 310, C_ARROW_DATA, 1.5)

    block(g, 310, y1, 130, 40, "Background Worker", "run_test_suite()",
          C_CTRL_FILL, C_CTRL)

    # ── Sweep Expansion ──
    y2 = H - 140
    block(g, 30, y2, 130, 40, "Sweep Config", "SNR x noise x echo x backend",
          C_CTRL_FILL, C_CTRL)
    arrow_right(g, 160, y2 + 20, 195, C_ARROW_DATA, 1.5, "Cartesian product")

    block(g, 195, y2, 100, 40, "Test Cases", "N cases generated",
          C_CTRL_FILL, C_CTRL)
    arrow_right(g, 295, y2 + 20, 330, C_ARROW_DATA, 1.5)

    # ── Checkpoint ──
    block(g, 330, y2, 120, 40, "Checkpoint Load", "skip completed hashes",
          C_STORE_FILL, C_STORE)

    arrow_down(g, 375, y1, y2 + 40, C_ARROW, 1.2)

    # ── Scheduler ──
    y3 = H - 225
    section_bg(g, 15, y3 - 25, 670, 85, "TestScheduler (asyncio)")

    block(g, 30, y3 - 5, 130, 50, "Rate Limiter", "TokenBucket per backend\nRPM + concurrency",
          C_CTRL_FILL, C_CTRL)
    block(g, 180, y3 - 5, 100, 50, "Semaphore", "max 50 workers\nasyncio.Semaphore",
          C_CTRL_FILL, C_CTRL)
    block(g, 300, y3 - 5, 120, 50, "Execute Case", "pipeline.run()\nwith timeout",
          C_LLM_FILL, C_LLM)
    block(g, 440, y3 - 5, 110, 50, "Evaluate", "command_match\nor llm_judge",
          C_EVAL_FILL, C_EVAL)
    block(g, 570, y3 - 5, 100, 50, "Persist Result", "DB + checkpoint\nJSONL append",
          C_STORE_FILL, C_STORE)

    arrow_right(g, 160, y3 + 20, 180, C_ARROW, 1.2)
    arrow_right(g, 280, y3 + 20, 300, C_ARROW, 1.2)
    arrow_right(g, 420, y3 + 20, 440, C_ARROW, 1.2)
    arrow_right(g, 550, y3 + 20, 570, C_ARROW, 1.2)

    arrow_down(g, 390, y2, y3 + 45, C_ARROW, 1.2)

    # ── Progress broadcast ──
    y4 = y3 - 70
    block(g, 200, y4, 120, 35, "WebSocket", "broadcast progress",
          C_CTRL_FILL, C_CTRL)
    block(g, 380, y4, 120, 35, "Frontend UI", "live update",
          C_INPUT_FILL, C_INPUT)
    arrow_right(g, 320, y4 + 17, 380, C_ARROW_DATA, 1.5, "events")

    arrow_down(g, 260, y3 - 25, y4 + 35, C_ARROW, 1.2, "progress")

    # ── Error handling ──
    y5 = y4 - 55
    section_bg(g, 50, y5 - 10, 600, 45, "Error Handling & Recovery")
    small_block(g, 65, y5, 85, 25, "Timeout (120s)", C_EVAL_FILL, C_EVAL)
    small_block(g, 160, y5, 85, 25, "API Error", C_EVAL_FILL, C_EVAL)
    small_block(g, 255, y5, 85, 25, "Rate Limited", C_EVAL_FILL, C_EVAL)
    small_block(g, 350, y5, 85, 25, "Parse Error", C_EVAL_FILL, C_EVAL)
    small_block(g, 445, y5, 95, 25, "Mark Failed", C_STORE_FILL, C_STORE)
    small_block(g, 550, y5, 85, 25, "Continue", C_CTRL_FILL, C_CTRL)

    arrow_right(g, 435, y5 + 12, 445, C_ARROW, 1)
    arrow_right(g, 540, y5 + 12, 550, C_ARROW, 1)

    d.add(g)
    return d


# ════════════════════════════════════════════════════════════════════════════
# BUILD PDF
# ════════════════════════════════════════════════════════════════════════════

def build_pdf(output_path):
    doc = SimpleDocTemplate(
        output_path, pagesize=landscape(letter),
        topMargin=0.5 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        title="Audio LLM Test Platform - Block Diagrams",
        author="Audio LLM Test Team",
    )
    story = []

    # ── Cover ──
    story.append(Spacer(1, 1.5 * inch))
    story.append(Paragraph("Audio LLM Test Platform", styles["DiagTitle"]))
    story.append(Paragraph("System Block Diagrams &amp; Signal Flow", styles["DiagSubtitle"]))
    story.append(Spacer(1, 0.4 * inch))
    story.append(Paragraph(
        "This document provides detailed block diagrams showing the signal flow, control "
        "paths, and data routes through the Audio LLM Test Platform. Each diagram illustrates "
        "a different subsystem: the overall architecture, audio DSP pipeline, evaluation "
        "pipelines, TTS/STT subsystem, acoustic echo simulator, statistics gathering, "
        "and execution control flow.",
        styles["DiagBody"]
    ))
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph(
        f"Generated {datetime.date.today().strftime('%B %d, %Y')}  |  Version 0.1.0",
        styles["FooterStyle"]
    ))
    story.append(PageBreak())

    # ── Diagram 1 ──
    story.append(Paragraph("1. System Overview", styles["SectionTitle"]))
    story.append(Paragraph(
        "High-level view showing all major subsystems from inputs through processing, "
        "evaluation, and analysis. Data flows top to bottom through four layers.",
        styles["DiagCaption"]
    ))
    story.append(Spacer(1, 4))
    story.append(DiagramFlowable(diagram_system_overview()))
    story.append(PageBreak())

    # ── Diagram 2 ──
    story.append(Paragraph("2. Audio DSP Pipeline", styles["SectionTitle"]))
    story.append(Paragraph(
        "Detailed signal flow through the audio degradation pipeline: noise generation, "
        "SNR mixing with soft-clipping, acoustic echo simulation, and biquad filter chain.",
        styles["DiagCaption"]
    ))
    story.append(Spacer(1, 4))
    story.append(DiagramFlowable(diagram_dsp_pipeline()))
    story.append(PageBreak())

    # ── Diagram 3 ──
    story.append(Paragraph("3. Evaluation Pipelines A &amp; B", styles["SectionTitle"]))
    story.append(Paragraph(
        "Side-by-side comparison of Pipeline A (direct audio to multimodal LLM) and "
        "Pipeline B (ASR transcription then text LLM). Both share the same audio degradation "
        "path and converge at the evaluation stage.",
        styles["DiagCaption"]
    ))
    story.append(Spacer(1, 4))
    story.append(DiagramFlowable(diagram_pipelines()))
    story.append(PageBreak())

    # ── Diagram 4 ──
    story.append(Paragraph("4. TTS &amp; STT Subsystem", styles["SectionTitle"]))
    story.append(Paragraph(
        "The speech synthesis and recognition subsystem. Nine TTS providers (3 requiring API "
        "keys, 2 free cloud, 4 local) feed the voice catalog. Whisper ASR operates in local "
        "GPU or cloud API mode for Pipeline B transcription.",
        styles["DiagCaption"]
    ))
    story.append(Spacer(1, 4))
    story.append(DiagramFlowable(diagram_tts_stt()))
    story.append(PageBreak())

    # ── Diagram 5 ──
    story.append(Paragraph("5. Acoustic Echo Path Simulator", styles["SectionTitle"]))
    story.append(Paragraph(
        "Detailed view of the echo path that models speaker-to-microphone feedback in a "
        "vehicle cabin. Configurable delay, gain attenuation, and EQ filter chain simulate "
        "the acoustic characteristics of the cabin environment.",
        styles["DiagCaption"]
    ))
    story.append(Spacer(1, 4))
    story.append(DiagramFlowable(diagram_echo_detail()))
    story.append(PageBreak())

    # ── Diagram 6 ──
    story.append(Paragraph("6. Statistics &amp; Analysis Pipeline", styles["SectionTitle"]))
    story.append(Paragraph(
        "Three-stage statistical analysis: group-level aggregation with Wilson CIs, pairwise "
        "backend comparison (McNemar + Wilcoxon + Holm-Bonferroni), and ANOVA with effect "
        "sizes. Results feed into visualizations and the React frontend.",
        styles["DiagCaption"]
    ))
    story.append(Spacer(1, 4))
    story.append(DiagramFlowable(diagram_statistics()))
    story.append(PageBreak())

    # ── Diagram 7 ──
    story.append(Paragraph("7. Test Execution &amp; Control Flow", styles["SectionTitle"]))
    story.append(Paragraph(
        "The execution engine: from API trigger through Redis queue, sweep expansion, "
        "checkpoint loading, rate-limited parallel execution, evaluation, result persistence, "
        "and real-time WebSocket progress broadcasting.",
        styles["DiagCaption"]
    ))
    story.append(Spacer(1, 4))
    story.append(DiagramFlowable(diagram_execution()))

    # Build
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output_path


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                       "Audio_LLM_Test_Platform_Block_Diagrams.pdf")
    build_pdf(out)
    print(f"PDF generated: {out}")
