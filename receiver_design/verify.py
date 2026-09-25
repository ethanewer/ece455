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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPICE_NETLIST = ROOT / "receiver_design/spice/receiver.cir"
KICAD_NETLIST = ROOT / "receiver_design/kicad/receiver.net"
BOM = ROOT / "receiver_design/bom.csv"
ALLOWED = ROOT / "new_allowed_components.json"


def allowed_components_check() -> None:
    inventory = json.loads(ALLOWED.read_text())
    kit = inventory["thomson"]
    allowed_values = {
        "resistors": kit["resistors"],
        "ceramic": kit["ceramic_capacitors"],
        "electrolytic": kit["electrolytic_capacitors"]["values_f"],
    }
    unit_scale = {
        "ohm": 1.0, "kohm": 1e3, "megohm": 1e6,
        "pF": 1e-12, "nF": 1e-9, "uF": 1e-6,
    }
    with BOM.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    forbidden_receiver_refs = {"J4", "SENSOR", "C25", "C26", "C27",
                               "C28", "C29", "C30", "C31", "FB1", "FB2"}
    for row in rows:
        refs = row["Reference"].split()
        if forbidden_receiver_refs.intersection(refs):
            raise SystemExit(f"external sensor part remains in receiver BOM: {refs}")
        if all(re.fullmatch(r"[A-Z]+\d+", ref) for ref in refs):
            if int(row["Qty"]) != len(refs):
                raise SystemExit(f"BOM quantity does not match references: {row['Reference']}")
        if refs == ["U3"] or refs == ["MOD1"]:
            continue
        if refs and all(re.fullmatch(r"D\d+", ref) for ref in refs):
            diode = next((part for part in kit["diodes"]
                          if part["part"] == row["Value or part"]), None)
            if diode is None or int(row["Qty"]) > diode["quantity"]:
                raise SystemExit(f"diode exceeds lab inventory: {row['Reference']}")
            continue
        if refs and all(re.fullmatch(r"Q\d+", ref) for ref in refs):
            if (row["Value or part"] not in kit["transistors"]
                    or int(row["Qty"]) > kit["transistor_quantity_each"]):
                raise SystemExit(f"transistor exceeds lab inventory: {row['Reference']}")
            continue
        if not refs or not all(re.fullmatch(r"[RC]\d+", ref) for ref in refs):
            raise SystemExit(f"non-lab BOM item: {row['Reference']}")
        match = re.fullmatch(
            r"([\d.]+)\s+(ohm|kohm|megohm|pF|nF|uF)",
            row["Value or part"],
        )
        if match is None:
            raise SystemExit(f"BOM has an unparseable passive value: {row['Reference']}")
        value = float(match.group(1)) * unit_scale[match.group(2)]
        if refs[0].startswith("R"):
            category = "resistors"
            count = kit["resistor_quantity_each"]
        elif "electrolytic" in row["Package"]:
            category = "electrolytic"
            count = kit["electrolytic_capacitors"]["quantity_each"]
        else:
            category = "ceramic"
            count = kit["ceramic_capacitor_quantity_each"]
        if not any(abs(value - candidate) <= 1e-9 * candidate
                   for candidate in allowed_values[category]):
            raise SystemExit(f"BOM passive is not in Thomson kit: {row['Reference']} = {value:g}")
        if int(row["Qty"]) > count:
            raise SystemExit(f"BOM count exceeds Thomson kit: {row['Reference']}")
    print("PASS BOM fitted parts are in Thomson kit or are the purchased modules")


