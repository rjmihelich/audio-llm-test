#!/usr/bin/env python3
"""Generate a 1-page high-level test plan PDF for the Audio LLM Test Platform."""

import os
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)


# ── Colours ─────────────────────────────────────────────────────────────────

C_HDR   = HexColor("#1e3a5f")
C_ACCENT = HexColor("#2563eb")
C_BG     = HexColor("#f0f4fa")
C_WHITE  = HexColor("#ffffff")
C_BORDER = HexColor("#cbd5e1")
C_TEXT   = HexColor("#1e293b")
C_SUB    = HexColor("#475569")
C_GREEN  = HexColor("#dcfce7")
C_GREENB = HexColor("#16a34a")


def build():
    out = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                       "Audio_LLM_Test_Plan.pdf")

    doc = SimpleDocTemplate(
        out, pagesize=letter,
        topMargin=0.5*inch, bottomMargin=0.45*inch,
        leftMargin=0.6*inch, rightMargin=0.6*inch,
        title="Audio LLM Test Platform — Test Plan",
    )

    # ── Styles ──────────────────────────────────────────────────────────
    s_title = ParagraphStyle("Title1", fontName="Helvetica-Bold",
                             fontSize=16, textColor=C_HDR, alignment=TA_CENTER,
                             spaceAfter=2)
    s_sub = ParagraphStyle("Sub1", fontName="Helvetica",
                           fontSize=9, textColor=C_SUB, alignment=TA_CENTER,
                           spaceAfter=8)
    s_h2 = ParagraphStyle("H2", fontName="Helvetica-Bold",
                          fontSize=10, textColor=C_ACCENT, spaceBefore=8,
                          spaceAfter=3)
    s_body = ParagraphStyle("Body1", fontName="Helvetica",
                            fontSize=8.5, textColor=C_TEXT, leading=11,
                            spaceAfter=2)
    s_cell = ParagraphStyle("Cell", fontName="Helvetica",
                            fontSize=8, textColor=C_TEXT, leading=10)
    s_cellb = ParagraphStyle("CellB", fontName="Helvetica-Bold",
                             fontSize=8, textColor=C_HDR, leading=10)
    s_note = ParagraphStyle("Note", fontName="Helvetica-Oblique",
                            fontSize=7.5, textColor=C_SUB, leading=9,
                            spaceBefore=4)

    story = []

    # ── Header ──────────────────────────────────────────────────────────
    story.append(Paragraph("Audio LLM Test Platform — Test Plan", s_title))
    story.append(Paragraph("High-Level Verification &amp; Validation Strategy", s_sub))

    # ── 1. Objective ────────────────────────────────────────────────────
    story.append(Paragraph("1. Objective", s_h2))
    story.append(Paragraph(
        "Verify end-to-end correctness and performance of the audio pipeline — from speech input "
        "through noise mixing, echo simulation, network impairment, audio pre/post-processing, "
        "LLM inference, and evaluation — under controlled, repeatable conditions.",
        s_body))

    # ── 2. Scope ────────────────────────────────────────────────────────
    story.append(Paragraph("2. Scope", s_h2))
    scope_data = [
        [Paragraph("<b>In Scope</b>", s_cell),
         Paragraph("<b>Out of Scope</b>", s_cell)],
        [Paragraph(
            "• Audio mixer gain accuracy &amp; summing<br/>"
            "• Noise injection (road, fan, babble) at target SNR<br/>"
            "• Echo simulator coupling path fidelity<br/>"
            "• Network simulator (packet loss, jitter, BW limiting)<br/>"
            "• Audio pre/post-processing chain<br/>"
            "• LLM response correctness (intent, action)<br/>"
            "• Evaluation scoring (command match, LLM judge)<br/>"
            "• Statistical analysis (ANOVA, McNemar, Wilcoxon)", s_cell),
         Paragraph(
            "• TTS provider internal quality<br/>"
            "• Third-party API availability / uptime<br/>"
            "• Frontend UI cosmetic testing<br/>"
            "• Load / stress testing beyond stated concurrency<br/>"
            "• Hardware-in-the-loop acoustic testing", s_cell)],
    ]
    scope_tbl = Table(scope_data, colWidths=[3.5*inch, 3.3*inch])
    scope_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_HDR),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("BACKGROUND", (0, 1), (-1, -1), C_BG),
        ("BOX", (0, 0), (-1, -1), 0.6, C_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, C_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(scope_tbl)

    # ── 3. Test Areas ───────────────────────────────────────────────────
    story.append(Paragraph("3. Test Areas", s_h2))

    areas = [
        ["Area", "Tests", "Method", "Pass Criteria"],
        ["Audio Mixer",
         "Gain linearity, channel summing, clipping behaviour",
         "Unit — inject known tones, measure output amplitude",
         "Output within ±0.5 dB of expected level"],
        ["Noise Injection",
         "SNR accuracy for road, fan, babble at 0–30 dB range",
         "Unit — measure RMS ratio of signal vs. noise",
         "Measured SNR within ±1 dB of target"],
        ["Echo Simulator",
         "Delay accuracy, gain, coupling path feedback loop",
         "Unit — impulse response measurement",
         "Delay within ±1 ms; gain within ±0.5 dB"],
        ["Network Simulator",
         "Packet loss %, jitter distribution, BW throttling",
         "Unit — frame-level loss counting, timing analysis",
         "Measured loss/jitter within 5% of configured value"],
        ["Audio Pre-processing",
         "Format conversion, sample rate, bit depth, encoding",
         "Unit — round-trip encode/decode, compare buffers",
         "Bit-exact or PESQ > 4.0 after round-trip"],
        ["LLM Integration",
         "API connectivity, response parsing, timeout handling",
         "Integration — live API call with known prompts",
         "Correct intent extracted; latency < target"],
        ["Audio Post-processing",
         "Decode, normalisation, output format",
         "Unit — validate output sample rate and level",
         "Output conforms to expected format and level"],
        ["Evaluation Engine",
         "Command match scoring, LLM judge agreement",
         "Integration — score known-good and known-bad pairs",
         "Accuracy ≥ 95% vs. human-labelled ground truth"],
        ["End-to-End Pipeline",
         "Full path: speech → mixer → echo → net → LLM → eval",
         "System — sweep SNR, noise type, echo, network profiles",
         "Results reproducible within ±2% across repeated runs"],
        ["Statistical Analysis",
         "ANOVA, McNemar, Wilcoxon, confidence intervals",
         "Unit — synthetic result sets with known distributions",
         "p-values and CIs match reference implementation"],
    ]

    col_w = [1.05*inch, 1.85*inch, 1.9*inch, 1.95*inch]
    area_tbl = Table(
        [[Paragraph(c, s_cellb) if r == 0 else Paragraph(c, s_cell)
          for c in row]
         for r, row in enumerate(areas)],
        colWidths=col_w,
    )
    area_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_HDR),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("BACKGROUND", (0, 1), (-1, -1), C_WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_BG]),
        ("BOX", (0, 0), (-1, -1), 0.6, C_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, C_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(area_tbl)

    # ── 4. Environment & Dependencies ───────────────────────────────────
    story.append(Paragraph("4. Environment", s_h2))
    story.append(Paragraph(
        "<b>Runtime:</b> Python 3.9+, PostgreSQL, Redis, arq worker &nbsp;|&nbsp; "
        "<b>CI:</b> pytest (unit + integration), pre-commit hooks &nbsp;|&nbsp; "
        "<b>APIs:</b> OpenAI, Anthropic, Google, Deepgram, ElevenLabs &nbsp;|&nbsp; "
        "<b>Metrics:</b> PESQ, SNR, latency (ms), intent accuracy (%)",
        s_body))

    # ── 5. Risks ────────────────────────────────────────────────────────
    story.append(Paragraph("5. Key Risks", s_h2))
    story.append(Paragraph(
        "• <b>API rate limits / outages</b> — mitigate with retry logic and mock backends for CI<br/>"
        "• <b>Non-deterministic LLM output</b> — mitigate with temperature=0, seed params, and tolerance bands<br/>"
        "• <b>Network sim fidelity</b> — validated against real cellular capture traces (packet loss, jitter profiles)",
        s_body))

    # ── Footer note ─────────────────────────────────────────────────────
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "This test plan covers high-level verification strategy. Detailed test cases, "
        "data sets, and automation scripts are maintained in the project repository.",
        s_note))

    # ── Build ───────────────────────────────────────────────────────────
    def page_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(HexColor("#9ca3af"))
        canvas.drawCentredString(
            letter[0]/2, 0.3*inch,
            "Audio LLM Test Platform  |  Test Plan  |  Confidential")
        canvas.restoreState()

    doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    print(f"PDF generated: {out}")
    return out


if __name__ == "__main__":
    build()
