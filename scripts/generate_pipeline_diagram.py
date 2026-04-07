#!/usr/bin/env python3
"""Generate a simplified left-to-right audio pipeline diagram."""

import math
import os

from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white
from reportlab.graphics.shapes import (
    Drawing, Rect, String, Line, Group, Polygon,
)
from reportlab.graphics import renderPDF
from reportlab.platypus import SimpleDocTemplate, Spacer, Flowable


# ── Colors ──────────────────────────────────────────────────────────────────

BG = white
C_TITLE = HexColor("#0f172a")

C_SPEECH_S = HexColor("#16a34a"); C_SPEECH_F = HexColor("#dcfce7")
C_ROAD_S   = HexColor("#ca8a04"); C_ROAD_F   = HexColor("#fef9c3")
C_FAN_S    = HexColor("#ca8a04"); C_FAN_F    = HexColor("#fef9c3")
C_BABBLE_S = HexColor("#9333ea"); C_BABBLE_F = HexColor("#f3e8ff")

C_MIX_S  = HexColor("#1e40af"); C_MIX_F  = HexColor("#dbeafe")
C_PROC_S = HexColor("#16a34a"); C_PROC_F = HexColor("#dcfce7")
C_LLM_S  = HexColor("#1e40af"); C_LLM_F  = HexColor("#dbeafe")
C_EVAL_S = HexColor("#16a34a"); C_EVAL_F = HexColor("#dcfce7")
C_BLOCK_S = HexColor("#334155"); C_BLOCK_F = HexColor("#f8fafc")

C_ARROW    = HexColor("#334155")
C_ARROW_LT = HexColor("#64748b")
C_SUBLABEL = HexColor("#64748b")
C_LABEL    = HexColor("#1e293b")


# ── Helpers ─────────────────────────────────────────────────────────────────

def rrect(g, x, y, w, h, fill, stroke, r=4, sw=1.5):
    g.add(Rect(x, y, w, h, rx=r, ry=r,
               fillColor=fill, strokeColor=stroke, strokeWidth=sw))


def box(g, x, y, w, h, title, sub=None, fill=C_BLOCK_F, stroke=C_BLOCK_S,
        tsz=9, ssz=7):
    rrect(g, x, y, w, h, fill, stroke)
    if sub:
        g.add(String(x + w/2, y + h/2 + 5, title,
                     fontName="Helvetica-Bold", fontSize=tsz,
                     fillColor=C_LABEL, textAnchor="middle"))
        g.add(String(x + w/2, y + h/2 - 8, sub,
                     fontName="Helvetica", fontSize=ssz,
                     fillColor=C_SUBLABEL, textAnchor="middle"))
    else:
        g.add(String(x + w/2, y + h/2 - 3, title,
                     fontName="Helvetica-Bold", fontSize=tsz,
                     fillColor=C_LABEL, textAnchor="middle"))


def arr(g, x1, y1, x2, y2, color=C_ARROW, w=1.5, hs=6):
    g.add(Line(x1, y1, x2, y2, strokeColor=color, strokeWidth=w))
    a = math.atan2(y2 - y1, x2 - x1)
    g.add(Polygon([x2, y2,
                   x2 - hs*math.cos(a - 0.4), y2 - hs*math.sin(a - 0.4),
                   x2 - hs*math.cos(a + 0.4), y2 - hs*math.sin(a + 0.4)],
                  fillColor=color, strokeColor=color, strokeWidth=0.5))


def harr(g, x1, x2, y, color=C_ARROW, w=1.5):
    arr(g, x1, y, x2, y, color, w)


class DiagWrap(Flowable):
    def __init__(self, d):
        Flowable.__init__(self)
        self.drawing = d
        self.width = d.width
        self.height = d.height

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        renderPDF.draw(self.drawing, self.canv, 0, 0)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(HexColor("#9ca3af"))
    canvas.drawCentredString(doc.pagesize[0]/2, 0.35*inch,
                             "Audio LLM Test Platform  |  Pipeline Diagram")
    canvas.restoreState()


# ════════════════════════════════════════════════════════════════════════════
# PIPELINE DIAGRAM
# ════════════════════════════════════════════════════════════════════════════

