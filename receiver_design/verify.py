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
LTSPICE_NETLIST = ROOT / "receiver_design/ltspice/receiver.cir"
KICAD_BOARD = ROOT / "receiver_design/kicad/receiver.kicad_pcb"


def run(command: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


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
            str(LTSPICE_NETLIST),
        ])
        log = (output / "receiver.log").read_text(errors="replace")
        if re.search(r"(?im)^error:", log) or "fatal error" in log.lower():
            raise SystemExit("ngspice reported an error")
    print("PASS ngspice receiver netlist")


def kicad_check(required: bool) -> None:
    executable = shutil.which("kicad-cli")
    fallback = Path("/Applications/KiCad.app/Contents/MacOS/kicad-cli")
    if executable is None and fallback.exists():
        executable = str(fallback)
    if executable is None:
        if required:
            raise SystemExit("kicad-cli is required but was not found")
        print("SKIP KiCad DRC, executable not found")
        return
    with tempfile.TemporaryDirectory(prefix="ece455-kicad-") as directory:
        report = Path(directory) / "receiver-drc.txt"
        run([
            executable, "pcb", "drc",
            "--output", str(report),
            "--format", "report",
            "--severity-all",
            "--exit-code-violations",
            str(KICAD_BOARD),
        ], cwd=KICAD_BOARD.parent)
        text = report.read_text(errors="replace")
        if "Found 0 DRC violations" not in text or "Found 0 unconnected pads" not in text:
            raise SystemExit(f"KiCad did not produce a clean report: {report}")
    print("PASS KiCad receiver board DRC")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-tools", action="store_true",
        help="fail instead of skipping when ngspice or KiCad is unavailable",
    )
    args = parser.parse_args()
    ngspice_check(args.require_tools)
    kicad_check(args.require_tools)


if __name__ == "__main__":
    main()
