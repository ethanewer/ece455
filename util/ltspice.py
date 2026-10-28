"""Read an LTspice schematic (.asc) and translate it into an ngspice deck.

Connectivity comes from the drawing: wire ends, symbol pins, and net flags
join where they coincide or where one lies on a wire. Pin offsets are listed
for the symbols the amplifier uses. An unknown symbol raises an error rather
than being guessed. LTspice's UniversalOpAmp2 is replaced by an ngspice
subcircuit with the same structure (see OPAMP_SUBCIRCUIT).
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# Pin offsets at orientation R0, in SpiceOrder, from LTspice's symbol files.
SYMBOL_PINS = {
    "res": ((16, 16), (16, 96)),
    "cap": ((16, 0), (16, 64)),
    "ind": ((16, 16), (16, 96)),
    "voltage": ((0, 16), (0, 96)),
    # In+, In-, V+, V-, OUT
    "OpAmps/UniversalOpAmp2": ((-32, 16), (-32, -16), (0, -32), (0, 32), (32, 0)),
}
OPAMP_PINS = ("in+", "in-", "v+", "v-", "out")
OPAMP_PARAMETERS = ("avol", "gbw", "slew", "ilimit", "rail", "vos",
                    "en", "enk", "in", "ink", "rin")


@dataclass(frozen=True)
class Element:
    name: str
    symbol: str
    nodes: tuple[str, ...]
    value: str
    attributes: dict[str, str] = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class Schematic:
    elements: dict[str, Element]
    directives: tuple[str, ...]
    comments: tuple[str, ...]
    # Every net flag name -> the node name used for its net. A net with
    # several flags is named by ground ("0") or by its first flag in sort
    # order; names that ngspice would read as numbers get an "n" prefix.
    flags: dict[str, str] = field(default_factory=dict, compare=False)

    def node(self, element: str, pin: int) -> str:
        """Net at pin (1-based SpiceOrder) of an element."""
        return self.elements[element].nodes[pin - 1]

    @property
    def params(self) -> dict[str, str]:
        found = {}
        for directive in self.directives:
            if directive.lower().startswith(".param"):
                for name, value in re.findall(r"(\w+)\s*=\s*(\S+)", directive[6:]):
                    found[name] = value
        return found

    @property
    def steps(self) -> dict[str, tuple[float, ...]]:
        """`.step param NAME list ...` sweeps."""
        found = {}
        for directive in self.directives:
            match = re.match(r"\.step\s+param\s+(\w+)\s+list\s+(.+)", directive, re.I)
            if match:
                found[match.group(1)] = tuple(spice_number(v) for v in match.group(2).split())
        return found

    @property
    def unconnected(self) -> frozenset[str]:
        """Elements none of whose pins reach another element."""
        uses: dict[str, int] = defaultdict(int)
        for element in self.elements.values():
            for node in set(element.nodes):
                uses[node] += 1
        return frozenset(element.name for element in self.elements.values()
                         if all(uses[node] == 1 and node != "0" for node in element.nodes))

    def directive(self, command: str) -> str | None:
        """The first directive starting with command, such as .tran."""
        for directive in self.directives:
            if directive.lower().split()[0] == command.lower():
                return directive
        return None


_SCALE = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3,
          "k": 1e3, "meg": 1e6, "g": 1e9, "t": 1e12}


def spice_number(text: str) -> float:
    """A SPICE number with an optional scale factor and unit, such as 4.6nF or 10Meg."""
    match = re.fullmatch(r"([-+]?[0-9]*\.?[0-9]+(?:e[-+]?\d+)?)(meg|[fpnumkgt])?[a-z]*",
                         text.strip().replace("µ", "u").lower())
    if match is None:
        raise ValueError(f"not a SPICE number: {text!r}")
    return float(match.group(1)) * _SCALE.get(match.group(2) or "", 1.0)


def _orient(x: int, y: int, orientation: str) -> tuple[int, int]:
    """LTspice symbol orientation: optional mirror (M) about the symbol's y axis, then rotation."""
    if orientation.startswith("M"):
        x = -x
    turns = int(orientation[1:]) // 90 % 4
    for _ in range(turns):
        x, y = -y, x
    return x, y


def _on_segment(point, start, end) -> bool:
    (px, py), (ax, ay), (bx, by) = point, start, end
    if (bx - ax) * (py - ay) != (by - ay) * (px - ax):
        return False
    return min(ax, bx) <= px <= max(ax, bx) and min(ay, by) <= py <= max(ay, by)


