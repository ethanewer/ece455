"""Generate a readable construction schematic for the analog receiver path."""
from __future__ import annotations

from pathlib import Path

import schemdraw
import schemdraw.elements as elm


def _wire(drawing: schemdraw.Drawing, start, end) -> None:
    drawing += elm.Line().at(start).to(end)


def _net(drawing: schemdraw.Drawing, at, name: str) -> None:
    drawing += elm.Dot().at(at)
    drawing += elm.Label().at((at[0], at[1] + 0.52)).label(
        name, color="#174a7e", fontsize=7
    )


def build_receiver_schematic(output_dir: Path) -> tuple[Path, Path]:
    """Write SVG and PNG schematics of the buildable analog signal path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    d = schemdraw.Drawing(show=False)
    d.config(unit=2.0, fontsize=7, lw=1.2, bgcolor="white", margin=0.35)

    d += elm.Label().at((0, 15.4)).label(
        "Proton magnetometer receiver: broadband coil input, blanking, and 1.5-2.5 kHz bandpass",
        fontsize=14,
    )
    d += elm.Label().at((0, 14.85)).label(
        "U1 is OPA4197. Power pins: 4 = OPA_AVDD_5V, 11 = GND. Place C22 100nF at U1.",
        fontsize=8,
    )
    d += elm.Label().at((0, 14.45)).label(
        "U1A: OUT 1, −IN 2, +IN 3   |   U1B: +IN 5, −IN 6, OUT 7   |   U1C: OUT 8, −IN 9, +IN 10   |   U1D: +IN 12, −IN 13, OUT 14",
        fontsize=7,
    )
    d += elm.Label().at((0, 14.05)).label(
        "Filtered coil-to-ADC gain: 1915-2012 V/V from 1.5-2.5kHz; ADS1256 internal PGA excluded",
        color="#174a7e", fontsize=7,
    )

    # Untuned broadband sensor and protected input.
    d += elm.SourceSin().at((0, 12.0)).down(length=1.6).label("Vfid\nexternal", loc="left")
    d += elm.Ground()
    d += elm.Resistor().at((0, 12.0)).right(length=1.6).label("Rcoil 14Ω")
    d += elm.Inductor().right(length=1.6).label("Lcoil 22mH")
    coil_hi = d.here
    d += elm.Dot().at(coil_hi)
    d += elm.Label().at((coil_hi[0], coil_hi[1] + 0.5)).label(
        "COIL_HI (untuned)", color="#174a7e", fontsize=7
    )
    d += elm.Capacitor().at(coil_hi).right(length=1.65).label("C5 1µF", loc="bottom")
    d += elm.Resistor().right(length=1.65).label("R1 1k", loc="top")
    pre_in = d.here
    _net(d, pre_in, "PRE_IN")

    # Spread the four protection and blanking branches along the PRE_IN wire.
    u1a = d.add(elm.Opamp().at((16.0, 12.0)).right().label("U1A"))
    _wire(d, pre_in, (15.2, 12.0))
    _wire(d, (15.2, 12.0), (15.2, u1a.in2[1]))
    _wire(d, (15.2, u1a.in2[1]), u1a.in2)  # Lower '+' input.
    branch_x = [pre_in[0] + offset for offset in (0.6, 2.1, 3.7, 5.3)]
    d += elm.Diode().at((branch_x[0], 12.0)).down(length=1.25).reverse().label(
        "D1 BAS116", loc="left"
    )
    d += elm.Ground()
    d += elm.Resistor().at((branch_x[1], 12.0)).down(length=1.25).label("R2 1M", loc="left")
    d += elm.Arrow().down(length=0.4)
    d += elm.Label().at((branch_x[1] + 0.45, 10.35)).label(
        "VREF_2V5", fontsize=7, halign="left"
    )
    d += elm.Diode().at((branch_x[2], 12.0)).up(length=1.25).label("D2 BAS116", loc="right")
    d += elm.Arrow().up(length=0.4).label("AVDD_3V3", loc="right")
    d += elm.Switch(nc=True).at((branch_x[3], 12.0)).down(length=1.25).label(
        "U2 TMUX1101\nblanking shunt", loc="right"
    )
    d += elm.Arrow().down(length=0.4).label("VREF_2V5", loc="right")

    # U1A feedback: R7 from output to minus input, R6 from minus input to VREF.
    d += elm.Resistor().at(u1a.in1).up(length=1.05).label("R6 1k", loc="right")
    d += elm.Arrow().up(length=0.4).label("VREF_2V5", loc="right")
    feedback_y = 10.05
    _wire(d, u1a.out, (u1a.out[0], feedback_y))
    d += elm.Resistor().at((u1a.out[0], feedback_y)).left(length=2.15).label("R7 58k", loc="bottom")
    _wire(d, d.here, (u1a.in1[0], feedback_y))
    _wire(d, (u1a.in1[0], feedback_y), u1a.in1)
    _net(d, u1a.out, "STAGE1  gain 59.0")

    # U1B AC-coupled high-pass stage.
    d += elm.Label().at((0, 8.5)).label("High-pass and gain stage", fontsize=10)
    d += elm.Arrow().at((0, 7.25)).right(length=0.7).label("STAGE1", loc="top")
    d += elm.Capacitor().right(length=1.7).label("C7 100n C0G")
    d += elm.Resistor().right(length=1.7).label("R8 1.05k")
    input_end = d.here
    u1b = d.add(elm.Opamp().at((7.0, 6.62)).right().label("U1B"))
    _wire(d, input_end, u1b.in1)  # Inverting '-' input.
    d += elm.Arrow().at(u1b.in2).left(length=0.8).label("VREF_2V5", loc="bottom")
    feedback_y = 4.75
    _wire(d, u1b.out, (u1b.out[0], feedback_y))
    d += elm.Resistor().at((u1b.out[0], feedback_y)).left(length=2.15).label("R9 59k", loc="bottom")
    _wire(d, d.here, (u1b.in1[0], feedback_y))
    _wire(d, (u1b.in1[0], feedback_y), u1b.in1)
    d += elm.Dot().at(u1b.out)
    d += elm.Label().at((u1b.out[0] + 0.15, u1b.out[1] + 0.5)).label(
        "STAGE2", color="#174a7e", fontsize=7, halign="left"
    )
    d += elm.Label().at((u1b.out[0] + 0.15, u1b.out[1] - 0.55)).label(
        "HP 1.516kHz, gain −56.19", fontsize=7, halign="left"
    )

    # U1C low-pass stage and differential ADC input filter.
    d += elm.Label().at((11.0, 8.5)).label("Low-pass and ADS1256 differential input", fontsize=10)
    d += elm.Arrow().at((11.0, 7.25)).right(length=0.7).label("STAGE2", loc="top")
    d += elm.Resistor().right(length=1.7).label("R10 10.2k")
    input_end = d.here
    u1c = d.add(elm.Opamp().at((15.8, 6.62)).right().label("U1C"))
    _wire(d, input_end, u1c.in1)
    d += elm.Arrow().at(u1c.in2).left(length=0.8).label("VREF_2V5", loc="bottom")
    feedback_y = 4.7
    _wire(d, u1c.out, (u1c.out[0], feedback_y))
    d += elm.Resistor().at((u1c.out[0], feedback_y)).left(length=2.15).label("R11 10.2k", loc="bottom")
    _wire(d, d.here, (u1c.in1[0], feedback_y))
    _wire(d, (u1c.in1[0], feedback_y), u1c.in1)
    cap_y = 3.9
    d += elm.Capacitor().at((u1c.out[0], cap_y)).left(length=2.15).label("C8 6.2n C0G", loc="bottom")
    _wire(d, (u1c.out[0], feedback_y), (u1c.out[0], cap_y))
    _wire(d, (u1c.in1[0], feedback_y), (u1c.in1[0], cap_y))
    d += elm.Resistor().at(u1c.out).right(length=1.45).label("R12 1k")
    ain0 = d.here
    d += elm.Dot().at(ain0)
    d += elm.Label().at((ain0[0] + 0.15, ain0[1] + 0.52)).label(
        "ADS1256 AIN0", color="#174a7e", fontsize=7, halign="left"
    )
    d += elm.Capacitor().at(ain0).down(length=1.15)
    d += elm.Label().at((ain0[0] + 0.42, ain0[1] - 0.55)).label(
        "C9 22n C0G", fontsize=7, halign="left"
    )
    d += elm.Arrow().down(length=0.4).label("VREF_2V5 / AIN1", loc="right")

    # Buffered 2.5 V reference used by every marked node.
    d += elm.Label().at((0, 3.3)).label("Buffered 2.5V reference", fontsize=10)
    d += elm.Arrow().at((1.2, 2.7)).down(length=0.01).label("OPA_AVDD_5V", loc="left")
    d += elm.Resistor().down(length=1.1)
    d += elm.Label().at((0.65, 2.15)).label("R4 10k 0.1%", fontsize=7, halign="right")
    vref_raw = d.here
    d += elm.Dot().at(vref_raw)
    d += elm.Label().at((vref_raw[0] + 0.3, vref_raw[1] + 0.35)).label(
        "VREF_RAW", color="#174a7e", fontsize=7, halign="left"
    )
    d += elm.Resistor().at(vref_raw).down(length=1.1)
    d += elm.Label().at((0.65, 1.05)).label("R5 10k 0.1%", fontsize=7, halign="right")
    d += elm.Ground()
    _wire(d, vref_raw, (3.5, vref_raw[1]))
    d += elm.Capacitor().at((3.5, vref_raw[1])).down(length=1.1)
    d += elm.Label().at((3.9, 1.4)).label("C6 10µF", fontsize=7, halign="left")
    d += elm.Ground()
    u1d = d.add(elm.Opamp().at((6.5, vref_raw[1] + 0.625)).right().label("U1D buffer"))
    _wire(d, vref_raw, u1d.in2)
    loop_y = vref_raw[1] + 1.65
    _wire(d, u1d.out, (u1d.out[0], loop_y))
    _wire(d, (u1d.out[0], loop_y), (u1d.in1[0], loop_y))
    _wire(d, (u1d.in1[0], loop_y), u1d.in1)
    d += elm.Dot().at(u1d.out)
    d += elm.Label().at((u1d.out[0] + 0.15, u1d.out[1] + 0.48)).label(
        "VREF_2V5", color="#174a7e", fontsize=7, halign="left"
    )
    d += elm.Label().at((5.5, -0.35)).label(
        "VREF_2V5 drives all marked nodes and ADS1256 AIN1", fontsize=7
    )

    d += elm.Label().at((11.0, 2.85)).label(
        "Power and control notes\n"
        "FB2: USB 5V → OPA_AVDD_5V; C21 10µF + C22 100nF at U1\n"
        "FB1: XIAO 3V3 → AVDD_3V3; C10 10µF + C11/C12 100nF + C13 1µF\n"
        "U2 BLANK_D1_GPIO27: R3 100k pull-up to AVDD_3V3; drive low to receive\n"
        "ADS1256: AIN0−AIN1, input buffer on, PGA 64, 30kSPS",
        fontsize=7,
        halign="left",
    )

    svg_path = output_dir / "receiver-construction-schematic.svg"
    png_path = output_dir / "receiver-construction-schematic.png"
    d.save(svg_path, transparent=False)
    d.save(png_path, transparent=False, dpi=200)
    return svg_path, png_path
