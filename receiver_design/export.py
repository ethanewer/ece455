#!/usr/bin/env python3
"""Build a timestamped engineering export of the receiver input path."""
from __future__ import annotations

import csv
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIVER = ROOT / "receiver_design"
KICAD_DIR = RECEIVER / "kicad"
LOCAL = ROOT / "local"
sys.path.insert(0, str(ROOT))

from receiver_design.schematic import build_receiver_schematic
from verification_modeling.coil import current_coil
from verification_modeling.eda.report import build_spice_report


def run(command: list[str], *, log: Path | None = None) -> None:
    print("+", " ".join(command))
    if log is None:
        subprocess.run(command, cwd=ROOT, check=True)
        return
    with log.open("a") as stream:
        stream.write("+ " + " ".join(command) + "\n")
        stream.flush()
        subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            stdout=stream,
            stderr=subprocess.STDOUT,
            text=True,
        )


def new_export_directory() -> Path:
    LOCAL.mkdir(parents=True, exist_ok=True)
    stem = "export-" + datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    path = LOCAL / stem
    suffix = 1
    while path.exists():
        path = LOCAL / f"{stem}-{suffix:02d}"
        suffix += 1
    path.mkdir()
    return path


def set_test_source(source: str, *, frequency_hz: float, amplitude_v: float) -> str:
    """Set the FID source at the external receiver input fixture."""
    replacements = (
        (r"(?m)^\.param fL=.*$", f".param fL={frequency_hz:.6f}"),
        (r"(?m)^\.param V0=.*$", f".param V0={amplitude_v * 1e6:.9f}u"),
    )
    text = source
    for pattern, replacement in replacements:
        text, count = re.subn(pattern, replacement, text, count=1)
        if count != 1:
            raise RuntimeError(f"receiver deck is missing a unique match for {pattern}")
    return text


def write_bom_markdown(csv_path: Path, output_path: Path) -> None:
    with csv_path.open(newline="") as stream:
        rows = list(csv.reader(stream))
    header, entries = rows[0], rows[1:]
    lines = ["# Bill of materials", "", " | ".join(header), " | ".join(["---"] * len(header))]
    lines.extend(" | ".join(cell.replace("|", "\\|") for cell in row) for row in entries)
    output_path.write_text("\n".join(lines) + "\n")


def git_text(*args: str) -> str:
    process = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return process.stdout.strip()


def export_board(output_dir: Path, verification_log: Path) -> str:
    board = KICAD_DIR / "receiver.kicad_pcb"
    if not board.exists():
        message = (
            "No receiver.kicad_pcb exists. PCB source and renders are intentionally "
            "absent; do not substitute a connectivity diagram for a routed board.\n"
        )
        (output_dir / "PCB-NOT-AVAILABLE.txt").write_text(message)
        return "not available: receiver.kicad_pcb has not been created"

    cli = shutil.which("kicad-cli") or "/Applications/KiCad.app/Contents/MacOS/kicad-cli"
    if not Path(cli).exists() and shutil.which(cli) is None:
        raise RuntimeError("kicad-cli is required to validate and render the PCB")

    drc = output_dir / "receiver-drc.txt"
    run(
        [
            cli,
            "pcb",
            "drc",
            "--output",
            str(drc),
            "--format",
            "report",
            "--severity-all",
            "--exit-code-violations",
            str(board),
        ],
        log=verification_log,
    )
    drc_text = drc.read_text(errors="replace")
    if "** Found 0 DRC violations **" not in drc_text:
        raise RuntimeError("KiCad DRC report does not state zero violations")
    if "** Found 0 unconnected pads **" not in drc_text:
        raise RuntimeError("KiCad DRC report does not state zero unconnected pads")
    shutil.copy2(board, output_dir / "receiver-final.kicad_pcb")

    run(
        [
            cli,
            "pcb",
            "export",
            "svg",
            "--output",
            str(output_dir / "receiver-routed-pcb.svg"),
            "--mode-single",
            "--layers",
            "F.Cu,B.Cu,F.Silkscreen,B.Silkscreen,Edge.Cuts",
            "--fit-page-to-board",
            "--exclude-drawing-sheet",
            str(board),
        ],
        log=verification_log,
    )
    run(
        [
            cli,
            "pcb",
            "render",
            "--output",
            str(output_dir / "receiver-final-pcb.png"),
            "--width",
            "1800",
            "--height",
            "1100",
            "--background",
            "opaque",
            "--quality",
            "high",
            "--floor",
            "--perspective",
            "--zoom",
            "2.2",
            "--rotate",
            "315,0,35",
            str(board),
        ],
        log=verification_log,
    )
    return "strict DRC passed; routed SVG, final KiCad board, and 3D PNG exported"


