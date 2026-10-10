"""Draw the active AD8421 module receiver and its module wiring."""
from __future__ import annotations

import re
from pathlib import Path

import matplotlib
import schemdraw
import schemdraw.elements as elm

BLUE = "#174a7e"
GREY = "#555555"


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


def resistor(drawing, start, end, text, loc="top"):
    drawing += elm.Resistor(scale=0.7).endpoints(start, end).label(text, loc=loc, fontsize=7.5)


def capacitor(drawing, start, end, text, loc="top"):
    drawing += elm.Capacitor(scale=0.7).endpoints(start, end).label(
        text, loc=loc, fontsize=7.5)


def build_receiver_schematic(output_dir: Path) -> tuple[Path, Path]:
    """Write the construction schematic; KiCad connectivity mirrors it."""
    output_dir.mkdir(parents=True, exist_ok=True)
    drawing = schemdraw.Drawing(show=False)
    drawing.config(unit=1.5, inches_per_unit=0.55, fontsize=8,
                   lw=1.1, bgcolor="white", margin=0.5)

    label(drawing, (0.0, 14.6), "AD8421 module proton magnetometer receiver",
          fontsize=14, halign="left", valign="bottom")
    label(drawing, (0.0, 14.0),
          "|Z_in| ≥ 1 MΩ; ≤ 5 nV/√Hz with the coil, including ADC noise; "
          "≥ 90 dB alias rejection at the 1.92 MHz ADC modulator rate. "
          "The sensing coil, tuning capacitor, and damping resistor are external to J1.",
          fontsize=8.5, color=BLUE, halign="left", valign="bottom")

    # Input and clamps. Q1/Q2 are diode-connected 2N3904s (collector = base).
    y_in = 10.0
    label(drawing, (0.0, y_in + 0.25), "J1 signal", color=BLUE,
          halign="left", valign="bottom")
    label(drawing, (0.0, y_in - 0.3), "J1 return → GND", color=BLUE,
          halign="left", valign="top")
    dot(drawing, (0.0, y_in))
    for x, name, reverse in ((1.3, "Q1", False), (2.6, "Q2", True)):
        dot(drawing, (x, y_in))
        bottom = (x, y_in - 1.8)
        clamp = elm.Diode(scale=0.7).endpoints((x, y_in), bottom)
        if reverse:
            clamp = clamp.reverse()
        drawing += clamp.label(f"{name}\n2N3904\nC=B", loc="bottom", fontsize=7)
        ground(drawing, bottom)

    # AD8421 module (MOD2). Pin numbers are the AD8421's own.
    module = elm.Ic(
        pins=[
            elm.IcPin(name="+IN", pin="4", side="left", anchorname="inp"),
            elm.IcPin(name="−IN", pin="1", side="left", anchorname="inn"),
            elm.IcPin(name="RG", pin="2", side="top", anchorname="rga"),
            elm.IcPin(name="RG", pin="3", side="top", anchorname="rgb"),
            elm.IcPin(name="OUT", pin="7", side="right", anchorname="out"),
            elm.IcPin(name="V+", side="bottom", anchorname="vp"),
            elm.IcPin(name="GND", side="bottom", anchorname="gnd"),
            elm.IcPin(name="V−", side="bottom", anchorname="vn"),
        ],
        size=(5.6, 3.2), pinspacing=1.3, leadlen=0.6, lsize=9, plblsize=8,
    ).right().anchor("inp").at((4.0, y_in)).label(
        "MOD2 AD8421 module\nG = 1 + 9.9 kΩ/R1 = 100\nREF ← BIAS trimmer, 2.5 V",
        loc="center", fontsize=8)
    drawing += module
    wire(drawing, (0.0, y_in), module.inp)
    inn = module.inn
    wire(drawing, inn, (inn[0] - 0.5, inn[1]), (inn[0] - 0.5, inn[1] - 0.6))
    ground(drawing, (inn[0] - 0.5, inn[1] - 0.6))
    label(drawing, (inn[0] - 0.6, inn[1] + 0.15), "module jumper", fontsize=7,
          color=GREY, halign="right", valign="bottom")

    # R1 sets the gain; it fits the module's GAIN footprint.
    rga, rgb = module.rga, module.rgb
    top = max(rga[1], rgb[1]) + 0.6
    wire(drawing, rga, (rga[0], top))
    wire(drawing, rgb, (rgb[0], top))
    resistor(drawing, (rga[0], top), (rgb[0], top), "R1 100 Ω")

    # Batteries: BT1 gives +9 V and BT2 gives −9 V around GND.
    x_bat = 2.0
    y_pos = module.vp[1] - 1.0
    y_mid = y_pos - 1.7
    y_neg = y_mid - 1.7
    # The long plate is the positive terminal.
    drawing += elm.BatteryCell().endpoints((x_bat, y_pos), (x_bat, y_mid)).label(
        "BT1 9 V", loc="top", fontsize=7.5)
    drawing += elm.BatteryCell().endpoints((x_bat, y_mid), (x_bat, y_neg)).label(
        "BT2 9 V", loc="top", fontsize=7.5)
    for pin, y, text in ((module.vp, y_pos, "+9 V"), (module.gnd, y_mid, "GND"),
                         (module.vn, y_neg, "−9 V")):
        wire(drawing, pin, (pin[0], y), (x_bat, y))
        dot(drawing, (x_bat, y))
        label(drawing, (x_bat - 0.2, y), text, fontsize=7.5, color=BLUE,
              halign="right", valign="center")
    ground(drawing, (x_bat - 1.2, y_mid))
    wire(drawing, (x_bat, y_mid), (x_bat - 1.2, y_mid))

    # SMA-to-Dupont cable, then the two-section RC anti-aliasing filter.
    out = module.out
    cable_end = (out[0] + 2.6, out[1])
    wire(drawing, out, cable_end)
    label(drawing, ((out[0] + cable_end[0]) / 2, out[1] + 0.15),
          "SMA jack → W1 SMA–Dupont", fontsize=7.5, color=GREY, valign="bottom")
    dot(drawing, cable_end)
    mid = (cable_end[0] + 1.8, out[1])
    resistor(drawing, cable_end, mid, "R2 1 kΩ")
    dot(drawing, mid)
    capacitor(drawing, mid, (mid[0], mid[1] - 1.6), "C1\n22 nF", loc="bottom")
    ground(drawing, (mid[0], mid[1] - 1.6))
    ain0 = (mid[0] + 2.0, out[1])
    resistor(drawing, mid, ain0, "R3 10 kΩ")
    dot(drawing, ain0)
    capacitor(drawing, ain0, (ain0[0], ain0[1] - 1.6), "C2\n2.2 nF", loc="bottom")
    ground(drawing, (ain0[0], ain0[1] - 1.6))
    end = (ain0[0] + 0.8, out[1])
    wire(drawing, ain0, end)
    label(drawing, (end[0] + 0.1, end[1]), "ADS1256 AIN0", color=BLUE,
          halign="left", valign="center")
    label(drawing, (end[0] + 0.1, end[1] - 0.8), "ADS1256 AIN1 → GND", color=BLUE,
          halign="left", valign="center")
    label(drawing, (cable_end[0], out[1] - 2.6),
          "Anti-aliasing: two RC poles near 7.2 kHz.\n"
          "−0.8 dB at 2.2 kHz, −14 dB at 15 kHz,\n"
          "about −96 dB at 1.92 MHz.",
          fontsize=7.5, color=GREY, halign="left", valign="top")

    # Settings and module wiring.
    y_t = y_neg - 1.2
    for row, text in enumerate((
        "Before use: remove the module's input RFI parts, set its REF jumper to BIAS, "
        "and trim OUT to 2.50 V with J1 shorted.",
        "ADS1256 module: 5V ← XIAO VBUS, GND ← GND. AIN0 − AIN1, buffer off, PGA 1, 30 kSPS.",
        "SPI wired directly (3.3 V): XIAO D8/GPIO2 → SCLK, D10/GPIO3 → DIN, D9/GPIO4 ← DOUT,",
        "D3/GPIO5 → CS, D2/GPIO28 ← DRDY, D4/GPIO6 → SYNC/PDWN. No level translation is needed.",
    )):
        label(drawing, (0.0, y_t - 0.6 * row), text, halign="left", valign="center")

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
