"""Read KiCad schematics, boards, and BOM exports without kicad-cli.

The parser recovers parts and pin-level connectivity directly from the
s-expression files so tests can compare a schematic with its board and with
the other design files. It reads connectivity only. It is not ERC or DRC.
"""
from __future__ import annotations

import csv
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))')
_ESCAPE = re.compile(r"\\(.)")


def parse_sexpr(text: str) -> list:
    """Parse one KiCad s-expression into nested lists of strings."""
    stack: list[list] = [[]]
    position, end = 0, len(text.rstrip())
    while position < end:
        match = _TOKEN.match(text, position)
        if match is None:
            raise ValueError(f"unreadable s-expression near {text[position:position + 40]!r}")
        position = match.end()
        if match.group(1):
            stack.append([])
        elif match.group(2):
            item = stack.pop()
            stack[-1].append(item)
        elif match.group(3) is not None:
            stack[-1].append(_ESCAPE.sub(lambda m: {"n": "\n"}.get(m.group(1), m.group(1)),
                                         match.group(3)))
        else:
            stack[-1].append(match.group(4))
    if len(stack) != 1 or len(stack[0]) != 1:
        raise ValueError("unbalanced s-expression")
    return stack[0][0]


def _children(node: list, name: str) -> list[list]:
    return [child for child in node[1:] if isinstance(child, list) and child and child[0] == name]


def _child(node: list, name: str) -> list | None:
    found = _children(node, name)
    return found[0] if found else None


def _properties(node: list) -> dict[str, str]:
    return {prop[1]: prop[2] for prop in _children(node, "property")}


def _flag(node: list, name: str) -> bool:
    child = _child(node, name)
    return child is not None and (len(child) == 1 or child[1] == "yes")


@dataclass(frozen=True)
class Part:
    ref: str
    lib_id: str
    value: str
    footprint: str
    description: str
    sheet: str
    in_bom: bool
    dnp: bool


@dataclass(frozen=True)
class Netlist:
    """Parts and nets. Each net maps to the (reference, pin number) pairs on it."""

    parts: dict[str, Part]
    nets: dict[str, frozenset[tuple[str, str]]]
    pin_names: dict[tuple[str, str], str]

    def net_of(self, ref: str, pin: str) -> str:
        for name, members in self.nets.items():
            if (ref, pin) in members:
                return name
        raise KeyError(f"{ref} pin {pin} is not in the netlist")

    def connections(self) -> set[frozenset[tuple[str, str]]]:
        """Nets with two or more pins, as unnamed pin sets."""
        return {members for members in self.nets.values() if len(members) > 1}

    def pin_by_name(self, ref: str, name: str) -> str:
        numbers = [pin for (part, pin), pin_name in self.pin_names.items()
                   if part == ref and pin_name == name]
        if len(numbers) != 1:
            raise KeyError(f"{ref} has {len(numbers)} pins named {name!r}")
        return numbers[0]


def _key(x, y) -> tuple[int, int]:
    """Exact grid key: KiCad stores coordinates in mm with 1e-4 mm resolution."""
    return round(float(x) * 1e4), round(float(y) * 1e4)


def _place(px: float, py: float, at: list, mirror: str | None) -> tuple[float, float]:
    """Library pin position to sheet position. Library Y points up; sheet Y points down."""
    x, y = px, -py
    angle = math.radians(float(at[3]) if len(at) > 3 else 0.0)
    c, s = round(math.cos(angle)), round(math.sin(angle))
    x, y = x * c + y * s, -x * s + y * c
    if mirror == "x":
        y = -y
    elif mirror == "y":
        x = -x
    return float(at[1]) + x, float(at[2]) + y


def _library_pins(symbol: list) -> list[dict]:
    pins = []
    for unit in _children(symbol, "symbol"):
        unit_number, style = (int(v) for v in unit[1].rsplit("_", 2)[1:])
        for pin in _children(unit, "pin"):
            at = _child(pin, "at")
            pins.append(dict(unit=unit_number, style=style, number=_child(pin, "number")[1],
                             name=_child(pin, "name")[1], x=float(at[1]), y=float(at[2])))
    return pins


