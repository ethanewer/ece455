"""Simulate ltspice/AmplificationSim.asc with ngspice and write docs/simulation/.

Run `python3 -m util.simulate` (`make sim`). util/ltspice.py translates the
drawing, so the simulation follows the LTspice file with no hand-copied
netlist. Tuning values come from the KiCad bank and TuningCapacitors.xlsx,
and ADC settings from the firmware. All results are simulated, not measured.
"""
from __future__ import annotations

import csv
import itertools
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from util import coil, crb, design, physics, spice
from util.ltspice import Schematic, ngspice_deck, spice_number

OUTPUT = design.ROOT / "docs/simulation"
AC_RANGE_HZ = (100.0, 100e3)
POINTS_PER_DECADE = 100
PGA_SETTINGS = (1, 2, 4, 8, 16, 32, 64)

# Reference palette (dataviz skill): categorical slots 1-3, light surface.
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")


@dataclass(frozen=True)
class Source:
    amplitude_v: float
    frequency_hz: float
    tau_s: float


def fid_source(schematic: Schematic) -> Source:
    """Amplitude, frequency, and decay of the SINE source standing in for the FID."""
    value = schematic.elements[design.FID_SOURCE].value
    args = [spice_number(v) for v in value[value.index("(") + 1:value.rindex(")")].split()]
    theta = args[4] if len(args) > 4 else 0.0
    return Source(args[1], args[2], 1.0 / theta if theta else math.inf)


def nodes(schematic: Schematic) -> dict[str, str]:
    tank = next(n for n in schematic.elements[design.TANK].nodes if n != "0")
    return {"tank": tank, "stage1": schematic.node("U1", 5), "stage2": schematic.node("U2", 5),
            "j6": schematic.flags["VopAmpOut2"], "adc_p": schematic.flags[design.ADC_SIGNAL],
            "adc_n": schematic.flags[design.ADC_REFERENCE]}


def decks(schematic: Schematic) -> dict[float, str]:
    """One deck per value of the drawing's .step parameter (or one nominal deck)."""
    steps = schematic.steps
    if not steps:
        return {0.0: ngspice_deck(schematic, title="AmplificationSim", ac_source=design.FID_SOURCE)}
    (name, values), = steps.items()
    return {value: ngspice_deck(schematic, title=f"AmplificationSim, {name} = {value:g}",
                                params={name: value}, ac_source=design.FID_SOURCE)
            for value in values}


def tank_capacitance(schematic: Schematic) -> float:
    """Nominal tank capacitance: C1's value with .param values and every .step parameter at 0."""
    value = schematic.elements[design.TANK].value.strip()
    if not value.startswith("{"):
        return spice_number(value)
    expression = value.strip("{}")
    names = {**{name: spice_number(v) for name, v in schematic.params.items()},
             **{name: 0.0 for name in schematic.steps}}
    for name in sorted(names, key=len, reverse=True):
        expression = re.sub(rf"\b{name}\b", repr(names[name]), expression)
    if not re.fullmatch(r"[-+*/(). 0-9e]+", expression):
        raise ValueError(f"cannot evaluate {value}")
    return float(eval(expression))  # digits and arithmetic only, checked above


def resonance_hz(inductance_h: float, capacitance_f: float) -> float:
    return 1.0 / (2.0 * math.pi * math.sqrt(inductance_h * capacitance_f))


def bank_settings(bank) -> list[tuple[float, tuple]]:
    """Every switch combination with at least one capacitor: (total farads, capacitors)."""
    settings = []
    for chosen in itertools.product((False, True), repeat=len(bank)):
        on = tuple(c for c, used in zip(bank, chosen) if used)
        if on:
            settings.append((sum(c.farads for c in on), on))
    return settings


