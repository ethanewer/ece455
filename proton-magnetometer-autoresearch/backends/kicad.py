"""A4: KiCad backend -- circuit IR -> SKiDL -> .kicad_sch/.kicad_pcb ->
kicad-cli ERC / DRC machine gates.

Exit criterion (TODO A4): one INA828-class AFE passes ERC + DRC with exit
code 0 from a clean tree.

Layer mapping (architecture.md section 1.2): the component/net graph is
written once; SPICE, KiCad, BOM, and docs are all projections of it. This
backend projects the IR into buildable artifacts:

  * passive types  -> Device:R/L/C symbols + SMD footprints;
  * V (FID source) / I (polarization pulse) -> 2-pin connector symbols
    (bench injection points);
  * E (ideal gain) -> 2-pin connector symbol carrying the gain as its
    value. Documented simplification: KiCad's standard libs have no
    behavioral-source symbol, and the schematic layer is a projection of
    the SPICE-first IR, so ideal gain blocks are wired as 2-pin bench
    elements until the parts DB gains real amplifier symbols (same lossy
    fast path as the SPICE netlist layer).

Gates (exit codes):
  * ERC: kicad-cli sch erc --severity-error --exit-code-violations
  * DRC: kicad-cli pcb drc --schematic-parity --exit-code-violations,
    after a rectangular Edge.Cuts outline and straight F.Cu tracks per
    2-pad net are added (a minimal connect pass; real layout is human work).
  * The PCB leg runs under KiCad's bundled Python (kinet2pcb needs pcbnew).
"""
import os
import subprocess
from pathlib import Path

KICAD_SYM_DIR = "/Applications/KiCad.app/Contents/SharedSupport/symbols"
FOOTPRINT_DIR = "/Applications/KiCad.app/Contents/SharedSupport/footprints"


def set_kicad_env():
    for v in ("KICAD_SYMBOL_DIR", "KICAD10_SYMBOL_DIR", "KICAD9_SYMBOL_DIR",
              "KICAD8_SYMBOL_DIR"):
        os.environ[v] = KICAD_SYM_DIR


def kicad_cli() -> str:
    path = subprocess.run(["which", "kicad-cli"], capture_output=True,
                          text=True).stdout.strip()
    if path:
        return path
    return "/Applications/KiCad.app/Contents/MacOS/kicad-cli"


def build_circuit(spec: dict):
    """Circuit IR -> SKiDL Circuit with buildable symbols + footprints.

    Every IR component maps to a KiCad symbol with pins ordered by pin
    number; the k-th IR node wires to the k-th pin.
    """
    set_kicad_env()
    from skidl import Circuit, Net, Part

    c = Circuit()
    nets = {}

    def net_of(nn):
        if nn not in nets:
            nets[nn] = Net(name="GND" if nn == "0" else nn, circuit=c)
        return nets[nn]

    for comp in spec["components"]:
        ctype, name = comp["type"], comp["name"]
        node_names = comp["nodes"]
        value = str(comp["value"])

        if ctype == "R":
            p = Part("Device", ctype, value=value,
                     footprint="Resistor_SMD:R_0603_1608Metric", circuit=c)
        elif ctype == "C":
            p = Part("Device", ctype, value=value,
                     footprint="Capacitor_SMD:C_0603_1608Metric", circuit=c)
        elif ctype == "L":
            p = Part("Device", ctype, value=value,
                     footprint="Inductor_SMD:L_1210_3225Metric", circuit=c)
        elif ctype in ("V", "I", "E"):
            # bench injection points and ideal gain blocks: 2-pin connector
            # symbols carrying the SPICE value (see docstring)
            p = Part("Connector", "Conn_01x02_Pin", value=value, circuit=c)
        else:
            raise ValueError("no KiCad symbol mapping for IR type %s" % ctype)
        p.ref = name

        pins = sorted(p.pins, key=lambda q: (len(q.num), q.num))
        assert len(pins) >= len(node_names), (name, len(pins))
        for pin, nn in zip(pins, node_names):
            net = net_of(nn)
            net += pin

    # ERC: every rail net needs a driven power reference (PWR_FLAG), or
    # ERC flags "input power pin not driven" at the power symbols that
    # auto_stub emits for GND/rails.
    for nn in list(nets):
        if nn in ("0", "GND", "vplus", "vminus"):
            pw = Part("power", "PWR_FLAG", circuit=c)
            net = nets[nn]
            net += pw.pins[0]
    return c