def _on_segment(point, start, end) -> bool:
    (px, py), (ax, ay), (bx, by) = point, start, end
    if (bx - ax) * (py - ay) != (by - ay) * (px - ax):
        return False
    return min(ax, bx) <= px <= max(ax, bx) and min(ay, by) <= py <= max(ay, by)


def _sheets(path: Path, sheet_path: str = "/") -> list[tuple[str, list]]:
    root = parse_sexpr(path.read_text(encoding="utf-8"))
    found = [(sheet_path, root)]
    for sheet in _children(root, "sheet"):
        props = _properties(sheet)
        child = path.parent / props["Sheetfile"]
        found += _sheets(child, f"{sheet_path}{props['Sheetname']}/")
    return found


def read_schematic(path: Path | str) -> Netlist:
    """Connectivity of a (hierarchical) schematic from its root sheet.

    Wire ends, pins, labels, and junctions connect where they coincide or
    where one lies on a wire. Local labels join within a sheet, global
    labels and power symbols across sheets, and hierarchical labels to the
    matching sheet pin in the parent.
    """
    parent: dict = {}

    def find(item):
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(a, b) -> None:
        parent[find(a)] = find(b)

    parts: dict[str, Part] = {}
    pins: dict[tuple, tuple[str, str, str]] = {}
    names: dict[tuple, list[tuple[int, str, str]]] = defaultdict(list)
    sheet_pins: dict[str, list[tuple[tuple, str]]] = defaultdict(list)

    for sheet_path, root in _sheets(Path(path)):
        libraries = {s[1]: s for s in _children(_child(root, "lib_symbols"), "symbol")}
        points: dict[tuple[int, int], list[tuple]] = defaultdict(list)
        wires = []
        for index, wire in enumerate(_children(root, "wire")):
            (_, x0, y0), (_, x1, y1) = _children(_child(wire, "pts"), "xy")[:2]
            item = ("wire", sheet_path, index)
            wires.append((_key(x0, y0), _key(x1, y1), item))
            points[_key(x0, y0)].append(item)
            points[_key(x1, y1)].append(item)
        for junction in _children(root, "junction"):
            at = _child(junction, "at")
            points[_key(at[1], at[2])].append(("junction", sheet_path, _key(at[1], at[2])))
        for kind, priority in (("global_label", 0), ("hierarchical_label", 1), ("label", 2)):
            for index, label in enumerate(_children(root, kind)):
                at = _child(label, "at")
                item = (kind, sheet_path, index)
                points[_key(at[1], at[2])].append(item)
                text = label[1]
                if kind == "global_label":
                    names[item].append((priority, text, "global:" + text))
                elif kind == "label":
                    names[item].append((priority, sheet_path + text, sheet_path + "label:" + text))
                else:
                    names[item].append((priority, sheet_path + text, sheet_path + "hier:" + text))
        for sheet in _children(root, "sheet"):
            props = _properties(sheet)
            child_path = f"{sheet_path}{props['Sheetname']}/"
            for index, pin in enumerate(_children(sheet, "pin")):
                at = _child(pin, "at")
                item = ("sheet_pin", sheet_path, child_path, index)
                points[_key(at[1], at[2])].append(item)
                sheet_pins[child_path].append((item, pin[1]))
        for symbol in _children(root, "symbol"):
            lib_id = _child(symbol, "lib_id")[1]
            props = _properties(symbol)
            library = libraries[lib_id]
            at = _child(symbol, "at")
            mirror = _child(symbol, "mirror")
            unit = int(_child(symbol, "unit")[1]) if _child(symbol, "unit") else 1
            ref = props["Reference"]
            power = _child(library, "power") is not None
            if not power:
                if ref in parts and parts[ref].lib_id != lib_id:
                    raise ValueError(f"reference {ref} is used by two different symbols")
                parts[ref] = Part(ref, lib_id, props.get("Value", ""), props.get("Footprint", ""),
                                  props.get("Description", ""), sheet_path,
                                  _flag(symbol, "in_bom"), _flag(symbol, "dnp"))
            for pin in _library_pins(library):
                if pin["unit"] not in (0, unit) or pin["style"] not in (0, 1):
                    continue
                key = _key(*_place(pin["x"], pin["y"], at, mirror[1] if mirror else None))
                item = ("pin", sheet_path, ref, pin["number"])
                points[key].append(item)
                if power:
                    value = props["Value"]
                    names[item].append((0, value, "global:" + value))
                else:
                    pins[item] = (ref, pin["number"], pin["name"])
        for items in points.values():
            for item in items[1:]:
                union(items[0], item)
        for start, end, wire in wires:
            for key, items in points.items():
                if key in (start, end) or not _on_segment(key, start, end):
                    continue
                for item in items:
                    # Two wires only join where one ends on the other.
                    if item[0] != "wire" or key in wires[item[2]][:2]:
                        union(wire, item)

    # Hierarchical labels join the sheet pin of the same name in the parent.
    for child_path, entries in sheet_pins.items():
        for item, pin_name in entries:
            for label, label_names in names.items():
                if label[0] == "hierarchical_label" and label[1] == child_path and any(
                        scope == child_path + "hier:" + pin_name for _, _, scope in label_names):
                    union(item, label)
    first_in_scope: dict[str, tuple] = {}
    for item, item_names in names.items():
        for _, _, scope in item_names:
            if scope in first_in_scope:
                union(item, first_in_scope[scope])
            else:
                first_in_scope[scope] = item

    groups: dict[tuple, list[tuple]] = defaultdict(list)
    for item in set(parent) | set(pins):
        groups[find(item)].append(item)
    nets: dict[str, frozenset[tuple[str, str]]] = {}
    for items in groups.values():
        members = frozenset(pins[item][:2] for item in items if item in pins)
        if not members:
            continue
        labels = sorted({(priority, text) for item in items for priority, text, _ in names.get(item, ())})
        if labels:
            name = labels[0][1]
        else:
            ref, number = min(members)
            name = f"Net-({ref}-Pad{number})"
        if name in nets:
            raise ValueError(f"two nets are both named {name}")
        nets[name] = members
    pin_names = {(ref, number): pin_name for ref, number, pin_name in pins.values()}
    return Netlist(parts, nets, pin_names)


