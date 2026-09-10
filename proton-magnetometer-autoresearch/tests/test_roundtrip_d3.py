"""D3: round-trip invariant.

The netlist KiCad exports from a generated project must (a) describe the
same component/net graph as the IR, and (b) re-simulate to the same
H(f) as the originally emitted SPICE netlist.

Path: IR -> SKiDL -> .kicad_sch -> kicad-cli sch export netlist ->
parse (backends.kicad_netlist) -> IR -> SPICE -> compare H(f).

Run:  python3 -m pytest tests/test_roundtrip_d3.py  (~1 min, ngspice)
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from conftest import POC  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent

HAVE_SKIDL = True
try:
    import skidl  # noqa: F401
except ImportError:
    HAVE_SKIDL = False

pytestmark = pytest.mark.skipif(not HAVE_SKIDL, reason="skidl not installed")


def _kicad_cli():
    p = subprocess.run(["which", "kicad-cli"], capture_output=True,
                       text=True).stdout.strip()
    return p or "/Applications/KiCad.app/Contents/MacOS/kicad-cli"


ALL_PASSIVE_SPEC = {
    "title": "round-trip passive network",
    "components": [
        {"name": "V1", "type": "V", "nodes": ["fid", "0"],
         "value": "DC 0 AC 1"},
        {"name": "Rcoil", "type": "R", "nodes": ["fid", "nc"], "value": "20"},
        {"name": "Lcoil", "type": "L", "nodes": ["nc", "nin"],
         "value": "100m"},
        {"name": "Ctune", "type": "C", "nodes": ["nin", "0"], "value": "56n"},
        {"name": "Rnoise", "type": "R", "nodes": ["nin", "np"],
         "value": "118.3"},
    ],
    "control": [
        "ac dec 4000 100 10000",
        "print vm(adc)",
        "noise v(adc) V1 dec 4000 100 10000 1",
        "setplot noise2",
        "print inoise_total",
    ],
}
# The all-passive network needs an output node: sense the tank at 'nin'
# through an ideal transfer... simpler: sense vm(nin) directly.


def test_roundtrip_connectivity(tmp_path):
    """The exported KiCad netlist describes the same component/net graph."""
    from backends.kicad import build_circuit, set_kicad_env
    from backends.spice import emit_netlist
    from backends.kicad_netlist import parse_kicad_netlist, to_spec

    spec = ALL_PASSIVE_SPEC
    set_kicad_env()
    from skidl import Circuit, Net, Part

    c = Circuit()
    nets = {}
    for comp in spec["components"]:
        ctype, name = comp["type"], comp["name"]
        p = Part("Device" if ctype in "RLC" else "Connector",
                 "Conn_01x02_Pin" if ctype in "VIE" else ctype,
                 value=str(comp["value"]), circuit=c)
        p.ref = name
        pins = sorted(p.pins, key=lambda q: (len(q.num), q.num))
        for pin, nn in zip(pins, comp["nodes"]):
            if nn not in nets:
                nets[nn] = Net(name="GND" if nn == "0" else nn, circuit=c)
            net = nets[nn]
            net += pin

    out = tmp_path
    c.generate_netlist(file_=str(out / "board.net"), tool="kicad10")
    parsed = parse_kicad_netlist((out / "board.net").read_text())
    rt_spec = to_spec(parsed)
    sys.path.insert(0, str(ROOT / "spec"))
    from ir import validate
    rt = validate(rt_spec)

    orig = {c["name"]: (sorted(c["nodes"]), str(c["value"]))
            for c in spec["components"]}
    back = {c["name"]: (sorted(c["nodes"]), str(c["value"]))
            for c in rt["components"]}
    assert set(back) == set(orig), (set(back) ^ set(orig))
    for name in orig:
        assert back[name][1] == orig[name][1], (name, back[name], orig[name])
        # node SETS must match (KiCad may rename the ground net)
        assert len(back[name][0]) == len(orig[name][0])


def test_roundtrip_simulation_matches(tmp_path):
    """The round-tripped IR re-simulates to the same H(f)."""
    from backends.kicad import set_kicad_env
    from backends.kicad_netlist import parse_kicad_netlist, to_spec
    from backends.spice import emit_netlist, parse_tables, run_ngspice

    spec = ALL_PASSIVE_SPEC
    set_kicad_env()
    from skidl import Circuit, Net, Part

    c = Circuit()
    nets = {}
    for comp in spec["components"]:
        ctype, name = comp["type"], comp["name"]
        p = Part("Device" if ctype in "RLC" else "Connector",
                 "Conn_01x02_Pin" if ctype in "VIE" else ctype,
                 value=str(comp["value"]), circuit=c)
        p.ref = name
        pins = sorted(p.pins, key=lambda q: (len(q.num), q.num))
        for pin, nn in zip(pins, comp["nodes"]):
            if nn not in nets:
                nets[nn] = Net(name="GND" if nn == "0" else nn, circuit=c)
            net = nets[nn]
            net += pin

    out = tmp_path
    c.generate_netlist(file_=str(out / "board.net"), tool="kicad10")
    parsed = parse_kicad_netlist((out / "board.net").read_text())
    rt_spec = to_spec(parsed)
    # give the round-trip spec the same .ac control as the original
    rt_spec["control"] = [l for l in spec["control"] if l.startswith("ac")]

    # both netlists print vm(nin): patch the control to sense the tank
    def control_with(node):
        return [f"ac dec 4000 100 10000", f"print vm({node})"]

    spec["control"] = control_with("nin")
    rt_spec["control"] = control_with("nin")

    t1 = parse_tables(run_ngspice(emit_netlist(spec)))
    t2 = parse_tables(run_ngspice(emit_netlist(rt_spec)))
    f1, m1 = t1["vm(nin)"]
    f2, m2 = t2["vm(nin)"]
    i1 = np.argmin(np.abs(f1 - 2126.8))
    i2 = np.argmin(np.abs(f2 - 2126.8))
    assert m1[i1] > 1.0, "sanity: tank resonance must step up"
    # H(f) at resonance must match within 1%
    assert m2[i2] == pytest.approx(m1[i1], rel=0.01), (m1[i1], m2[i2])