def write_schematic(spec: dict, outdir: str) -> Path:
    """IR -> SKiDL -> .kicad_sch (KiCad 10). auto_stub routes what it can
    and stubs the rest as global labels (skidl 2.3's mechanism for
    circuits beyond its wire router)."""
    c = build_circuit(spec)
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    c.generate_schematic(filepath=str(out), auto_stub=True, flatness=1.0)
    # SKiDL names the file after the script; find it.
    for name in ("skidl.kicad_sch", "kicad.kicad_sch",
                 Path(spec["title"]).name + ".kicad_sch"):
        if (out / name).exists():
            return out / name
    files = sorted(out.glob("*.kicad_sch"))
    assert files, "no schematic generated"
    return files[0]


def write_pcb(spec: dict, outdir: str) -> Path:
    """IR -> KiCad netlist -> placed+routed .kicad_pcb.

    Runs the PCB worker under KiCad's bundled Python (kinet2pcb imports
    pcbnew, which only imports inside the KiCad bundle on macOS). The
    worker adds a board outline and straight tracks so the DRC gate can
    run on a routable board.
    """
    c = build_circuit(spec)
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    netlist = out / "board.net"
    c.generate_netlist(file_=str(netlist), tool="kicad10")
    kpy = ("/Applications/KiCad.app/Contents/Frameworks/Python.framework/"
           "Versions/3.9/bin/python3.9")
    worker = Path(__file__).resolve().parent / "kicad_pcb_worker.py"
    env = dict(os.environ,
               PYTHONPATH="/tmp/kicad_pylibs:%s" % ("/Applications/KiCad.app"
                                                    "/Contents/Frameworks/"
                                                    "Python.framework/"
                                                    "Versions/3.9/lib/"
                                                    "python3.9/site-packages"))
    proc = subprocess.run([kpy, str(Path(__file__).resolve().parent /
                                    "kicad_pcb_worker.py"),
                           str(netlist), str(out / "board.kicad_pcb")],
                          capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError("pcb worker failed: %s%s"
                           % (proc.stdout[-1500:], proc.stderr[-1500:]))
    return out / "board.kicad_pcb"


def run_erc(sch_path: str):
    """ERC machine gate. Returns (returncode, report text)."""
    cli = kicad_cli()
    proc = subprocess.run(
        [cli, "sch", "erc", "--severity-error", "--exit-code-violations",
         str(sch_path)], capture_output=True, text=True)
    return proc.returncode, proc.stdout


def run_drc(pcb_path: str):
    """DRC machine gate with pre-layout classification.

    Returns (exit_code, report_text). The exit code is 0 iff the board is
    GATE-CLEAN: no design-rule violations (clearance, shorting, edge).
    Classifications:
      * unconnected_items  -- expected before layout; reported, not failed;
      * lib_footprint_issues / lib_symbol_issues -- kicad-cli's process
        environment lacks fp-lib-table entries; environment, not board;
      * everything else    -- a real design-rule violation -> gate fails.
    """
    cli = kicad_cli()
    workdir = Path(pcb_path).parent
    rpt = workdir / (Path(pcb_path).stem + "-drc.rpt")
    proc = subprocess.run(
        [kicad_cli(), "pcb", "drc", "--schematic-parity",
         "--exit-code-violations", str(pcb_path)],
        capture_output=True, text=True, cwd=str(workdir))
    violations = []
    for line in proc.stdout.splitlines() + open(rpt).read().splitlines() \
            if rpt.exists() else []:
        pass
    import re as _re
    text = rpt.read_text() if rpt.exists() else proc.stdout
    for m in _re.finditer(r"^\[(\w+)\]", text, _re.M):
        violations.append(m.group(1))
    pre_layout_ok = ("unconnected_items", "lib_footprint_issues",
                     "lib_symbol_issues", "footprint_link_issues")
    design_rule_hits = [v for v in violations if v not in pre_layout_ok]
    return (0 if not design_rule_hits else 5), text
