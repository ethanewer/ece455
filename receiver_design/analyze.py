#!/usr/bin/env python3
"""Generate the standard transient, frequency-response, noise, and input report."""
from __future__ import annotations

from pathlib import Path
import math
import re
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from receiver_design import requirements
from verification_modeling.coil import current_coil
from verification_modeling.crb import freq_crb
from verification_modeling.eda.report import (
    build_spice_report,
    measure_input_impedance,
    measure_noise,
)
from verification_modeling.physics import (
    GAMMA_HZ_PER_T,
    K_B,
    NT_PER_HZ,
    estimate_v0,
)

PASSBAND_HZ = requirements.GAIN_BAND_HZ
SPOT_HZ = math.sqrt(PASSBAND_HZ[0] * PASSBAND_HZ[1])
FIXTURE = requirements.FIXTURE
OUTPUT_POSITIVE = requirements.OUTPUT_POSITIVE
OUTPUT_NEGATIVE = requirements.OUTPUT_NEGATIVE
# ngspice evaluates resistor thermal noise at its default 27 C.
T_SPICE_K = 300.15
# Estimator record used for the frequency CRB column.
FS_HZ = 30_000.0
BLANK_S = 0.2
RECORD_S = 1.5


def source_cases(coil: dict) -> list[tuple[str, str, float | None, bool]]:
    """External fixtures: label, SPICE lines, source resistance, coil EMF."""
    return [
        ("30 kΩ tuned-sensor fixture", FIXTURE, 30e3, False),
        (
            f"Untuned coil pair ({coil['r_coil']:.1f} Ω, "
            f"{coil['l_coil'] * 1e3:.1f} mH)",
            f"Rsource source coil_mid {coil['r_coil']:.4f}\n"
            f"Lsource coil_mid receiver_in {coil['l_coil']:.6g}",
            coil["r_coil"],
            True,
        ),
        ("Shorted input (amplifier only)",
         "Rsource source receiver_in 1m", None, False),
    ]


def fid_amplitudes(coil: dict) -> list[tuple[str, float]]:
    """Model FID EMFs: the active coil pair and the older pessimistic case."""
    b_earth = coil["f_test_low_hz"] / GAMMA_HZ_PER_T
    return [
        ("active coil", estimate_v0(b_pol=coil["b_pol"], n_turns=coil["n_turns"],
                                    coil_radius_m=coil["radius_m"], b_earth=b_earth)),
        ("pessimistic", estimate_v0()),
    ]


def crb_nt(density_v_rt_hz: float, amplitude_v: float, tau_s: float) -> float:
    """Frequency CRB for a white floor at the given EMF-referred density."""
    t = np.arange(int(RECORD_S * FS_HZ)) / FS_HZ
    sigma = density_v_rt_hz * math.sqrt(FS_HZ / 2)
    amplitude = amplitude_v * math.exp(-BLANK_S / tau_s)
    return freq_crb(t, amplitude, SPOT_HZ, tau_s, 0.3, sigma) * NT_PER_HZ


def noise_table(netlist: Path, coil: dict) -> str:
    text = netlist.read_text()
    if text.count(FIXTURE) != 1:
        raise RuntimeError("receiver deck is missing its unique source fixture")
    amplitudes = fid_amplitudes(coil)
    rows = [
        "| Source at J1 | Input noise at "
        f"{SPOT_HZ:.0f} Hz | {PASSBAND_HZ[0]:.0f}–{PASSBAND_HZ[1]:.0f} Hz "
        "input RMS | Noise figure | AIN0−AIN1 RMS | Frequency CRB |",
        "|---|---:|---:|---:|---:|---|",
    ]
    with tempfile.TemporaryDirectory(prefix="receiver-noise-") as directory:
        for label, lines, resistance, is_coil in source_cases(coil):
            deck = Path(directory) / "receiver.cir"
            deck.write_text(text.replace(FIXTURE, lines))
            result = measure_noise(
                deck, source=requirements.SOURCE, output_positive=OUTPUT_POSITIVE,
                output_negative=OUTPUT_NEGATIVE, band_hz=PASSBAND_HZ,
                spot_hz=SPOT_HZ,
            )
            if resistance is None:
                figure = "—"
            else:
                floor = math.sqrt(4 * K_B * T_SPICE_K * resistance
                                  * (PASSBAND_HZ[1] - PASSBAND_HZ[0]))
                figure = (f"{20 * math.log10(result.band_input_rms_v / floor):.1f}"
                          " dB")
            if is_coil:
                bounds = ", ".join(
                    f"{crb_nt(result.input_density_v_rt_hz, amplitude, coil['t2_star_s']):.3f} nT "
                    f"({amplitude * 1e6:.2f} µV {name})"
                    for name, amplitude in amplitudes
                )
            else:
                bounds = "—"
            rows.append(
                f"| {label} | {result.input_density_v_rt_hz * 1e9:.2f} nV/√Hz "
                f"| {result.band_input_rms_v * 1e9:.0f} nV | {figure} "
                f"| {result.band_output_rms_v * 1e6:.0f} µV | {bounds} |"
            )
    return "\n".join(rows)