def tuning_rows(bank, inductances: dict[str, float], targets_hz: list[float]) -> list[dict]:
    settings = bank_settings(bank)
    rows = []
    for target in targets_hz:
        for source, inductance in inductances.items():
            required = 1.0 / ((2.0 * math.pi * target) ** 2 * inductance)
            total, on = min(settings, key=lambda s: abs(s[0] - required))
            rows.append(dict(
                target_hz=target, field_ut=physics.field_nt(target) / 1e3, coil=source,
                inductance_mh=inductance * 1e3, required_nf=required * 1e9, bank_nf=total * 1e9,
                tuned_hz=resonance_hz(inductance, total),
                capacitors=" ".join(c.ref for c in sorted(on, key=lambda c: -c.farads)),
                switches=" ".join(f"{c.switch}-{c.position}"
                                  for c in sorted(on, key=lambda c: (c.switch, c.position)))))
    return rows


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(True, which="major", color=GRID, linewidth=0.8)
    ax.grid(True, which="minor", color=GRID, linewidth=0.4, alpha=0.6)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK_2)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.xaxis.label.set_color(INK)
    ax.yaxis.label.set_color(INK)


def _save(fig, path: Path) -> None:
    fig.savefig(path, dpi=150, facecolor=SURFACE, metadata={"Software": None})


