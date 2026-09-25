"""Deterministic ngspice analyses and engineering figures.

This module operates on a supplied SPICE netlist and node names. It does not
import or mutate the active receiver design, search component values, or rank
alternatives.
"""
from __future__ import annotations

import csv
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class ReportResult:
    transient_csv: Path
    response_csv: Path
    waveforms_png: Path
    response_png: Path
    summary_md: Path


def _without_analysis_cards(text: str) -> list[str]:
    """Remove top-level analyses while preserving .ends subcircuit cards."""
    ignored = {".ac", ".noise", ".tran", ".save", ".end", ".control", ".endc"}
    output = []
    in_control = False
    for line in text.splitlines():
        words = line.lstrip().lower().split(maxsplit=1)
        head = words[0] if words else ""
        if head == ".control":
            in_control = True
            continue
        if head == ".endc":
            in_control = False
            continue
        if in_control or head in ignored:
            continue
        output.append(line)
    return output


def _write_csv(path: Path, header: tuple[str, ...], columns: tuple[np.ndarray, ...]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(zip(*columns))


def build_spice_report(
    netlist: Path,
    output_dir: Path,
    *,
    input_node: str,
    output_positive: str,
    output_negative: str,
    resonance_hz: float,
    passband_hz: tuple[float, float] | None = None,
    transient_stop_s: float = 0.020,
    max_step_s: float = 5e-6,
    transient_title: str = "Nominal receiver transient response",
    response_title: str = "Nominal receiver frequency response",
) -> ReportResult:
    """Run transient and AC analyses and write CSV, PNG, and Markdown outputs."""
    if passband_hz is not None and not 0 < passband_hz[0] < passband_hz[1]:
        raise ValueError("passband_hz must contain increasing positive frequencies")
    executable = shutil.which("ngspice")
    if executable is None:
        raise RuntimeError("ngspice was not found on PATH")
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ece455-report-") as directory:
        work = Path(directory)
        tran_raw = work / "transient.dat"
        ac_raw = work / "response.dat"
        driver = work / "analysis.cir"
        lines = _without_analysis_cards(netlist.read_text())
        if output_negative == "0":
            transient_vectors = f"v({input_node}) v({output_positive})"
            ac_vectors = f"vdb({output_positive}) vp({output_positive})"
        else:
            transient_vectors = (
                f"v({input_node}) v({output_positive}) v({output_negative})"
            )
            ac_vectors = (
                f"vdb({output_positive},{output_negative}) "
                f"vp({output_positive},{output_negative})"
            )
        lines += [
            ".control",
            "set wr_singlescale",
            "set wr_vecnames",
            f"tran {max_step_s:g} {transient_stop_s:g} 0 {max_step_s:g}",
            f"wrdata {tran_raw} {transient_vectors}",
            "ac dec 1000 100 100k",
            f"wrdata {ac_raw} {ac_vectors}",
            ".endc",
            ".end",
        ]
        driver.write_text("\n".join(lines) + "\n")
        process = subprocess.run(
            [executable, "-b", str(driver)], capture_output=True, text=True,
            timeout=30,
        )
        if process.returncode != 0 or not tran_raw.exists() or not ac_raw.exists():
            raise RuntimeError(
                "ngspice report failed:\n" + process.stdout[-2000:] + process.stderr[-2000:]
            )
        transient = np.loadtxt(tran_raw, skiprows=1)
        response = np.loadtxt(ac_raw, skiprows=1)

    expected_transient_columns = 3 if output_negative == "0" else 4
    if transient.ndim != 2 or transient.shape[1] != expected_transient_columns:
        raise RuntimeError(
            f"unexpected transient wrdata shape {transient.shape}; "
            f"expected (*, {expected_transient_columns})"
        )
    if response.ndim != 2 or response.shape[1] != 3:
        raise RuntimeError(
            f"unexpected AC wrdata shape {response.shape}; expected (*, 3)"
        )

    time_s = transient[:, 0]
    input_v = transient[:, 1]
    output_v = (transient[:, 2] if output_negative == "0" else
                transient[:, 2] - transient[:, 3])
    frequency_hz = response[:, 0]
    gain_db = response[:, 1]
    # ngspice vp() returns phase in radians; unwrap before converting for CSV.
    phase_deg = np.unwrap(response[:, 2]) * 180.0 / np.pi

    transient_csv = output_dir / "receiver-waveforms.csv"
    response_csv = output_dir / "receiver-frequency-response.csv"
    _write_csv(transient_csv, ("time_s", "fid_source_v", "adc_differential_v"),
               (time_s, input_v, output_v))
    _write_csv(response_csv, ("frequency_hz", "gain_db", "phase_deg"),
               (frequency_hz, gain_db, phase_deg))

    # Import only when figures are requested so numeric adapters remain light.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": 0.3})
    fig, axes = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True, constrained_layout=True)
    axes[0].plot(time_s * 1e3, input_v * 1e6, color="#1769aa", linewidth=1)
    axes[0].set_ylabel("FID source (µV)")
    axes[0].set_title(transient_title)
    axes[1].plot(time_s * 1e3, output_v * 1e6, color="#c62828", linewidth=1)
    axes[1].set_ylabel("ADS1256 AIN0 − AIN1 (µV)")
    axes[1].set_xlabel("Time (ms)")
    waveforms_png = output_dir / "receiver-waveforms.png"
    fig.savefig(waveforms_png, dpi=180)
    plt.close(fig)

    fig, gain_axis = plt.subplots(figsize=(10, 6), constrained_layout=True)
    gain_axis.semilogx(frequency_hz, gain_db, color="#1769aa", linewidth=1.6)
    gain_axis.axvline(resonance_hz, color="#555", linestyle="--", linewidth=1)
    if passband_hz is not None:
        gain_axis.axvspan(
            passband_hz[0], passband_hz[1], color="#2e7d32", alpha=0.10,
            label=(
                f"Intended passband {passband_hz[0] / 1000:.3f}"
                f"-{passband_hz[1] / 1000:.3f} kHz"
            ),
        )
        gain_axis.legend(loc="lower left")
    gain_axis.set_xlabel("Frequency (Hz)")
    gain_axis.set_ylabel("Source-to-ADC differential gain (dB)", color="#1769aa")
    phase_axis = gain_axis.twinx()
    phase_axis.semilogx(frequency_hz, phase_deg, color="#c62828", linewidth=1.1, alpha=0.8)
    phase_axis.set_ylabel("Phase (degrees)", color="#c62828")
    gain_axis.set_title(response_title)
    response_png = output_dir / "receiver-frequency-response.png"
    fig.savefig(response_png, dpi=180)
    plt.close(fig)

    index = int(np.argmin(np.abs(frequency_hz - resonance_hz)))
    settled = time_s >= transient_stop_s / 2
    input_peak = float(np.max(np.abs(input_v[settled])))
    output_center = float(np.mean(output_v[settled]))
    output_peak = float(np.max(np.abs(output_v[settled] - output_center)))
    summary_md = output_dir / "README.md"
    try:
        displayed_netlist = netlist.relative_to(output_dir.parent).as_posix()
    except ValueError:
        displayed_netlist = netlist.name
    passband_summary = ""
    if passband_hz is not None:
        in_band = ((frequency_hz >= passband_hz[0]) &
                   (frequency_hz <= passband_hz[1]))
        if not np.any(in_band):
            raise RuntimeError("AC sweep has no samples in the requested passband")
        band_gain = 10 ** (gain_db[in_band] / 20)
        passband_summary = (
            f"- Intended passband: {passband_hz[0]:.0f} to "
            f"{passband_hz[1]:.0f} Hz\n"
            f"- Simulated in-band gain range: {np.min(band_gain):.1f} to "
            f"{np.max(band_gain):.1f} V/V\n"
        )
    summary_md.write_text(
        "# Generated receiver analysis\n\n"
        "Generated by `python3 receiver_design/analyze.py` using ngspice and "
        "Matplotlib. Values are simulated, not measured.\n\n"
        f"- Analysis netlist: `{displayed_netlist}`\n"
        f"- Nominal frequency marker: {resonance_hz:.3f} Hz\n"
        f"- Gain near nominal frequency: {gain_db[index]:.2f} dB "
        f"({10 ** (gain_db[index] / 20):.1f} V/V)\n"
        f"{passband_summary}"
        f"- Settled input peak: {input_peak * 1e6:.3f} µV\n"
        f"- Settled ADC differential peak about its mean: {output_peak * 1e6:.1f} µV\n\n"
        "![Input and output waveforms](receiver-waveforms.png)\n\n"
        "![Frequency response](receiver-frequency-response.png)\n"
    )
    return ReportResult(transient_csv, response_csv, waveforms_png,
                        response_png, summary_md)