def _decode(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def read_asc(path: Path | str) -> Schematic:
    symbols: list[dict] = []
    wires: list[tuple[tuple[int, int], tuple[int, int]]] = []
    flags: list[tuple[tuple[int, int], str]] = []
    directives: list[str] = []
    comments: list[str] = []
    for line in _decode(Path(path).read_bytes()).splitlines():
        words = line.split()
        if not words:
            continue
        head = words[0]
        if head == "WIRE":
            x0, y0, x1, y1 = (int(v) for v in words[1:5])
            wires.append(((x0, y0), (x1, y1)))
        elif head == "FLAG":
            flags.append(((int(words[1]), int(words[2])), words[3]))
        elif head == "SYMBOL":
            name = re.sub(r"\\+", "/", words[1])
            symbols.append(dict(symbol=name, at=(int(words[2]), int(words[3])),
                                orientation=words[4], attributes={}))
        elif head == "SYMATTR" and symbols:
            key, _, value = line.split(None, 1)[1].partition(" ")
            symbols[-1]["attributes"][key] = value.strip()
        elif head == "TEXT":
            text = line.split(None, 5)[5]
            target = directives if text.startswith("!") else comments
            target += [part.strip() for part in text[1:].split("\\n") if part.strip()]
        elif head == "IOPIN":
            raise ValueError("hierarchical LTspice schematics are not supported")

    parent: dict = {}

    def find(item):
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    points: dict[tuple[int, int], list] = defaultdict(list)
    for index, (start, end) in enumerate(wires):
        points[start].append(("wire", index))
        points[end].append(("wire", index))
    for index, (point, _name) in enumerate(flags):
        points[point].append(("flag", index))
    for index, symbol in enumerate(symbols):
        if symbol["symbol"] not in SYMBOL_PINS:
            raise ValueError(f"no pin offsets for LTspice symbol {symbol['symbol']!r}")
        x0, y0 = symbol["at"]
        for pin, (dx, dy) in enumerate(SYMBOL_PINS[symbol["symbol"]]):
            dx, dy = _orient(dx, dy, symbol["orientation"])
            points[(x0 + dx, y0 + dy)].append(("pin", index, pin))
    for items in points.values():
        for item in items[1:]:
            parent[find(item)] = find(items[0])
    for index, (start, end) in enumerate(wires):
        for point, items in points.items():
            if point in (start, end) or not _on_segment(point, start, end):
                continue
            for item in items:
                if item[0] != "wire" or point in wires[item[1]]:
                    parent[find(item)] = find(("wire", index))

    flag_names: dict = defaultdict(set)
    for index, (_point, name) in enumerate(flags):
        flag_names[find(("flag", index))].add(name)
    # Flags with the same name are one net.
    by_name: dict[str, tuple] = {}
    for root, names in list(flag_names.items()):
        for name in names:
            if name in by_name:
                parent[find(root)] = find(by_name[name])
            else:
                by_name[name] = root
    net_names: dict = defaultdict(set)
    for index, _ in enumerate(flags):
        net_names[find(("flag", index))].add(flags[index][1])

    elements: dict[str, Element] = {}
    pin_roots = {}
    for index, symbol in enumerate(symbols):
        name = symbol["attributes"].get("InstName")
        if not name or name in elements:
            raise ValueError(f"LTspice symbol at {symbol['at']} has a missing or repeated InstName")
        pin_roots[name] = [find(("pin", index, pin))
                           for pin in range(len(SYMBOL_PINS[symbol["symbol"]]))]
    # Unnamed nets take the name of their first element pin, e.g. c4_2.
    unnamed = {}
    for name in sorted(pin_roots):
        for pin, root in enumerate(pin_roots[name]):
            unnamed.setdefault(root, f"{name.lower()}_{pin + 1}")
    for symbol in symbols:
        attributes = symbol["attributes"]
        name = attributes["InstName"]
        nodes = [_net_name(net_names[root]) if root in net_names else unnamed[root]
                 for root in pin_roots[name]]
        elements[name] = Element(name, symbol["symbol"], tuple(nodes),
                                 attributes.get("Value", "").replace("µ", "u"), dict(attributes))
    flag_nodes = {name: _net_name(names) for names in net_names.values() for name in names}
    return Schematic(elements, tuple(directives), tuple(comments), flag_nodes)


def _net_name(flags: set[str]) -> str:
    """Node name for a flagged net, usable in ngspice expressions (25P becomes n25P)."""
    if "0" in flags:
        return "0"
    name = re.sub(r"\W", "_", min(flags))
    return name if re.match(r"[A-Za-z_]", name) else "n" + name


def _parameters(element: Element) -> dict[str, str]:
    text = " ".join(element.attributes.get(key, "") for key in ("Value2", "SpiceLine", "SpiceLine2"))
    return {key.lower(): value for key, value in re.findall(r"(\w+)\s*=\s*(\S+)", text)}


OPAMP_SUBCIRCUIT = """\
* ngspice equivalent of LTspice's UniversalOpAmp2 (SpiceModel level2): a
* transconductance stage into one internal node with Rout and Cout, the
* slew-rate limit as a limit on that stage's output current, and an output
* that stays Rail volts inside each supply. Ilimit is accepted but the
* output current limit is not modeled. En and In are white noise densities;
* Enk and Ink are their 1/f corner frequencies. Controlled sources are
* noiseless; each noise resistor drives only a controlling input.
.subckt universalopamp2 inp inn vp vn out params: avol=1Meg gbw=10Meg slew=10Meg
+ ilimit=25m rail=0 vos=0 en=0 enk=0 in=0 ink=0 rin=500Meg
.param rout=100Meg
.param cout={avol/gbw/(2*3.141592653589793)/rout}
.param gm={avol/rout}
.param imax={slew*cout}
.param fourkt={4*1.380649e-23*300.15}
.param rv={max(en*en/fourkt, 1e-6)}
.param gi={in/sqrt(fourkt*1k)}
* Input resistance Rin from each input to mid-supply.
Grin1 vp inp vp inp {0.5/rin}
Grin2 inp vn inp vn {0.5/rin}
Grin3 vp inn vp inn {0.5/rin}
Grin4 inn vn inn vn {0.5/rin}
* Input voltage noise: thermal noise of rv, plus 1/f noise from 1 mA in it.
Iv 0 nv DC 1m
Rv nv 0 rflickv r={rv}
.model rflickv R(kf={en*en*enk/(rv*rv*1e-6)} af=2)
* Input current noise on each input from 1 kohm noise resistors.
Ii1 0 ni1 DC 1m
Ri1 ni1 0 rflicki r=1k
Ii2 0 ni2 DC 1m
Ri2 ni2 0 rflicki r=1k
.model rflicki R(kf={in*in*ink/max(gi*gi, 1e-60)} af=2)
Bi1 inp 0 I={gi}*(V(ni1)-1)
Bi2 inn 0 I={gi}*(V(ni2)-1)
* Transconductance stage with the slew-rate current limit.
Bgm 0 x I=min(max({gm}*(V(inp)-V(inn)+V(nv)-{rv*1m}+{vos}), -{imax}), {imax})
Grout1 vp x vp x {0.5/rout}
Grout2 x vn x vn {0.5/rout}
Cx x 0 {cout}
Bclamp1 x 0 I=V(x) > V(vp) ? pwr({2*slew*cout}*(V(x)-V(vp)), 2) : 0
Bclamp2 0 x I=V(x) < V(vn) ? pwr({2*slew*cout}*(V(vn)-V(x)), 2) : 0
* Output follows x through 10 ohms, Rail volts inside each supply.
Bout o 0 V=min(max(V(x), V(vn)+{rail}), V(vp)-{rail})
Gout o out o out 0.1
.ends universalopamp2
"""


def _source(element: Element, ac: bool) -> str:
    value = element.value.strip()
    match = re.fullmatch(r"(SINE|SIN)\s*\((.*)\)", value, re.I)
    if match:
        args = match.group(2).replace(",", " ").split()
        if len(args) > 6:
            raise ValueError(f"{element.name}: SINE Ncycles is not supported in ngspice")
        text = f"DC {args[0]} SIN({' '.join(args)})"
    elif re.fullmatch(r"(PULSE|PWL)\s*\(.*\)", value, re.I):
        text = value
    else:
        spice_number(value)
        text = f"DC {value}"
    return text + (" AC 1" if ac else "")


def ngspice_deck(schematic: Schematic, *, title: str, params: dict[str, float] | None = None,
                 ac_source: str | None = None) -> str:
    """ngspice deck without analysis cards. params override or add .param values."""
    merged = dict(schematic.params)
    merged.update({name: f"{value:.12g}" for name, value in (params or {}).items()})
    lines = [f"* {title}"]
    lines += [f".param {name}={value}" for name, value in merged.items()]
    uses_opamp = False
    for element in sorted(schematic.elements.values(), key=lambda e: e.name):
        if element.name in schematic.unconnected:
            lines.append(f"* {element.name} ({element.value}) is not connected in the schematic.")
            continue
        nodes = " ".join(element.nodes)
        extra = _parameters(element)
        series = extra.pop("rser", None)
        kind = element.symbol
        if kind in ("res", "cap", "ind"):
            if series is not None and kind != "res":
                lines.append(f"{element.name} {element.nodes[0]} {element.name}_rser {element.value}")
                lines.append(f"R{element.name}_rser {element.name}_rser {element.nodes[1]} {series}")
            else:
                lines.append(f"{element.name} {nodes} {element.value}")
        elif kind == "voltage":
            if series is not None:
                raise ValueError(f"{element.name}: source Rser is not supported")
            lines.append(f"{element.name} {nodes} {_source(element, element.name == ac_source)}")
        elif kind == "OpAmps/UniversalOpAmp2":
            unknown = set(extra) - set(OPAMP_PARAMETERS)
            if unknown:
                raise ValueError(f"{element.name}: unsupported op-amp parameters {sorted(unknown)}")
            values = " ".join(f"{key}={extra[key]}" for key in OPAMP_PARAMETERS if key in extra)
            lines.append(f"X{element.name} {nodes} universalopamp2 {values}")
            uses_opamp = True
        else:
            raise ValueError(f"{element.name}: no ngspice translation for {kind}")
    if ac_source is not None and ac_source not in schematic.elements:
        raise ValueError(f"AC source {ac_source} is not in the schematic")
    if uses_opamp:
        lines.append(OPAMP_SUBCIRCUIT.rstrip())
    lines.append(".end")
    return "\n".join(lines) + "\n"
