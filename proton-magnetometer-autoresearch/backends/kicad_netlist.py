"""D3: KiCad netlist <-> circuit IR round-trip.

`kicad-cli sch export netlist` emits a s-expression netlist. This module
parses it and rebuilds a circuit IR (spec dict) from it, so the
round-trip invariant can be tested: the netlist KiCad exports from a
generated project must describe the SAME component/net graph, and the
SPICE netlist re-emitted from the round-tripped IR must simulate to the
same H(f) as the original.

Component mapping (backends/kicad.py's projection): every IR component
maps to a 2-pin KiCad symbol (R/L/C Device symbols; V/I/E as connectors)
whose Value field carries the SPICE value string -- including the E
blocks' "nc+ nc- gain" form. The converter therefore reconstructs the IR
component list exactly: type = ref prefix, value = Value field, nodes =
the net names of pins 1..k in numeric order.
"""
from __future__ import annotations

import re
from pathlib import Path


def _tokens(text: str):
    """S-expression tokenizer (enough for KiCad netlists)."""
    return re.findall(r'\(|\)|"(?:[^"]*)"|[^\s()]+', text)


def parse_kicad_netlist(text: str) -> dict:
    """Parse a KiCad s-expression netlist into {refs: {ref: value},
    nets: {net_name: [(ref, pin), ...]}}."""
    toks = _tokens(text)
    pos = 0

    def parse_expr() -> list:
        nonlocal pos
        assert toks[pos] == "("
        pos += 1
        out = []
        while toks[pos] != ")":
            if toks[pos] == "(":
                out.append(parse_expr())
            else:
                t = toks[pos]
                out.append(t[1:-1] if t.startswith('"') else t)
                pos += 1
        pos += 1
        return out

    tree = parse_expr()

    comps = {}
    nets = {}
    walk = None

    def find_all(node, key):
        found = []
        for item in (node if isinstance(node, list) else []):
            if isinstance(item, list) and item and item[0] == key:
                found.append(item)
            if isinstance(item, list):
                found.extend(find_all(item, key))
        return found

    def fields(node):
        d = {}
        for item in node[1:]:
            if isinstance(item, list) and item:
                d[item[0]] = item[1] if len(item) > 1 else None
        return d

    for comp in find_all(tree, "comp"):
        f = fields(comp)
        ref = f.get("ref")
        val = f.get("value")
        if ref:
            comps[ref] = val or ""
    for net in find_all(tree, "net"):
        f = fields(net)
        name = f.get("name") or f.get("code")
        nodes = []
        for node in find_all(net, "node"):
            nf = fields(node)
            nodes.append((nf.get("ref"), nf.get("pin")))
        if name:
            nets[name] = nodes
    return {"components": comps, "nets": nets}


def to_spec(parsed: dict) -> dict:
    """Rebuild a circuit IR (spec dict) from a parsed KiCad netlist."""
    # pin -> net lookup
    pin_net = {}
    for net_name, nodes in parsed["nets"].items():
        for ref, pin in nodes:
            pin_net[(ref, str(pin))] = net_name

    comps = []
    for ref in sorted(parsed["components"]):
        value = parsed["components"][ref]
        ctype = ref[0]
        # collect this ref's pins in numeric order
        pins = sorted({p for (r, p) in pin_net if r == ref},
                      key=lambda s: (len(s), s))
        nodes = [pin_net[(ref, p)] for p in pins]
        comps.append({"name": ref, "type": ctype, "nodes": nodes,
                      "value": value})
    # KiCad renames the ground net (e.g. "GND"); map it back to "0".
    for c in comps:
        c["nodes"] = ["0" if n.upper() in ("GND",) else n for n in c["nodes"]]
    return {"title": "round-trip", "components": comps, "control": []}
