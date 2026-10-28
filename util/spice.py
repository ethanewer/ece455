"""Run ngspice analyses on a deck and return NumPy arrays.

The functions take deck text and node names. They do not read design files,
search component values, or rank alternatives. Any analysis cards already in
the deck are removed so each call runs exactly one analysis.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Noise:
    frequency_hz: np.ndarray
    input_v_rt_hz: np.ndarray
    output_v_rt_hz: np.ndarray


def _without_analysis_cards(deck: str) -> list[str]:
    """Drop top-level analyses and .control blocks; keep subcircuits and models."""
    ignored = {".ac", ".noise", ".tran", ".op", ".save", ".end", ".step", ".meas"}
    output, in_control = [], False
    for line in deck.splitlines():
        head = (line.lstrip().lower().split(maxsplit=1) or [""])[0]
        if head == ".control":
            in_control = True
        elif head == ".endc":
            in_control = False
        elif not in_control and head not in ignored:
            output.append(line)
    return output


def run(deck: str, control: list[str], outputs: tuple[str, ...] = (), timeout_s: float = 300.0
        ) -> tuple[str, dict[str, np.ndarray]]:
    """Run ngspice in batch mode with the given .control lines.

    `{dir}` in a control line is the scratch directory. Each name in outputs
    is a wrdata file written there; its table is returned under that name.
    """
    executable = shutil.which("ngspice")
    if executable is None:
        raise RuntimeError("ngspice was not found on PATH")
    with tempfile.TemporaryDirectory(prefix="ece455-ngspice-") as directory:
        work = Path(directory)
        lines = _without_analysis_cards(deck)
        lines += [".control", "set wr_singlescale", "set wr_vecnames",
                  *(line.replace("{dir}", directory) for line in control), ".endc", ".end"]
        (work / "deck.cir").write_text("\n".join(lines) + "\n")
        process = subprocess.run([executable, "-b", str(work / "deck.cir")],
                                 capture_output=True, text=True, timeout=timeout_s)
        tables = {}
        for name in outputs:
            path = work / name
            if path.exists():
                tables[name] = np.atleast_2d(np.loadtxt(path, skiprows=1))
        # ngspice exits with 1 after a .control-only batch run ("no simulations
        # run"), so failures are recognised by their messages and missing output.
        failed = (process.returncode not in (0, 1) or len(tables) != len(outputs)
                  or re.search(r"(?im)^\s*error|fatal error|interrupted due to error",
                               process.stdout + process.stderr))
        if failed:
            raise RuntimeError("ngspice failed:\n" + process.stdout[-3000:] + process.stderr[-3000:])
    return process.stdout, tables


def operating_point(deck: str, nodes: list[str]) -> dict[str, float]:
    """DC node voltages."""
    stdout, _ = run(deck, ["op", *(f"print v({node})" for node in nodes)])
    values = dict(re.findall(r"^v\((\S+)\)\s*=\s*([-0-9.eE+]+)", stdout, re.M))
    return {node: float(values[node.lower()]) for node in nodes}


def ac(deck: str, expressions: dict[str, str], *, start_hz: float, stop_hz: float,
       points_per_decade: int) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Real AC expressions (for example vm(out)) on a logarithmic sweep."""
    names = list(expressions)
    control = [f"ac dec {points_per_decade} {start_hz:g} {stop_hz:g}"]
    control += [f"let r_{index} = {expressions[name]}" for index, name in enumerate(names)]
    control.append("wrdata {dir}/ac.dat " + " ".join(f"r_{i}" for i in range(len(names))))
    _, tables = run(deck, control, ("ac.dat",))
    table = tables["ac.dat"]
    return table[:, 0], {name: table[:, index + 1] for index, name in enumerate(names)}


def ac_points(deck: str, expressions: dict[str, str], frequencies_hz: list[float]
              ) -> dict[str, np.ndarray]:
    """Real AC expressions at exact frequencies."""
    names = list(expressions)
    control = []
    for point, frequency in enumerate(frequencies_hz):
        control.append(f"ac lin 1 {frequency:g} {frequency:g}")
        control += [f"let r_{index} = {expressions[name]}" for index, name in enumerate(names)]
        control.append(f"wrdata {{dir}}/ac{point}.dat "
                       + " ".join(f"r_{i}" for i in range(len(names))))
    outputs = tuple(f"ac{point}.dat" for point in range(len(frequencies_hz)))
    _, tables = run(deck, control, outputs)
    return {name: np.array([tables[output][0, index + 1] for output in outputs])
            for index, name in enumerate(names)}


def noise(deck: str, *, output: str, reference: str, source: str, start_hz: float,
          stop_hz: float, points_per_decade: int) -> Noise:
    """Output noise of v(output, reference) and its value referred to source."""
    probe = f"v({output})" if reference == "0" else f"v({output},{reference})"
    control = [f"noise {probe} {source} dec {points_per_decade} {start_hz:g} {stop_hz:g}",
               "setplot noise1", "wrdata {dir}/noise.dat inoise_spectrum onoise_spectrum"]
    _, tables = run(deck, control, ("noise.dat",))
    table = tables["noise.dat"]
    return Noise(table[:, 0], table[:, 1], table[:, 2])


def transient(deck: str, expressions: dict[str, str], *, stop_s: float, step_s: float,
              max_step_s: float | None = None) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Transient expressions resampled onto a uniform step_s grid."""
    names = list(expressions)
    control = [f"tran {step_s:g} {stop_s:g} 0 {max_step_s or step_s:g}", "linearize"]
    control += [f"let r_{index} = {expressions[name]}" for index, name in enumerate(names)]
    control.append("wrdata {dir}/tran.dat " + " ".join(f"r_{i}" for i in range(len(names))))
    _, tables = run(deck, control, ("tran.dat",))
    table = tables["tran.dat"]
    return table[:, 0], {name: table[:, index + 1] for index, name in enumerate(names)}


def band_rms(frequency_hz: np.ndarray, density: np.ndarray, band_hz: tuple[float, float]) -> float:
    """RMS of a one-sided density integrated across band_hz (trapezoidal, interpolated)."""
    low, high = band_hz
    grid = np.linspace(low, high, 4001)
    values = np.interp(grid, frequency_hz, density)
    return float(np.sqrt(np.trapezoid(values ** 2, grid)))