def read_board(path: Path | str) -> Netlist:
    """Footprints and pad nets from a .kicad_pcb file."""
    root = parse_sexpr(Path(path).read_text(encoding="utf-8"))
    parts: dict[str, Part] = {}
    nets: dict[str, set[tuple[str, str]]] = defaultdict(set)
    pin_names: dict[tuple[str, str], str] = {}
    for footprint in _children(root, "footprint"):
        props = _properties(footprint)
        ref = props.get("Reference", "")
        parts[ref] = Part(ref, "", props.get("Value", ""), footprint[1],
                          props.get("Description", ""), "/", True, False)
        for pad in _children(footprint, "pad"):
            net = _child(pad, "net")
            if net is None or not ref:
                continue
            name = net[-1]
            pin_function = _child(pad, "pinfunction")
            nets[name].add((ref, pad[1]))
            if pin_function is not None:
                pin_names[(ref, pad[1])] = pin_function[1]
    return Netlist(parts, {name: frozenset(members) for name, members in nets.items()}, pin_names)


def read_bom_csv(path: Path | str) -> dict[str, dict[str, str]]:
    """Reference -> row of a KiCad grouped BOM export (Reference, Qty, Value, ...)."""
    rows: dict[str, dict[str, str]] = {}
    with Path(path).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            refs = [ref.strip() for ref in row["Reference"].split(",")]
            if int(row["Qty"]) != len(refs):
                raise ValueError(f"BOM quantity does not match references: {row['Reference']}")
            for ref in refs:
                if ref in rows:
                    raise ValueError(f"BOM lists {ref} twice")
                rows[ref] = row
    return rows


_SI = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6}


def parse_value(text: str) -> float:
    """Component value text such as 4.7nF, 2.2u, 24.9k, 220, or 1K Potentiometer."""
    match = re.match(r"\s*([0-9]*\.?[0-9]+)\s*(Meg|[pnuµmkKM])?", text)
    if match is None:
        raise ValueError(f"no numeric value in {text!r}")
    scale = 1e6 if match.group(2) == "Meg" else _SI.get(match.group(2) or "", 1.0)
    return float(match.group(1)) * scale
