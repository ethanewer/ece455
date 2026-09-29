#!/usr/bin/env python3
"""Run external-tool checks against the active receiver artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from receiver_design import requirements  # noqa: E402
SPICE_NETLIST = ROOT / "receiver_design/spice/receiver.cir"
KICAD_NETLIST = ROOT / "receiver_design/kicad/receiver.net"
BOM = ROOT / "receiver_design/bom.csv"
ALLOWED = ROOT / "new_allowed_components.json"


def allowed_components_check() -> None:
    inventory = json.loads(ALLOWED.read_text())
    kit = inventory["thomson"]
    plexus = inventory["plexus"]
    modules = {module["part"]: module for module in inventory["purchased_modules"]}
    allowed_values = {
        ("thomson", "resistors"): kit["resistors"],
        ("thomson", "ceramic"): kit["ceramic_capacitors"],
        ("thomson", "electrolytic"): kit["electrolytic_capacitors"]["values_f"],
        ("plexus", "resistors"): plexus["resistors"],
        ("plexus", "ceramic"): plexus["capacitors"],
    }
    # The Plexus list gives values but no counts; Thomson counts are per value.
    kit_counts = {
        "resistors": kit["resistor_quantity_each"],
        "ceramic": kit["ceramic_capacitor_quantity_each"],
        "electrolytic": kit["electrolytic_capacitors"]["quantity_each"],
    }
    unit_scale = {
        "ohm": 1.0, "kohm": 1e3, "megohm": 1e6,
        "pF": 1e-12, "nF": 1e-9, "uF": 1e-6,
    }
    with BOM.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    forbidden_receiver_refs = {"J4", "SENSOR", "FB1", "FB2"}
    transistor_totals: dict[str, int] = {}
    seen_modules = set()
    for row in rows:
        refs = row["Reference"].split()
        if forbidden_receiver_refs.intersection(refs):
            raise SystemExit(f"external sensor part remains in receiver BOM: {refs}")
        if not refs or not all(re.fullmatch(r"[A-Z]+\d+", ref) for ref in refs):
            raise SystemExit(f"BOM row has malformed references: {row['Reference']}")
        if int(row["Qty"]) != len(refs):
            raise SystemExit(f"BOM quantity does not match references: {row['Reference']}")
        part = row["Value or part"]
        if part in modules:
            if int(row["Qty"]) > modules[part]["quantity"]:
                raise SystemExit(f"module count exceeds purchased quantity: {part}")
            seen_modules.add(part)
            continue
        if all(re.fullmatch(r"D\d+", ref) for ref in refs):
            diode = next((item for item in kit["diodes"] if item["part"] == part), None)
            if diode is None or int(row["Qty"]) > diode["quantity"]:
                raise SystemExit(f"diode exceeds lab inventory: {row['Reference']}")
            continue
        if all(re.fullmatch(r"Q\d+", ref) for ref in refs):
            if part not in kit["transistors"]:
                raise SystemExit(f"transistor is not in lab inventory: {row['Reference']}")
            transistor_totals[part] = transistor_totals.get(part, 0) + int(row["Qty"])
            if transistor_totals[part] > kit["transistor_quantity_each"]:
                raise SystemExit(f"transistor exceeds lab inventory: {part}")
            continue
        if not all(re.fullmatch(r"[RC]\d+", ref) for ref in refs):
            raise SystemExit(f"non-inventory BOM item: {row['Reference']}")
        match = re.fullmatch(r"([\d.]+)\s+(ohm|kohm|megohm|pF|nF|uF)", part)
        if match is None:
            raise SystemExit(f"BOM has an unparseable passive value: {row['Reference']}")
        value = float(match.group(1)) * unit_scale[match.group(2)]
        source = "plexus" if row["Package"].startswith("Plexus") else "thomson"
        if not row["Package"].startswith(("Plexus", "Thomson")):
            raise SystemExit(f"BOM passive has no inventory source: {row['Reference']}")
        if refs[0].startswith("R"):
            category = "resistors"
        elif "electrolytic" in row["Package"]:
            category = "electrolytic"
        else:
            category = "ceramic"
        candidates = allowed_values.get((source, category))
        if candidates is None or not any(
                abs(value - candidate) <= 1e-9 * candidate for candidate in candidates):
            raise SystemExit(
                f"BOM passive is not in the {source} inventory: "
                f"{row['Reference']} = {value:g}"
            )
        if source == "thomson" and int(row["Qty"]) > kit_counts[category]:
            raise SystemExit(f"BOM count exceeds Thomson kit: {row['Reference']}")
    if seen_modules != set(modules):
        raise SystemExit(f"BOM is missing purchased modules: {sorted(set(modules) - seen_modules)}")
    print("PASS BOM parts are in new_allowed_components.json with available counts")


def run(command: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


SPICE_MODELS = {"Q2N3904": "2N3904", "Q2N3906": "2N3906"}
UNIT_SUFFIX = {"ohm": "", "kohm": "k", "megohm": "Meg",
               "pF": "p", "nF": "n", "uF": "u"}


def spice_elements(spice: str) -> dict[str, tuple[list[str], str]]:
    """Fitted R, C, and Q cards: reference -> (nodes, value or model)."""
    elements = {}
    for line in spice.splitlines():
        words = line.split()
        if words and re.fullmatch(r"[RCQ]\d+", words[0]):
            elements[words[0]] = (words[1:-1], words[-1])
    return elements


def kicad_pins(connectivity: str) -> dict[tuple[str, str], str]:
    """(reference, pin) -> net name from the generated KiCad netlist."""
    pins = {}
    nets = connectivity[connectivity.find("(nets"):]
    for block in re.split(r"\n\s*\(net\s*\n?\s*\(code", nets):
        name = re.search(r'\(name "([^"]+)"\)', block)
        if name is None:
            continue
        for ref, pin in re.findall(
                r'\(ref "([^"]+)"\)\s+\(pin "([^"]+)"\)', block):
            pins[(ref, pin)] = name.group(1)
    return pins


def bom_values() -> dict[str, str]:
    """Reference -> SPICE-style value, e.g. 4.7k or 2N3904."""
    values = {}
    with BOM.open(newline="") as stream:
        for row in csv.DictReader(stream):
            match = re.fullmatch(r"([\d.]+)\s+(ohm|kohm|megohm|pF|nF|uF)",
                                 row["Value or part"])
            value = (match.group(1) + UNIT_SUFFIX[match.group(2)]
                     if match else row["Value or part"])
            for ref in row["Reference"].split():
                values[ref] = value
    return values


def artifact_check() -> None:
    allowed_components_check()
    spice = SPICE_NETLIST.read_text(errors="replace")
    connectivity = KICAD_NETLIST.read_text(errors="replace")
    if connectivity.count("(") != connectivity.count(")"):
        raise SystemExit("KiCad connectivity netlist has unbalanced parentheses")

    for token in (".param PGA=1", requirements.FIXTURE, requirements.SUPPLY,
                  "Epga pga_out 0 out bias {PGA}"):
        if token not in spice:
            raise SystemExit(f"SPICE artifact is missing {token}")

    # Every fitted R, C, and Q in the SPICE deck must appear in the BOM with
    # the same value and map pin-for-pin onto one KiCad net per SPICE node.
    elements = spice_elements(spice)
    values = bom_values()
    pins = kicad_pins(connectivity)
    fitted = {ref for ref in values if re.fullmatch(r"[RCQ]\d+", ref)}
    if set(elements) != fitted:
        raise SystemExit(
            "SPICE and BOM parts differ: "
            f"{sorted(set(elements) ^ fitted)}"
        )
    node_to_net: dict[str, str] = {}
    for ref, (nodes, value) in sorted(elements.items()):
        if SPICE_MODELS.get(value, value) != values[ref]:
            raise SystemExit(f"{ref} is {value} in SPICE but {values[ref]} in the BOM")
        # SPICE orders BJT nodes C B E; KiCad TO-92 symbols number E B C.
        order = ("3", "2", "1") if ref.startswith("Q") else ("1", "2")
        for pin, node in zip(order, nodes):
            net = pins.get((ref, pin))
            if net is None:
                raise SystemExit(f"KiCad netlist has no {ref} pin {pin}")
            if node_to_net.setdefault(node, net) != net:
                raise SystemExit(f"SPICE node {node} maps to {net} and {node_to_net[node]}")
    if len(set(node_to_net.values())) != len(node_to_net):
        raise SystemExit("two SPICE nodes map to one KiCad net")
    if node_to_net.get("0") != "GND":
        raise SystemExit("SPICE ground is not the KiCad GND net")

    # Module and connector interfaces have no SPICE counterpart.
    interface = {
        ("J1", "1"): node_to_net["receiver_in"], ("J1", "2"): "GND",
        ("J3", "1"): node_to_net["out"], ("J3", "2"): node_to_net["bias"],
        ("U3", "14"): "USB_VBUS_5V", ("J2", "1"): "USB_VBUS_5V",
        ("U3", "13"): "GND", ("J2", "2"): "GND",
        ("U3", "9"): "SPI0_SCLK_D8_GPIO2", ("J2", "3"): "SPI0_SCLK_D8_GPIO2",
        ("U3", "11"): "SPI0_MOSI_D10_GPIO3_ADS_DIN",
        ("J2", "4"): "SPI0_MOSI_D10_GPIO3_ADS_DIN",
        ("U3", "10"): "SPI0_MISO_D9_GPIO4_ADS_DOUT",
        ("J2", "5"): "SPI0_MISO_D9_GPIO4_ADS_DOUT",
        ("U3", "4"): "ADS_CS_D3_GPIO5", ("J2", "6"): "ADS_CS_D3_GPIO5",
        ("U3", "3"): "ADS_DRDY_D2_GPIO28", ("J2", "7"): "ADS_DRDY_D2_GPIO28",
        ("U3", "5"): "ADS_PDWN_D4_GPIO6", ("J2", "8"): "ADS_PDWN_D4_GPIO6",
        ("R11", "1"): "USB_VBUS_5V",
    }
    for (ref, pin), net in interface.items():
        if pins.get((ref, pin)) != net:
            raise SystemExit(f"{ref} pin {pin} is on {pins.get((ref, pin))}, expected {net}")
    print(f"PASS SPICE, BOM, and connectivity agree for {len(elements)} parts")


def ngspice_check(required: bool) -> None:
    executable = shutil.which("ngspice")
    if executable is None:
        if required:
            raise SystemExit("ngspice is required but was not found")
        print("SKIP ngspice, executable not found")
        return
    scratch = ROOT / "local" / "receiver-verify"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="spice-", dir=scratch) as directory:
        output = Path(directory)
        run([
            executable,
            "-b",
            "-r", str(output / "receiver.raw"),
            "-o", str(output / "receiver.log"),
            str(SPICE_NETLIST),
        ])
        log = (output / "receiver.log").read_text(errors="replace")
        if re.search(r"(?im)^error:", log) or "fatal error" in log.lower():
            raise SystemExit("ngspice reported an error")
        if log.count("No. of Data Rows") < 3:
            raise SystemExit("ngspice did not complete AC, spectral noise, and integrated noise")
    print("PASS ngspice receiver AC and noise analyses")


def requirements_check() -> None:
    """Fail unless every requirement holds at every corner."""
    if shutil.which("ngspice") is None:
        raise SystemExit("ngspice is required to check the receiver requirements")
    print(
        "REQUIREMENTS gain >= "
        f"{requirements.GAIN_MIN_V_PER_V:.0f} V/V over "
        f"{requirements.GAIN_BAND_HZ[0]:.0f}-{requirements.GAIN_BAND_HZ[1]:.0f} Hz; "
        f"|Z_in| >= {requirements.ZIN_MIN_OHM / 1e6:g} Mohm over "
        f"{requirements.ZIN_BAND_HZ[0]:.0f}-{requirements.ZIN_BAND_HZ[1]:.0f} Hz; "
        f"noise <= {requirements.NOISE_MAX_V_RT_HZ * 1e9:g} nV/rtHz; "
        + "; ".join(
            f"no clipping for {amplitude * 1e3:g} mV at {low:g}-{high:g} Hz"
            for (low, high), amplitude in requirements.INTERFERENCE
        )
    )
    failures = []
    for result in requirements.check_requirements(SPICE_NETLIST):
        status = "PASS" if not result.failures else "FAIL"
        print(
            f"{status} {result.corner.name:26s} gain {result.gain_min:6.0f} V/V  "
            f"|Z_in| {result.zin_min_ohm / 1e6:5.2f} Mohm  "
            f"noise {result.noise_max_v_rt_hz * 1e9:5.2f} nV/rtHz  "
            + "  ".join(f"tone {tolerance * 1e3:5.1f} mV"
                        for tolerance, _node in result.interference)
        )
        failures += [f"{result.corner.name}: {text}" for text in result.failures]
    if failures:
        raise SystemExit("receiver requirements failed:\n  " + "\n  ".join(failures))
    print("PASS receiver requirements hold at every corner")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-tools", action="store_true",
        help="fail instead of skipping when ngspice is unavailable",
    )
    args = parser.parse_args()
    artifact_check()
    ngspice_check(args.require_tools)
    requirements_check()
    print("NOTE no routed PCB, DRC report, or clean KiCad ERC is claimed")


if __name__ == "__main__":
    main()