def export_frequency_case(
    output_dir: Path,
    source: str,
    *,
    name: str,
    frequency_hz: float,
) -> None:
    """Simulate one external input frequency and write its receiver report."""
    version_dir = output_dir / name
    version_dir.mkdir()
    netlist = version_dir / "receiver.cir"
    netlist.write_text(set_test_source(
        source, frequency_hz=frequency_hz, amplitude_v=10e-6,
    ))
    label = f"{frequency_hz:.0f} Hz external input"
    result = build_spice_report(
        netlist,
        version_dir,
        input_node="source",
        output_positive="ads_ain0",
        output_negative="vref",
        marker_hz=frequency_hz,
        passband_hz=(1500.0, 2500.0),
        transient_start_s=0.200,
        transient_stop_s=0.220,
        transient_title=f"Receiver transient, {label}",
        response_title=f"Receiver frequency response, {label}",
    )
    heading = "# Generated receiver analysis\n"
    text = result.summary_md.read_text()
    if not text.startswith(heading):
        raise RuntimeError("analysis summary is missing its heading")
    result.summary_md.write_text(
        heading + "\n"
        + f"This directory uses a 10 µV, {label} with 30 kohm source "
        + "impedance. The shaded span is the receiver's fixed 1.5–2.5 kHz "
        + "filter. Coil tuning and damping are external.\n"
        + text[len(heading):]
    )


def main() -> None:
    output_dir = new_export_directory()
    verification_log = output_dir / "verification.log"
    try:
        print(f"export directory: {output_dir}")
        run([sys.executable, str(KICAD_DIR / "validate.py")], log=verification_log)
        run([sys.executable, str(RECEIVER / "verify.py"), "--require-tools"], log=verification_log)

        coil = current_coil()
        source = (RECEIVER / "spice" / "receiver.cir").read_text()
        export_frequency_case(
            output_dir, source,
            name="1.7kHz", frequency_hz=coil["f_test_low_hz"],
        )
        export_frequency_case(
            output_dir, source,
            name="2.1kHz", frequency_hz=coil["f_test_high_hz"],
        )
        build_receiver_schematic(output_dir)

        bom_csv = output_dir / "bill-of-materials.csv"
        shutil.copy2(RECEIVER / "bom.csv", bom_csv)
        write_bom_markdown(bom_csv, output_dir / "bill-of-materials.md")
        shutil.copy2(RECEIVER / "spice" / "receiver.cir", output_dir / "receiver.cir")
        shutil.copy2(KICAD_DIR / "receiver.net", output_dir / "receiver.net")

        pcb_status = export_board(output_dir, verification_log)
        revision = git_text("rev-parse", "HEAD")
        dirty = git_text("status", "--porcelain", "--untracked-files=no")
        manifest = (
            "# Receiver engineering export\n\n"
            f"- Created: {datetime.now().astimezone().isoformat(timespec='seconds')}\n"
            f"- Git revision: `{revision}`\n"
            f"- Tracked working tree: {'modified' if dirty else 'clean'}\n"
            "- Simulation: ngspice transient and AC analyses completed for two input frequencies\n"
            "- Connectivity: receiver validation passed\n"
            f"- PCB: {pcb_status}\n\n"
            "The two frequency directories exercise the same receiver from "
            "its input connector. Coil tuning and damping remain external.\n\n"
            "## Shared contents\n\n"
            "- `receiver-construction-schematic.svg` and `.png`: receiver input and signal path\n"
            "- `bill-of-materials.csv` and `.md`: receiver parts only\n"
            "- `receiver.cir`: canonical receiver deck\n"
            "- `receiver.net`: receiver connectivity\n"
            "- `verification.log`: commands and validation output\n"
            "- PCB source and images when a strict-DRC-clean board exists\n\n"
            "## Each input-frequency directory\n\n"
            "- `receiver.cir`: 10 µV external-port stimulus at the named frequency\n"
            "- `receiver-waveforms.png` and `.csv`: transient source and ADC input\n"
            "- `receiver-frequency-response.png` and `.csv`: AC gain and phase\n"
            "- `README.md`: receiver gain and amplitudes\n\n"
            "Simulation and connectivity checks are not hardware measurements.\n"
        )
        (output_dir / "README.md").write_text(manifest)
        print(f"completed export: {output_dir}")
    except Exception as error:
        (output_dir / "EXPORT-FAILED.txt").write_text(f"{type(error).__name__}: {error}\n")
        print(f"export failed; retained diagnostics in {output_dir}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
