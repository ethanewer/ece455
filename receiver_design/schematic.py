"""Generate a readable construction schematic for the analog receiver path."""
from __future__ import annotations

import re
from pathlib import Path

import schemdraw
import schemdraw.elements as elm

# schemdraw Opamp, direction right, anchor at the input-side midpoint.
_IN_OFFSET = 0.625
_TOP_OFFSET = 1.25
_NET = "#174a7e"


def _wire(drawing: schemdraw.Drawing, start, end) -> None:
    drawing += elm.Line().at(start).to(end)


def _dot(drawing: schemdraw.Drawing, at) -> None:
    drawing += elm.Dot(radius=0.055).at(at)


def _text(drawing: schemdraw.Drawing, at, text: str, **kwargs) -> None:
    kwargs.setdefault("fontsize", 8)
    drawing += elm.Label().at(at).label(text, **kwargs)


def _bias_arrow(drawing: schemdraw.Drawing, at, direction: str, name: str) -> None:
    """Short rail arrow with the net name beside the head, off the shaft."""
    arrow = elm.Arrow().at(at)
    if direction == "up":
        drawing += arrow.up(length=0.28)
        _text(drawing, (at[0] + 0.16, at[1] + 0.42), name, halign="left", valign="center", color=_NET)
    elif direction == "down":
        drawing += arrow.down(length=0.28)
        _text(drawing, (at[0] + 0.16, at[1] - 0.42), name, halign="left", valign="center", color=_NET)
    else:
        drawing += arrow.left(length=0.55)
        _text(drawing, (at[0] - 0.7, at[1] - 0.28), name, halign="right", valign="top", color=_NET)


