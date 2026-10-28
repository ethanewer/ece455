"""Place the active receiver on a standard 830-point solderless breadboard.

The layout is fixed data, not a placer. `check_layout` rebuilds the board's
connectivity from strips, rails, and jumpers and requires it to match
spice/receiver.cir node for node before anything is drawn.
"""
from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Rectangle

from receiver_design.verify import spice_elements

ROOT = Path(__file__).resolve().parents[1]
SPICE_NETLIST = ROOT / "receiver_design/spice/receiver.cir"
BOM = ROOT / "receiver_design/bom.csv"

# Standard 830-point board: 63 columns of two 5-hole strips (a-e, f-j)
# across a centre channel, plus two rail pairs of 50 holes in groups of 5.
COLUMNS = 63
ROW_Y = {"a": 3, "b": 4, "c": 5, "d": 6, "e": 7,
         "f": 10, "g": 11, "h": 12, "i": 13, "j": 14}
RAIL_Y = {"T+": 0, "T-": 1, "B+": 16, "B-": 17}
RAIL_COLUMNS = frozenset(start + offset for start in range(3, 58, 6)
                         for offset in range(5))
HOLE = re.compile(r"(T\+|T-|B\+|B-|[a-j])(\d+)")


@dataclass(frozen=True)
class Placement:
    """A fitted part. Holes follow the SPICE card's node order (C B E)."""

    ref: str
    kind: str  # resistor, ceramic, electrolytic, npn, pnp
    holes: tuple[str, ...]


@dataclass(frozen=True)
class Wire:
    start: str
    end: str
    color: str
    route: tuple[tuple[float, float], ...] = ()  # bends for off-board loops


@dataclass(frozen=True)
class OffBoard:
    """A wire that leaves the board for J1, the XIAO, or the ADS1256."""

    hole: str
    text: str
    node: str
    label_at: tuple[float, float]


RED, BLACK, ORANGE = "#d62728", "#222222", "#ff7f0e"
GREEN, BLUE, VIOLET, YELLOW = "#2ca02c", "#1f77b4", "#8e44ad", "#e6b800"

PARTS = (
    # Supply filter. VBUS enters on strip 6 (bottom).
    Placement("R11", "resistor", ("j6", "B+6")),
    Placement("C6", "electrolytic", ("B+9", "B-9")),
    # Input clamps: diode-connected 2N3904s.
    Placement("Q6", "npn", ("d9", "d10", "d11")),
    Placement("Q5", "npn", ("b11", "b12", "b13")),
    # Stage 1. Q1 in the top half; Q2 and Q3 below it.
    Placement("C1", "ceramic", ("d12", "d16")),
    Placement("Q1", "npn", ("c15", "c16", "c17")),
    Placement("R4", "resistor", ("T+15", "a15")),
    Placement("R1", "resistor", ("b16", "b19")),
    Placement("C2", "ceramic", ("a19", "a17")),
    Placement("R8", "resistor", ("d17", "d20")),
    Placement("C4", "electrolytic", ("a20", "T-21")),
    Placement("R2", "resistor", ("c19", "c24")),
    Placement("Q2", "pnp", ("g16", "g15", "g14")),
    Placement("R5", "resistor", ("j16", "B-16")),
    Placement("Q3", "npn", ("g17", "g18", "g19")),
    Placement("R6", "resistor", ("j19", "B-19")),
    Placement("R7", "resistor", ("f19", "e17")),
    # Sallen-Key high-pass and the Q7 follower.
    Placement("C8", "ceramic", ("h19", "h21")),
    Placement("R12", "resistor", ("f21", "f23")),
    Placement("C9", "ceramic", ("i21", "i24")),
    Placement("R13", "resistor", ("f24", "e24")),
    Placement("Q7", "npn", ("g25", "g24", "g23")),
    Placement("R14", "resistor", ("j23", "B-23")),
    # Sallen-Key low-pass and the Q8 follower.
    Placement("R15", "resistor", ("h23", "h27")),
    Placement("R16", "resistor", ("f27", "f29")),
    Placement("C10", "ceramic", ("i27", "i30")),
    Placement("C11", "ceramic", ("j29", "B-29")),
    Placement("Q8", "pnp", ("g28", "g29", "g30")),
    Placement("R17", "resistor", ("B+30", "j30")),
    # Stage 2 and the DC loop back to BIAS.
    Placement("Q4", "npn", ("c31", "c30", "c29")),
    Placement("R9", "resistor", ("a29", "T-29")),
    Placement("C5", "electrolytic", ("d29", "d27")),
    Placement("R10", "resistor", ("T+31", "a31")),
    Placement("C7", "ceramic", ("j31", "B-31")),
    Placement("R3", "resistor", ("d31", "d35")),
    Placement("C3", "ceramic", ("a35", "T-35")),
)