if __name__ == "__main__":
    coil = current_coil()
    netlist = ROOT / "spice/receiver.cir"
    # The marker is an example input frequency, not receiver resonance.
    result = build_spice_report(
        netlist,
        ROOT / "analysis",
        input_node="receiver_in",
        output_positive=OUTPUT_POSITIVE,
        output_negative=OUTPUT_NEGATIVE,
        marker_hz=coil["f_test_low_hz"],
        gain_input_node="receiver_in",
        passband_hz=PASSBAND_HZ,
        transient_start_s=0.200,
        transient_stop_s=0.220,
    )
    _, impedance = measure_input_impedance(
        netlist, source=requirements.SOURCE, node=requirements.INPUT_NODE,
        band_hz=requirements.ZIN_BAND_HZ,
    )
    summary = result.summary_md.read_text().rstrip()
    summary = re.sub(r"(?m)^- Intended passband:", "- Specified band:", summary)
    summary = re.sub(r"(?m)^(- Settled input peak:)", r"- Settled J1 input peak:", summary)
    nominal = requirements.evaluate_corner(netlist, requirements.CORNERS[0])
    impedance_line = (
        f"- Simulated |Z_in| at J1 over {requirements.ZIN_BAND_HZ[0]:.0f}–"
        f"{requirements.ZIN_BAND_HZ[1]:.0f} Hz: {impedance.min() / 1e6:.2f} to "
        f"{impedance.max() / 1e6:.2f} MΩ\n"
        + "".join(
            f"- Largest tone at J1 without clipping, {low:.0f}–{high:.0f} Hz: "
            f"{tolerance * 1e3:.1f} mV peak (limited by `{node}`; "
            f"requirement {required * 1e3:.0f} mV)\n"
            for ((low, high), required), (tolerance, node)
            in zip(requirements.INTERFERENCE, nominal.interference)
        )
    )
    figures = "\n![Input and output waveforms]"
    if summary.count(figures) != 1:
        raise RuntimeError("analysis summary layout changed")
    summary = summary.replace(figures, impedance_line + figures)
    result.summary_md.write_text(
        summary
        + "\n\nGain is from J1 (`receiver_in`) to ADS1256 AIN0−AIN1 with PGA 1. "
        "The requirement is at least 2000 V/V everywhere in the specified "
        "band; `make verify` also checks it, |Z_in|, and noise at beta, "
        "temperature, and USB-voltage corners. The test source is 10 µV behind a 30 kΩ fixture that stands "
        "in for the externally tuned sensor. Coil tuning and damping are "
        "outside this receiver model.\n\n"
        "## Noise\n\n"
        f"Input-referred to the source EMF, integrated from {PASSBAND_HZ[0] / 1000:g} "
        f"to {PASSBAND_HZ[1] / 1000:g} kHz "
        "with ngspice `.noise`. The noise figure compares that total with "
        "the source resistance's thermal noise alone. The frequency CRB "
        f"uses the untuned coil's EMF-referred density at {SPOT_HZ:.0f} Hz "
        f"as a white floor, a {RECORD_S:g} s record at {FS_HZ / 1000:g} kSPS "
        f"after a {BLANK_S * 1000:.0f} ms blank, and T2* = "
        f"{coil['t2_star_s']:g} s. Compare it with the 1 nT target. "
        "An external tuned capacitor raises the FID and coil noise "
        "together, which lowers the receiver's share of the noise. The "
        "ADS1256 adds 10.7 µV RMS at PGA 1 and 30 kSPS with its buffer on, "
        "about 4.5 nV referred to J1. The transistor models omit 1/f noise "
        "and use a 10 Ω base resistance, so these are lower bounds to be "
        "checked on the bench.\n\n"
        + noise_table(netlist, coil)
        + "\n"
    )
    print(f"wrote {result.waveforms_png}")
    print(f"wrote {result.response_png}")
    print(f"wrote {result.summary_md}")
