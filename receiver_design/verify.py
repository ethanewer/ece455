#!/usr/bin/env python3
"""Run external-tool checks against the active receiver artifacts."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPICE_NETLIST = ROOT / "receiver_design/spice/receiver.cir"
KICAD_NETLIST = ROOT / "receiver_design/kicad/receiver.net"


def run(command: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def artifact_check() -> None:
    spice = SPICE_NETLIST.read_text(errors="replace")
    connectivity = KICAD_NETLIST.read_text(errors="replace")

    # Forbid the former top-level Epre/Ebp/Eadc ideal gain blocks. E-elements
    # are allowed inside a named real-component compact macromodel.
    for forbidden in ("Epre", "Ebp", "Eadc"):
        if re.search(rf"(?im)^\s*{forbidden}\b", spice):
            raise SystemExit(f"forbidden ideal gain block remains: {forbidden}")

    required_spice = (
        "XU1A", "XU1B", "XU1C", "XU1D", "OPA4197", "TMUXSW",
        "ads_ain0", "Epga", ".param PGA=64", "30 kSPS", "D8/GPIO2",
    )
    required_connectivity = (
        "OPA4197IPWR", "TMUX1101DBVR", "XIAO-RP2350-SMD",
        "HILETGO ADS1256 DIGITAL HEADER", "ADS1256_AIN0_SIGNAL",
        "BLANK_D1_GPIO27", "74AHCT1G125", "74LVC1G125",
        "FID SENSING COIL", "USB_VBUS_5V",
    )
    for token in required_spice:
        if token not in spice:
            raise SystemExit(f"SPICE artifact is missing {token}")
    for token in required_connectivity:
        if token not in connectivity:
            raise SystemExit(f"KiCad connectivity netlist is missing {token}")

    # Catch truncated output and verify safety-critical pin assignments rather
    # than treating the presence of net names as proof of connectivity.
    if connectivity.count("(") != connectivity.count(")"):
        raise SystemExit("KiCad connectivity netlist has unbalanced parentheses")

    expected_nodes = {
        "GND": {("U1", "11"), ("U2", "3"), ("U3", "13"),
                ("U3", "26"), ("U3", "30"), ("J2", "2")},
        "USB_VBUS_5V": {("U3", "14"), ("J2", "1"),
                        ("U4", "5"), ("U7", "5")},
        "AVDD_3V3": {("FB1", "2"), ("U2", "5"), ("D2", "1")},
        "OPA_AVDD_5V": {("FB2", "2"), ("U1", "4"), ("R4", "1")},
        "PRE_IN": {("D1", "1"), ("D2", "2"), ("R1", "2"),
                   ("R2", "1"), ("U1", "3"), ("U2", "1")},
        "VREF_2V5": {("U1", "5"), ("U1", "10"), ("U1", "13"),
                      ("U1", "14"), ("U2", "2"), ("C9", "2"),
                      ("J3", "2")},
        "ADS1256_AIN0_SIGNAL": {("C9", "1"), ("R12", "2"),
                                ("J3", "1")},
        "BLANK_D1_GPIO27": {("R3", "2"), ("U2", "4"), ("U3", "2")},
        "MCU_SPI0_SCLK_D8_GPIO2": {("U3", "9"), ("U4", "2")},
        "ADS1256_SCLK_5V": {("U4", "4"), ("J2", "3")},
        "MCU_SPI0_MISO_D9_GPIO4": {("U3", "10"), ("U8", "4")},
        "ADS1256_DOUT_5V": {("U8", "2"), ("J2", "5")},
        "MCU_ADS_DRDY_D2_GPIO28": {("U3", "3"), ("U9", "4")},
        "ADS1256_DRDY_5V": {("U9", "2"), ("J2", "7")},
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
