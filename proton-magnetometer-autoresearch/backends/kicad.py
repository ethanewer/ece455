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

    # ERC: every rail net needs a driven power reference (PWR_FLAG), or
    # ERC flags "input power pin not driven" at the power symbols that
    # auto_stub emits for GND/rails.
    for nn, net in nets.items():
        if nn in ("0", "GND", "vplus", "vminus"):
            pw = Part("power", "PWR_FLAG", circuit=c)
            net += pw.pins[0]

        pins = sorted(p.pins, key=lambda q: (len(q.num), q.num))
        assert len(pins) >= len(node_names), (name, len(pins))
        for pin, nn in zip(pins, node_names):
            net = net_of(nn)
            net += pin
    return c


def write_schematic(spec: dict, outdir: str) -> Path:
    """IR -> SKiDL -> .kicad_sch (KiCad 10)."""
    c = build_circuit(spec)
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    c.generate_schematic(filepath=str(out))
    return out / "skidl.kicad_sch"


def write_pcb(spec: dict, outdir: str, fp_libs=None):
    """IR -> netlist -> placed .kicad_pcb (kinet2pcb under KiCad Python)."""
    c = build_circuit(spec)
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    c.generate_pcb(file_=str(out / "board.kicad_pcb"),
                   fp_libs=fp_libs or [FOOTPRINT_DIR])
    return out / "board.kicad_pcb"


def run_erc(sch_path: str):
    """ERC machine gate. Returns (returncode, report text)."""
    cli = kicad_cli()
    proc = subprocess.run(
        [cli, "sch", "erc", "--severity-error", "--exit-code-violations",
         str(sch_path)], capture_output=True, text=True)
    return proc.returncode, proc.stdout


def run_drc(pcb_path: str):
    """DRC machine gate. Returns (returncode, report text)."""
    cli = kicad_cli()
    proc = subprocess.run(
        [cli, "pcb", "drc", "--schematic-parity", "--exit-code-violations",
         str(pcb_path)], capture_output=True, text=True)
    return proc.returncode, proc.stdout
