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


def allowed_passives_check() -> None:
    inventory = json.loads(ALLOWED.read_text())
    unit_scale = {
        "ohm": 1.0, "kohm": 1e3, "megohm": 1e6,
        "pF": 1e-12, "nF": 1e-9, "uF": 1e-6,
    }
    with BOM.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    forbidden_receiver_refs = {"J4", "SENSOR", "C25", "C26", "C27",
                               "C28", "C29", "C30", "C31"}
    for row in rows:
        refs = row["Reference"].split()
        if forbidden_receiver_refs.intersection(refs):
            raise SystemExit(f"external sensor part remains in receiver BOM: {refs}")
        if not refs or not all(re.fullmatch(r"[RC]\d+", ref) for ref in refs):
            continue
        match = re.fullmatch(
            r"([\d.]+)\s+(ohm|kohm|megohm|pF|nF|uF)",
            row["Value or part"],
        )
        if match is None:
            raise SystemExit(f"BOM has an unparseable passive value: {row['Reference']}")
        value = float(match.group(1)) * unit_scale[match.group(2)]
        category = "resistors" if refs[0].startswith("R") else "capacitors"
        if not any(abs(value - candidate) <= 1e-9 * candidate
                   for candidate in inventory[category]):
            raise SystemExit(f"BOM passive is not allowed: {row['Reference']} = {value:g}")
    print("PASS BOM resistor and capacitor values are in new_allowed_components.json")