def write_csv(path: Path, header: list[str], rows) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def main(output: Path = OUTPUT) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output.mkdir(parents=True, exist_ok=True)
    schematic = design.amplifier()
    source = fid_source(schematic)
    probe = nodes(schematic)
    runs = decks(schematic)
    nominal = runs[0.0]
    step_name, step_values = next(iter(schematic.steps.items()), ("step", (0.0,)))
    constants = design.firmware_constants()
    band = (constants["EXPECTED_FREQ_MIN_HZ"], constants["EXPECTED_FREQ_MAX_HZ"])
    fs = constants["ADS_NOMINAL_SAMPLE_RATE"]
    full_scale = design.adc_full_scale_v()
    adc = f"v({probe['adc_p']})-v({probe['adc_n']})"
    (output / "amplifier.cir").write_text(
        "* Generated by `python3 -m util.simulate` from ltspice/AmplificationSim.asc.\n"
        f"* {step_name} = 0; {design.FID_SOURCE} carries AC 1 for gain and noise analyses.\n"
        + nominal)

    # Operating point, small-signal gain, and noise.
    op_nodes = [probe["stage1"], probe["stage2"], probe["j6"], probe["adc_p"], probe["adc_n"]]
    op = spice.operating_point(nominal, op_nodes)
    gain_expr = {"tank": f"vm({probe['tank']})", "stage1": f"vm({probe['stage1']})",
                 "stage2": f"vm({probe['stage2']})", "adc": f"mag({adc})"}
    report_hz = sorted({band[0], 2000.0, source.frequency_hz, band[1]})
    point_gain = {value: spice.ac_points(deck, gain_expr, report_hz) for value, deck in runs.items()}
    frequency, sweep = spice.ac(nominal, {k: f"db({v})" for k, v in gain_expr.items()},
                                start_hz=AC_RANGE_HZ[0], stop_hz=AC_RANGE_HZ[1],
                                points_per_decade=POINTS_PER_DECADE)
    corners = {value: spice.ac(deck, {"adc": f"db({adc})"}, start_hz=AC_RANGE_HZ[0],
                               stop_hz=AC_RANGE_HZ[1], points_per_decade=POINTS_PER_DECADE)[1]["adc"]
               for value, deck in runs.items() if value != 0.0}
    noise = spice.noise(nominal, output=probe["adc_p"], reference=probe["adc_n"],
                        source=design.FID_SOURCE, start_hz=AC_RANGE_HZ[0],
                        stop_hz=AC_RANGE_HZ[1], points_per_decade=POINTS_PER_DECADE)
    emf_density = float(np.interp(source.frequency_hz, noise.frequency_hz, noise.input_v_rt_hz))
    out_density = float(np.interp(source.frequency_hz, noise.frequency_hz, noise.output_v_rt_hz))
    nyquist_band = (AC_RANGE_HZ[0], fs / 2)
    band_rms = spice.band_rms(noise.frequency_hz, noise.output_v_rt_hz, band)
    wide_rms = spice.band_rms(noise.frequency_hz, noise.output_v_rt_hz, nyquist_band)

    # The FID transient from the drawing's .tran card.
    tran = schematic.directive(".tran").split()
    stop_s, drawn_step_s = spice_number(tran[2]), spice_number(tran[4])
    # At the drawing's step, trapezoidal integration detunes the Q = 10 tank
    # enough to understate the FID, so use at least 100 points per cycle.
    step_s = min(drawn_step_s, 0.01 / source.frequency_hz)
    time_s, wave = spice.transient(nominal, {"adc": adc}, stop_s=stop_s, step_s=step_s)
    _, coarse = spice.transient(nominal, {"adc": adc}, stop_s=0.1, step_s=drawn_step_s)
    coarse_peak = float(np.max(np.abs(coarse["adc"])))
    differential = wave["adc"]
    first = time_s <= 0.1
    initial_peak = float(np.max(np.abs(differential[first])))
    fitting = [pga for pga in PGA_SETTINGS
               if initial_peak <= 2.0 * constants["ADS_VREF"] / pga]

    # Frequency CRB for the firmware's capture of this FID.
    record_s = min(constants["MAX_CAPTURE_US"] * 1e-6,
                   source.tau_s * math.log(1.0 / constants["DECAY_STOP_FRACTION"]))
    t = np.arange(int(record_s * fs)) / fs
    bound_nt = crb.crb_nt(t, source.amplitude_v, source.frequency_hz, source.tau_s, 0.3,
                          emf_density * math.sqrt(fs / 2))

    # Tuning bank against the two coil inductances on record.
    bank = design.tuning_bank()
    l1, l2 = design.workbook_coil_inductances_h()
    coil_r, coil_l = design.simulated_coil()
    inductances = {"TuningCapacitors.xlsx": l1 + l2, "AmplificationSim.asc": coil_l}
    targets = sorted({band[0], 1750.0, 2000.0, source.frequency_hz, 2250.0, band[1]})
    rows = tuning_rows(bank, inductances, targets)
    bank_total = sum(c.farads for c in bank)
    tank_c = tank_capacitance(schematic)

    # FID amplitude and polarizer turn-off pickup from the coil design.
    plan = design.coil_plan()
    sensing_form = design.coil_form(design.SENSING_FORM)
    polarizing_form = design.coil_form(design.POLARIZING_FORM)
    sample_area = sensing_form.opening[0] * sensing_form.opening[1] * 1e-6
    gain_at_source = float(point_gain[0.0]["adc"][report_hz.index(source.frequency_hz)])
    field_per_amp = plan.polarizing_field_t / plan.polarizing_current_a
    current_slope = ((plan.clamp_v + plan.polarizing_current_a * plan.polarizing_resistance_ohm)
                     / plan.polarizing_inductance_h)
    fid_rows = []
    for sensing in design.sensing_coils():
        emf = 2 * physics.fid_emf(plan.polarizing_field_t, sensing.turns, sample_area,
                                  source.frequency_hz, plan.temperature_k)
        pickup = (2 * sensing.turns * field_per_amp
                  * coil.mean_turn_area_m2(plan.sensing, sensing.turns) * current_slope)
        fid_rows.append((sensing, emf, emf * gain_at_source, pickup))
    nest_fits = (sensing_form.flange[0] <= min(polarizing_form.opening)
                 and 2 * sensing_form.flange[1] <= max(polarizing_form.opening))

    # CSV outputs.
    write_csv(output / "frequency-response.csv",
              ["frequency_hz", "tank_db", "stage1_db", "stage2_db", "adc_db",
               *(f"adc_{step_name}_{value:+g}_db" for value in corners)],
              ([f"{f:.6g}", *(f"{sweep[k][i]:.5f}" for k in ("tank", "stage1", "stage2", "adc")),
                *(f"{corners[value][i]:.5f}" for value in corners)]
               for i, f in enumerate(frequency)))
    write_csv(output / "noise.csv", ["frequency_hz", "emf_referred_nv_rt_hz", "adc_uv_rt_hz"],
              ([f"{f:.6g}", f"{i * 1e9:.5f}", f"{o * 1e6:.5f}"]
               for f, i, o in zip(noise.frequency_hz, noise.input_v_rt_hz, noise.output_v_rt_hz)))
    window = time_s <= constants["PYTHON_PLOT_WINDOW_MS"] * 1e-3
    write_csv(output / "transient-first-10ms.csv", ["time_s", "adc_differential_mv"],
              ([f"{s:.6f}", f"{v * 1e3:.5f}"] for s, v in zip(time_s[window], differential[window])))
    write_csv(output / "tuning-bank.csv", list(rows[0]),
              ([f"{v:.4f}" if isinstance(v, float) else v for v in row.values()] for row in rows))

    # Figures.
    plt.rcParams.update({"font.size": 10, "svg.hashsalt": "simulation"})
    fig, (ax, bx) = plt.subplots(2, 1, figsize=(10, 8), sharex=True, constrained_layout=True,
                                 gridspec_kw={"height_ratios": [3, 2]})
    fig.patch.set_facecolor(SURFACE)
    for axis in (ax, bx):
        _style(axis)
        axis.axvspan(*band, color="#d9d8d3", alpha=0.45, linewidth=0)
        axis.axvline(source.frequency_hz, color=INK_2, linestyle=(0, (4, 3)), linewidth=1)
    curves = (("Tank (J5)", "tank", SERIES[0]), ("Stage 1 output", "stage1", SERIES[1]),
              ("ADC input, AIN1 − AIN3", "adc", SERIES[2]))
    for label, key, color in curves:
        ax.semilogx(frequency, sweep[key], color=color, linewidth=2, label=label)
        index = int(np.argmin(np.abs(frequency - 500.0)))
        ax.annotate(label, (frequency[index], sweep[key][index]), xytext=(0, 7),
                    textcoords="offset points", fontsize=9, color=INK, ha="center")
    for value, curve in corners.items():
        ax.semilogx(frequency, curve, color=SERIES[2], linewidth=1, linestyle=(0, (3, 2)),
                    label=f"ADC input, tank C {value:+.0%}")
    ax.set_ylabel("Gain from coil EMF (dB)")
    ax.set_title(f"Gain from the coil EMF ({design.FID_SOURCE}) with C1 = {tank_c * 1e9:g} nF; "
                 f"shaded: firmware band {band[0]:.0f}–{band[1]:.0f} Hz", color=INK, fontsize=11,
                 loc="left")
    ax.legend(loc="lower right", frameon=False, fontsize=9, labelcolor=INK)
    bx.loglog(noise.frequency_hz, noise.input_v_rt_hz * 1e9, color=SERIES[0], linewidth=2)
    bx.set_ylabel("Noise referred to\ncoil EMF (nV/√Hz)")
    bx.set_xlabel("Frequency (Hz)")
    bx.set_title(f"Input-referred noise; dashed line: {design.FID_SOURCE} at "
                 f"{source.frequency_hz:g} Hz", color=INK, fontsize=11, loc="left")
    _save(fig, output / "frequency-response.png")
    plt.close(fig)

    fig, (ax, bx) = plt.subplots(2, 1, figsize=(10, 7), constrained_layout=True)
    fig.patch.set_facecolor(SURFACE)
    for axis, mask, scale, unit in ((ax, slice(None), 1.0, "s"), (bx, window, 1e3, "ms")):
        _style(axis)
        axis.plot(time_s[mask] * scale, differential[mask] * 1e3, color=SERIES[0],
                  linewidth=0.6 if axis is ax else 1.5)
        for sign in (1, -1):
            axis.axhline(sign * full_scale * 1e3, color=INK_2, linestyle=(0, (4, 3)), linewidth=1)
        axis.text(1.0, full_scale * 1e3, f"±{full_scale * 1e3:.1f} mV full scale (PGA "
                  f"{constants['ADS_PGA']:.0f})", transform=axis.get_yaxis_transform(),
                  ha="right", va="bottom", fontsize=9, color=INK_2)
        axis.set_xlabel(f"Time ({unit})")
        axis.set_ylabel("AIN1 − AIN3 (mV)")
    ax.set_title(f"ADC input for a {source.amplitude_v * 1e6:g} µV, {source.frequency_hz:g} Hz FID "
                 f"(τ = {source.tau_s:.2f} s), C1 = {tank_c * 1e9:g} nF", color=INK, fontsize=11,
                 loc="left")
    bx.set_title(f"First {constants['PYTHON_PLOT_WINDOW_MS']:g} ms, the window the firmware "
                 "sends for plotting", color=INK, fontsize=11, loc="left")
    _save(fig, output / "transient.png")
    plt.close(fig)

    # Summary.
    def gain_cells(value, key):
        return " | ".join(f"{g:,.1f} ({20 * math.log10(g):.1f} dB)" for g in point_gain[value][key])

    lines = [
        "# Amplifier simulation",
        "",
        "Generated by `python3 -m util.simulate` (`make sim`) from "
        "[`ltspice/AmplificationSim.asc`](../../ltspice/AmplificationSim.asc) with ngspice. "
        "Do not edit by hand. Values are simulated, not measured.",
        "",
        "`util/ltspice.py` reads the drawing's wires, flags, and symbols and writes "
        "[`amplifier.cir`](amplifier.cir). Its `universalopamp2` subcircuit reproduces LTspice's "
        "UniversalOpAmp2 (level 2) model; on 2026-10-28 it matched LTspice 17.2.4 to within "
        "0.001 dB in gain from 1 to 5 kHz (0.03 dB at 20 kHz) and 0.01% in noise for this "
        "circuit (`util/tests/test_ltspice.py`). "
        "The output current limit (Ilimit) is not modeled.",
        "",
        "## Circuit as drawn",
        "",
        f"- Coil: {design.FID_SOURCE} `{schematic.elements[design.FID_SOURCE].value}` in series "
        f"with {coil_r:g} Ω and {coil_l * 1e3:g} mH. The FID is "
        f"{source.amplitude_v * 1e6:g} µV peak at {source.frequency_hz:g} Hz "
        f"({physics.field_nt(source.frequency_hz) / 1e3:.2f} µT), decaying with τ = "
        f"{source.tau_s:.2f} s.",
        f"- Tank: C1 = `{schematic.elements[design.TANK].value}`, {tank_c * 1e9:g} nF nominally"
        + (f", with {step_name} stepped through {', '.join(f'{v:+g}' for v in step_values)}. "
           if schematic.steps else ". ")
        + 
        f"The drawing notes that {1e9 / ((2 * math.pi * source.frequency_hz) ** 2 * coil_l):.1f} nF "
        "would resonate exactly at the source frequency.",
        "- Two non-inverting stages, each 1 + 50 kΩ / 1 kΩ = 51, biased at 2.5 V and AC coupled "
        "(C5 4.6 nF / R9 33 kΩ, then C6 18 nF / R12 33 kΩ). R14/C8, R15/C9, R1/C3, and R13/C7 "
        "model op-amp and ADS1256 input impedance rather than parts.",
        f"- {', '.join(sorted(schematic.unconnected))} is drawn but not connected, so it is not "
        "simulated." if schematic.unconnected else "",
        "",
        "## Operating point",
        "",
        "Node | DC level",
        "--- | ---",
        f"Stage 1 output (`{probe['stage1']}`) | {op[probe['stage1']]:.4f} V",
        f"Stage 2 output (`{probe['stage2']}`) | {op[probe['stage2']]:.4f} V",
        f"J6 (`{probe['j6']}`, after C6/R12) | {op[probe['j6']]:.4f} V",
        f"ADC signal input (`{probe['adc_p']}`) | {op[probe['adc_p']]:.4f} V",
        f"ADC reference input (`{probe['adc_n']}`, AIN3 in the drawing) | {op[probe['adc_n']]:.4f} V",
        "",
        "## Gain from the coil EMF",
        "",
        "Node | " + " | ".join(f"{f:g} Hz" for f in report_hz),
        "--- | " + " | ".join("---" for _ in report_hz),
        f"Tank (J5) | {gain_cells(0.0, 'tank')}",
        f"Stage 1 output | {gain_cells(0.0, 'stage1')}",
        f"Stage 2 output | {gain_cells(0.0, 'stage2')}",
        f"ADC input, AIN1 − AIN3 | {gain_cells(0.0, 'adc')}",
        *(f"ADC input, tank C {value:+.0%} | {gain_cells(value, 'adc')}"
          for value in point_gain if value != 0.0),
        "",
        "![Frequency response and noise](frequency-response.png)",
        "",
        "## FID amplitude",
        "",
        "[`spreadsheets/CoilDesign.xlsx`](../../spreadsheets/CoilDesign.xlsx) plans the coils, and "
        "the print files in [`3d_models/`](../../3d_models/) give their forms "
        "(`util/printfile.py` measures them from the G-code):",
        "",
        f"- Sensing form: {sensing_form.core[0]:g} × {sensing_form.core[1]:g} mm core, "
        f"{sensing_form.opening[0]:g} × {sensing_form.opening[1]:g} mm opening for the water, "
        f"{sensing_form.winding_length:g} mm winding length, {sensing_form.flange[0]:g} × "
        f"{sensing_form.flange[1]:g} mm flanges, {sensing_form.height:g} mm tall. Planned winding: "
        f"{plan.sensing_turns} turns of {plan.sensing.wire_od_m * 1e3:g} mm wire.",
        f"- Polarizing form: {polarizing_form.core[0]:g} × {polarizing_form.core[1]:g} mm core, "
        f"{polarizing_form.opening[0]:g} × {polarizing_form.opening[1]:g} mm opening, "
        f"{polarizing_form.winding_length:g} mm winding length. Planned winding: "
        f"{plan.polarizing_turns} turns, {plan.polarizing_current_a:g} A, "
        f"{plan.polarizing_field_t * 1e3:.2f} mT at the center, "
        f"{plan.polarizing_inductance_h * 1e3:.2f} mH, {plan.polarizing_resistance_ohm:.2f} Ω.",
        (f"- Two sensing forms fit side by side in the polarizing form's opening, with their "
         f"windings over the same {polarizing_form.winding_length:g} mm, so the forms appear made "
         "to nest, the sensing coils sharing the polarizing coil's axis." if nest_fits else
         "- The sensing forms do not fit inside the polarizing form."),
        "",
        f"Curie-law FID for the two sensing coils in series, each around water that fills its "
        f"opening, fully polarized at {plan.polarizing_field_t * 1e3:.2f} mT, with the polarizing "
        f"axis perpendicular to Earth's field, at {source.frequency_hz:g} Hz and "
        f"{plan.temperature_k - 273.15:.0f} °C. \"At the ADC\" applies the simulated gain at that "
        f"frequency ({gain_at_source:,.0f} V/V); the last column is the open-circuit voltage the "
        "polarizer's turn-off induces in the pair (below).",
        "",
        "Sensing coil | Turns per coil | L per coil | R per coil | FID at the pair | At the ADC "
        "| Peak / wideband noise | Turn-off pickup",
        "--- | --- | --- | --- | --- | --- | --- | ---",
        *(f"{s.label} | {s.turns} | {s.inductance_h * 1e3:.1f} mH | {s.resistance_ohm:.1f} Ω "
          f"| {emf * 1e6:.2f} µV | {adc_peak * 1e3:.0f} mV | {adc_peak / wide_rms:.0f} "
          f"| {pickup:.0f} V" for s, emf, adc_peak, pickup in fid_rows),
        "",
        f"The measured inductances ({l1 * 1e3:g} and {l2 * 1e3:g} mH) and the drawing's "
        f"{coil_r:g} Ω coil resistance both imply about {fid_rows[2][0].turns}–"
        f"{fid_rows[1][0].turns} turns per coil, not {plan.sensing_turns}. The drawing's "
        f"{source.amplitude_v * 1e6:g} µV is {source.amplitude_v / fid_rows[0][1]:.1f} times the "
        f"planned estimate and {source.amplitude_v / fid_rows[1][1]:.1f} times the as-built one; "
        "the workbook's 72 µV \"illustrative series-pair peak\" is scaled from an assumed "
        "baseline, not a physical prediction. Each assumption above is a best case: a partly "
        "filled opening, incomplete polarization (water's T1 is about 2–3 s), a polarizing axis "
        "not perpendicular to Earth's field, and the coils' finite length all lower the FID.",
        "",
        f"Turn-off pickup: when the polarizer's current falls into its TVS (the workbook assumes "
        f"{plan.clamp_v:g} V), it starts falling at {current_slope:,.0f} A/s and reaches zero in "
        f"about {plan.turnoff_s * 1e3:.2f} ms. For nested coils the induced EMF is about turns × "
        "field per amp × mean turn area × that rate, using the polarizer's center field. The sensing coils "
        "sit off center, where the field is weaker, so the real voltage is lower but of the same "
        "order. The sensing circuit, the damping switch, and the amplifier input must survive it.",
        "",
        "## ADC headroom",
        "",
        f"The firmware sets PGA {constants['ADS_PGA']:.0f} with VREF = {constants['ADS_VREF']:g} V, "
        f"a differential full scale of ±{full_scale * 1e3:.1f} mV. The drawing's FID reaches "
        f"{initial_peak * 1e3:.1f} mV peak at the ADC in its first 100 ms, "
        f"{initial_peak / full_scale:.1f} times full scale"
        + (". It would clip." if initial_peak > full_scale else ", which fits.")
        + (f" PGA {max(fitting)} or lower keeps it within full scale."
           if fitting else " No PGA setting keeps it within full scale.")
        + " The Curie-law estimates above reach "
        + ", ".join(f"{adc_peak * 1e3:.0f} mV ({s.label.split(' (')[0]}, "
                    f"{'clips' if adc_peak > full_scale else 'fits'})"
                    for s, _emf, adc_peak, _pickup in fid_rows)
        + "." + " The ADS1256 input buffer is on (BUFEN = 1), so each input must also stay within "
        "0 to AVDD − 2 V. The firmware measures AIN1 − AIN0, while the drawing biases AIN3; "
        "confirm which ADS1256 inputs the J4 socket reaches.",
        "",
        f"The transient runs to {stop_s:g} s as the drawing's `.tran` does, but with a "
        f"{step_s * 1e6:.1f} µs step. At the drawing's {drawn_step_s * 1e6:g} µs maximum step, about "
        f"{1 / (drawn_step_s * source.frequency_hz):.0f} points per cycle, trapezoidal integration "
        f"detunes the tank and the same FID peaks at {coarse_peak * 1e3:.1f} mV, "
        f"{(1 - coarse_peak / initial_peak):.0%} low. Use a maximum step near "
        f"{step_s * 1e6:.0f} µs in LTspice too.",
        "",
        "![FID at the ADC](transient.png)",
        "",
        "## Noise",
        "",
        f"- Referred to the coil EMF at {source.frequency_hz:g} Hz: {emf_density * 1e9:.2f} nV/√Hz. "
        f"At the ADC input: {out_density * 1e6:.2f} µV/√Hz.",
        f"- ADC-input RMS noise over {band[0]:.0f}–{band[1]:.0f} Hz: {band_rms * 1e6:.0f} µV; over "
        f"{nyquist_band[0]:.0f} Hz to {nyquist_band[1]:.0f} Hz (Nyquist at the firmware's nominal "
        f"{fs / 1e3:g} kSPS): {wide_rms * 1e6:.0f} µV. The zero-crossing estimator does not filter, "
        "so the wider figure applies to it. Noise above Nyquist also aliases into the record; "
        "the ADS1256's digital filter is not modeled.",
        f"- Peak FID to wideband RMS noise at the ADC: {initial_peak / wide_rms:,.0f} for the "
        "drawing's FID; the FID amplitude table gives it for the Curie-law estimates.",
        f"- Frequency Cramér–Rao bound: {bound_nt:.4f} nT, for a white floor at the EMF-referred "
        f"density, {fs / 1e3:g} kSPS, and a {record_s:.2f} s record (the firmware stops when the "
        f"signal falls to {constants['DECAY_STOP_FRACTION']:.0%} of its initial amplitude, at most "
        f"{constants['MAX_CAPTURE_US'] * 1e-6:g} s). It bounds an ideal estimator, not the "
        "zero-crossing fit.",
        "",
        "## Tuning bank",
        "",
        f"The signal board switches {len(bank)} capacitors across the coil with SW1 and SW2: "
        + ", ".join(f"{c.ref} {c.farads * 1e9:g} nF ({c.switch}-{c.position})" for c in bank)
        + f", {bank_total * 1e9:.2f} nF in total. TuningCapacitors.xlsx uses a "
        f"{design.workbook_bank_total_f() * 1e9:.2f} nF bank total in its reference row"
        + (", which does not match the schematic." if abs(design.workbook_bank_total_f() - bank_total)
           > 1e-12 else ".")
        + f" The workbook's coils are {l1 * 1e3:g} mH and {l2 * 1e3:g} mH in series "
        f"({(l1 + l2) * 1e3:.2f} mH, mutual inductance neglected); the LTspice coil is "
        f"{coil_l * 1e3:g} mH. With every switch on, the tank resonates at "
        + " and ".join(f"{resonance_hz(value, bank_total):.0f} Hz ({name})"
                       for name, value in inductances.items())
        + f". With {coil_r:g} Ω of coil resistance the tank's Q is about "
        f"{math.sqrt(coil_l / tank_c) / coil_r:.0f}, so its bandwidth near "
        f"{source.frequency_hz:g} Hz is about "
        f"{source.frequency_hz * coil_r / math.sqrt(coil_l / tank_c):.0f} Hz, far wider than "
        f"the {min(c.farads for c in bank) * 1e9:g} nF step.",
        "",
        "Switch settings closest to each target (`SW2-1` is switch 1 of SW2):",
        "",
        "Target | Field | Coil | Needed | Bank | Tuned | Capacitors on | Switches on",
        "--- | --- | --- | --- | --- | --- | --- | ---",
        *(f"{r['target_hz']:g} Hz | {r['field_ut']:.2f} µT | {r['coil']} ({r['inductance_mh']:.2f} mH)"
          f" | {r['required_nf']:.2f} nF | {r['bank_nf']:.2f} nF | {r['tuned_hz']:.1f} Hz"
          f" | {r['capacitors']} | {r['switches']}" for r in rows),
        "",
        "Fields use the shielded-proton ratio, 0.0425764 Hz/nT. The firmware and the workbook use "
        "the free-proton ratio, 25.7 ppm higher (`util/physics.py`).",
        "",
        "Files: [`frequency-response.csv`](frequency-response.csv), [`noise.csv`](noise.csv), "
        "[`transient-first-10ms.csv`](transient-first-10ms.csv), "
        "[`tuning-bank.csv`](tuning-bank.csv).",
    ]
    (output / "README.md").write_text("\n".join(line for line in lines if line is not None) + "\n")
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
