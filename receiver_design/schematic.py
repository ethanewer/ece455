"""Draw the active minimal receiver and its module wiring."""
from __future__ import annotations

import re
from pathlib import Path

import matplotlib
import schemdraw
import schemdraw.elements as elm

BLUE = "#174a7e"
GREY = "#555555"
# schemdraw BJT anchors relative to the base: collector/emitter offsets.
BJT_DX = 0.7517
BJT_DY = 0.6967


def wire(drawing, *points):
    for start, end in zip(points, points[1:]):
        drawing += elm.Line().at(start).to(end)


def label(drawing, at, text, **kwargs):
    kwargs.setdefault("fontsize", 8)
    drawing += elm.Label().at(at).label(text, **kwargs)


def dot(drawing, at):
    drawing += elm.Dot(radius=0.06).at(at)


def ground(drawing, at):
    drawing += elm.Ground(lead=False).at(at)


def rail(drawing, at, name="VA"):
    drawing += elm.Vdd(lead=False).at(at).label(name, fontsize=7)


def resistor(drawing, start, end, text, loc="top"):
    drawing += elm.Resistor(scale=0.7).endpoints(start, end).label(text, loc=loc, fontsize=7.5)


def capacitor(drawing, start, end, text, polar=False, loc="top"):
    drawing += elm.Capacitor(polar=polar, scale=0.7).endpoints(start, end).label(
        text, loc=loc, fontsize=7.5)


def npn(drawing, base, text):
    drawing += elm.BjtNpn(circle=True).right().anchor("base").at(base).label(
        text, loc="right", fontsize=7.5, ofst=(0.1, 0))
    return ((base[0] + BJT_DX, base[1] + BJT_DY),
            (base[0] + BJT_DX, base[1] - BJT_DY))


def pnp(drawing, base, text):
    drawing += elm.BjtPnp(circle=True).right().anchor("base").at(base).label(
        text, loc="right", fontsize=7.5, ofst=(0.1, 0))
    # Returns (emitter at top, collector at bottom).
    return ((base[0] + BJT_DX, base[1] + BJT_DY),
            (base[0] + BJT_DX, base[1] - BJT_DY))