def run(command: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def artifact_check() -> None:
    allowed_passives_check()
    spice = SPICE_NETLIST.read_text(errors="replace")
    connectivity = KICAD_NETLIST.read_text(errors="replace")

    # Forbid the former top-level Epre/Ebp/Eadc ideal gain blocks. E-elements
    # are allowed inside a named real-component compact macromodel.
    for forbidden in ("Epre", "Ebp", "Eadc"):
        if re.search(rf"(?im)^\s*{forbidden}\b", spice):
            raise SystemExit(f"forbidden ideal gain block remains: {forbidden}")
    for forbidden in ("Lcoil", "C25", "C26", "C27", "C28",
                      "C29", "C30", "C31", "R17 n17", "R21 n21"):
        if re.search(rf"(?im)^\s*{forbidden}\b", spice):
            raise SystemExit(f"external tuning part remains in receiver SPICE: {forbidden}")

    required_spice = (
        "XU1A", "XU1B", "XU1C", "XU1D", "OPA4197", "TMUXSW",
        "ads_ain0", "Epga", ".param PGA=64", "30 kSPS", "D8/GPIO2",
        "XU1A pre_in stage1 stage1 opamp5 0 OPA4197",
        "C7 stage1 hp_in 100n",
        "Rsource source receiver_in 30k",
        "C5 receiver_in protected 3.3n",
        "R2 pre_in bias1 510k", "R6 bias1 bias2 510k",
        "R24 bias2 bias3 510k", "R25 bias3 bias4 510k",
        "R26 bias4 bias5 510k", "R27 bias5 bias6 510k",
        "R28 bias6 bias7 510k", "R29 bias7 bias8 510k",
        "R30 bias8 bias9 510k", "R31 bias9 vref 510k",
        "R8 hp_in stage2_n 1.05k", "R9 stage2 stage2_n 56k",
        "R10 stage2 sk10_mid 10k", "R22 sk10_mid sk_mid 1k",
        "R11 sk_mid sk11_mid 10k", "R23 sk11_mid stage3_n 1k",
        "C8 sk_mid stage3 3.3n",
        "C32 sk_mid stage3 3.3n",
        "D3 ads_ain0 clamp3 BAS116",
    )
    required_connectivity = (
        "OPA4197IPWR", "TMUX1101DBVR", "XIAO-RP2350-SMD",
        "HILETGO ADS1256 DIGITAL HEADER", "ADS1256_AIN0_SIGNAL",
        "BLANK_D1_GPIO27", "74AHCT1G125", "74LVC1G125",
        "EXTERNAL SENSOR SIGNAL", "RECEIVER_IN", "USB_VBUS_5V",
    )
    for token in required_spice:
        if token not in spice:
            raise SystemExit(f"SPICE artifact is missing {token}")
    for token in required_connectivity:
        if token not in connectivity:
            raise SystemExit(f"KiCad connectivity netlist is missing {token}")
    for removed_ref in ("J4", "C1", "C2", "C3", "C4",
                        "C25", "C26", "C27", "C28", "C29", "C30", "C31"):
        if f'(ref "{removed_ref}")' in connectivity:
            raise SystemExit(
                f"obsolete fixed tuning capacitor remains: {removed_ref}"
            )

    # Catch truncated output and verify safety-critical pin assignments rather
    # than treating the presence of net names as proof of connectivity.
    if connectivity.count("(") != connectivity.count(")"):
        raise SystemExit("KiCad connectivity netlist has unbalanced parentheses")

    expected_nodes = {
        "GND": {("U1", "11"), ("U2", "3"), ("U3", "13"),
                ("U3", "26"), ("U3", "30"), ("J2", "2"),
                ("R19", "2"), ("R20", "2"), ("J1", "2")},
        "RECEIVER_IN": {("J1", "1"), ("C5", "1"), ("TP2", "1")},
        "SK_R10_MID": {("R10", "2"), ("R22", "1")},
        "SK_R11_MID": {("R11", "2"), ("R23", "1")},
        "STAGE1": {("U1", "1"), ("U1", "2"), ("C7", "1")},
        "USB_VBUS_5V": {("U3", "14"), ("J2", "1"),
                        ("U4", "5"), ("U7", "5"),
                        ("R17", "1"), ("R18", "1")},
        "XIAO_3V3_OUT": {("U3", "12"), ("R13", "1"), ("R16", "1")},
        "AVDD_3V3": {("FB1", "2"), ("U2", "5"), ("D2", "1")},
        "OPA_AVDD_5V": {("FB2", "2"), ("U1", "4"), ("R4", "1"),
                        ("R14", "1")},
        "PRE_IN": {("D1", "1"), ("D2", "2"), ("R1", "2"),
                   ("R2", "1"), ("U1", "3"), ("U2", "1")},
        "VBIAS_1V36": {("U1", "5"), ("U1", "13"),
                      ("U1", "14"), ("U2", "2"), ("R31", "2"), ("C9", "2"),
                      ("C23", "2"), ("J3", "2"), ("J3", "3")},
        "ADS1256_AIN0_SIGNAL": {("C9", "1"), ("R12", "2"),
                                ("J3", "1"), ("D3", "2")},
        "CLAMP_1V6": {("R14", "2"), ("R15", "1"), ("C24", "1"),
                      ("D3", "1")},
        "MCU_ADS_CS_D3_GPIO5": {("U3", "4"), ("U6", "2"), ("R13", "2")},
        "MCU_ADS_PDWN_D4_GPIO6": {("U3", "5"), ("U7", "2"), ("R16", "2")},
        "ADS1256_DOUT_5V": {("U8", "2"), ("J2", "5"), ("R17", "2")},
        "ADS1256_DRDY_5V": {("U9", "2"), ("J2", "7"), ("R18", "2")},
        "BLANK_D1_GPIO27": {("R3", "2"), ("U2", "4"), ("U3", "2")},
        "MCU_SPI0_SCLK_D8_GPIO2": {("U3", "9"), ("U4", "2"),
                                  ("R19", "1")},
        "MCU_SPI0_MOSI_D10_GPIO3": {("U3", "11"), ("U5", "2"),
                                   ("R20", "1")},
        "ADS1256_SCLK_5V": {("U4", "4"), ("J2", "3")},
        "MCU_SPI0_MISO_D9_GPIO4": {("U3", "10"), ("U8", "4")},
        "MCU_ADS_DRDY_D2_GPIO28": {("U3", "3"), ("U9", "4")},
    }
    bias_refs = ("R2", "R6", "R24", "R25", "R26",
                 "R27", "R28", "R29", "R30", "R31")
    for index, (left, right) in enumerate(zip(bias_refs, bias_refs[1:]), 1):
        expected_nodes[f"BIAS_RETURN_{index}"] = {(left, "2"), (right, "1")}
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
    print("PASS complete receiver connectivity and no former ideal gain blocks")


def ngspice_check(required: bool) -> None:
    executable = shutil.which("ngspice")
    if executable is None:
        if required:
            raise SystemExit("ngspice is required but was not found")
        print("SKIP ngspice, executable not found")
        return
    with tempfile.TemporaryDirectory(prefix="ece455-spice-") as directory:
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
