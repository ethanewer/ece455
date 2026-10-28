"""Place the off-board amplifier on a standard 830-point breadboard.

The signal board brings the tuned coil out on J5 and takes the amplified
signal back on J6; the two op-amp stages between them exist only in
ltspice/AmplificationSim.asc. This module holds one fixed layout for them
(data, not a placer). `check_layout` rebuilds the board's connectivity from
strips, rails, jumpers, the op-amp pins, and off-board leads, and fails
unless it reproduces the LTspice netlist node for node and every lead lands
on the intended signal-board net. Run `python3 -m util.breadboard`
(`make breadboard`) to check the layout and write docs/breadboard/.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Rectangle

from util import design, kicad
from util.kicad import Netlist
from util.ltspice import Schematic, spice_number

OUTPUT = design.ROOT / "docs/breadboard"

# Standard 830-point board: 63 columns of two 5-hole strips (a-e, f-j)
# across a centre channel, plus two rail pairs of 50 holes in groups of 5.
COLUMNS = 63
ROW_Y = {"a": 3, "b": 4, "c": 5, "d": 6, "e": 7,
         "f": 10, "g": 11, "h": 12, "i": 13, "j": 14}
RAIL_Y = {"T-": 0, "T+": 1, "B+": 16, "B-": 17}
RAIL_COLUMNS = frozenset(start + offset for start in range(3, 58, 6) for offset in range(5))
HOLE = re.compile(r"(T\+|T-|B\+|B-|[a-j])(\d+)")
RAIL_USE = {"T+": "+5 V", "B+": "+2.5 V", "B-": "GND", "T-": "unused"}

# The design files name no op-amp part. The layout assumes single op amps in
# the standard 8-pin DIP pinout; check it against the chosen part.
DIP_PINS = {"in-": 2, "in+": 3, "v-": 4, "out": 6, "v+": 7}
DIP_UNUSED = (1, 5, 8)


@dataclass(frozen=True)
class Placement:
    """A two-terminal part. Holes follow the LTspice pin order unless it is a test part."""

    ref: str
    holes: tuple[str, str]
    nodes: tuple[str, str] = ()   # test parts only; amplifier parts take theirs from LTspice
    value: str = ""


@dataclass(frozen=True)
class Chip:
    ref: str
    column: int   # pin 1 sits at row f of this column; the notch faces left


@dataclass(frozen=True)
class Wire:
    start: str
    end: str
    color: str


@dataclass(frozen=True)
class Lead:
    """A wire to the signal board (`pin` is REF.pin) or to the bench (`pin` is None)."""

    hole: str
    text: str
    node: str           # LTspice node, or a test-fixture node
    pin: str | None
    color: str


RED, BLACK, ORANGE, YELLOW = "#d62728", "#222222", "#ff7f0e", "#e6b800"
GREY, BLUE, GREEN, PURPLE = "#5a5a5a", "#1f77b4", "#2ca02c", "#7b4173"

CHIPS = (Chip("U1", 16), Chip("U2", 28))

PARTS = (
    # Stage 1: C4 couples J5 to U1 +IN; R8 biases it; R4 and R3 set the gain.
    Placement("C4", ("h18", "h13")),
    Placement("R8", ("j18", "B+18")),
    Placement("R4", ("B+17", "j17")),
    Placement("R3", ("f21", "e21")),
    # Interstage high-pass to U2 +IN.
    Placement("C5", ("c25", "c21")),
    Placement("R9", ("j25", "B+25")),
    # Stage 2.
    Placement("R11", ("B+29", "j29")),
    Placement("R10", ("f33", "e33")),
    # Output high-pass to J6.
    Placement("C6", ("c37", "c33")),
    Placement("R12", ("j37", "B-37")),
)

# A 1001:1 divider lets a function generator stand in for the coil.
TEST_PARTS = (
    Placement("RT1", ("g4", "g10"), ("generator", "amp_in"), "100k"),
    Placement("RT2", ("j10", "B-10"), ("amp_in", "0"), "100"),
)
TEST_WIRES = (Wire("i10", "i13", GREEN),)

WIRES = (
    Wire("a17", "T+17", RED), Wire("j19", "B-19", BLACK),          # U1 supplies
    Wire("g17", "g21", BLUE), Wire("b18", "b21", ORANGE),           # U1 feedback
    Wire("f25", "e25", YELLOW), Wire("h25", "h30", YELLOW),         # to U2 +IN
    Wire("a29", "T+29", RED), Wire("j31", "B-31", BLACK),          # U2 supplies
    Wire("g29", "g33", BLUE), Wire("b30", "b33", ORANGE),           # U2 feedback
    Wire("f37", "e37", PURPLE),                                    # output to the J6 lead
)

LEADS = (
    Lead("j13", "J5 pin 2: tuned coil", "tank", "J5.2", GREEN),
    Lead("B-12", "J5 pin 1: GND", "0", "J5.1", BLACK),
    Lead("h37", "J6 pin 2: amplifier output", "VopAmpOut2", "J6.2", PURPLE),
    Lead("B-39", "J6 pin 1: GND", "0", "J6.1", BLACK),
    Lead("T+41", "TP4: +5 V", "5P", "TP4.1", RED),
    Lead("B+41", "TP5: +2.5 V bias", "25P", "TP5.1", ORANGE),
    Lead("j4", "Function generator signal (test only)", "generator", None, GREY),
    Lead("B-11", "Function generator ground (test only)", "0", None, GREY),
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


def chip_holes(chip: Chip) -> dict[int, str]:
    """DIP pin number -> hole: pins 1-4 along row f, 5-8 back along row e."""
    return {**{n: f"f{chip.column + n - 1}" for n in range(1, 5)},
            **{n: f"e{chip.column + 8 - n}" for n in range(5, 9)}}


def _crossed_holes(start: str, end: str) -> list[str]:
    """Holes strictly between two holes on one row or one column."""
    (r0, c0), (r1, c1) = parse_hole(start), parse_hole(end)
    if r0 == r1:
        lo, hi = sorted((c0, c1))
        return [f"{r0}{c}" for c in range(lo + 1, hi) if r0 not in RAIL_Y or c in RAIL_COLUMNS]
    if c0 == c1:
        y0, y1 = sorted((hole_xy(start)[1], hole_xy(end)[1]))
        return [f"{r}{c0}" for r, y in {**ROW_Y, **RAIL_Y}.items()
                if y0 < y < y1 and (r not in RAIL_Y or c0 in RAIL_COLUMNS)]
    return []


def board_nodes(schematic: Schematic) -> dict[str, str]:
    """Layout node names -> LTspice nodes. V5 is a second 2.5 V source; the board has one rail."""
    tank = next(n for n in schematic.elements[design.TANK].nodes if n != "0")
    return {"tank": tank, "amp_in": tank, "0": "0", "5P": schematic.flags["5P"],
            "25P": schematic.flags["25P"], "VopAmpOut2": schematic.flags["VopAmpOut2"],
            schematic.node("V5", 1): schematic.flags["25P"]}


def part_nodes(schematic: Schematic) -> dict[str, tuple[str, ...]]:
    """Each fitted part's LTspice nodes, with V5's node folded into the 2.5 V rail."""
    alias = board_nodes(schematic)
    return {ref: tuple(alias.get(node, node) for node in schematic.elements[ref].nodes)
            for ref in design.AMPLIFIER_PARTS}


def check_layout(schematic: Schematic, board: Netlist) -> dict[str, frozenset[str]]:
    """Fail unless the layout reproduces the amplifier netlist; map each node to its contacts."""
    nodes = part_nodes(schematic)
    alias = board_nodes(schematic)
    placed = {part.ref for part in PARTS} | {chip.ref for chip in CHIPS}
    if placed != set(design.AMPLIFIER_PARTS) or len(PARTS) + len(CHIPS) != len(placed):
        raise ValueError(f"layout and amplifier parts differ: {sorted(placed ^ set(design.AMPLIFIER_PARTS))}")
    for chip in CHIPS:
        if not schematic.elements[chip.ref].symbol.endswith("UniversalOpAmp2"):
            raise ValueError(f"{chip.ref} is not an op amp in the LTspice drawing")
    for lead in LEADS:
        if lead.pin is None:
            continue
        ref, pin = lead.pin.split(".")
        expected = design.COIL_NET if lead.node == "tank" else design.NET_MAP[lead.node]
        if board.net_of(ref, pin) != expected:
            raise ValueError(f"{lead.pin} is on {board.net_of(ref, pin)}, not {expected}")

    occupied: dict[str, str] = {}

    def occupy(hole: str, owner: str) -> None:
        parse_hole(hole)
        if hole in occupied:
            raise ValueError(f"{hole} holds both {occupied[hole]} and {owner}")
        occupied[hole] = owner

    leads: list[tuple[str, str, str]] = []
    for part in PARTS:
        for hole, node in zip(part.holes, nodes[part.ref]):
            occupy(hole, part.ref)
            leads.append((contact(hole), node, f"{part.ref}:{hole}"))
    for part in TEST_PARTS:
        for hole, node in zip(part.holes, part.nodes):
            occupy(hole, part.ref)
            leads.append((contact(hole), alias.get(node, node), f"{part.ref}:{hole}"))
    for chip in CHIPS:
        holes = chip_holes(chip)
        if {parse_hole(h)[0] for h in holes.values()} != {"e", "f"}:
            raise ValueError(f"{chip.ref} does not straddle the channel")
        for number, hole in holes.items():
            occupy(hole, f"{chip.ref} pin {number}")
        for name, number in DIP_PINS.items():
            node = nodes[chip.ref][("in+", "in-", "v+", "v-", "out").index(name)]
            leads.append((contact(holes[number]), node, f"{chip.ref} pin {number}"))
        for number in DIP_UNUSED:
            leads.append((contact(holes[number]), f"{chip.ref}.nc{number}", f"{chip.ref} pin {number}"))
    for wire in WIRES + TEST_WIRES:
        occupy(wire.start, "wire")
        occupy(wire.end, "wire")
    for lead in LEADS:
        occupy(lead.hole, lead.text)
        leads.append((contact(lead.hole), alias.get(lead.node, lead.node), lead.text))

    # Straight leads, bodies, and jumpers may not pass over a used hole.
    for owner, (start, end) in [(p.ref, p.holes) for p in PARTS + TEST_PARTS] + [
            ("wire", (w.start, w.end)) for w in WIRES + TEST_WIRES]:
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
    node_root: dict[str, str] = {}
    root_node: dict[str, str] = {}
    for strip, node, where in leads:
        root = find(strip)
        if node_root.setdefault(node, root) != root:
            raise ValueError(f"node {node} is split on the board at {where}")
        if root_node.setdefault(root, node) != node:
            raise ValueError(f"{where} shorts {node} to {root_node[root]}")
    for chip in CHIPS:
        for number in DIP_UNUSED:
            if sum(1 for strip, _n, _w in leads
                   if find(strip) == find(contact(chip_holes(chip)[number]))) != 1:
                raise ValueError(f"{chip.ref} pin {number} must stay unconnected")
    for wire in WIRES + TEST_WIRES:
        if find(contact(wire.start)) not in root_node:
            raise ValueError(f"wire {wire.start}-{wire.end} connects nothing")
    for rail, use in RAIL_USE.items():
        node = root_node.get(find(rail))
        expected = {"+5 V": alias["5P"], "+2.5 V": alias["25P"], "GND": "0", "unused": None}[use]
        if node != expected:
            raise ValueError(f"rail {rail} carries {node}, documented as {use}")
    contacts = {strip for strip, _node, _where in leads}
    return {node: frozenset(c for c in contacts if find(c) == root) for node, root in node_root.items()}


_E24 = (1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
        3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1)
_E12 = _E24[::2]


def nearest_standard(value: float, series: tuple[float, ...]) -> float:
    exponent = math.floor(math.log10(value))
    candidates = [m * 10.0 ** e for e in (exponent - 1, exponent, exponent + 1) for m in series]
    return min(candidates, key=lambda c: abs(math.log(c / value)))


def value_text(ref: str, value: float) -> str:
    unit = "Ω" if ref.startswith("R") else "F"
    for scale, prefix in ((1e6, "M"), (1e3, "k"), (1.0, ""), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p")):
        if value >= scale * 0.999:
            return f"{value / scale:.3g} {prefix}{unit}"
    return f"{value:g} {unit}"


def _segment(ax, start, end, **kwargs):
    ax.plot([start[0], end[0]], [start[1], end[1]], solid_capstyle="round", **kwargs)


def _draw_board(ax) -> None:
    ax.add_patch(FancyBboxPatch((-0.4, -1.4), COLUMNS + 1.8, 20.0,
                                boxstyle="round,pad=0,rounding_size=0.8",
                                fc="#f3efe6", ec="#b8b0a0", lw=1.2, zorder=0))
    ax.add_patch(Rectangle((-0.4, 8.0), COLUMNS + 1.8, 1.0, fc="#e2dccd", ec="none", zorder=0.1))
    for y, color in ((-0.7, BLUE), (1.7, RED), (15.3, RED), (17.7, BLUE)):
        _segment(ax, (2.4, y), (61.6, y), color=color, lw=1.0, zorder=0.2)
    for rail, y in RAIL_Y.items():
        ax.text(1.4, y, "+" if rail.endswith("+") else "−", ha="center", va="center",
                fontsize=7, color=RED if rail.endswith("+") else BLUE)
        ax.text(62.6, y, RAIL_USE[rail], ha="left", va="center", fontsize=6.5,
                color=RED if rail.endswith("+") else BLUE, fontweight="bold")
    for column in range(1, COLUMNS + 1):
        rows = list(ROW_Y.values()) + (list(RAIL_Y.values()) if column in RAIL_COLUMNS else [])
        for y in rows:
            ax.add_patch(Rectangle((column - 0.16, y - 0.16), 0.32, 0.32,
                                   fc="#9c968a", ec="none", zorder=0.3))
        if column == 1 or column % 5 == 0:
            for y in (2.05, 14.95):
                ax.text(column, y, str(column), ha="center", va="center", fontsize=5.5,
                        color="#6b665c")
    for row, y in ROW_Y.items():
        ax.text(0.2, y, row, ha="center", va="center", fontsize=6, color="#6b665c")


def _body_text(ax, xy, text, *, color="black", size=5.4):
    ax.text(xy[0], xy[1], text, ha="center", va="center", fontsize=size, color=color,
            fontweight="bold", zorder=8)


def _draw_two_terminal(ax, part: Placement) -> None:
    (x0, y0), (x1, y1) = hole_xy(part.holes[0]), hole_xy(part.holes[1])
    _segment(ax, (x0, y0), (x1, y1), color="#8d8d8d", lw=1.1, zorder=4)
    for x, y in ((x0, y0), (x1, y1)):
        ax.add_patch(Circle((x, y), 0.12, fc="#8d8d8d", zorder=4))
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    length = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    if part.ref.startswith("R"):
        body = min(max(0.62 * length, 1.1), 2.6)
        nx, ny = -uy * 0.32, ux * 0.32
        corners = [(mx - ux * body / 2 + nx, my - uy * body / 2 + ny),
                   (mx + ux * body / 2 + nx, my + uy * body / 2 + ny),
                   (mx + ux * body / 2 - nx, my + uy * body / 2 - ny),
                   (mx - ux * body / 2 - nx, my - uy * body / 2 - ny)]
        ax.add_patch(Polygon(corners, closed=True, fc="#d8b27a", ec="#8a6a3a", lw=0.6, zorder=5))
        _body_text(ax, (mx, my), part.ref, size=5.4 if len(part.ref) < 3 else 4.6)
    else:
        ax.add_patch(Circle((mx, my), 0.5, fc="#e8a33d", ec="#9a6414", lw=0.6, zorder=5))
        _body_text(ax, (mx, my), part.ref, size=5.0)


def _draw_chip(ax, chip: Chip) -> None:
    holes = chip_holes(chip)
    x0 = chip.column - 0.45
    ax.add_patch(FancyBboxPatch((x0, 6.55), 3.9, 3.9, boxstyle="round,pad=0,rounding_size=0.25",
                                fc="#262626", ec="#000000", lw=0.8, zorder=6))
    ax.add_patch(Circle((x0, 8.5), 0.35, fc="#f3efe6", ec="#000000", lw=0.6, zorder=6.1))
    _body_text(ax, (chip.column + 1.5, 8.2), chip.ref, color="white", size=7)
    _body_text(ax, (chip.column + 1.5, 9.0), "op amp", color="#cccccc", size=4.8)
    names = {number: name.upper() for name, number in DIP_PINS.items()}
    for number, hole in holes.items():
        x, y = hole_xy(hole)
        used = number in names
        ax.add_patch(Circle((x, y), 0.2, fc="#ffd479" if used else "#9a9a9a", zorder=6.5))
        label = {"IN-": "−IN", "IN+": "+IN", "V-": "V−", "V+": "V+", "OUT": "OUT"}.get(
            names.get(number, ""), "nc")
        ax.text(x, y + (0.55 if y > 8.5 else -0.55), f"{number} {label}", ha="center",
                va="center", fontsize=4.2, color="#5a4a1a" if used else "#8d8d8d", zorder=6.6,
                fontweight="bold")


def _draw_wire(ax, wire: Wire) -> None:
    points = [hole_xy(wire.start), hole_xy(wire.end)]
    ax.plot(*zip(*points), color=wire.color, lw=2.2, zorder=3, solid_capstyle="round")
    for x, y in points:
        ax.add_patch(Circle((x, y), 0.17, fc=wire.color, ec="white", lw=0.4, zorder=3.5))


def _draw_lead(ax, lead: Lead, index: int, below: bool) -> None:
    x, y = hole_xy(lead.hole)
    target = (x, 21.5 + 1.1 * index) if below else (x, -3.0 - 1.1 * index)
    ax.plot([x, target[0]], [y, target[1]], color=lead.color, lw=1.6, zorder=2.5,
            linestyle="solid" if lead.pin else (0, (2, 1.5)))
    ax.add_patch(Circle((x, y), 0.17, fc=lead.color, ec="white", lw=0.4, zorder=3.5))
    ax.text(target[0] + 0.3, target[1], lead.text, ha="left", va="center", fontsize=6.5,
            color="#174a7e", zorder=8, bbox=dict(boxstyle="round,pad=0.25", fc="#eaf1fa",
                                                 ec="#174a7e", lw=0.6))


def build_breadboard(output_dir: Path = OUTPUT) -> tuple[Path, Path, Path]:
    """Check the layout, then draw it and list every hole."""
    schematic = design.amplifier()
    check_layout(schematic, design.signal_board())
    values = {ref: spice_number(schematic.elements[ref].value)
              for ref in design.AMPLIFIER_PARTS if not ref.startswith("U")}
    values |= {part.ref: spice_number(part.value) for part in TEST_PARTS}
    output_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(22.0, 13.0))
    ax.set_xlim(-2.0, 70.0)
    ax.set_ylim(33.5, -10.5)
    ax.set_aspect("equal")
    ax.axis("off")
    _draw_board(ax)
    for wire in WIRES + TEST_WIRES:
        _draw_wire(ax, wire)
    for part in PARTS + TEST_PARTS:
        _draw_two_terminal(ax, part)
    for chip in CHIPS:
        _draw_chip(ax, chip)
    # Labels for leads further right sit nearer the board, so no lead crosses a label.
    by_x = sorted(LEADS, key=lambda lead: -hole_xy(lead.hole)[0])
    top = [lead for lead in by_x if hole_xy(lead.hole)[1] < 8.5]
    bottom = [lead for lead in by_x if hole_xy(lead.hole)[1] > 8.5]
    for index, lead in enumerate(top):
        _draw_lead(ax, lead, index, below=False)
    for index, lead in enumerate(bottom):
        _draw_lead(ax, lead, index, below=True)
    ax.text(11.5, 8.5, "test jumper", ha="center", va="center", fontsize=5.5, color=GREEN,
            fontweight="bold")
    ax.text(-1.5, -9.6, "Off-board amplifier on an 830-point breadboard, between signal-board "
            "J5 and J6", fontsize=13, fontweight="bold", ha="left", va="center")
    ax.text(-1.5, -8.4, "Top view. Parts, values, and nodes follow ltspice/AmplificationSim.asc; "
            "leads are checked against the signal-board KiCad nets. Op amps: standard single "
            "op-amp DIP-8 pinout assumed.", fontsize=7.5, color="#174a7e", ha="left", va="center")
    ordered = sorted(values, key=lambda ref: (ref.startswith("RT"), ref[0], int(ref.lstrip("RTC"))))
    for index, ref in enumerate(ordered):
        ax.text(-1.5 + 7.6 * (index % 9), 30.5 + 1.2 * (index // 9),
                f"{ref}  {value_text(ref, values[ref])}", fontsize=7.2, ha="left", va="center")

    svg_path = output_dir / "amplifier-breadboard.svg"
    png_path = output_dir / "amplifier-breadboard.png"
    fig.patch.set_facecolor("white")
    with matplotlib.rc_context({"svg.hashsalt": "amplifier-breadboard"}):
        fig.savefig(svg_path, format="svg", facecolor="white", bbox_inches="tight",
                    metadata={"Date": None})
    fig.savefig(png_path, dpi=150, facecolor="white", bbox_inches="tight",
                metadata={"Software": None})
    plt.close(fig)
    svg_path.write_text("\n".join(line.rstrip() for line in svg_path.read_text().splitlines()) + "\n")
    md_path = output_dir / "README.md"
    md_path.write_text(_placement_markdown(values))
    return svg_path, png_path, md_path


def _placement_markdown(values: dict[str, float]) -> str:
    def standard_note(ref: str) -> str:
        series = _E24 if ref.startswith("R") else _E12
        nearest = nearest_standard(values[ref], series)
        if abs(nearest / values[ref] - 1) < 1e-6:
            return ""
        name = "E24" if ref.startswith("R") else "E12"
        return f"not an {name} value; nearest {value_text(ref, nearest)}"

    lines = [
        "# Off-board amplifier breadboard",
        "",
        "Generated by `python3 -m util.breadboard` (`make breadboard`). Do not edit by hand.",
        "",
        "The signal board has no amplifier: J5 brings out the tuned coil and J6 takes the "
        "amplified signal back to the ADC path. This layout builds the two stages from "
        "[`ltspice/AmplificationSim.asc`](../../ltspice/AmplificationSim.asc) on a standard "
        "830-point breadboard. References are the LTspice ones, so this R8 "
        f"({value_text('R8', values['R8'])}) is not the signal board's R8 "
        f"({value_text('R8', kicad.parse_value(design.signal_board().parts['R8'].value))}). "
        "Before drawing, the generator checks every hole against the LTspice "
        "netlist and every lead against the signal-board schematic.",
        "",
        "![Breadboard layout](amplifier-breadboard.png)",
        "",
        "Rows a–e are above the centre channel and f–j below it. Rails: "
        + ", ".join(f"`{rail}` {use}" for rail, use in RAIL_USE.items())
        + ". Check that each rail is continuous from column 10 to column 41; some boards split "
        "their rails at the middle.",
        "",
        "## Op amps",
        "",
        "The design files do not name the op amp. The LTspice model is a generic "
        "UniversalOpAmp2 (Avol 316k, GBW 3 MHz, slew 2.4 V/µs, 2.7 nV/√Hz, 5 V single supply, "
        "outputs within 0.1 V of the rails). The layout assumes two single op amps in the "
        "standard DIP-8 pinout, notch toward column 1: pin 2 −IN, 3 +IN, 4 V−, 6 OUT, 7 V+, and "
        "pins 1, 5, 8 unconnected. Check the chosen part's pinout first.",
        "",
        "Op amp | Pin holes (1–4, then 5–8)",
        "--- | ---",
    ]
    for chip in CHIPS:
        holes = chip_holes(chip)
        lines.append(f"{chip.ref} | " + ", ".join(holes[n] for n in range(1, 9)))
    lines += ["", "## Parts", "", "Ref | Value | Holes | Note", "--- | --- | --- | ---"]
    for part in PARTS:
        lines.append(f"{part.ref} | {value_text(part.ref, values[part.ref])} | "
                     f"{part.holes[0]}, {part.holes[1]} | {standard_note(part.ref)}")
    lines += ["", "## Jumpers", "", "From | To", "--- | ---"]
    lines += [f"{wire.start} | {wire.end}" for wire in WIRES]
    lines += ["", "## Leads", "", "Hole | Connects to", "--- | ---"]
    lines += [f"{lead.hole} | {lead.text}" for lead in LEADS if lead.pin]
    lines += [
        "",
        "The +5 V and +2.5 V leads come from signal-board test points TP4 (5VRail) and TP5 "
        "(the OPA320-buffered 2.5VBias). In the LTspice drawing these are 5P and 25P, and the "
        "same 2.5 V also biases the ADC input, as on the board. V5, the drawing's separate "
        "2.5 V source for R9, is the same rail here. Ground returns through J5 pin 1 and J6 "
        "pin 1. Use twisted pairs for the J5 and J6 leads.",
        "",
        "## Function-generator test",
        "",
        "The drawing suggests starting without the coil, with ±180 µV at the amplifier input. "
        "RT1 (100 kΩ) and RT2 (100 Ω) divide a High-Z generator by about 1001, so set it to "
        "about 180 mV peak. Measure RT1 and RT2 for the exact ratio.",
        "",
        "Ref | Value | Holes",
        "--- | --- | ---",
        *(f"{part.ref} | {value_text(part.ref, values[part.ref])} | {part.holes[0]}, {part.holes[1]}"
          for part in TEST_PARTS),
        "",
        "Generator signal → j4, ground → B-11. The green jumper i10–i13 joins the divider to "
        "the amplifier input. Remove the jumper and the generator before connecting J5 and the "
        "coil; RT1 and RT2 can stay.",
    ]
    return "\n".join(line.rstrip() for line in lines) + "\n"


if __name__ == "__main__":
    for path in build_breadboard():
        print(f"wrote {path}")