def run(command: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def artifact_check() -> None:
    allowed_components_check()
    spice = SPICE_NETLIST.read_text(errors="replace")
    connectivity = KICAD_NETLIST.read_text(errors="replace")

    for forbidden in ("Lcoil", "Ctune", "Rdamp", "OPA4197", "TMUXSW"):
        if re.search(rf"(?im)^\s*{forbidden}\b", spice):
            raise SystemExit(f"obsolete part remains in receiver SPICE: {forbidden}")

    required_spice = (
        "ads_ain0", "Epga", ".param PGA=64", "30 kSPS", "D8/GPIO2",
        "Rsource source receiver_in 30k",
        "C5 receiver_in coupled 22n", "R1 coupled ads_ain0 10k",
        "R2 ads_ain0 bias_mid 1Meg", "R3 bias_mid vref 1Meg",
        "C9 ads_ain0 vref 100p", "D1 vref ads_ain0 KIT4148",
        "D2 ads_ain0 vref KIT4148", "R4 vbus5 vref 1k",
        "R5 vref 0 470", "Gads ads_ain0 vref ads_ain0 vref 100n",
    )
    required_connectivity = (
        "XIAO-RP2350-SMD", "HILETGO ADS1256 LOGICAL DIGITAL WIRES",
        "ADS1256_AIN0_SIGNAL", "MODULE_SPI_VDD_SELECT",
        "EXTERNAL SENSOR WIRE INTERFACE", "RECEIVER_IN", "USB_VBUS_5V",
        "2N3904", "1N4148",
    )
    for token in required_spice:
        if token not in spice:
            raise SystemExit(f"SPICE artifact is missing {token}")
    for token in required_connectivity:
        if token not in connectivity:
            raise SystemExit(f"KiCad connectivity netlist is missing {token}")
    for removed_ref in ("J4", "C1", "C2", "C3", "C4", "FB1", "FB2",
                        "C25", "C26", "C27", "C28", "C29", "C30", "C31",
                        "U1", "U2", "U4", "U5", "U6", "U7", "U8", "U9"):
        if f'(ref "{removed_ref}")' in connectivity:
            raise SystemExit(
                f"obsolete receiver component remains: {removed_ref}"
            )

    # Catch truncated output and verify safety-critical pin assignments rather
    # than treating the presence of net names as proof of connectivity.
    if connectivity.count("(") != connectivity.count(")"):
        raise SystemExit("KiCad connectivity netlist has unbalanced parentheses")

    expected_nodes = {
        "GND": {("U3", "13"), ("U3", "26"), ("U3", "30"),
                ("J1", "2"), ("J2", "2"), ("R5", "2"),
                ("Q1", "1"), ("Q6", "1")},
        "RECEIVER_IN": {("J1", "1"), ("C5", "1"), ("TP2", "1")},
        "COUPLED_INPUT": {("C5", "2"), ("R1", "1")},
        "BIAS_RETURN_MID": {("R2", "2"), ("R3", "1")},
        "VBIAS_1V60": {("C6", "1"), ("C7", "1"), ("C9", "2"),
                       ("D1", "2"), ("D2", "1"), ("R3", "2"),
                       ("R4", "2"), ("R5", "1"), ("J3", "2")},
        "ADS1256_AIN0_SIGNAL": {("R1", "2"), ("R2", "1"),
                                 ("C9", "1"), ("D1", "1"),
                                 ("D2", "2"), ("J3", "1")},
        "USB_VBUS_5V": {("U3", "14"), ("J2", "1"),
                        ("R4", "1"), ("JP1", "3")},
        "XIAO_3V3_OUT": {("U3", "12"), ("JP1", "1"),
                         ("R18", "1"), ("R19", "1")},
        "MODULE_SPI_VDD_SELECT": {("JP1", "2"), ("R12", "1"),
                                   ("R15", "1"), ("R22", "1"),
                                   ("R23", "1")},
        "MCU_SPI0_SCLK_D8_GPIO2": {("U3", "9"), ("R6", "1"),
                                    ("R18", "2")},
        "MCU_SPI0_MOSI_D10_GPIO3": {("U3", "11"), ("R7", "1"),
                                    ("R19", "2")},
        "MCU_ADS_CS_D3_GPIO5": {("U3", "4"), ("R8", "1"),
                                 ("R21", "1")},
        "MCU_ADS_PDWN_D4_GPIO6": {("U3", "5"), ("R9", "1"),
                                   ("R20", "1")},
        "ADS1256_SCLK": {("Q1", "3"), ("R12", "2"),
                          ("D3", "1"), ("J2", "3")},
        "ADS1256_DIN": {("Q2", "3"), ("J2", "4")},
        "ADS1256_DOUT": {("R10", "1"), ("R22", "2"), ("J2", "5")},
        "ADS1256_DRDY": {("R11", "1"), ("R23", "2"), ("J2", "7")},
        "MCU_SPI0_MISO_D9_GPIO4": {("U3", "10"), ("Q5", "3")},
        "MCU_ADS_DRDY_D2_GPIO28": {("U3", "3"), ("Q6", "3")},
    }
    nets_start = connectivity.find("(nets")
    for name, expected in expected_nodes.items():
        name_at = connectivity.find(f'(name "{name}")', nets_start)
        if name_at < 0:
            raise SystemExit(f"KiCad connectivity netlist is missing net {name}")
        block_start = connectivity.rfind("(net", nets_start, name_at)
        block_end = connectivity.find("\n    (net", name_at)
        block = connectivity[block_start:block_end if block_end >= 0 else None]
        actual = set(re.findall(
            r'\(node\s+\(ref "([^"]+)"\)\s+\(pin "([^"]+)"\)', block
        ))
        missing = expected - actual
        if missing:
            raise SystemExit(f"net {name} is missing nodes {sorted(missing)}")
    print("PASS lab-parts receiver connectivity")


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-tools", action="store_true",
        help="fail instead of skipping when ngspice is unavailable",
    )
    args = parser.parse_args()
    artifact_check()
    ngspice_check(args.require_tools)
    print("NOTE no routed PCB, DRC report, or clean KiCad ERC is claimed")


if __name__ == "__main__":
    main()
