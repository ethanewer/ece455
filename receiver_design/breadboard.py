"""Place the receiver, ADC, and microcontroller on a standard 830-point breadboard.

The layout is fixed data, not a placer, and follows the board as built: the
clamps sit in columns 15-19 and the filter in columns 26-35. A 1000:1
divider in columns 5-11 lets a function generator stand in for the coil, and
the XIAO straddles the channel in columns 56-62. `check_layout` rebuilds the
board's connectivity from strips, rails, jumpers, the XIAO's pins, and
off-board leads. The receiver must match spice/receiver.cir node for node
and the XIAO-to-ADS1256 wires must match kicad/receiver.net before anything
is drawn. The AD8421 module, its batteries, the SMA cable, and the ADS1256
module are drawn beside the board.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import patheffects
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Rectangle

from receiver_design.verify import KICAD_NETLIST, kicad_pins, spice_elements

ROOT = Path(__file__).resolve().parents[1]
SPICE_NETLIST = ROOT / "receiver_design/spice/receiver.cir"

# Standard 830-point board: 63 columns of two 5-hole strips (a-e, f-j)
# across a centre channel, plus two rail pairs of 50 holes in groups of 5.
# The outer top rail row, beside the blue line, is GND.
COLUMNS = 63
ROW_Y = {"a": 3, "b": 4, "c": 5, "d": 6, "e": 7,
         "f": 10, "g": 11, "h": 12, "i": 13, "j": 14}
RAIL_Y = {"T-": 0, "T+": 1, "B+": 16, "B-": 17}
RAIL_COLUMNS = frozenset(start + offset for start in range(3, 58, 6)
                         for offset in range(5))
HOLE = re.compile(r"(T\+|T-|B\+|B-|[a-j])(\d+)")
# R1 is soldered to the module's GAIN footprint, not the breadboard.
ON_MODULE = frozenset({"R1"})


@dataclass(frozen=True)
class Placement:
    """A fitted part. Holes follow the SPICE card's node order (C B E).

    Receiver parts take their nodes and value from the SPICE deck. Test
    fixture parts are not in the deck, so they carry their own.
    """

    ref: str
    kind: str  # resistor, ceramic, npn
    holes: tuple[str, ...]
    nodes: tuple[str, ...] = ()
    value: str = ""


@dataclass(frozen=True)
class Wire:
    start: str
    end: str
    color: str


@dataclass(frozen=True)
class OffBoard:
    """A lead that leaves the board.

    `node` is a SPICE node, or `REF.pin` for a pin in kicad/receiver.net.
    Without a color the lead is dashed to a labelled box at `end`. With a
    color it is a real wire drawn through `route` to `end`, a module pin.
    Leads with the same `via` are joined inside that module.
    """

    hole: str
    text: str
    node: str
    end: tuple[float, float]
    route: tuple[tuple[float, float], ...] = ()
    color: str | None = None
    text_at: tuple[float, float] | None = None
    via: str | None = None


RED, BLACK, ORANGE = "#d62728", "#222222", "#ff7f0e"
YELLOW, GREY, BLUE, GREEN = "#e6b800", "#5a5a5a", "#1f77b4", "#2ca02c"

PARTS = (
    # Input clamps: diode-connected 2N3904s. Strip 17 is J1 signal.
    Placement("Q2", "npn", ("d15", "d16", "d17")),
    Placement("Q1", "npn", ("b17", "b18", "b19")),
    # Two-section anti-aliasing filter. Strip 26 is the AD8421 output.
    Placement("R2", "resistor", ("b26", "b31")),
    Placement("C1", "ceramic", ("a31", "T-31")),
    Placement("R3", "resistor", ("c31", "c35")),
    Placement("C2", "ceramic", ("a35", "T-35")),
)

# Bench input: a 1000:1 divider stands in for the coil. RT2 is close to the
# coil's 100 ohm resistance, so the noise check sees a similar source.
TEST_PARTS = (
    Placement("RT1", "resistor", ("b5", "b11"), ("wavegen", "receiver_in"), "100k"),
    Placement("RT2", "resistor", ("a11", "T-11"), ("receiver_in", "0"), "100"),
)

WIRES = (
    # Q1 collector to base; Q2 collector and base to GND; Q1 emitter to GND.
    Wire("c17", "c18", YELLOW),
    Wire("a15", "T-15", BLACK),
    Wire("a16", "T-16", BLACK),
    Wire("a19", "T-19", BLACK),
)

# The divider output reaches J1 through one jumper; remove it for the coil.
TEST_WIRES = (Wire("e11", "e17", GREEN),)

# Seeed XIAO RP2350 (U1), USB-C toward column 63. Its castellated pin rows
# are 0.7 in apart, so they straddle the channel in rows c and h. Pin
# numbers follow the KiCad symbol: 1-7 are D0-D6, 8-14 are D7-D10, 3V3,
# GND, and 5V. The board is 21 mm long and covers columns 55-63.
XIAO_PINS = {**{str(7 - i): f"c{56 + i}" for i in range(7)},
             **{str(8 + i): f"h{56 + i}" for i in range(7)}}
XIAO_NAMES = {**{str(n + 1): f"D{n}" for n in range(11)},
              "12": "3V3", "13": "GND", "14": "5V"}
XIAO_COVERED = tuple(f"{row}{column}" for column in range(55, 64) for row in "cdefgh")

# HiLetgo ADS1256 module (MOD1), off the board, top view. Header order
# follows the labels on the underside in the seller's photo. The analog
# header pairs each AINk (outer pin) with a GND pin (inner pin).
ADS = (40.0, -21.0, 58.0, -6.0)
ADS_DIGITAL = ("5V", "GND", "SCLK", "DIN", "DOUT", "DRDY", "CS", "PDWN")
# kicad/generate.py numbers the logical J2 wires in this order instead.
ADS_J2 = ("5V", "GND", "SCLK", "DIN", "DOUT", "CS", "DRDY", "PDWN")
ADS_PIN_XY = {
    **{name: (57.2, -19.0 + row) for row, name in enumerate(ADS_DIGITAL)},
    **{f"AIN{k}": (40.8, -19.0 + k) for k in range(8)},
    **{f"GND{k}": (41.8, -19.0 + k) for k in range(8)},
}
WIRE_COLORS = {
    "AIN0": "#8c564b", "AIN1": "#1f3a93", "SCLK": "#17becf", "DIN": "#7b4173",
    "DOUT": BLUE, "DRDY": "#e377c2", "CS": "#bcbd22", "PDWN": "#9467bd",
    "5V": RED, "GND": BLACK,
}

# AD8421 module features in drawing coordinates (the y axis points down).
MODULE = (12.0, -20.0, 30.0, -5.0)
PIN_IN_PLUS = (MODULE[0] + 1.4, -11.5)
PIN_OUT = (MODULE[2] + 1.4, -12.5)
TERMINALS = {"V+": (MODULE[0] + 6.5, -20.6), "GND": (MODULE[0] + 9.0, -20.6),
             "V−": (MODULE[0] + 11.5, -20.6)}
CABLE_SPLIT = (MODULE[2] + 3.0, -3.4)


def _to_ads(hole: str, pin: str, route, via: str | None = None) -> OffBoard:
    """A Dupont lead from `hole` to an ADS1256 module pin."""
    if pin in ADS_J2:
        node = f"J2.{ADS_J2.index(pin) + 1}"
    else:
        node = {"AIN0": "ain0"}.get(pin, "0")
    name = {"GND": "GND (digital header)"}.get(
        pin, "GND (analog header)" if pin.startswith("GND") else pin)
    color = WIRE_COLORS["GND" if pin.startswith("GND") else pin]
    return OffBoard(hole, f"ADS1256 {name}", node, ADS_PIN_XY[pin], tuple(route),
                    color, via=via)


OFF_BOARD = (
    # Function generator: signal into the divider; ground clip right of the
    # analog grounds, so ground-loop current stays out of the input path.
    OffBoard("e5", "Function generator signal", "wavegen", (-2.0, 7.0)),
    OffBoard("T-40", "Function generator ground clip", "0", (43.6, -3.6)),
    OffBoard("a17", "jumper to module +IN pin", "receiver_in", PIN_IN_PLUS,
             ((17.0, -4.0), (PIN_IN_PLUS[0], -4.0)), ORANGE, (11.5, -3.0)),
    OffBoard("a26", "W1 signal lead", "amp_out", CABLE_SPLIT,
             ((26.0, -3.4),), RED, (23.6, -2.4)),
    OffBoard("T-28", "W1 shield lead", "0", CABLE_SPLIT,
             ((28.0, -2.2), (CABLE_SPLIT[0], -2.2)), BLACK, (30.6, -1.8)),
    # ADS1256 analog header. AIN1 senses GND beside C2; the GND lead is the
    # only ground link from the ADS1256 module and the XIAO to the board.
    _to_ads("e35", "AIN0", ((35.5, 7.0), (35.5, -4.2), (38.4, -4.2), (38.4, -19.0))),
    _to_ads("T-36", "AIN1", ((36.0, -3.4), (39.0, -3.4), (39.0, -18.0))),
    _to_ads("T-37", "GND7", ((37.0, -2.6), (41.8, -2.6)), via="ADS1256 GND"),
    # ADS1256 digital header, from the XIAO's top and bottom pin rows.
    _to_ads("a58", "PDWN", ((58.0, -3.0), (61.4, -3.0), (61.4, -12.0))),
    _to_ads("a59", "CS", ((59.0, -2.4), (62.0, -2.4), (62.0, -13.0))),
    _to_ads("a60", "DRDY", ((60.0, -1.8), (62.6, -1.8), (62.6, -14.0))),
    _to_ads("j57", "SCLK", ((57.0, 21.6), (67.4, 21.6), (67.4, -17.0))),
    _to_ads("j58", "DOUT", ((58.0, 21.0), (66.8, 21.0), (66.8, -15.0))),
    _to_ads("j59", "DIN", ((59.0, 20.4), (66.2, 20.4), (66.2, -16.0))),
    _to_ads("j61", "GND", ((61.0, 19.8), (65.6, 19.8), (65.6, -18.0)), via="ADS1256 GND"),
    _to_ads("j62", "5V", ((62.0, 19.2), (65.0, 19.2), (65.0, -19.0))),
)


def parse_hole(hole: str) -> tuple[str, int]:
    match = HOLE.fullmatch(hole)
    if match is None:
        raise ValueError(f"malformed hole {hole!r}")
    row, column = match.group(1), int(match.group(2))
    if not 1 <= column <= COLUMNS:
        raise ValueError(f"{hole} is off the board")
    if row in RAIL_Y and column not in RAIL_COLUMNS:
        raise ValueError(f"{hole} is in a rail gap")
    return row, column


def hole_xy(hole: str) -> tuple[float, float]:
    row, column = parse_hole(hole)
    return float(column), float(RAIL_Y.get(row, ROW_Y.get(row)))


def contact(hole: str) -> str:
    """The metal strip or rail a hole belongs to."""
    row, column = parse_hole(hole)
    if row in RAIL_Y:
        return row
    return f"{'top' if row in 'abcde' else 'bottom'}{column}"


def _crossed_holes(start: str, end: str) -> list[str]:
    """Holes strictly between two holes on one row or one column."""
    (r0, c0), (r1, c1) = parse_hole(start), parse_hole(end)
    if r0 == r1:
        lo, hi = sorted((c0, c1))
        return [f"{r0}{c}" for c in range(lo + 1, hi)
                if r0 not in RAIL_Y or c in RAIL_COLUMNS]
    if c0 == c1:
        y0, y1 = sorted((hole_xy(start)[1], hole_xy(end)[1]))
        rows = {**ROW_Y, **RAIL_Y}
        return [f"{r}{c0}" for r, y in rows.items() if y0 < y < y1
                and (r not in RAIL_Y or c0 in RAIL_COLUMNS)]
    return []


def _resolve(node: str, pins: dict[tuple[str, str], str]) -> str:
    """A SPICE node, or a KiCad REF.pin mapped to its net (GND is node 0)."""
    if "." not in node:
        return node
    net = pins.get(tuple(node.split(".")))
    if net is None:
        return node  # an unconnected pin is a node of its own
    return "0" if net == "GND" else net


def check_layout(spice: str, connectivity: str) -> dict[str, str]:
    """Fail unless the board reproduces both netlists; map each node to its contact."""
    elements = spice_elements(spice)
    pins = kicad_pins(connectivity)
    placed = {part.ref: part for part in PARTS}
    if (set(placed) | ON_MODULE != set(elements) or set(placed) & ON_MODULE
            or len(placed) != len(PARTS)):
        raise ValueError(
            f"board and SPICE parts differ: {sorted((set(placed) | ON_MODULE) ^ set(elements))}")
    test_refs = {part.ref for part in TEST_PARTS}
    if test_refs & set(elements) or len(test_refs) != len(TEST_PARTS):
        raise ValueError("test fixture parts must be distinct from the receiver's")
    missing = {f"J2.{n}" for n in range(1, len(ADS_J2) + 1)} - {t.node for t in OFF_BOARD}
    if missing:
        raise ValueError(f"no lead reaches ADS1256 pins {sorted(missing)}")

    occupied: dict[str, str] = {}

    def occupy(hole: str, owner: str) -> None:
        parse_hole(hole)
        if hole in occupied:
            raise ValueError(f"{hole} holds both {occupied[hole]} and {owner}")
        occupied[hole] = owner

    fitted = [(part, *elements[part.ref]) for part in PARTS]
    fitted += [(part, list(part.nodes), part.value) for part in TEST_PARTS]
    for part, nodes, model in fitted:
        if len(part.holes) != len(nodes):
            raise ValueError(f"{part.ref} has {len(part.holes)} leads for {len(nodes)} nodes")
        expected = {"R": {"resistor"}, "C": {"ceramic"}, "Q": {"npn"}}[part.ref[0]]
        if part.kind not in expected or (part.kind == "npn" and model != "Q2N3904"):
            raise ValueError(f"{part.ref} is drawn as {part.kind}")
        if part.kind == "npn":
            rows = {parse_hole(h)[0] for h in part.holes}
            columns = sorted(parse_hole(h)[1] for h in part.holes)
            if len(rows) != 1 or rows & set(RAIL_Y) or columns != list(
                    range(columns[0], columns[0] + 3)):
                raise ValueError(f"{part.ref} leads are not three adjacent holes in a row")
            if parse_hole(part.holes[1])[1] != columns[1]:
                raise ValueError(f"{part.ref} base is not the middle lead")
        for hole in part.holes:
            occupy(hole, part.ref)
    for pin, hole in XIAO_PINS.items():
        occupy(hole, f"XIAO {XIAO_NAMES[pin]}")
    for hole in XIAO_COVERED:
        if hole not in XIAO_PINS.values():
            occupy(hole, "the XIAO body")
    for wire in WIRES + TEST_WIRES:
        occupy(wire.start, "wire")
        occupy(wire.end, "wire")
    for terminal in OFF_BOARD:
        occupy(terminal.hole, terminal.text)

    # Straight leads, bodies, and jumpers may not pass over a used hole.
    for owner, start, end in [(part.ref, part.holes[0], part.holes[-1])
                              for part, _nodes, _model in fitted
                              if part.kind != "npn"] + [
            ("wire", w.start, w.end) for w in WIRES + TEST_WIRES]:
        for hole in _crossed_holes(start, end):
            if hole in occupied:
                raise ValueError(f"{owner} passes over {occupied[hole]} at {hole}")

    parent: dict[str, str] = {}

    def find(item: str) -> str:
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for wire in WIRES + TEST_WIRES:
        parent[find(contact(wire.start))] = find(contact(wire.end))
    through: dict[str, str] = {}
    for terminal in OFF_BOARD:
        if terminal.via is not None:
            other = through.setdefault(terminal.via, contact(terminal.hole))
            parent[find(contact(terminal.hole))] = find(other)

    leads = [(contact(hole), node, f"{part.ref}:{hole}")
             for part, nodes, _model in fitted
             for hole, node in zip(part.holes, nodes)]
    leads += [(contact(hole), _resolve(f"U1.{pin}", pins), f"XIAO {XIAO_NAMES[pin]}")
              for pin, hole in XIAO_PINS.items()]
    leads += [(contact(t.hole), _resolve(t.node, pins), t.text) for t in OFF_BOARD]
    node_root: dict[str, str] = {}
    root_node: dict[str, str] = {}
    for strip, node, where in leads:
        root = find(strip)
        if node_root.setdefault(node, root) != root:
            raise ValueError(f"node {node} is split on the board at {where}")
        if root_node.setdefault(root, node) != node:
            raise ValueError(f"{where} shorts {node} to {root_node[root]}")
    for wire in WIRES + TEST_WIRES:
        if find(contact(wire.start)) not in root_node:
            raise ValueError(f"wire {wire.start}-{wire.end} connects nothing")
    return node_root


def _value_text(ref: str, value: str) -> str:
    if ref.startswith("Q"):
        return value.removeprefix("Q")
    match = re.fullmatch(r"([\d.]+)(Meg|k|n|u|p)?", value)
    number, suffix = match.group(1), match.group(2) or ""
    unit = {"R": {"": "Ω", "k": "kΩ", "Meg": "MΩ"},
            "C": {"n": "nF", "u": "µF", "p": "pF"}}[ref[0]][suffix]
    return f"{number} {unit}"


def _segment(ax, start, end, **kwargs):
    ax.plot([start[0], end[0]], [start[1], end[1]], solid_capstyle="round", **kwargs)


def _polyline(ax, points, **kwargs):
    ax.plot([p[0] for p in points], [p[1] for p in points], solid_capstyle="round",
            solid_joinstyle="round", **kwargs)


def _draw_board(ax) -> None:
    ax.add_patch(FancyBboxPatch((-0.4, -1.4), COLUMNS + 1.8, 20.0,
                                boxstyle="round,pad=0,rounding_size=0.8",
                                fc="#f3efe6", ec="#b8b0a0", lw=1.2, zorder=0))
    ax.add_patch(Rectangle((-0.4, 8.0), COLUMNS + 1.8, 1.0, fc="#e2dccd",
                           ec="none", zorder=0.1))
    for y, color in ((-0.7, BLUE), (1.7, RED), (15.3, RED), (17.7, BLUE)):
        _segment(ax, (2.4, y), (61.6, y), color=color, lw=1.0, zorder=0.2)
    for rail, y in RAIL_Y.items():
        ax.text(1.4, y, "+" if rail.endswith("+") else "−", ha="center", va="center",
                fontsize=7, color=RED if rail.endswith("+") else BLUE)
    for column in range(1, COLUMNS + 1):
        for y in ROW_Y.values():
            ax.add_patch(Rectangle((column - 0.16, y - 0.16), 0.32, 0.32,
                                   fc="#9c968a", ec="none", zorder=0.3))
        if column in RAIL_COLUMNS:
            for y in RAIL_Y.values():
                ax.add_patch(Rectangle((column - 0.16, y - 0.16), 0.32, 0.32,
                                       fc="#9c968a", ec="none", zorder=0.3))
        if column == 1 or column % 5 == 0:
            for y in (2.05, 14.95):
                ax.text(column, y, str(column), ha="center", va="center",
                        fontsize=5.5, color="#6b665c")
    for row, y in ROW_Y.items():
        for x in (0.2, 64.6):
            ax.text(x, y, row, ha="center", va="center", fontsize=6, color="#6b665c")
    ax.text(0.4, 19.4, "outer top − rail (blue line) = GND; the other three rails are unused",
            fontsize=6.5, color=BLUE, ha="left", va="center", style="italic")


def _body_text(ax, xy, text, *, color="black", rotation=0.0, size=5.4):
    ax.text(xy[0], xy[1], text, ha="center", va="center", fontsize=size,
            color=color, rotation=rotation, rotation_mode="anchor",
            fontweight="bold", zorder=8)


def _draw_two_terminal(ax, part: Placement) -> None:
    (x0, y0), (x1, y1) = hole_xy(part.holes[0]), hole_xy(part.holes[1])
    _segment(ax, (x0, y0), (x1, y1), color="#8d8d8d", lw=1.1, zorder=4)
    for x, y in ((x0, y0), (x1, y1)):
        ax.add_patch(Circle((x, y), 0.12, fc="#8d8d8d", zorder=4))
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    length = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    if part.kind == "resistor":
        body = min(max(0.62 * length, 1.1), 2.6)
        nx, ny = -uy * 0.32, ux * 0.32
        corners = [(mx - ux * body / 2 + nx, my - uy * body / 2 + ny),
                   (mx + ux * body / 2 + nx, my + uy * body / 2 + ny),
                   (mx + ux * body / 2 - nx, my + uy * body / 2 - ny),
                   (mx - ux * body / 2 - nx, my - uy * body / 2 - ny)]
        ax.add_patch(Polygon(corners, closed=True, fc="#d8b27a", ec="#8a6a3a",
                             lw=0.6, zorder=5))
        _body_text(ax, (mx, my), part.ref, size=5.4 if len(part.ref) < 3 else 4.6)
    else:
        ax.add_patch(Circle((mx, my), 0.5, fc="#e8a33d", ec="#9a6414", lw=0.6, zorder=5))
        _body_text(ax, (mx, my), part.ref, size=5.0)


def _draw_transistor(ax, part: Placement, value: str) -> None:
    xs = sorted(hole_xy(h)[0] for h in part.holes)
    y = hole_xy(part.holes[0])[1]
    ax.add_patch(FancyBboxPatch((xs[0] - 0.45, y - 0.55), xs[2] - xs[0] + 0.9, 1.1,
                                boxstyle="round,pad=0,rounding_size=0.42",
                                fc="#2a2a2a", ec="#000000", lw=0.6, zorder=6))
    _body_text(ax, (xs[1], y - 0.24), f"{part.ref}  {value}", color="#ffd479", size=4.6)
    for name, hole in zip("CBE", part.holes):
        _body_text(ax, (hole_xy(hole)[0], y + 0.24), name, color="white", size=5.0)


def _draw_wire(ax, wire: Wire) -> None:
    points = [hole_xy(wire.start), hole_xy(wire.end)]
    _polyline(ax, points, color=wire.color, lw=2.2, zorder=3)
    for x, y in points:
        ax.add_patch(Circle((x, y), 0.17, fc=wire.color, ec="white", lw=0.4, zorder=3.5))


def _label(ax, xy, text, *, ha="left", size=6.5):
    ax.text(xy[0], xy[1], text, ha=ha, va="center", fontsize=size, color="#174a7e",
            zorder=8, bbox=dict(boxstyle="round,pad=0.25", fc="#eaf1fa", ec="#174a7e",
                                lw=0.6))


def _draw_off_board(ax, terminal: OffBoard) -> None:
    x, y = hole_xy(terminal.hole)
    if terminal.color is None:
        lx, ly = terminal.end
        ax.plot([x, lx], [y, ly], color=GREY, lw=1.1, ls=(0, (2, 1.5)), zorder=2.5)
        ax.add_patch(Circle((x, y), 0.17, fc=GREY, zorder=3.5))
        _label(ax, terminal.end, terminal.text, ha="right" if lx < x else "left")
        return
    # A white halo shows which wire passes over another where they cross.
    _polyline(ax, [(x, y), *terminal.route, terminal.end], color=terminal.color,
              lw=2.2, zorder=7, path_effects=[
                  patheffects.Stroke(linewidth=3.8, foreground="white"),
                  patheffects.Normal()])
    ax.add_patch(Circle((x, y), 0.17, fc=terminal.color, ec="white", lw=0.4, zorder=7.5))
    if terminal.text_at is not None:
        ax.text(*terminal.text_at, terminal.text, ha="center", va="center", fontsize=6.3,
                color=terminal.color, fontweight="bold", zorder=8)


def _draw_battery(ax, ref: str, x0: float, snap_left: bool, upper: str
                  ) -> dict[str, tuple[float, float]]:
    """A 9 V battery on its side; returns its snap contacts. `upper` is + or −."""
    y0, width, height = -27.0, 8.0, 3.6
    ax.add_patch(FancyBboxPatch((x0, y0), width, height,
                                boxstyle="round,pad=0,rounding_size=0.4",
                                fc="#3b3b3b", ec="#111111", lw=0.8, zorder=5))
    ax.text(x0 + width / 2, y0 + height / 2, f"{ref}\n9 V alkaline", ha="center",
            va="center", fontsize=7, color="white", fontweight="bold", zorder=6)
    xs = x0 - 0.5 if snap_left else x0 + width + 0.5
    ax.add_patch(Rectangle((xs - 0.5, y0 + 0.3), 1.0, height - 0.6, fc="#1c1c1c",
                           ec="#000000", lw=0.6, zorder=5))
    lower = "−" if upper == "+" else "+"
    contacts = {upper: (xs, y0 + 0.9), lower: (xs, y0 + height - 0.9)}
    for name, point in contacts.items():
        ax.text(*point, name, ha="center", va="center", fontsize=6, color="white",
                fontweight="bold", zorder=7)
    return contacts


def _draw_module(ax, values: dict[str, str]) -> None:
    x0, y0, x1, y1 = MODULE
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0,
                                boxstyle="round,pad=0,rounding_size=0.4",
                                fc="#2e9e4f", ec="#1d6b34", lw=1.0, zorder=4))
    for cx, cy in ((x0 + 1, y0 + 1), (x1 - 1, y0 + 1), (x0 + 1, y1 - 1), (x1 - 1, y1 - 1)):
        ax.add_patch(Circle((cx, cy), 0.45, fc="#d9d9d9", ec="#7d7d7d", lw=0.6, zorder=5))
    ax.text((x0 + x1) / 2, y1 - 0.8, "MOD2 AD8421 module, top view", ha="center",
            va="center", fontsize=6.8, color="white", fontweight="bold", zorder=6)
    # Supply screw terminal on the top edge.
    ax.add_patch(Rectangle((x0 + 5.2, y0 - 1.3), 7.6, 1.6, fc="#5fbf6a", ec="#2f6b35",
                           lw=0.8, zorder=5))
    for name, (tx, ty) in TERMINALS.items():
        ax.add_patch(Circle((tx, ty - 0.1), 0.45, fc="#c8c8c8", ec="#555555", lw=0.6,
                            zorder=6))
        ax.text(tx, y0 + 0.8, name, ha="center", va="center", fontsize=6.5,
                color="white", fontweight="bold", zorder=6)
    # Input SMA jacks (unused) and the 3-pin input header with its jumper.
    for y, name in ((-16.5, "−IN SMA"), (-8.5, "+IN SMA")):
        ax.add_patch(Rectangle((x0 - 1.3, y - 0.5), 1.3, 1.0, fc="#d4af37", ec="#8a6d1a",
                               lw=0.6, zorder=5))
        ax.text(x0 - 1.5, y - 0.9, f"{name} (unused)", ha="right", va="center",
                fontsize=5.5, color="#555555")
    px = PIN_IN_PLUS[0]
    for y, name in ((-13.5, "−IN"), (-12.5, "GND"), (-11.5, "+IN")):
        ax.add_patch(Rectangle((px - 0.25, y - 0.25), 0.5, 0.5, fc="#111111", zorder=6))
        ax.text(px + 0.6, y, name, ha="left", va="center", fontsize=5.8,
                color="white", zorder=6)
    ax.add_patch(Rectangle((px - 0.4, -13.85), 0.8, 1.7, fc="#1f1f1f",
                           ec="#ffd479", lw=0.6, zorder=6.5))
    ax.text(px + 2.8, -13.0, "← jumper ties\n   −IN to GND", ha="left",
            va="center", fontsize=5.5, color="#fff3c4", zorder=6)
    # AD8421 under its shield can, R1 in the GAIN footprint.
    ax.add_patch(Rectangle((x0 + 9.5, -14.2), 5.0, 3.6, fc="none", ec="#e6e6e6", lw=0.8,
                           ls=(0, (2, 1.5)), zorder=5))
    ax.add_patch(Rectangle((x0 + 10.8, -13.2), 2.4, 1.6, fc="#151515", zorder=5))
    ax.text(x0 + 12.0, -12.4, "AD8421", ha="center", va="center", fontsize=5.5,
            color="white", zorder=6)
    ax.text(x0 + 12.0, -10.9, "shield can", ha="center", va="center", fontsize=5,
            color="#e6e6e6", zorder=6)
    ax.add_patch(Rectangle((x0 + 7.9, -17.6), 3.2, 0.9, fc="#d8b27a", ec="#8a6a3a",
                           lw=0.6, zorder=6))
    ax.text(x0 + 9.5, -17.15, "R1", ha="center", va="center", fontsize=5.5,
            fontweight="bold", zorder=7)
    ax.text(x0 + 9.5, -18.4, f"GAIN footprint: R1 {values['R1']}", ha="center",
            va="center", fontsize=5.8, color="white", zorder=6)
    # BIAS trimmer and REF jumper.
    ax.add_patch(Rectangle((x0 + 2.4, -8.4), 1.6, 1.6, fc="#2f6fd6", ec="#173a73",
                           lw=0.6, zorder=6))
    ax.text(x0 + 4.4, -7.6, "BIAS trimmer: set OUT to 2.50 V", ha="left", va="center",
            fontsize=5.6, color="white", zorder=6)
    ax.text(x0 + 4.4, -6.6, "REF jumper on BIAS", ha="left", va="center",
            fontsize=5.6, color="white", zorder=6)
    # Output SMA jack and the cable.
    ax.add_patch(Rectangle((x1, PIN_OUT[1] - 0.5), 1.4, 1.0, fc="#d4af37", ec="#8a6d1a",
                           lw=0.6, zorder=5))
    ax.text(x1 - 0.3, PIN_OUT[1], "OUT", ha="right", va="center", fontsize=6,
            color="white", fontweight="bold", zorder=6)
    _polyline(ax, [PIN_OUT, (CABLE_SPLIT[0], PIN_OUT[1]), CABLE_SPLIT], color="#7a7a7a",
              lw=4.0, zorder=6)
    ax.add_patch(Circle(CABLE_SPLIT, 0.4, fc="#7a7a7a", zorder=6.5))
    ax.text(CABLE_SPLIT[0] + 0.8, -8.0, "W1 SMA–Dupont\ncable", ha="left", va="center",
            fontsize=6.3, color="#555555", fontweight="bold")


def _draw_batteries(ax) -> None:
    # BT1 + to V+; BT1 − and BT2 + meet at GND; BT2 − to V−. Each lead runs
    # level from its snap, then straight down into its terminal.
    bt1 = _draw_battery(ax, "BT1", MODULE[0] - 7.0, snap_left=False, upper="−")
    bt2 = _draw_battery(ax, "BT2", MODULE[0] + 17.0, snap_left=True, upper="+")
    leads = (
        (bt1["+"], TERMINALS["V+"][0], RED),
        (bt1["−"], TERMINALS["GND"][0] - 0.3, BLACK),
        (bt2["+"], TERMINALS["GND"][0] + 0.3, RED),
        (bt2["−"], TERMINALS["V−"][0], BLACK),
    )
    for start, x, color in leads:
        _polyline(ax, [start, (x, start[1]), (x, TERMINALS["V+"][1])], color=color,
                  lw=2.0, zorder=5.5)
    for name, x in (("W2 snap", MODULE[0] + 1.5), ("W3 snap", MODULE[0] + 16.5)):
        ax.text(x, -27.8, name, ha="center", va="center", fontsize=6, color="#333333",
                fontweight="bold")


def _draw_ads1256(ax) -> None:
    x0, y0, x1, y1 = ADS
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0,
                                boxstyle="round,pad=0,rounding_size=0.4",
                                fc="#1f5fae", ec="#123a6b", lw=1.0, zorder=4))
    for cx, cy in ((x0 + 1, y0 + 1), (x1 - 1, y0 + 1), (x0 + 1, y1 - 1), (x1 - 1, y1 - 1)):
        ax.add_patch(Circle((cx, cy), 0.45, fc="#d9d9d9", ec="#7d7d7d", lw=0.6, zorder=5))
    # Analog header: row k holds AINk (outer) and a GND (inner).
    ax.add_patch(Rectangle((40.35, -19.5), 1.9, 8.0, fc="#151515", zorder=5))
    for k in range(8):
        for name in (f"AIN{k}", f"GND{k}"):
            px, py = ADS_PIN_XY[name]
            ax.add_patch(Rectangle((px - 0.17, py - 0.17), 0.34, 0.34, fc="#d4af37",
                                   zorder=5.5))
        ax.text(42.5, -19.0 + k, f"AIN{k} · GND", ha="left", va="center", fontsize=5.2,
                color="white", zorder=6)
    # Digital header.
    ax.add_patch(Rectangle((56.8, -19.5), 0.8, 8.0, fc="#151515", zorder=5))
    for name in ADS_DIGITAL:
        px, py = ADS_PIN_XY[name]
        ax.add_patch(Rectangle((px - 0.17, py - 0.17), 0.34, 0.34, fc="#d4af37",
                               zorder=5.5))
        ax.text(56.4, py, name, ha="right", va="center", fontsize=5.6, color="white",
                fontweight="bold", zorder=6)
    ax.add_patch(Rectangle((46.6, -18.4), 4.8, 3.2, fc="#151515", zorder=5))
    ax.text(49.0, -16.8, "ADS1256", ha="center", va="center", fontsize=6, color="white",
            zorder=6)
    ax.add_patch(Rectangle((47.2, -13.6), 1.6, 1.2, fc="#151515", zorder=5))
    ax.text(48.0, -12.0, "ADR03 2.5 V", ha="center", va="center", fontsize=4.8,
            color="white", zorder=6)
    ax.add_patch(FancyBboxPatch((50.4, -13.5), 3.0, 1.0,
                                boxstyle="round,pad=0,rounding_size=0.4",
                                fc="#d0d0d0", ec="#8a8a8a", lw=0.6, zorder=5))
    ax.text(51.9, -12.0, "7.68 MHz", ha="center", va="center", fontsize=4.8,
            color="white", zorder=6)
    ax.text((x0 + x1) / 2, y1 - 2.0, "MOD1 HiLetgo ADS1256 module, top view",
            ha="center", va="center", fontsize=6.8, color="white", fontweight="bold",
            zorder=6)
    ax.text((x0 + x1) / 2, y1 - 1.0, "pin labels are on its underside; check them first",
            ha="center", va="center", fontsize=5.6, color="#dce9ff", zorder=6)


def _draw_xiao(ax, used: set[str]) -> None:
    xs = [hole_xy(hole)[0] for hole in XIAO_PINS.values()]
    top, bottom = hole_xy("c56")[1], hole_xy("h56")[1]
    left, right, middle = min(xs) - 1.13, max(xs) + 1.13, (top + bottom) / 2
    ax.add_patch(FancyBboxPatch((left, top - 0.35), right - left, bottom - top + 0.7,
                                boxstyle="round,pad=0,rounding_size=0.5",
                                fc="#1c1c1c", ec="#000000", lw=0.8, zorder=6))
    ax.add_patch(Rectangle((left + 1.6, top + 1.3), 4.6, bottom - top - 2.6, fc="#c3c7cc",
                           ec="#8a8f94", lw=0.6, zorder=6.2))
    ax.text(left + 3.9, middle, "U1\nXIAO\nRP2350", ha="center", va="center",
            fontsize=6.2, fontweight="bold", color="#222222", zorder=6.4)
    # USB-C receptacle and cable off the board's right end.
    ax.add_patch(Rectangle((right - 0.2, middle - 1.77), 1.0, 3.54, fc="#d0d0d0",
                           ec="#7a7a7a", lw=0.6, zorder=6.3))
    ax.add_patch(FancyBboxPatch((right + 0.8, middle - 1.3), 1.8, 2.6,
                                boxstyle="round,pad=0,rounding_size=0.3",
                                fc="#555555", ec="#333333", lw=0.6, zorder=6.3))
    _segment(ax, (right + 2.6, middle), (72.0, middle), color="#6e6e6e", lw=5.0, zorder=2)
    ax.text(68.4, middle - 1.3, "USB-C to laptop", ha="left", va="center", fontsize=6.5,
            color="#333333", fontweight="bold")
    ax.text(68.4, middle + 1.5, "powers the XIAO and,\nthrough its 5V pin, the ADS1256",
            ha="left", va="center", fontsize=5.6, color="#333333")
    for pin, hole in XIAO_PINS.items():
        x, y = hole_xy(hole)
        color = "#ffd479" if pin in used else "#9a9a9a"
        ax.add_patch(Circle((x, y), 0.22, fc=color, ec="#5a4a1a", lw=0.4, zorder=6.5))
        ax.text(x, y + (0.78 if y < middle else -0.78), XIAO_NAMES[pin], ha="center",
                va="center", fontsize=4.6, color=color, fontweight="bold", zorder=6.6)


def build_receiver_breadboard(output_dir: Path, spice_path: Path = SPICE_NETLIST,
                              kicad_path: Path = KICAD_NETLIST
                              ) -> tuple[Path, Path, Path]:
    """Check the layout against both netlists, then draw it and list every hole."""
    spice = spice_path.read_text()
    check_layout(spice, kicad_path.read_text())
    elements = spice_elements(spice)
    values = {ref: _value_text(ref, model) for ref, (_nodes, model) in elements.items()}
    values |= {part.ref: _value_text(part.ref, part.value) for part in TEST_PARTS}
    used = {pin for pin, hole in XIAO_PINS.items()
            if any(contact(t.hole) == contact(hole) for t in OFF_BOARD)}
    output_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(24.0, 16.0))
    ax.set_xlim(-14.5, 76.0)
    ax.set_ylim(36.0, -32.0)
    ax.set_aspect("equal")
    ax.axis("off")
    _draw_board(ax)
    for wire in WIRES + TEST_WIRES:
        _draw_wire(ax, wire)
    for part in PARTS + TEST_PARTS:
        if part.kind == "npn":
            _draw_transistor(ax, part, values[part.ref])
        else:
            _draw_two_terminal(ax, part)
    _draw_xiao(ax, used)
    _draw_module(ax, values)
    _draw_batteries(ax)
    _draw_ads1256(ax)
    for terminal in OFF_BOARD:
        _draw_off_board(ax, terminal)
    ax.text(14.0, 8.5, "J1 (test jumper): remove it for the coil", ha="center",
            va="center", fontsize=6.0, color=GREEN, fontweight="bold")

    ax.text(-14.0, -31.0, "Receiver bench assembly — AD8421 module, ADS1256 module, XIAO "
            "RP2350, and an 830-point breadboard", fontsize=13, fontweight="bold",
            ha="left", va="center")
    ax.text(-14.0, -29.7,
            "Top view, laid out as the board was built. Holes, parts, and jumpers match "
            "spice/receiver.cir node for node, and the XIAO–ADS1256 wires match "
            "kicad/receiver.net. RT1 and RT2 let a function generator stand in for the coil.",
            fontsize=7.5, color="#174a7e", ha="left", va="center")
    steps = (
        "Prepare the AD8421 module first (assembly.md): confirm the AD8421 marking, remove the "
        "input RFI parts between the input jacks and the chip, and fit R1 in the GAIN footprint.",
        "Batteries go only to the module's screw terminal: BT1 + → V+, BT1 − and BT2 + twisted "
        "together → GND, BT2 − → V−. Disconnect a battery when idle.",
        "W1: plug the SMA end into OUT. The Dupont lead that reaches the SMA center pin goes to "
        "a26; the shield lead goes to T-28. That shield is the only ground link from the AD8421 "
        "module to the breadboard.",
        "The orange jumper (male to female Dupont) runs from a17 to the module's +IN header pin; "
        "keep it short. Leave the header jumper on −IN/GND and the REF jumper on BIAS.",
        "Q1 and Q2 are 2N3904 clamp diodes; the letters give the lead each hole needs (C, B, E). "
        "C1, C2, RT2, and the black jumpers reach the outer rail row, past the + row.",
        "Test input: RT1 (100 kΩ) and RT2 (100 Ω) divide the generator by about 1001; the green "
        "jumper e11–e17 is J1. Set the generator to High-Z load. Clip its signal to e5 and its "
        "ground to T-40, right of every analog ground, so ground-loop current through the laptop "
        "stays out of the input.",
        "For the coil instead: remove the green jumper and the generator; coil signal → e17, coil "
        "return → T-17.",
        "ADS1256 (female Dupont ends on its pins): AIN0 ← e35, AIN1 ← T-36, analog-header GND ← "
        "T-37. Do not jumper AIN1 to the GND pin beside it. Configure buffer off, PGA 1, "
        "30 kSPS, AIN0 − AIN1.",
        "XIAO: pins in rows c and h, columns 56–62, USB-C off the right end. a58 D4 → PDWN, a59 "
        "D3 → CS, a60 D2 → DRDY, j57 D8 → SCLK, j58 D9 → DOUT, j59 D10 → DIN, j61 GND → GND, "
        "j62 5V → 5V. The XIAO's ground reaches the breadboard only through the ADS1256 module.",
        "With the generator off, trim BIAS until OUT reads 2.50 V; AIN0 (e35) then reads about "
        "2.39 V. Check that the outer top rail is continuous from column 11 to column 40.",
    )
    ax.text(-14.0, 22.4, "Part values", fontsize=8.5, fontweight="bold",
            ha="left", va="center")
    ordered = sorted(values, key=lambda ref: (ref[0] != "R", ref.startswith("RT"), ref[0],
                                              int(ref.lstrip("RTCQ"))))
    for index, ref in enumerate(ordered):
        where = " (on module)" if ref in ON_MODULE else " (test)" if ref.startswith("RT") else ""
        ax.text(-14.0 + 9.8 * index, 23.6, f"{ref}  {values[ref]}{where}",
                fontsize=7.2, ha="left", va="center")
    for index, step in enumerate(steps):
        ax.text(-14.0, 25.2 + 1.05 * index, f"{index + 1}. {step}", fontsize=7.2,
                ha="left", va="center", color="#333333")

    svg_path = output_dir / "receiver-breadboard.svg"
    png_path = output_dir / "receiver-breadboard.png"
    fig.patch.set_facecolor("white")
    with matplotlib.rc_context({"svg.hashsalt": "receiver-breadboard"}):
        fig.savefig(svg_path, format="svg", facecolor="white", bbox_inches="tight",
                    metadata={"Date": None})
    fig.savefig(png_path, dpi=150, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    svg_path.write_text("\n".join(line.rstrip()
                                  for line in svg_path.read_text().splitlines()) + "\n")
    md_path = output_dir / "receiver-breadboard.md"
    md_path.write_text(_placement_markdown(values))
    return svg_path, png_path, md_path


def _part_rows(parts, values) -> list[str]:
    rows = []
    for part in parts:
        if part.kind == "npn":
            pins = ", ".join(f"{name} {hole}" for name, hole in zip("CBE", part.holes))
        else:
            pins = f"{part.holes[0]}, {part.holes[1]}"
        rows.append(f"{part.ref} | {values[part.ref]} | {pins}")
    return rows


def _placement_markdown(values) -> str:
    lines = [
        "# Receiver breadboard placement",
        "",
        "Standard 830-point board: columns 1–63, rows a–e above the centre channel and "
        "f–j below it. `T-` is the outer top rail row, beside the blue line, used as GND; "
        "the other three rails stay unused. `receiver-breadboard.png` draws the same holes "
        "with the AD8421 module, its batteries, the ADS1256 module, and the XIAO.",
        "",
        "## Receiver parts",
        "",
        "Ref | Part | Holes",
        "--- | --- | ---",
    ]
    lines += _part_rows(PARTS, values)
    lines += [f"{ref} | {values[ref]} | module GAIN footprint" for ref in sorted(ON_MODULE)]
    lines += [
        "",
        "## Test input",
        "",
        "A function generator stands in for the coil. Set it to High-Z load; the voltage at "
        "J1 is then its amplitude × RT2 / (RT1 + RT2), about 1/1001. Measure RT1 and RT2 for "
        "the exact ratio.",
        "",
        "Ref | Part | Holes",
        "--- | --- | ---",
    ]
    lines += _part_rows(TEST_PARTS, values)
    lines += [
        "",
        "For the coil, remove the e11–e17 jumper and the generator leads, then connect the "
        "coil signal to e17 and the coil return to T-17.",
        "",
        "## Jumpers",
        "",
        "From | To",
        "--- | ---",
    ]
    lines += [f"{wire.start} | {wire.end}" for wire in WIRES]
    lines += [f"{wire.start} | {wire.end} (test J1; remove for the coil)"
              for wire in TEST_WIRES]
    lines += [
        "",
        "## XIAO RP2350 (U1)",
        "",
        "The XIAO straddles the channel with its pins in rows c and h, columns 56–62, and its "
        "USB-C connector past column 63. Its body covers rows c–h of columns 55–63.",
        "",
        "Pin | Pin hole | Wire from | To",
        "--- | --- | --- | ---",
    ]
    for pin, hole in sorted(XIAO_PINS.items(), key=lambda item: int(item[0])):
        for terminal in OFF_BOARD:
            if contact(terminal.hole) == contact(hole):
                lines.append(f"{XIAO_NAMES[pin]} | {hole} | {terminal.hole} | {terminal.text}")
    lines += ["", "## Off-board wires", "", "Hole | Connection", "--- | ---"]
    lines += [f"{terminal.hole} | {terminal.text}" for terminal in OFF_BOARD]
    lines += [
        "",
        "## Modules and batteries",
        "",
        "- BT1 + → AD8421 module V+; BT1 − and BT2 + → module GND; BT2 − → module V−.",
        "- W1 SMA end → module OUT jack; its signal lead → a26, its shield lead → T-28.",
        "- Keep the AD8421 module's input jumper on −IN/GND and its REF jumper on BIAS.",
        "- The ADS1256 module's pin labels are on its underside. Use female Dupont ends on its "
        "pins, run the AIN0, AIN1, and GND leads together, and do not jumper AIN1 to the GND "
        "pin beside it.",
        "- Clip the generator ground to T-40, right of every analog ground on the rail.",
        "",
        "Check each transistor's pinout before inserting it; the holes name its C, B, and E "
        "leads.",
    ]
    return "\n".join(lines) + "\n"