def build_receiver_schematic(output_dir: Path) -> tuple[Path, Path]:
    """Write the construction schematic; KiCad connectivity mirrors it."""
    output_dir.mkdir(parents=True, exist_ok=True)
    drawing = schemdraw.Drawing(show=False)
    drawing.config(unit=1.5, inches_per_unit=0.55, fontsize=8,
                   lw=1.1, bgcolor="white", margin=0.5)

    label(drawing, (0.0, 17.2), "Discrete band-pass proton magnetometer receiver",
          fontsize=14, halign="left", valign="bottom")
    label(drawing, (0.0, 16.6),
          "Gain ≥ 2000 V/V (J1 to AIN0−AIN1) across 1.6–2.2 kHz; |Z_in| ≥ 1 MΩ. "
          "The sensing coil, tuning capacitor, and damping resistor are external to J1.",
          fontsize=8.5, color=BLUE, halign="left", valign="bottom")

    # Input and clamps. Q5/Q6 are diode-connected 2N3904s (collector = base).
    y_in = 12.0
    label(drawing, (0.0, y_in + 0.25), "J1 signal", color=BLUE,
          halign="left", valign="bottom")
    label(drawing, (0.0, y_in - 0.3), "J1 return → GND", color=BLUE,
          halign="left", valign="top")
    dot(drawing, (0.0, y_in))
    wire(drawing, (0.0, y_in), (3.6, y_in))
    for x, name, reverse in ((1.3, "Q5", False), (2.6, "Q6", True)):
        dot(drawing, (x, y_in))
        bottom = (x, y_in - 1.8)
        clamp = elm.Diode(scale=0.7).endpoints((x, y_in), bottom)
        if reverse:
            clamp = clamp.reverse()
        drawing += clamp.label(f"{name}\n2N3904\nC=B", loc="bottom", fontsize=7)
        ground(drawing, bottom)
    capacitor(drawing, (3.6, y_in), (5.2, y_in), "C1 100 nF")
    base_node = (5.2, y_in)
    dot(drawing, base_node)
    base1 = (5.8, y_in)
    wire(drawing, base_node, base1)

    # Stage 1: Q1 input, Q2 gain, Q3 follower; gain 1 + R7/R8.
    q1_col, q1_emit = npn(drawing, base1, "Q1\n2N3904")
    top1 = (q1_col[0], q1_col[1] + 0.5)
    wire(drawing, q1_col, top1)
    resistor(drawing, (top1[0], top1[1] + 1.6), top1, "R4 24.9 kΩ", loc="bottom")
    rail(drawing, (top1[0], top1[1] + 1.6))
    base2 = (top1[0] + 1.2, top1[1])
    wire(drawing, top1, base2)
    dot(drawing, top1)
    q2_emit, q2_col = pnp(drawing, base2, "Q2\n2N3906")
    rail(drawing, q2_emit)
    q2_node = (q2_col[0], q2_col[1] - 0.6)
    wire(drawing, q2_col, q2_node)
    dot(drawing, q2_node)
    resistor(drawing, q2_node, (q2_node[0], q2_node[1] - 1.0), "R5\n47 kΩ", loc="bottom")
    ground(drawing, (q2_node[0], q2_node[1] - 1.0))
    base3 = (q2_node[0] + 0.8, q2_node[1])
    wire(drawing, q2_node, base3)
    q3_col, q3_emit = npn(drawing, base3, "Q3\n2N3904")
    rail(drawing, q3_col)

    y_fb = 10.0
    emit = (q1_emit[0], y_fb)
    wire(drawing, q1_emit, emit)
    dot(drawing, emit)
    stage1 = (q3_emit[0], y_fb)
    wire(drawing, q3_emit, stage1)
    dot(drawing, stage1)
    wire(drawing, emit, (emit[0] + 0.7, y_fb))
    resistor(drawing, (stage1[0] - 0.6, y_fb), (emit[0] + 0.7, y_fb), "R7 5.1 kΩ", loc="bottom")
    wire(drawing, (stage1[0] - 0.6, y_fb), stage1)
    resistor(drawing, emit, (emit[0], y_fb - 1.4), "R8\n150 Ω", loc="bottom")
    capacitor(drawing, (emit[0], y_fb - 1.4), (emit[0], y_fb - 2.7),
              "C4\n1 µF", polar=True, loc="bottom")
    ground(drawing, (emit[0], y_fb - 2.7))
    resistor(drawing, stage1, (stage1[0], y_fb - 1.5), "R6\n2.2 kΩ", loc="bottom")
    ground(drawing, (stage1[0], y_fb - 1.5))

    # Bootstrapped bias: R1 to BOOT, C2 from BOOT to Q1 emitter, R2 to BIAS.
    boot = (base_node[0], y_fb)
    resistor(drawing, base_node, boot, "R1\n470 kΩ", loc="top")
    dot(drawing, boot)
    capacitor(drawing, boot, emit, "C2 100 nF", loc="bottom")
    y_bias = 6.3
    bias = (boot[0], y_bias)
    resistor(drawing, boot, (boot[0], y_bias + 0.9), "R2\n100 kΩ", loc="top")
    wire(drawing, (boot[0], y_bias + 0.9), bias)
    dot(drawing, bias)
    capacitor(drawing, bias, (bias[0] - 1.3, bias[1]), "C3 100 nF", loc="bottom")
    wire(drawing, (bias[0] - 1.3, bias[1]), (bias[0] - 1.3, bias[1] - 0.6))
    ground(drawing, (bias[0] - 1.3, bias[1] - 0.6))

    # Band-pass filter between the stages. Sallen-Key high-pass (C8, C9,
    # R12, R13) buffered by Q7, then Sallen-Key low-pass (R15, R16, C10,
    # C11) buffered by the PNP follower Q8.
    hp_in = (stage1[0] + 0.4, y_fb)
    wire(drawing, stage1, hp_in)
    hp_a = (hp_in[0] + 1.4, y_fb)
    capacitor(drawing, hp_in, hp_a, "C8 6.8 nF")
    dot(drawing, hp_a)
    hp_b = (hp_a[0] + 1.4, y_fb)
    capacitor(drawing, hp_a, hp_b, "C9 6.8 nF")
    dot(drawing, hp_b)
    resistor(drawing, hp_b, (hp_b[0], y_fb - 1.8), "R13\n47 kΩ", loc="bottom")
    wire(drawing, (hp_b[0], y_fb - 1.8), (hp_b[0], y_bias))
    dot(drawing, (hp_b[0], y_bias))
    base7 = (hp_b[0] + 0.6, y_fb)
    wire(drawing, hp_b, base7)
    q7_col, q7_emit = npn(drawing, base7, "Q7\n2N3904")
    rail(drawing, q7_col)
    filt = (q7_emit[0], q7_emit[1] - 0.4)
    wire(drawing, q7_emit, filt)
    dot(drawing, filt)
    resistor(drawing, filt, (filt[0], filt[1] - 1.4), "R14\n47 kΩ", loc="bottom")
    ground(drawing, (filt[0], filt[1] - 1.4))
    r12_y = y_fb + 1.9
    wire(drawing, hp_a, (hp_a[0], r12_y))
    resistor(drawing, (hp_a[0], r12_y), (filt[0] + 0.5, r12_y), "R12 6.8 kΩ")
    wire(drawing, (filt[0] + 0.5, r12_y), (filt[0] + 0.5, filt[1]), filt)

    lp_in = (filt[0] + 0.5, filt[1])
    dot(drawing, lp_in)
    lp_a = (lp_in[0] + 1.5, filt[1])
    resistor(drawing, lp_in, lp_a, "R15 20 kΩ")
    dot(drawing, lp_a)
    lp_b = (lp_a[0] + 1.5, filt[1])
    resistor(drawing, lp_a, lp_b, "R16 20 kΩ")
    dot(drawing, lp_b)
    capacitor(drawing, lp_b, (lp_b[0], lp_b[1] - 1.3), "C11\n1 nF", loc="bottom")
    ground(drawing, (lp_b[0], lp_b[1] - 1.3))
    base8 = (lp_b[0] + 0.6, lp_b[1])
    wire(drawing, lp_b, base8)
    q8_emit, q8_col = pnp(drawing, base8, "Q8\n2N3906")
    ground(drawing, q8_col)
    lpo = (q8_emit[0], q8_emit[1] + 0.4)
    wire(drawing, q8_emit, lpo)
    dot(drawing, lpo)
    resistor(drawing, (lpo[0], lpo[1] + 1.4), lpo, "R17 33 kΩ", loc="bottom")
    rail(drawing, (lpo[0], lpo[1] + 1.4))
    c10_y = y_fb + 3.3
    wire(drawing, lp_a, (lp_a[0], c10_y))
    capacitor(drawing, (lp_a[0], c10_y), (lpo[0] + 0.5, c10_y), "C10 6.8 nF")
    wire(drawing, (lpo[0] + 0.5, c10_y), (lpo[0] + 0.5, lpo[1]), lpo)

    # Stage 2: Q4 common emitter; its collector is AIN0.
    base4 = (lpo[0] + 1.1, lpo[1])
    dot(drawing, (lpo[0] + 0.5, lpo[1]))
    wire(drawing, (lpo[0] + 0.5, lpo[1]), base4)
    q4_col, q4_emit = npn(drawing, base4, "Q4\n2N3904")
    out = (q4_col[0], q4_col[1] + 0.7)
    wire(drawing, q4_col, out)
    dot(drawing, out)
    resistor(drawing, (out[0], out[1] + 1.6), out, "R10 20 kΩ", loc="bottom")
    rail(drawing, (out[0], out[1] + 1.6))
    e4 = (q4_emit[0], q4_emit[1] - 0.4)
    wire(drawing, q4_emit, e4)
    dot(drawing, e4)
    resistor(drawing, e4, (e4[0], e4[1] - 1.5), "R9\n8.2 kΩ", loc="bottom")
    ground(drawing, (e4[0], e4[1] - 1.5))
    wire(drawing, e4, (e4[0] + 1.1, e4[1]))
    capacitor(drawing, (e4[0] + 1.1, e4[1]), (e4[0] + 1.1, e4[1] - 1.5),
              "C5\n1 µF", polar=True, loc="bottom")
    ground(drawing, (e4[0] + 1.1, e4[1] - 1.5))

    # R3 closes the DC loop to BIAS; C7 to ground adds a low-pass pole.
    x_r3 = out[0] + 2.0
    x_c7 = out[0] + 3.0
    x_end = out[0] + 3.8
    wire(drawing, out, (x_end, out[1]))
    dot(drawing, (x_r3, out[1]))
    dot(drawing, (x_r3, y_bias))
    resistor(drawing, (x_r3, out[1]), (x_r3, out[1] - 1.8), "R3\n1 MΩ", loc="top")
    wire(drawing, (x_r3, out[1] - 1.8), (x_r3, y_bias))
    dot(drawing, (x_c7, out[1]))
    capacitor(drawing, (x_c7, out[1]), (x_c7, out[1] - 1.5), "C7\n2.2 nF", loc="bottom")
    ground(drawing, (x_c7, out[1] - 1.5))
    wire(drawing, bias, (x_end, y_bias))
    label(drawing, (x_end + 0.1, out[1]), "ADS1256 AIN0", color=BLUE,
          halign="left", valign="center")
    label(drawing, (x_end + 0.1, y_bias), "ADS1256 AIN1\n(BIAS ≈ 1.6 V)", color=BLUE,
          halign="left", valign="center")
    label(drawing, (0.0, y_bias - 1.5),
          "Stage 1 gain 1 + R7/R8 = 35 (Q1 ≈ 26 µA). Stage 2 gain ≈ (VA − VOUT)/VT. "
          "R3 closes the DC loop that sets every bias point; C2 bootstraps R1.\n"
          "Band-pass between the stages: Sallen-Key high-pass (1.31 kHz, Q 1.3) with Q7, "
          "Sallen-Key low-pass (3.05 kHz, Q 1.3) with Q8, and C7.",
          fontsize=8, color=GREY, halign="left", valign="top")

    # Power and module wiring.
    y_p = 2.6
    label(drawing, (0.0, y_p), "USB 5 V (XIAO VBUS)", color=BLUE, halign="left", valign="center")
    dot(drawing, (2.9, y_p))
    wire(drawing, (2.9, y_p), (3.4, y_p))
    resistor(drawing, (3.4, y_p), (5.2, y_p), "R11 470 Ω")
    dot(drawing, (5.2, y_p))
    capacitor(drawing, (5.2, y_p), (5.2, y_p - 1.4), "C6\n470 µF", polar=True, loc="bottom")
    ground(drawing, (5.2, y_p - 1.4))
    wire(drawing, (5.2, y_p), (6.2, y_p))
    label(drawing, (6.3, y_p), "VA ≈ 4.8 V", color=BLUE, halign="left", valign="center")
    for row, text in enumerate((
        "ADS1256 module: 5V ← XIAO VBUS, GND ← GND. Buffer on, PGA 1, 30 kSPS, AIN0 − AIN1.",
        "SPI wired directly (3.3 V): XIAO D8/GPIO2 → SCLK, D10/GPIO3 → DIN, D9/GPIO4 ← DOUT,",
        "D3/GPIO5 → CS, D2/GPIO28 ← DRDY, D4/GPIO6 → SYNC/PDWN. No level translation is needed.",
    )):
        label(drawing, (9.0, y_p + 0.4 - 0.65 * row), text, halign="left", valign="center")

    svg_path = output_dir / "receiver-construction-schematic.svg"
    png_path = output_dir / "receiver-construction-schematic.png"
    # A fixed salt makes Matplotlib's SVG clip-path IDs repeatable.
    with matplotlib.rc_context({"svg.hashsalt": "receiver-construction-schematic"}):
        drawing.save(svg_path, transparent=False)
    drawing.save(png_path, transparent=False, dpi=170)
    svg_text = svg_path.read_text()
    svg_text = re.sub(r"\n\s*<dc:date>.*?</dc:date>", "", svg_text)
    svg_path.write_text("\n".join(line.rstrip() for line in svg_text.splitlines()) + "\n")
    return svg_path, png_path
