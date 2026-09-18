#!/usr/bin/env python3
"""Run deterministic KiCad CLI checks for available receiver artifacts."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(command: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-board", action="store_true")
    args = parser.parse_args()
    cli = shutil.which("kicad-cli") or "/Applications/KiCad.app/Contents/MacOS/kicad-cli"

    run([sys.executable, str(HERE / "generate.py")], cwd=HERE)
    schematic = HERE / "receiver.kicad_sch"
    board = HERE / "receiver.kicad_pcb"
    if (schematic.exists() or board.exists()) and not Path(cli).exists() and shutil.which(cli) is None:
        raise SystemExit("kicad-cli is required to validate KiCad design artifacts")
    if schematic.exists():
        run([cli, "sch", "erc", "--output", str(HERE / "receiver-erc.txt"),
             "--exit-code-violations", str(schematic)])
    else:
        print("STATUS graphical schematic has not been generated yet")
    if board.exists():
        run([cli, "pcb", "drc", "--output", str(HERE / "receiver-drc.txt"),
             "--format", "report", "--severity-all", "--exit-code-violations",
             str(board)])
    else:
        print("STATUS physical PCB has not been generated yet")
        if args.require_board:
            raise SystemExit("receiver.kicad_pcb is required")


if __name__ == "__main__":
    main()