WIRES = (
    # Rail ties loop around the right end of the board.
    Wire("T+61", "B+61", RED, ((63.7, 0), (63.7, 16))),
    Wire("T-60", "B-60", BLACK, ((62.9, 1), (62.9, 17))),
    # Clamp grounds and the J1 strip pair.
    Wire("a9", "T-9", BLACK),
    Wire("a10", "T-10", BLACK),
    Wire("a13", "T-13", BLACK),
    Wire("a11", "a12", YELLOW),
    # Stage 1.
    Wire("e15", "f15", GREEN),
    Wire("j14", "B+13", RED),
    Wire("j17", "B+17", RED),
    Wire("h16", "h18", GREEN),
    # Filter and stage 2.
    Wire("j25", "B+25", RED),
    Wire("j28", "B-28", BLACK),
    Wire("f30", "e30", GREEN),
    Wire("a27", "T-27", BLACK),
    Wire("e31", "f31", BLUE),
    Wire("b24", "b35", VIOLET),
)

OFF_BOARD = (
    OffBoard("e12", "J1 signal (sensor)", "receiver_in", (-2.0, 7)),
    OffBoard("T-3", "J1 return (sensor)", "0", (-2.0, 1)),
    OffBoard("f6", "XIAO VBUS (USB 5 V)", "vbus5", (-2.0, 10)),
    OffBoard("g6", "ADS1256 module 5V", "vbus5", (-2.0, 11)),
    OffBoard("B-4", "XIAO GND", "0", (-2.0, 17)),
    OffBoard("B-5", "ADS1256 module GND", "0", (-2.0, 18.4)),
    OffBoard("h31", "ADS1256 AIN0", "out", (38.0, 12)),
    OffBoard("c35", "ADS1256 AIN1 (BIAS)", "bias", (38.0, 5)),
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


def _bom_electrolytics() -> set[str]:
    with BOM.open(newline="") as stream:
        return {ref for row in csv.DictReader(stream)
                if "electrolytic" in row["Package"] for ref in row["Reference"].split()}


def check_layout(spice: str) -> dict[str, str]:
    """Fail unless the board reproduces the SPICE circuit; map each node to its contact."""
    elements = spice_elements(spice)
    placed = {part.ref: part for part in PARTS}
    if set(placed) != set(elements) or len(placed) != len(PARTS):
        raise ValueError(f"board and SPICE parts differ: {sorted(set(placed) ^ set(elements))}")

    occupied: dict[str, str] = {}

    def occupy(hole: str, owner: str) -> None:
        parse_hole(hole)
        if hole in occupied:
            raise ValueError(f"{hole} holds both {occupied[hole]} and {owner}")
        occupied[hole] = owner

    electrolytics = _bom_electrolytics()
    for part in PARTS:
        nodes, model = elements[part.ref]
        if len(part.holes) != len(nodes):
            raise ValueError(f"{part.ref} has {len(part.holes)} leads for {len(nodes)} nodes")
        expected = {"R": {"resistor"}, "C": {"ceramic", "electrolytic"},
                    "Q": {"npn" if model == "Q2N3904" else "pnp"}}[part.ref[0]]
        if part.kind not in expected:
            raise ValueError(f"{part.ref} is drawn as {part.kind}")
        if (part.kind == "electrolytic") != (part.ref in electrolytics):
            raise ValueError(f"{part.ref} polarity disagrees with the BOM")
        if part.kind in ("npn", "pnp"):
            rows = {parse_hole(h)[0] for h in part.holes}
            columns = sorted(parse_hole(h)[1] for h in part.holes)
            if len(rows) != 1 or rows & set(RAIL_Y) or columns != list(
                    range(columns[0], columns[0] + 3)):
                raise ValueError(f"{part.ref} leads are not three adjacent holes in a row")
            if parse_hole(part.holes[1])[1] != columns[1]:
                raise ValueError(f"{part.ref} base is not the middle lead")
        for hole in part.holes:
            occupy(hole, part.ref)
    for wire in WIRES:
        occupy(wire.start, "wire")
        occupy(wire.end, "wire")
    for terminal in OFF_BOARD:
        occupy(terminal.hole, terminal.text)

    # Straight leads, bodies, and jumpers may not pass over a used hole.
    for owner, start, end in [(p.ref, p.holes[0], p.holes[-1]) for p in PARTS
                              if p.kind not in ("npn", "pnp")] + [
            ("wire", w.start, w.end) for w in WIRES if not w.route]:
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

    for wire in WIRES:
        parent[find(contact(wire.start))] = find(contact(wire.end))

    leads = [(contact(hole), node, f"{part.ref}:{hole}")
             for part in PARTS
             for hole, node in zip(part.holes, elements[part.ref][0])]
    leads += [(contact(t.hole), t.node, t.text) for t in OFF_BOARD]
    node_root: dict[str, str] = {}
    root_node: dict[str, str] = {}
    for strip, node, where in leads:
        root = find(strip)
        if node_root.setdefault(node, root) != root:
            raise ValueError(f"SPICE node {node} is split on the board at {where}")
        if root_node.setdefault(root, node) != node:
            raise ValueError(f"{where} shorts {node} to {root_node[root]}")
    for wire in WIRES:
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


def _draw_board(ax) -> None:
    ax.add_patch(FancyBboxPatch((-0.4, -1.4), COLUMNS + 1.8, 20.0,
                                boxstyle="round,pad=0,rounding_size=0.8",
                                fc="#f3efe6", ec="#b8b0a0", lw=1.2, zorder=0))
    ax.add_patch(Rectangle((-0.4, 8.0), COLUMNS + 1.8, 1.0, fc="#e2dccd",
                           ec="none", zorder=0.1))
    for y, color in ((-0.7, RED), (1.7, BLUE), (15.3, RED), (17.7, BLUE)):
        _segment(ax, (2.4, y), (61.6, y), color=color, lw=1.0, zorder=0.2)
    for rail, y in RAIL_Y.items():
        for x in (1.4,):
            ax.text(x, y, "+" if rail.endswith("+") else "−", ha="center",
                    va="center", fontsize=7, color=RED if rail.endswith("+") else BLUE)
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
        # Read along the body, never upside down (the y axis points down).
        angle = -math.degrees(math.atan2(y1 - y0, x1 - x0))
        if angle <= -90:
            angle += 180
        elif angle > 90:
            angle -= 180
        _body_text(ax, (mx, my), part.ref, rotation=angle)
    elif part.kind == "ceramic":
        ax.add_patch(Circle((mx, my), 0.5, fc="#e8a33d", ec="#9a6414", lw=0.6, zorder=5))
        _body_text(ax, (mx, my), part.ref, size=5.0)
    else:
        ax.add_patch(Circle((mx, my), 0.68, fc="#2d4f8e", ec="#16294d", lw=0.6, zorder=5))
        # Pale stripe toward the negative lead; "+" just outside the positive lead.
        ax.add_patch(Circle((mx + ux * 0.45, my + uy * 0.45), 0.17, fc="#c9d6ee",
                            ec="none", zorder=6))
        _body_text(ax, (x0 - ux * 0.5, y0 - uy * 0.5), "+", color=RED, size=7)
        _body_text(ax, (mx, my), part.ref, color="white", size=5.0)


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
    points = [hole_xy(wire.start), *wire.route, hole_xy(wire.end)]
    ax.plot([p[0] for p in points], [p[1] for p in points], color=wire.color,
            lw=2.2, solid_capstyle="round", solid_joinstyle="round", zorder=3)
    for x, y in (points[0], points[-1]):
        ax.add_patch(Circle((x, y), 0.17, fc=wire.color, ec="white", lw=0.4, zorder=3.5))


def _draw_off_board(ax, terminal: OffBoard) -> None:
    x, y = hole_xy(terminal.hole)
    lx, ly = terminal.label_at
    left = lx < x
    ax.plot([x, lx], [y, ly], color="#5a5a5a", lw=1.1, ls=(0, (2, 1.5)), zorder=2.5)
    ax.add_patch(Circle((x, y), 0.17, fc="#5a5a5a", zorder=3.5))
    ax.text(lx, ly, terminal.text, ha="right" if left else "left", va="center",
            fontsize=6.5, color="#174a7e", zorder=8,
            bbox=dict(boxstyle="round,pad=0.25", fc="#eaf1fa", ec="#174a7e", lw=0.6))


def build_receiver_breadboard(output_dir: Path, spice_path: Path = SPICE_NETLIST
                              ) -> tuple[Path, Path, Path]:
    """Check the layout against the SPICE deck, then draw it and list every hole."""
    spice = spice_path.read_text()
    check_layout(spice)
    elements = spice_elements(spice)
    values = {ref: _value_text(ref, model) for ref, (_nodes, model) in elements.items()}
    output_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(22.0, 10.2))
    ax.set_xlim(-14.5, 66.5)
    ax.set_ylim(31.6, -4.6)
    ax.set_aspect("equal")
    ax.axis("off")
    _draw_board(ax)
    for wire in WIRES:
        _draw_wire(ax, wire)
    for terminal in OFF_BOARD:
        _draw_off_board(ax, terminal)
    for part in PARTS:
        if part.kind in ("npn", "pnp"):
            _draw_transistor(ax, part, values[part.ref])
        else:
            _draw_two_terminal(ax, part)

    ax.text(-14.0, -3.6, "Receiver breadboard layout — standard 830-point board",
            fontsize=13, fontweight="bold", ha="left", va="center")
    ax.text(-14.0, -2.5,
            "Top view. Holes, parts, and jumpers match spice/receiver.cir node for node. "
            "Rails: top + and bottom + carry VA ≈ 4.8 V after R11; both − rails are GND.",
            fontsize=7.5, color="#174a7e", ha="left", va="center")
    notes = (
        "Transistor letters give the lead each hole needs (E, B, C). Check every kit 2N3904/2N3906 "
        "pinout before inserting; do not assume E-B-C.",
        "Q5 and Q6 are clamp diodes: their B and C strips are joined (yellow jumper for Q5, "
        "GND jumpers for Q6). Electrolytics C4, C5, C6: the + mark is the positive lead.",
        "Rails are drawn continuous. If your board splits its rails at the middle, bridge each rail "
        "across the split. The red and black loops tie the top and bottom rail pairs.",
        "XIAO RP2350 and ADS1256 module stay off the board. Wire SPI directly between them: "
        "D8→SCLK, D10→DIN, D9←DOUT, D3→CS, D2←DRDY, D4→SYNC/PDWN.",
        "Keep J1 wiring short and away from the AIN0 wire; run the AIN0 and AIN1 wires together "
        "to the module. Solderless contacts add noise; measure the floor on the bench.",
    )
    ax.text(-14.0, 20.0, "Part values", fontsize=8.5, fontweight="bold",
            ha="left", va="center")
    ordered = sorted(values, key=lambda ref: (ref[0] != "R", ref[0], int(ref[1:])))
    per_row = 9
    for index, ref in enumerate(ordered):
        ax.text(-14.0 + 8.9 * (index % per_row), 21.1 + 1.0 * (index // per_row),
                f"{ref}", fontsize=7.2, fontweight="bold", ha="left", va="center")
        ax.text(-11.9 + 8.9 * (index % per_row), 21.1 + 1.0 * (index // per_row),
                values[ref], fontsize=7.2, ha="left", va="center")
    notes_y = 21.1 + 1.0 * (-(-len(ordered) // per_row)) + 0.7
    for index, note in enumerate(notes):
        ax.text(-14.0, notes_y + 1.05 * index, "• " + note, fontsize=7.2, ha="left",
                va="center", color="#333333")

    svg_path = output_dir / "receiver-breadboard.svg"
    png_path = output_dir / "receiver-breadboard.png"
    fig.patch.set_facecolor("white")
    with matplotlib.rc_context({"svg.hashsalt": "receiver-breadboard"}):
        fig.savefig(svg_path, format="svg", facecolor="white", bbox_inches="tight",
                    metadata={"Date": None})
    fig.savefig(png_path, dpi=170, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    svg_path.write_text("\n".join(line.rstrip()
                                  for line in svg_path.read_text().splitlines()) + "\n")
    md_path = output_dir / "receiver-breadboard.md"
    md_path.write_text(_placement_markdown(elements, values))
    return svg_path, png_path, md_path


def _placement_markdown(elements, values) -> str:
    lines = [
        "# Receiver breadboard placement",
        "",
        "Standard 830-point board: columns 1–63, rows a–e above the centre channel and "
        "f–j below it. `T+`/`T-` are the top rails and `B+`/`B-` the bottom rails "
        "(`+` = VA after R11, `-` = GND). `receiver-breadboard.png` draws the same holes.",
        "",
        "## Parts",
        "",
        "Ref | Part | Holes",
        "--- | --- | ---",
    ]
    for part in PARTS:
        if part.kind in ("npn", "pnp"):
            pins = ", ".join(f"{name} {hole}" for name, hole in zip("CBE", part.holes))
        elif part.kind == "electrolytic":
            pins = f"+ {part.holes[0]}, − {part.holes[1]}"
        else:
            pins = f"{part.holes[0]}, {part.holes[1]}"
        lines.append(f"{part.ref} | {values[part.ref]} | {pins}")
    lines += ["", "## Jumpers", "", "From | To", "--- | ---"]
    lines += [f"{wire.start} | {wire.end}" for wire in WIRES]
    lines += ["", "## Off-board wires", "", "Hole | Connection", "--- | ---"]
    lines += [f"{terminal.hole} | {terminal.text}" for terminal in OFF_BOARD]
    lines += [
        "",
        "Wire the SPI directly between the XIAO and the ADS1256 module: D8→SCLK, "
        "D10→DIN, D9←DOUT, D3→CS, D2←DRDY, D4→SYNC/PDWN. Check each transistor's "
        "pinout before inserting it; the holes name its E, B, and C leads.",
    ]
    return "\n".join(lines) + "\n"
