"""A1: the frozen circuit IR -- JSON-able component/net graph.

The auto-research loop's source of truth for a circuit is a plain dict
(JSON round-trippable):

    {
      "title": str,
      "components": [ {"name": str, "type": TYPE, "nodes": [str, ...],
                       "value": str | number}, ... ],
      "control": [str, ...],   # ngspice .control lines (simulation leg)
    }

Element types and their node conventions (2-terminal unless noted):

    R  resistor                  nodes: n+ n-     value: "1.7k" (SPICE units)
    L  inductor                  nodes: n+ n-
    C  capacitor                 nodes: n+ n-
    V  independent voltage src   nodes: n+ n-     value: "DC 0 AC 1"
    I  independent current src   nodes: n+ n-     value: "PWL(...)"
    E  VCVS                      nodes: out+ out- value: "nc+ nc- gain"

Node names are arbitrary strings; the ground net is "0". Component names
are unique. Unknown types, malformed nodes, duplicate names, unknown
fields, and unsupported .control statements raise IRError (a ValueError)
with a targeted one-line message -- that is the A1 contract.
"""
import copy
import json
from pathlib import Path

# type -> (node count, value kind)
SCHEMA = {
    "R": (2, "strnum"),
    "L": (2, "strnum"),
    "C": (2, "strnum"),
    "V": (2, "str"),
    "I": (2, "str"),
    "E": (2, "spice_value"),
}

CONTROL_TYPES = {"ac", "noise", "tran", "print", "setplot", "meas", "let"}


class IRError(ValueError):
    """A spec dict violates the circuit IR schema."""


def validate(spec: dict) -> dict:
    """Validate a spec dict; returns a deep copy. Raises IRError."""
    if not isinstance(spec, dict):
        raise IRError("spec must be a dict")
    unknown = set(spec) - {"title", "components", "control", "meta"}
    if unknown:
        raise IRError("unknown top-level fields: %s" % sorted(unknown))

    title = spec.get("title")
    if not isinstance(title, str) or not title.strip():
        raise IRError("spec.title must be a non-empty string")

    comps = spec.get("components")
    if not isinstance(comps, list) or not comps:
        raise IRError("spec.components must be a non-empty list")

    seen = set()
    out_comps = []
    for i, c in enumerate(comps):
        if not isinstance(c, dict):
            raise IRError("component[%d] is not a dict: %r" % (i, c))
        extra = set(c) - {"name", "type", "nodes", "value"}
        if extra:
            raise IRError("component[%d] (%s) has unknown fields: %s"
                          % (i, c.get("name"), sorted(extra)))
        name = c.get("name")
        ctype = c.get("type")
        nodes = c.get("nodes")
        value = c.get("value")
        if not isinstance(name, str) or not name.strip():
            raise IRError("component[%d].name must be a non-empty string" % i)
        if name in seen:
            raise IRError("duplicate component name: %r" % name)
        seen.add(name)
        if ctype not in SCHEMA:
            raise IRError("%s: unknown component type %r (known: %s)"
                          % (name, ctype, sorted(SCHEMA)))
        arity, kind = SCHEMA[ctype]
        if not isinstance(nodes, list) or len(nodes) != arity:
            raise IRError("%s: type %s needs exactly %d node names, got %r"
                          % (name, ctype, arity, nodes))
        for n in nodes:
            if not isinstance(n, str) or not n.strip():
                raise IRError("%s: node names must be non-empty strings, "
                              "got %r" % (name, nodes))
        if kind == "spice_value":
            parts = str(value).split()
            if len(parts) != 3:
                raise IRError("%s: E value must be 'nc+ nc- gain', got %r"
                              % (name, value))
            try:
                float(parts[2])
            except ValueError:
                raise IRError("%s: E gain %r is not numeric"
                              % (name, parts[2]))
        elif not (isinstance(value, (str, int, float)) and str(value)):
            raise IRError("%s: value must be a non-empty string or number"
                          % name)
        out_comps.append(copy.deepcopy(c))

    control = spec.get("control", [])
    if not isinstance(control, list):
        raise IRError("spec.control must be a list of .control lines")
    for j, line in enumerate(control):
        if not isinstance(line, str) or not line.strip():
            raise IRError("control[%d] must be a non-empty string" % j)
        head = line.split()[0].lower().lstrip(".")
        if head not in CONTROL_TYPES:
            raise IRError("control[%d]: unsupported .control statement %r "
                          "(known: %s)" % (j, head, sorted(CONTROL_TYPES)))

    out = dict(title=title, components=out_comps, control=list(control))
    meta = spec.get("meta", {})
    if not isinstance(meta, dict):
        raise IRError("spec.meta must be a dict")
    out["meta"] = copy.deepcopy(meta)
    return out


def to_json(spec: dict, path=None) -> str:
    """Serialize the IR to JSON text (optionally write to a path)."""
    text = json.dumps(validate(spec), indent=1)
    if path is not None:
        Path(path).write_text(text)
    return text


def from_json(text_or_path: str) -> dict:
    """Load a spec from JSON text, or from a path to a .json file."""
    if isinstance(text_or_path, (str, Path)) and \
            str(text_or_path).endswith(".json"):
        text = Path(text_or_path).read_text()
    else:
        text = text_or_path
    return validate(json.loads(text))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "poc"))
    import circuit_spec as cs
    ok = validate(cs.afe_spec("smoke", e_amp=7e-9, i_amp=170e-15,
                              coil=dict(r_coil=120, l_coil="2m",
                                        n_turns=530, radius_m=0.015,
                                        b_pol=0.02)))
    print("validated", len(ok["components"]), "components")
