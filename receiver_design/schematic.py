"""Draw the active lab-parts receiver's analog path and SPI wiring guide."""
from __future__ import annotations

import re
from pathlib import Path

import schemdraw
import schemdraw.elements as elm

BLUE = "#174a7e"


def line(drawing, start, end):
    drawing += elm.Line().at(start).to(end)


def label(drawing, at, text, **kwargs):
    kwargs.setdefault("fontsize", 9)
    drawing += elm.Label().at(at).label(text, **kwargs)


def dot(drawing, at):
    drawing += elm.Dot(radius=0.055).at(at)


def build_receiver_schematic(output_dir: Path) -> tuple[Path, Path]:
    """Write an overview; the generated KiCad netlist defines full connectivity."""
    output_dir.mkdir(parents=True, exist_ok=True)
    drawing = schemdraw.Drawing(show=False)
    drawing.config(unit=2.0, inches_per_unit=0.5, fontsize=9,
                   lw=1.15, bgcolor="white", margin=0.5)

    label(drawing, (0.4, 15.3), "Lab-parts proton magnetometer receiver",
          fontsize=15, halign="left", valign="bottom")
    label(drawing, (0.4, 14.8),
          "The sensing coil, tuning capacitor, and damping resistor are external to J1.",
          fontsize=9, color=BLUE, halign="left", valign="bottom")

    signal_y = 11.8
    bias_y = 7.8
    line(drawing, (0.7, signal_y), (2.0, signal_y))
    dot(drawing, (0.7, signal_y))
    label(drawing, (0.7, 12.2), "J1 signal", color=BLUE,
          halign="left", valign="bottom")
    label(drawing, (0.7, 11.3), "J1 return → GND", color=BLUE,
          halign="left", valign="top")
    drawing += elm.Capacitor().at((2.0, signal_y)).right(length=2.0).label("C5 22 nF", loc="top")
    drawing += elm.Resistor().right(length=2.0).label("R1 10 kΩ", loc="top")
    ain = (6.0, signal_y)
    line(drawing, ain, (15.0, signal_y))
    dot(drawing, ain)
    label(drawing, (15.2, signal_y + 0.15), "HiLetgo ADS1256 AIN0",
          color=BLUE, halign="left", valign="bottom")

    # Parallel resistor, capacitor, and antiparallel diode branches all
    # terminate at the same common-mode bias line.
    line(drawing, (6.0, bias_y), (14.2, bias_y))
    for x in (7.1, 9.0, 10.9, 12.8):
        dot(drawing, (x, signal_y))
        dot(drawing, (x, bias_y))

    drawing += elm.Resistor().at((7.1, signal_y)).down(length=1.7)
    drawing += elm.Resistor().at((7.1, signal_y - 1.7)).down(length=1.7)
    line(drawing, (7.1, signal_y - 3.4), (7.1, bias_y))
    label(drawing, (7.1, 12.3), "R2+R3 2 MΩ",
          halign="center", valign="bottom", fontsize=8)

    drawing += elm.Capacitor().at((9.0, signal_y)).down(length=2.2)
    line(drawing, (9.0, signal_y - 2.2), (9.0, bias_y))
    label(drawing, (9.0, 12.3), "C9 100 pF",
          halign="center", valign="bottom", fontsize=8)

    drawing += elm.Diode().at((10.9, signal_y)).down(length=2.1).reverse()
    line(drawing, (10.9, signal_y - 2.1), (10.9, bias_y))
    label(drawing, (10.9, 12.3), "D1 1N4148",
          halign="center", valign="bottom", fontsize=8)

    drawing += elm.Diode().at((12.8, signal_y)).down(length=2.1)
    line(drawing, (12.8, signal_y - 2.1), (12.8, bias_y))
    label(drawing, (12.8, 12.3), "D2 1N4148",
          halign="center", valign="bottom", fontsize=8)

    label(drawing, (14.5, bias_y), "VBIAS_1V60 → ADS1256 AIN1",
          color=BLUE, halign="left", valign="center")
    label(drawing, (0.7, 7.2),
          "The ADS1256 internal buffer and PGA 64 are the first active stage. No external op-amp or LC tank is fitted.",
          fontsize=9, halign="left", valign="top")

    # Bias supply is separate from the signal-path row.
    label(drawing, (0.7, 5.6), "Common-mode bias", fontsize=11,
          halign="left", valign="bottom")
    label(drawing, (0.7, 4.6), "USB 5 V", color=BLUE,
          halign="left", valign="center")
    drawing += elm.Resistor().at((2.2, 4.6)).right(length=2.0).label("R4 1 kΩ", loc="top")
    line(drawing, (4.2, 4.6), (10.0, 4.6))
    dot(drawing, (4.2, 4.6))
    label(drawing, (10.2, 4.6), "VBIAS_1V60", color=BLUE,
          halign="left", valign="center")
    drawing += elm.Resistor().at((5.1, 4.6)).down(length=1.8)
    drawing += elm.Ground()
    label(drawing, (5.25, 3.7), "R5 470 Ω", halign="left", valign="center")
    drawing += elm.Capacitor().at((7.2, 4.6)).down(length=1.8)
    drawing += elm.Ground()
    label(drawing, (7.35, 3.7), "C6 47 µF ∥ C7 100 nF",
          halign="left", valign="center", fontsize=8)

    label(drawing, (0.7, 1.8),
          "SPI: Q1–Q6 each use a 2N3904, 10 kΩ base resistor, 2.2 kΩ pull-up, and 1N4148 Baker clamp.",
          halign="left", valign="center", fontsize=9)
    label(drawing, (0.7, 1.3),
          "Q1 SCLK, Q2 DIN, Q3 CS, Q4 SYNC/PDWN → module logic rail; Q5 DOUT, Q6 DRDY → XIAO 3.3 V.",
          halign="left", valign="center", fontsize=9)
    label(drawing, (0.7, 0.8),
          "JP1 selects the measured module SPI voltage. RP2350 GPIO overrides invert each translated wire.",
          halign="left", valign="center", fontsize=9, color=BLUE)

    svg_path = output_dir / "receiver-construction-schematic.svg"
    png_path = output_dir / "receiver-construction-schematic.png"
    drawing.save(svg_path, transparent=False)
    drawing.save(png_path, transparent=False, dpi=200)
    svg_text = svg_path.read_text()
    svg_text = re.sub(r"\n\s*<dc:date>.*?</dc:date>", "", svg_text)
    svg_path.write_text("\n".join(line.rstrip() for line in svg_text.splitlines()) + "\n")
    return svg_path, png_path
