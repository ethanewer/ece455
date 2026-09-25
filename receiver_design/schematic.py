"""Generate a readable construction schematic for the analog receiver path."""
from __future__ import annotations

import re
from pathlib import Path

import schemdraw
import schemdraw.elements as elm

# schemdraw Opamp, direction right, anchor at the input-side midpoint.
_IN_OFFSET = 0.625
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

    The signal runs left to right from J1. U2 is the blanker.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    drawing = schemdraw.Drawing(show=False)
    drawing.config(unit=2.0, inches_per_unit=0.5, fontsize=9, lw=1.15, bgcolor="white", margin=0.5)

    signal_y = 12.4
    _text(
        drawing, (0.2, 16.7),
        "Proton magnetometer receiver: high impedance input, blanking, and 1.5-2.5 kHz bandpass",
        fontsize=13, halign="left", valign="bottom",
    )
    _text(
        drawing, (0.2, 16.15),
        "J1 accepts an external sensor signal. Coil tuning and damping are outside this receiver. U2 blanks the amplifier.",
        fontsize=9, halign="left", valign="bottom", color=_NET,
    )
    _text(
        drawing, (0.2, 15.7),
        "U1 is OPA4197. Power: pin 4 = OPA_AVDD_5V, pin 11 = GND. Place C22 100 nF at U1.  "
        "U1A pins 1/2/3, U1B pins 7/6/5, U1C pins 8/9/10, U1D pins 14/13/12 (out, −in, +in).",
        fontsize=8, halign="left", valign="bottom",
    )

    # Input connector. The external coil and any tuning parts are not drawn.
    receiver_in = (4.65, signal_y)
    _wire(drawing, (0.35, signal_y), receiver_in)
    _dot(drawing, (0.35, signal_y))
    _dot(drawing, receiver_in)
    _text(drawing, (0.35, signal_y + 0.32), "J1 pin 1: external sensor signal",
          halign="left", valign="bottom", color=_NET)
    _text(drawing, (0.35, signal_y - 0.55), "J1 pin 2: sensor return to GND",
          halign="left", valign="top", color=_NET)
    _text(drawing, (receiver_in[0] + 0.15, receiver_in[1] + 0.28),
          "RECEIVER_IN", halign="left", valign="bottom", color=_NET)

    drawing += elm.Capacitor().at(receiver_in).right(length=2.05).label("C5 3.3n", loc="bottom")
    drawing += elm.Resistor().right(length=1.85).label("R1 1k", loc="top")
    pre_in = (receiver_in[0] + 3.9, signal_y)
    _dot(drawing, pre_in)
    _text(drawing, (pre_in[0] + 0.12, pre_in[1] + 0.32), "PRE_IN", halign="left", valign="bottom", color=_NET)

    # Clamps and the blanker share PRE_IN.
    d1_x, r2_x, d2_x, u2_x = (pre_in[0] + 1.35, pre_in[0] + 2.85, pre_in[0] + 4.35, pre_in[0] + 6.15)
    _wire(drawing, pre_in, (u2_x + 1.7, signal_y))
    _dot(drawing, (d1_x, signal_y))
    drawing += elm.Diode().at((d1_x, signal_y)).down(length=1.45).reverse()
    drawing += elm.Ground()
    _text(drawing, (d1_x - 0.16, signal_y - 0.75), "D1\nBAS116", halign="right", valign="center")

    _dot(drawing, (r2_x, signal_y))
    drawing += elm.Resistor().at((r2_x, signal_y)).down(length=1.45)
    _text(drawing, (r2_x - 0.35, signal_y - 3.0), "R2/R6/R24–R31\n5.1 MΩ total", halign="right", valign="top", fontsize=7)
    _bias_arrow(drawing, (r2_x, signal_y - 1.45), "down", "VBIAS_1V36")

    _dot(drawing, (d2_x, signal_y))
    drawing += elm.Diode().at((d2_x, signal_y)).up(length=1.35)
    _text(drawing, (d2_x - 0.16, signal_y + 0.68), "D2\nBAS116", halign="right", valign="center")
    _bias_arrow(drawing, (d2_x, signal_y + 1.35), "up", "AVDD_3V3")

    _dot(drawing, (u2_x, signal_y))
    drawing += elm.Switch().at((u2_x, signal_y)).down(length=1.55)
    _bias_arrow(drawing, (u2_x, signal_y - 1.55), "down", "VBIAS_1V36")
    _text(drawing, (u2_x, signal_y - 2.2), "U2 TMUX1101 blanker", halign="center", valign="top")
    _text(
        drawing, (u2_x, signal_y - 2.65),
        "BLANK high shorts the input to bias.\nR3 holds it on. Drive D1 low to receive.",
        halign="center", valign="top", fontsize=8,
    )

    u1a = drawing.add(elm.Opamp().at((u2_x + 1.7, signal_y + _IN_OFFSET)).right())
    _text(drawing, u1a.center, "U1A", fontsize=9)
    feedback_a = u1a.in1[1] + 0.7
    _wire(drawing, u1a.in1, (u1a.in1[0], feedback_a))
    _wire(drawing, (u1a.in1[0], feedback_a), (u1a.out[0], feedback_a))
    _wire(drawing, (u1a.out[0], feedback_a), u1a.out)
    _dot(drawing, u1a.out)
    _text(drawing, (u1a.center[0], feedback_a + 0.18), "unity gain", halign="center", valign="bottom")
    stage1 = (u1a.out[0], signal_y)
    _wire(drawing, u1a.out, stage1)
    _dot(drawing, stage1)
    _text(drawing, (stage1[0], stage1[1] - 0.42), "STAGE1", halign="center", valign="top", color=_NET)

    # Fixed high-pass. The op-amp hangs below the signal line so feedback stays above it.
    drawing += elm.Capacitor().at(stage1).right(length=2.25).label("C7 100n", loc="top")
    drawing += elm.Resistor().right(length=1.9).label("R8 1.05k", loc="top")
    join_b = (stage1[0] + 4.7, signal_y)
    _wire(drawing, (stage1[0] + 4.15, signal_y), join_b)
    _dot(drawing, join_b)
    u1b = drawing.add(elm.Opamp().at((join_b[0] + 0.85, signal_y - _IN_OFFSET)).right())
    _wire(drawing, join_b, u1b.in1)
    _text(drawing, u1b.center, "U1B", fontsize=9)
    _bias_arrow(drawing, u1b.in2, "left", "VBIAS_1V36")
    feedback_b = signal_y + 1.35
    _wire(drawing, join_b, (join_b[0], feedback_b))
    _wire(drawing, u1b.out, (u1b.out[0], feedback_b))
    drawing += (
        elm.Resistor()
        .at((join_b[0], feedback_b))
        .right(length=u1b.out[0] - join_b[0])
        .label("R9 56k", loc="bottom")
    )
    _text(
        drawing, ((join_b[0] + u1b.out[0]) / 2, feedback_b + 0.32),
        "1.516 kHz high-pass, gain −53.33", halign="center", valign="bottom",
    )
    stage2 = (u1b.out[0], signal_y)
    _wire(drawing, u1b.out, stage2)
    _dot(drawing, stage2)
    _text(drawing, (stage2[0] + 0.18, stage2[1] + 0.28), "STAGE2", halign="left", valign="bottom", color=_NET)

    # Fixed low-pass, then the ADC input pole and clamp on the same wire.
    drawing += elm.Resistor().at(stage2).right(length=2.05).label("R10 10k + R22 1k", loc="bottom")
    mid = (stage2[0] + 2.05, signal_y)
    _dot(drawing, mid)
    drawing += elm.Resistor().at(mid).right(length=2.05).label("R11 10k + R23 1k", loc="top")
    plus = (mid[0] + 2.05, signal_y)
    _dot(drawing, plus)
    u1c = drawing.add(elm.Opamp().at((plus[0] + 0.9, signal_y + _IN_OFFSET)).right())
    _wire(drawing, plus, u1c.in2)
    _text(drawing, u1c.center, "U1C", fontsize=9)
    drawing += elm.Capacitor().at(plus).down(length=1.35)
    _text(drawing, (plus[0] + 0.16, plus[1] - 0.68), "C23 3.3n", halign="left", valign="center")
    _bias_arrow(drawing, (plus[0], plus[1] - 1.35), "down", "VBIAS_1V36")

    loop_y = u1c.in1[1] + 0.65
    tap_x = u1c.in1[0] - 0.7
    _wire(drawing, u1c.in1, (tap_x, u1c.in1[1]))
    _wire(drawing, (tap_x, u1c.in1[1]), (tap_x, loop_y))
    _wire(drawing, (tap_x, loop_y), (u1c.out[0], loop_y))
    _wire(drawing, (u1c.out[0], loop_y), u1c.out)
    _text(drawing, ((tap_x + u1c.out[0]) / 2, loop_y + 0.16), "unity gain", halign="center", valign="bottom")

    return_y = signal_y - 2.35
    drawing += elm.Capacitor().at(mid).down(length=signal_y - return_y)
    _text(drawing, (mid[0] - 0.16, (signal_y + return_y) / 2), "C8+C32 3.3n parallel", halign="right", valign="center")
    _wire(drawing, (mid[0], return_y), (u1c.out[0], return_y))
    stage3 = (u1c.out[0], signal_y)
    _wire(drawing, (u1c.out[0], return_y), stage3)
    _wire(drawing, u1c.out, stage3)
    _dot(drawing, stage3)

    drawing += elm.Resistor().at(stage3).right(length=1.9).label("R12 6.8k", loc="top")
    r12_end = (stage3[0] + 1.9, signal_y)
    clamp_x = r12_end[0] + 1.15
    ain_x = clamp_x + 1.85
    _wire(drawing, r12_end, (ain_x, signal_y))
    _dot(drawing, (clamp_x, signal_y))
    _dot(drawing, (ain_x, signal_y))
    _text(drawing, (ain_x + 0.16, signal_y + 0.28), "ADS1256 AIN0", halign="left", valign="bottom", color=_NET)

    drawing += elm.Diode().at((clamp_x, signal_y)).up(length=1.55)
    _text(drawing, (clamp_x - 0.16, signal_y + 0.78), "D3\nBAS116", halign="right", valign="center")
    clamp = (clamp_x, signal_y + 1.55)
    _dot(drawing, clamp)
    _text(drawing, (clamp[0] + 0.55, clamp[1] + 0.58), "CLAMP_1V6", halign="left", valign="bottom", color=_NET)
    drawing += elm.Capacitor().at(clamp).left(length=1.35)
    _text(drawing, (clamp[0] - 1.5, clamp[1]), "C24 100n", halign="right", valign="center")
    drawing += elm.Resistor().at(clamp).right(length=1.5).label("R15 680", loc="bottom")
    drawing += elm.Ground()
    drawing += elm.Resistor().at(clamp).up(length=1.05)
    _text(drawing, (clamp[0] - 0.16, clamp[1] + 0.52), "R14 1.47k", halign="right", valign="center")
    _bias_arrow(drawing, (clamp[0], clamp[1] + 1.05), "up", "OPA_AVDD_5V")

    drawing += elm.Capacitor().at((ain_x, signal_y)).down(length=1.25)
    _text(drawing, (ain_x + 0.16, signal_y - 0.62), "C9 3.3n", halign="left", valign="center")
    _bias_arrow(drawing, (ain_x, signal_y - 1.25), "down", "VBIAS_1V36 / AIN1")

    # Bias sits under the input clamps.
    bias_x = r2_x
    raw_y = 6.15
    _text(drawing, (bias_x - 1.4, 8.15), "Buffered 1.36 V bias", fontsize=11, halign="left", valign="bottom")
    _text(drawing, (bias_x - 0.2, 7.55), "OPA_AVDD_5V", halign="right", valign="center", color=_NET)
    drawing += elm.Resistor().at((bias_x, 7.55)).down(length=1.4)
    _text(drawing, (bias_x - 0.18, 6.85), "R4 20k", halign="right", valign="center")
    raw = (bias_x, raw_y)
    _dot(drawing, raw)
    _text(drawing, (bias_x + 0.16, raw_y + 0.22), "VREF_RAW", halign="left", valign="bottom", color=_NET)
    drawing += elm.Resistor().at(raw).down(length=1.25)
    _text(drawing, (bias_x - 0.18, raw_y - 0.62), "R5 7.5k", halign="right", valign="center")
    drawing += elm.Ground()
    _wire(drawing, raw, (bias_x + 2.2, raw_y))
    drawing += elm.Capacitor().at((bias_x + 2.2, raw_y)).down(length=1.25)
    _text(drawing, (bias_x + 2.38, raw_y - 0.62), "C6 1µF", halign="left", valign="center")
    drawing += elm.Ground()
    u1d = drawing.add(elm.Opamp().at((bias_x + 4.5, raw_y + _IN_OFFSET)).right())
    _wire(drawing, (bias_x + 2.2, raw_y), u1d.in2)
    _text(drawing, u1d.center, "U1D", fontsize=9)
    loop_d = u1d.in1[1] + 0.6
    tap_d = u1d.in1[0] - 0.65
    _wire(drawing, u1d.in1, (tap_d, u1d.in1[1]))
    _wire(drawing, (tap_d, u1d.in1[1]), (tap_d, loop_d))
    _wire(drawing, (tap_d, loop_d), (u1d.out[0], loop_d))
    _wire(drawing, (u1d.out[0], loop_d), u1d.out)
    _dot(drawing, u1d.out)
    _text(drawing, (u1d.out[0] + 0.2, u1d.out[1] + 0.08), "VBIAS_1V36", halign="left", valign="bottom", color=_NET)
    _text(
        drawing, (bias_x - 1.4, 3.55),
        "VBIAS_1V36 drives every marked bias node and ADS1256 AIN1",
        fontsize=8, halign="left", valign="top",
    )

    _text(
        drawing, (u1d.out[0] + 2.4, 8.05),
        "Power and control\n"
        "FB2: USB 5 V to OPA_AVDD_5V. C21 1µF and C22 100nF at U1.\n"
        "FB1: XIAO 3V3 to AVDD_3V3. C10 1µF, C11/C12 100nF, C13 1µF.\n"
        "U2 BLANK is D1/GPIO27. R3 holds blanking on; drive it low to receive.\n"
        "R13 and R16 pull CS and SYNC/PDWN high.\n"
        "R19 and R20 pull SCLK and MOSI low.\n"
        "R17 and R18 pull DOUT and DRDY high.\n"
        "ADS1256: AIN0−AIN1, buffer on after offset cal, PGA 64, 30 kSPS.\n"
        "AIN2–AIN7 tied to VBIAS_1V36.",
        fontsize=8, halign="left", valign="top",
    )

    svg_path = output_dir / "receiver-construction-schematic.svg"
    png_path = output_dir / "receiver-construction-schematic.png"
    drawing.save(svg_path, transparent=False)
    drawing.save(png_path, transparent=False, dpi=200)
    svg_text = svg_path.read_text()
    svg_text = re.sub(r"\n\s*<dc:date>.*?</dc:date>", "", svg_text)
    svg_path.write_text("\n".join(line.rstrip() for line in svg_text.splitlines()) + "\n")
    return svg_path, png_path