def diagram_pipeline():
    W, H = 680, 340
    d = Drawing(W, H)
    d.add(Rect(0, 0, W, H, fillColor=BG, strokeColor=None))
    g = Group()

    # ── Vertical positions ──
    main_cy = 195          # centre-line of main horizontal flow
    bh = 40                # block height for main chain
    gap = 12               # horizontal gap between blocks

    # ── INPUT CHANNELS (left side, stacked vertically) ──────────────────
    input_w = 80
    input_h = 28
    input_x = 15
    input_gap = 8

    channels = [
        ("Speech",     C_SPEECH_F, C_SPEECH_S),
        ("Road Noise", C_ROAD_F,   C_ROAD_S),
        ("Fan Noise",  C_FAN_F,    C_FAN_S),
        ("Babble",     C_BABBLE_F, C_BABBLE_S),
    ]

    total_input_h = len(channels) * input_h + (len(channels) - 1) * input_gap
    input_top = main_cy + total_input_h / 2

    ch_ys = []
    for i, (name, fill, stroke) in enumerate(channels):
        cy = input_top - i * (input_h + input_gap) - input_h / 2
        ch_ys.append(cy)
        box(g, input_x, cy - input_h/2, input_w, input_h, name,
            fill=fill, stroke=stroke, tsz=8)

    # ── AUDIO MIXER (tall vertical box) ─────────────────────────────────
    mixer_x = input_x + input_w + 30
    mixer_h = total_input_h + 16
    mixer_w = 55
    mixer_y = main_cy - mixer_h / 2

    box(g, mixer_x, mixer_y, mixer_w, mixer_h, "Audio", "Mixer",
        fill=C_MIX_F, stroke=C_MIX_S, tsz=9, ssz=9)

    # Arrows: each input → mixer
    for cy in ch_ys:
        harr(g, input_x + input_w, mixer_x, cy)

    ax = mixer_x + mixer_w

    # ── ECHO SIMULATOR ──────────────────────────────────────────────────
    ew = 72
    ex = ax + gap
    ey = main_cy - bh/2
    box(g, ex, ey, ew, bh, "Echo", "Simulator", tsz=9, ssz=8)
    harr(g, ax, ex, main_cy)
    ax = ex + ew

    # ── NETWORK SIMULATOR ──────────────────────────────────────────────
    nw = 72
    nx = ax + gap
    ny = main_cy - bh/2
    box(g, nx, ny, nw, bh, "Network", "Simulator", tsz=9, ssz=8)
    harr(g, ax, nx, main_cy)
    ax = nx + nw

    # ── AUDIO PRE-PROCESSING ───────────────────────────────────────────
    ppw = 72
    ppx = ax + gap
    ppy = main_cy - bh/2
    box(g, ppx, ppy, ppw, bh, "Audio", "Pre-processing",
        fill=C_PROC_F, stroke=C_PROC_S, tsz=9, ssz=7)
    harr(g, ax, ppx, main_cy)
    ax = ppx + ppw

    # ── LLM ─────────────────────────────────────────────────────────────
    lw = 50
    lx = ax + gap
    ly = main_cy - bh/2
    box(g, lx, ly, lw, bh, "LLM",
        fill=C_LLM_F, stroke=C_LLM_S, tsz=10)
    harr(g, ax, lx, main_cy)
    ax = lx + lw

    # ── AUDIO POST-PROCESSING ──────────────────────────────────────────
    pow = 72
    pox = ax + gap
    poy = main_cy - bh/2
    box(g, pox, poy, pow, bh, "Audio", "Post-Processing",
        fill=C_PROC_F, stroke=C_PROC_S, tsz=9, ssz=7)
    harr(g, ax, pox, main_cy)
    ax = pox + pow

    # ── EVALUATION & ANALYSIS ENGINE ───────────────────────────────────
    evw = 90
    evh = 50
    evx = ax + gap + 5
    evy = main_cy - evh/2
    box(g, evx, evy, evw, evh, "Evaluation", "&\nAnalysis Engine",
        fill=C_EVAL_F, stroke=C_EVAL_S, tsz=9, ssz=7)
    # Manual multi-line: overwrite the sub
    # Clear and redraw with 3 lines
    rrect(g, evx, evy, evw, evh, C_EVAL_F, C_EVAL_S)
    g.add(String(evx + evw/2, evy + evh/2 + 12, "Evaluation",
                 fontName="Helvetica-Bold", fontSize=9,
                 fillColor=C_LABEL, textAnchor="middle"))
    g.add(String(evx + evw/2, evy + evh/2, "&",
                 fontName="Helvetica", fontSize=8,
                 fillColor=C_SUBLABEL, textAnchor="middle"))
    g.add(String(evx + evw/2, evy + evh/2 - 12, "Analysis Engine",
                 fontName="Helvetica-Bold", fontSize=8,
                 fillColor=C_LABEL, textAnchor="middle"))
    harr(g, ax, evx, main_cy)

    # ── ACOUSTIC ECHO COUPLING PATH (feedback loop along bottom) ───────
    fb_y = main_cy - bh/2 - 55  # below the main chain
    fb_start_x = pox + pow / 2   # bottom of post-processing
    fb_end_x = ex + ew / 2       # bottom of echo simulator

    # Down from post-processing
    g.add(Line(fb_start_x, poy, fb_start_x, fb_y,
               strokeColor=C_ARROW_LT, strokeWidth=1.5,
               strokeDashArray=[5, 3]))
    # Horizontal back to echo sim
    g.add(Line(fb_start_x, fb_y, fb_end_x, fb_y,
               strokeColor=C_ARROW_LT, strokeWidth=1.5,
               strokeDashArray=[5, 3]))
    # Up into echo sim
    arr(g, fb_end_x, fb_y, fb_end_x, ey,
        C_ARROW_LT, 1.5, hs=6)

    # Label centred on the horizontal segment
    label_cx = (fb_start_x + fb_end_x) / 2
    g.add(String(label_cx, fb_y - 12,
                 "Acoustic Echo Coupling Path",
                 fontName="Helvetica-Oblique", fontSize=8,
                 fillColor=C_ARROW_LT, textAnchor="middle"))

    # Dashed bracket marks
    g.add(String(fb_start_x + 3, fb_y + 3, "\u2193",
                 fontName="Helvetica", fontSize=7,
                 fillColor=C_ARROW_LT, textAnchor="middle"))

    d.add(g)
    return d


# ════════════════════════════════════════════════════════════════════════════

def build():
    out = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                       "Audio_LLM_Pipeline_Diagram.pdf")

    doc = SimpleDocTemplate(
        out, pagesize=landscape(letter),
        topMargin=0.8*inch, bottomMargin=0.5*inch,
        leftMargin=0.9*inch, rightMargin=0.9*inch,
        title="Audio LLM Test Platform - Pipeline Diagram",
    )
    story = [Spacer(1, 0.5*inch), DiagWrap(diagram_pipeline())]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"PDF generated: {out}")
    return out


if __name__ == "__main__":
    build()