def build_receiver_schematic(output_dir: Path) -> tuple[Path, Path]:
    """Write SVG and PNG schematics of the buildable analog signal path.

    Each stage is a horizontal band. Feedback stays above the op-amp, and
    shunt parts hang in the open side of that band so labels are not drawn
    on top of wires.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    drawing = schemdraw.Drawing(show=False)
    drawing.config(unit=2.0, inches_per_unit=0.62, fontsize=8, lw=1.15, bgcolor="white", margin=0.45)

    _text(
        drawing, (0.15, 16.55),
        "Proton magnetometer receiver: broadband coil input, blanking, and 1.5-2.5 kHz bandpass",
        fontsize=13, halign="left", valign="bottom",
    )
    _text(
        drawing, (0.15, 16.05),
        "U1 is OPA4197. Power pins: 4 = OPA_AVDD_5V, 11 = GND. Place C22 100nF at U1.",
        fontsize=8, halign="left", valign="bottom",
    )
    _text(
        drawing, (0.15, 15.62),
        "U1A: OUT 1, −IN 2, +IN 3    |    U1B: +IN 5, −IN 6, OUT 7    |    U1C: OUT 8, −IN 9, +IN 10    |    U1D: +IN 12, −IN 13, OUT 14",
        fontsize=7.5, halign="left", valign="bottom",
    )
    _text(
        drawing, (0.15, 15.22),
        "Filtered coil-to-ADC gain stays near 2000 V/V from 1.5-2.5 kHz; ADS1256 PGA excluded",
        fontsize=8, halign="left", valign="bottom", color=_NET,
    )

    # Row 1. Signal enters the lower (+) pin. Feedback and R6 sit above U1A.
    signal_y = 11.35
    drawing += elm.SourceSin().at((0.2, signal_y)).down(length=1.35)
    _text(drawing, (-1.25, signal_y - 0.62), "Vfid\nexternal", halign="right", valign="center")
    drawing += elm.Ground()
    drawing += elm.Resistor().at((0.2, signal_y)).right(length=1.9).label("Rcoil 14Ω", loc="top")
    drawing += elm.Inductor().right(length=1.9).label("Lcoil 22mH", loc="top")
    coil_hi = (0.2 + 3.8, signal_y)
    _dot(drawing, coil_hi)
    _text(drawing, (coil_hi[0] + 0.12, coil_hi[1] + 0.55), "COIL_HI (untuned)", halign="left", valign="bottom", color=_NET)
    drawing += elm.Capacitor().at(coil_hi).right(length=1.9).label("C5 3.3n", loc="bottom")
    drawing += elm.Resistor().right(length=1.9).label("R1 1k", loc="top")
    pre_in = (0.2 + 7.6, signal_y)
    _dot(drawing, pre_in)
    _text(drawing, (pre_in[0] + 0.12, pre_in[1] + 0.38), "PRE_IN", halign="left", valign="bottom", color=_NET)

    u1a = drawing.add(elm.Opamp().at((18.15, signal_y + _IN_OFFSET)).right())
    _wire(drawing, pre_in, u1a.in2)
    _text(drawing, u1a.center, "U1A", fontsize=8)

    branch_x = (9.35, 11.45, 13.55, 15.65)
    _dot(drawing, (branch_x[0], signal_y))
    drawing += elm.Diode().at((branch_x[0], signal_y)).down(length=1.35).reverse()
    drawing += elm.Ground()
    _text(drawing, (branch_x[0] - 0.62, signal_y - 0.72), "D1\nBAS116", halign="right", valign="center")

    _dot(drawing, (branch_x[1], signal_y))
    drawing += elm.Resistor().at((branch_x[1], signal_y)).down(length=1.35)
    _text(drawing, (branch_x[1] - 0.18, signal_y - 0.7), "R2 100k", halign="right", valign="center")
    _bias_arrow(drawing, (branch_x[1], signal_y - 1.35), "down", "VBIAS_1V5")

    _dot(drawing, (branch_x[2], signal_y))
    drawing += elm.Diode().at((branch_x[2], signal_y)).up(length=1.25)
    _text(drawing, (branch_x[2] + 0.58, signal_y + 0.62), "D2\nBAS116", halign="left", valign="center")
    _bias_arrow(drawing, (branch_x[2], signal_y + 1.25), "up", "AVDD_3V3")

    _dot(drawing, (branch_x[3], signal_y))
    drawing += elm.Switch(nc=True).at((branch_x[3], signal_y)).down(length=1.35)
    _text(
        drawing, (branch_x[3] + 0.55, signal_y - 0.85),
        "U2 TMUX1101\nblanking shunt", halign="left", valign="center",
    )
    _bias_arrow(drawing, (branch_x[3], signal_y - 1.35), "down", "VBIAS_1V5")

    feedback_y = u1a.center[1] + _TOP_OFFSET + 0.85
    join_x = u1a.in1[0] - 1.15
    _wire(drawing, u1a.in1, (join_x, u1a.in1[1]))
    _wire(drawing, (join_x, u1a.in1[1]), (join_x, feedback_y))
    drawing += elm.Resistor().at((join_x, feedback_y)).up(length=0.85)
    _text(drawing, (join_x - 0.16, feedback_y + 0.42), "R6 1k", halign="right", valign="center")
    _bias_arrow(drawing, (join_x, feedback_y + 0.85), "up", "VBIAS_1V5")
    _dot(drawing, u1a.out)
    _wire(drawing, u1a.out, (u1a.out[0], feedback_y))
    drawing += (
        elm.Resistor()
        .at((u1a.out[0], feedback_y))
        .left(length=u1a.out[0] - join_x)
        .label("R7 54.9k", loc="bottom")
    )
    _text(
        drawing, (u1a.out[0] + 0.28, u1a.out[1] - 0.08),
        "STAGE1\ngain 55.9", halign="left", valign="top", color=_NET,
    )

    # Row 2 left: inverting high-pass. Feedback is above U1B, clear of the input wire.
    _text(drawing, (0.15, 8.5), "High-pass and gain stage", fontsize=11, halign="left", valign="bottom")
    stage_y = 7.15
    drawing += elm.Arrow().at((0.15, stage_y)).right(length=0.9).label("STAGE1", loc="top")
    drawing += elm.Capacitor().right(length=1.9).label("C7 100n C0G 1206", loc="top")
    drawing += elm.Resistor().right(length=1.85).label("R8 1.05k", loc="top")
    r8_end = (0.15 + 0.9 + 1.9 + 1.85, stage_y)
    join_b = (r8_end[0] + 0.55, stage_y)
    u1b = drawing.add(elm.Opamp().at((join_b[0] + 1.15, stage_y - _IN_OFFSET)).right())
    _wire(drawing, r8_end, join_b)
    _dot(drawing, join_b)
    _wire(drawing, join_b, u1b.in1)
    _text(drawing, u1b.center, "U1B", fontsize=8)
    _bias_arrow(drawing, u1b.in2, "left", "VBIAS_1V5")

    feedback_b = u1b.center[1] + _TOP_OFFSET + 0.7
    _wire(drawing, join_b, (join_b[0], feedback_b))
    _wire(drawing, u1b.out, (u1b.out[0], feedback_b))
    drawing += (
        elm.Resistor()
        .at((u1b.out[0], feedback_b))
        .left(length=u1b.out[0] - join_b[0])
        .label("R9 59k", loc="bottom")
    )
    _dot(drawing, u1b.out)
    _text(drawing, (u1b.out[0] + 0.25, u1b.out[1] + 0.42), "STAGE2", halign="left", valign="bottom", color=_NET)
    _text(
        drawing, (u1b.out[0] + 0.25, u1b.out[1] - 0.12),
        "1.516 kHz\ngain −56.19", halign="left", valign="top",
    )

    # Row 2 right: unity-gain Sallen-Key. C8 returns below the op-amp.
    _text(
        drawing, (12.15, 8.5),
        "Sallen-Key low-pass and ADS1256 input",
        fontsize=11, halign="left", valign="bottom",
    )
    drawing += elm.Arrow().at((12.35, stage_y)).right(length=0.85).label("STAGE2", loc="top")
    drawing += elm.Resistor().right(length=1.7).label("R10 10.2k", loc="top")
    mid = (12.35 + 0.85 + 1.7, stage_y)
    _dot(drawing, mid)
    drawing += elm.Resistor().at(mid).right(length=1.7).label("R11 10.2k", loc="top")
    plus = (mid[0] + 1.7, stage_y)
    _dot(drawing, plus)
    u1c = drawing.add(elm.Opamp().at((plus[0] + 1.45, stage_y + _IN_OFFSET)).right())
    _wire(drawing, plus, u1c.in2)
    _text(drawing, u1c.center, "U1C", fontsize=8)

    drawing += elm.Capacitor().at(plus).down(length=1.25)
    _text(drawing, (plus[0] + 0.16, plus[1] - 0.62), "C23 3.9n", halign="left", valign="center")
    _bias_arrow(drawing, (plus[0], plus[1] - 1.25), "down", "VBIAS_1V5")

    loop_y = u1c.center[1] + _TOP_OFFSET + 0.58
    tap_x = u1c.in1[0] - 0.85
    _wire(drawing, u1c.in1, (tap_x, u1c.in1[1]))
    _wire(drawing, (tap_x, u1c.in1[1]), (tap_x, loop_y))
    _wire(drawing, (tap_x, loop_y), (u1c.out[0], loop_y))
    _wire(drawing, (u1c.out[0], loop_y), u1c.out)

    return_y = stage_y - 2.55
    drawing += elm.Capacitor().at(mid).down(length=stage_y - return_y)
    _text(drawing, (mid[0] - 0.16, (stage_y + return_y) / 2), "C8 6.8n", halign="right", valign="center")
    _wire(drawing, (mid[0], return_y), (u1c.out[0], return_y))
    _wire(drawing, (u1c.out[0], return_y), u1c.out)
    _dot(drawing, u1c.out)

    drawing += elm.Resistor().at(u1c.out).right(length=1.65).label("R12 10k", loc="top")
    r12_end = (u1c.out[0] + 1.65, u1c.out[1])
    clamp_x = r12_end[0] + 0.85
    ain_x = clamp_x + 1.7
    _wire(drawing, r12_end, (ain_x, r12_end[1]))
    _dot(drawing, (clamp_x, r12_end[1]))
    _dot(drawing, (ain_x, r12_end[1]))
    _text(
        drawing, (ain_x + 0.18, r12_end[1] + 0.16),
        "ADS1256 AIN0", halign="left", valign="bottom", color=_NET,
    )

    drawing += elm.Diode().at((clamp_x, r12_end[1])).up(length=1.4)
    _text(drawing, (clamp_x + 0.5, r12_end[1] + 0.48), "D3\nBAS116", halign="left", valign="center")
    clamp = (clamp_x, r12_end[1] + 1.4)
    _dot(drawing, clamp)
    _text(drawing, (clamp[0] + 1.85, clamp[1] + 0.02), "CLAMP_1V8", halign="left", valign="center", color=_NET)
    drawing += elm.Resistor().at(clamp).up(length=0.85)
    _text(drawing, (clamp[0] - 0.42, clamp[1] + 0.48), "R14 1.21k", halign="right", valign="center")
    _bias_arrow(drawing, (clamp[0], clamp[1] + 0.85), "up", "OPA_AVDD_5V")
    drawing += elm.Resistor().at(clamp).right(length=1.35).label("R15 681", loc="top")
    drawing += elm.Ground()
    drawing += elm.Capacitor().at(clamp).left(length=1.15).label("C24 100n", loc="bottom")

    drawing += elm.Capacitor().at((ain_x, r12_end[1])).down(length=1.15)
    _text(drawing, (ain_x + 0.16, r12_end[1] - 0.58), "C9 2.2n", halign="left", valign="center")
    _bias_arrow(drawing, (ain_x, r12_end[1] - 1.15), "down", "VBIAS_1V5 / AIN1")

    # Row 3: buffered bias, with the power notes to the right of U1D.
    _text(drawing, (0.15, 4.35), "Buffered 1.50 V bias", fontsize=11, halign="left", valign="bottom")
    raw_y = 2.15
    drawing += elm.Arrow().at((1.15, 3.35)).down(length=0.01)
    _text(drawing, (0.95, 3.35), "OPA_AVDD_5V", halign="right", valign="center", color=_NET)
    drawing += elm.Resistor().at((1.15, 3.35)).down(length=1.2)
    _text(drawing, (0.95, 2.75), "R4 23.2k 0.1%", halign="right", valign="center")
    raw = (1.15, raw_y)
    _dot(drawing, raw)
    _text(drawing, (1.85, raw_y + 0.42), "VREF_RAW", halign="left", valign="bottom", color=_NET)
    drawing += elm.Resistor().at(raw).down(length=1.15)
    _text(drawing, (0.95, raw_y - 0.58), "R5 10k 0.1%", halign="right", valign="center")
    drawing += elm.Ground()
    _wire(drawing, raw, (3.55, raw_y))
    drawing += elm.Capacitor().at((3.55, raw_y)).down(length=1.15)
    _text(drawing, (3.75, raw_y - 0.58), "C6 10µF", halign="left", valign="center")
    drawing += elm.Ground()

    u1d = drawing.add(elm.Opamp().at((6.15, raw_y + _IN_OFFSET)).right())
    _wire(drawing, (3.55, raw_y), u1d.in2)
    _text(drawing, u1d.center, "U1D", fontsize=8)
    loop_d = u1d.center[1] + _TOP_OFFSET + 0.55
    tap_d = u1d.in1[0] - 0.7
    _wire(drawing, u1d.in1, (tap_d, u1d.in1[1]))
    _wire(drawing, (tap_d, u1d.in1[1]), (tap_d, loop_d))
    _wire(drawing, (tap_d, loop_d), (u1d.out[0], loop_d))
    _wire(drawing, (u1d.out[0], loop_d), u1d.out)
    _dot(drawing, u1d.out)
    _text(drawing, (u1d.out[0] + 0.22, u1d.out[1] + 0.1), "VBIAS_1V5", halign="left", valign="bottom", color=_NET)
    _text(
        drawing, (0.15, 0.15),
        "VBIAS_1V5 drives all marked nodes and ADS1256 AIN1",
        fontsize=8, halign="left", valign="bottom",
    )

    _text(
        drawing, (12.2, 4.15),
        "Power and control notes\n"
        "FB2: USB 5 V → OPA_AVDD_5V. C21 10µF and C22 100nF at U1.\n"
        "FB1: XIAO 3V3 → AVDD_3V3. C10 10µF, C11/C12 100nF, C13 1µF.\n"
        "U2 BLANK on D1/GPIO27. R3 100k to AVDD_3V3. Drive low to receive.\n"
        "R13 and R16 pull CS and SYNC/PDWN high.\n"
        "R19 and R20 pull SCLK and MOSI low.\n"
        "R17 and R18 pull DOUT and DRDY high.\n"
        "ADS1256: AIN0−AIN1, buffer on after offset cal, PGA 64, 30 kSPS.\n"
        "AIN2–AIN7 tied to VBIAS_1V5.",
        fontsize=7.5, halign="left", valign="top",
    )

    svg_path = output_dir / "receiver-construction-schematic.svg"
    png_path = output_dir / "receiver-construction-schematic.png"
    drawing.save(svg_path, transparent=False)
    drawing.save(png_path, transparent=False, dpi=200)
    svg_text = svg_path.read_text()
    svg_text = re.sub(r"\n\s*<dc:date>.*?</dc:date>", "", svg_text)
    svg_path.write_text(svg_text)
    return svg_path, png_path
