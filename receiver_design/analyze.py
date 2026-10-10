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

PASSBAND_HZ = requirements.SIGNAL_BAND_HZ
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
# The AC sweep reaches past the ADS1256 modulator rate to show the
# anti-aliasing filter.
AC_STOP_HZ = 10e6
AC_POINTS_PER_DECADE = 200


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


def noise_table(netlist: Path, coil: dict, gain_min: float) -> str:
    text = netlist.read_text()
    if text.count(FIXTURE) != 1:
        raise RuntimeError("receiver deck is missing its unique source fixture")
    amplitudes = fid_amplitudes(coil)
    adc_density = requirements.adc_noise_density_v_rt_hz() / gain_min
    rows = [
        "| Source at J1 | Input noise at "
        f"{SPOT_HZ:.0f} Hz | {PASSBAND_HZ[0]:.0f}–{PASSBAND_HZ[1]:.0f} Hz "
        "input RMS | Noise figure | AIN0 RMS | Frequency CRB |",
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
            density = math.hypot(result.input_density_v_rt_hz, adc_density)
            band_rms = math.hypot(
                result.band_input_rms_v,
                adc_density * math.sqrt(PASSBAND_HZ[1] - PASSBAND_HZ[0]))
            if resistance is None:
                figure = "—"
            else:
                floor = math.sqrt(4 * K_B * T_SPICE_K * resistance
                                  * (PASSBAND_HZ[1] - PASSBAND_HZ[0]))
                figure = f"{20 * math.log10(band_rms / floor):.1f} dB"
            if is_coil:
                bounds = ", ".join(
                    f"{crb_nt(density, amplitude, coil['t2_star_s']):.3f} nT "
                    f"({amplitude * 1e6:.2f} µV {name})"
                    for name, amplitude in amplitudes
                )
            else:
                bounds = "—"
            rows.append(
                f"| {label} | {density * 1e9:.2f} nV/√Hz "
                f"| {band_rms * 1e9:.0f} nV | {figure} "
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
        ac_stop_hz=AC_STOP_HZ,
        ac_points_per_decade=AC_POINTS_PER_DECADE,
    )
    _, impedance = measure_input_impedance(
        netlist, source=requirements.SOURCE, node=requirements.INPUT_NODE,
        band_hz=requirements.ZIN_BAND_HZ,
    )
    summary = result.summary_md.read_text().rstrip()
    summary = re.sub(r"(?m)^- Intended passband:", "- Specified band:", summary)
    summary = re.sub(r"(?m)^(- Settled input peak:)", r"- Settled J1 input peak:", summary)
    summary, count = re.subn(r"(?m)^- Simulated -3 dB band: \d+ to (\d+) Hz$",
                             r"- Simulated low-pass -3 dB corner: \1 Hz", summary)
    if count != 1:
        raise RuntimeError("analysis summary layout changed")
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
        + f"- Alias rejection within {requirements.SIGNAL_BAND_HZ[1] / 1e3:g} kHz "
        f"of the {requirements.ADC_MODULATOR_HZ / 1e6:g} MHz modulator rate: "
        f"{nominal.alias_rejection_db:.1f} dB (requirement "
        f"{requirements.ALIAS_REJECTION_MIN_DB:.0f} dB)\n"
    )
    figures = "\n![Input and output waveforms]"
    if summary.count(figures) != 1:
        raise RuntimeError("analysis summary layout changed")
    summary = summary.replace(figures, impedance_line + figures)
    result.summary_md.write_text(
        summary
        + "\n\nGain is from J1 (`receiver_in`) through the AD8421 module "
        "(G = 100) and the two-section RC anti-aliasing filter to ADS1256 "
        "AIN0, with AIN1 at GND. The 11 kΩ filter resistance and the "
        "ADS1256's unbuffered input impedance lower the in-band gain to "
        "about 85 V/V. `make verify` checks |Z_in|, noise, interference, "
        "and alias rejection at temperature, supply, battery, trim, and "
        "tolerance corners. The test source is 10 µV behind a 30 kΩ fixture "
        "that stands in for the externally tuned sensor. Coil tuning and "
        "damping are outside this receiver model.\n\n"
        "## Noise\n\n"
        f"Input-referred to the source EMF, integrated from {PASSBAND_HZ[0] / 1000:g} "
        f"to {PASSBAND_HZ[1] / 1000:g} kHz "
        "with ngspice `.noise`, plus the ADS1256's "
        f"{requirements.ADC_NOISE_RMS_V * 1e6:.1f} µV RMS converter noise "
        "(PGA 1, 30 kSPS, buffer off) referred through the minimum in-band "
        f"gain, {requirements.adc_noise_density_v_rt_hz() / nominal.gain_min * 1e9:.2f} "
        "nV/√Hz. The noise figure compares the in-band total with the source "
        "resistance's thermal noise alone. The frequency CRB uses the "
        f"untuned coil's EMF-referred density at {SPOT_HZ:.0f} Hz as a white "
        f"floor, a {RECORD_S:g} s record at {FS_HZ / 1000:g} kSPS after a "
        f"{BLANK_S * 1000:.0f} ms blank, and T2* = {coil['t2_star_s']:g} s. "
        "Compare it with the 1 nT target. An external tuned capacitor raises "
        "the FID and coil noise together, which lowers the receiver's share "
        "of the noise. The AD8421 model uses the datasheet's maximum 3.2 "
        "nV/√Hz input voltage noise and typical 60 nV/√Hz output and 200 "
        "fA/√Hz current noise. It omits the module's BIAS/REF path noise, so "
        "measure the floor on the bench.\n\n"
        + noise_table(netlist, coil, nominal.gain_min)
        + "\n"
    )
    print(f"wrote {result.waveforms_png}")
    print(f"wrote {result.response_png}")
    print(f"wrote {result.summary_md}")
