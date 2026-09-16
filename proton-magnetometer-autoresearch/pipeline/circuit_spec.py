"""Machine-first circuit representation + SPICE characterization.

This module builds the candidate circuit specs (afe_spec) and runs their
SPICE characterization (simulate): complex H(f), EMF-referred noise
spectrum, ring-down tau from a polarization-pulse .tran, and the causal
impulse response h(t) from a .tran unit impulse (ground truth).

It does NOT score. Scoring is the single E2E evaluator pipeline/evaluate.py
(REDESIGN.md): candidate-shaped records -> the C estimator core -> J.
This module's main() is the CLI front end to that evaluator for the
reference candidates.

Candidate axes (all in the spec's meta): topology (tuned/untuned), parts
(e_amp/i_amp), gain staging, bandpass centering, coil geometry (coupled to
V0 -- E3 audit), the ESTIMATOR VARIANT (a C-core name; REDESIGN.md), and
the MCU/clock configuration.

Amplifier noise the ngspice-native way: voltage noise as a series resistor
R = e_n^2/(4kT) into a noiseless behavioral gain block; current noise as a
parallel resistor R = 4kT/i_n^2. Behavioral sources are noiseless, and
vendor PSpice macromodels often lose their noise sections in translation --
physical resistors are bulletproof.

Run:  python3 circuit_spec.py     (requires ngspice on PATH)
"""
import re
from pathlib import Path

import os
# Reproducibility (D11): pin single-threaded BLAS before numpy loads so
# LAPACK-backed numerics (ring-down fits, CRB solves) are run-to-run
# deterministic and the printed cards are byte-stable.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np

import crb
import fid

K_B = 1.380649e-23
T0 = 300.0
FS = 20_000.0
SWEEP = (100.0, FS / 2.0)          # .ac/.noise sweep to Nyquist
BLANKING_S = 0.2
RECORD_S = 1.5
T2_STAR = 1.5
RINGDOWN_BLANKING_FACTOR = 5.0     # blank until ring-down is 5 tau old

WORKDIR = Path("/tmp/poc_circuits")


def noise_resistance(e_n: float) -> float:
    """Series resistor whose Johnson noise equals e_n [V/rtHz]."""
    return e_n**2 / (4.0 * K_B * T0)


def input_resistance_for_i_n(i_n: float) -> float:
    """Parallel resistor whose Johnson current noise equals i_n:
    a resistor of value 4kT/i_n^2 in parallel injects i_n [A/rtHz] into the
    node it shunts (sqrt(4kT/R) = i_n by construction). Returns None if
    negligible (> 1 Gohm)."""
    r = 4.0 * K_B * T0 / i_n**2
    return r if r < 1e9 else None


# ---------------------------------------------------------------------------
# Candidate specs.  coil params feed fid.estimate_v0; e_n/i_n are datasheet
# values; tuned = series-resonant step-up (V_amp = Q * V0 at f0).
# --------------------------------------------------------------------------- #
def mfb_bandpass_components(scale: float = 1.0) -> list:
    """Multiple-feedback bandpass, f0 ~= 2.1 kHz, Q ~= 2.5, midband gain -5.
    `scale` multiplies all three resistors: f0 ~ 1/scale (B8's filter
    centering axis), Q and midband gain preserved."""
    return [
        {"name": "R1", "type": "R", "nodes": ["stage1", "nA"],
         "value": f"{1.7e3*scale:.6g}"},
        {"name": "R2", "type": "R", "nodes": ["nA", "0"],
         "value": f"{1.13e3*scale:.6g}"},
        {"name": "C1", "type": "C", "nodes": ["nA", "ninv"], "value": "22n"},
        {"name": "C2", "type": "C", "nodes": ["nA", "outbp"], "value": "22n"},
        {"name": "R3", "type": "R", "nodes": ["ninv", "outbp"],
         "value": f"{17e3*scale:.6g}"},
        {"name": "Ebp", "type": "E", "nodes": ["outbp", "0"],
         "value": "ninv 0 -1e5"},
    ]


def afe_spec(label, e_amp, i_amp, coil, tuned=False, preamp_gain=100.0,
             mfb_scale=1.0, wire_d_mm=None, winding_len_m=None,
             estimator="zoom", mcu=None) -> dict:
    """FID EMF -> [tuning C] -> amp-noise network -> ideal preamp
    (x preamp_gain) -> MFB bandpass -> AA RC -> ideal x10 -> adc.

    preamp_gain is a first-class candidate axis (B6): a tuned input with
    Q ~ 60 step-up saturates the ADC chain at the old x100 staging, and
    candidates that crank gain must be able to fail the clipping gate.

    V0/noise coupling (E3 audit finding 3, closing E6 finding 3): when
    wire_d_mm is given, r_coil and l_coil are DERIVED from the winding
    (n_turns, radius, wire gauge, axis length) via coil_model() -- the
    same geometry that sets V0 through estimate_v0 sets the noise
    drivers, so an optimizer cannot raise signal without paying winding
    resistance. Candidates that pass explicit r_coil/l_coil (the demo
    fixtures) keep them, but the optimizer's mutations use the derived
    path.
    """
    if coil.get("design_id"):
        from coil_design import current_coil
        expected = current_coil()
        if wire_d_mm is not None or any(
                coil.get(k) != v for k, v in expected.items() if k != "c_tune"):
            raise ValueError("Week3 hardware is fixed; only tuning capacitance may vary")
    if wire_d_mm is not None:
        derived = coil_model(n_turns=coil["n_turns"],
                             radius_m=coil["radius_m"],
                             wire_d_mm=wire_d_mm, b_pol=coil["b_pol"],
                             winding_len_m=winding_len_m)
        coil = dict(coil, r_coil=derived["r_coil"], l_coil=derived["l_coil"])
    en_r = noise_resistance(e_amp)
    comps = [
        {"name": "V1", "type": "V", "nodes": ["fid", "0"],
         "value": "DC 0 AC 1"},
        {"name": "Rcoil", "type": "R", "nodes": ["fid", "nc"],
         "value": f"{coil['r_coil']}"},
        {"name": "Lcoil", "type": "L", "nodes": ["nc", "nin"],
         "value": f"{coil['l_coil']}"},
    ]
    if tuned:
        # Series-resonant step-up: the tuning capacitor shunts the amp input
        # node to ground, so the coil EMF (in series with L and R_coil)
        # drives a loop through L and C; at parallel resonance the voltage
        # across Ctune is Q * V0 with Q = 2*pi*f0*L/R_coil (audit E6: the
        # earlier revision placed Ctune IN SERIES toward a high-Z amp tap,
        # where the only AC return is the 1.7 Mohm i_n resistor -- Q
        # collapsed to ~1e-3 and the "tuned" candidate had no step-up).
        comps.append({"name": "Ctune", "type": "C", "nodes": ["nin", "0"],
                      "value": f"{coil['c_tune']}"})
    else:
        comps.append({"name": "Rlead", "type": "R", "nodes": ["nin", "nq"],
                      "value": "1"})             # lead resistance
        comps.append({"name": "Cstray", "type": "C", "nodes": ["nin", "0"],
                      "value": "100p"})          # coil self-capacitance
    comps += [
        {"name": "Rnoise", "type": "R",
         "nodes": ["nin", "np"] if tuned else ["nq", "np"],
         "value": f"{en_r:.1f}"},
        {"name": "E1", "type": "E", "nodes": ["stage1", "0"],
         "value": f"np 0 {preamp_gain:g}"},
    ]
    rin = input_resistance_for_i_n(i_amp)
    if rin is not None:
        comps.append({"name": "Rin", "type": "R", "nodes": ["np", "0"],
                      "value": f"{rin:.3e}"})
    comps += mfb_bandpass_components(mfb_scale)
    comps += [
        {"name": "Raa", "type": "R", "nodes": ["outbp", "naa"],
         "value": "1k"},
        {"name": "Caa", "type": "C", "nodes": ["naa", "0"], "value": "22n"},
        {"name": "E2", "type": "E", "nodes": ["adc", "0"],
         "value": "naa 0 10"},
        # Polarization-coupled transient: 1 mA current pulse collapsing at
        # t = 0.4..0.5 ms (JPM-4: cut within ~400 us), injected in parallel
        # with the coil so the stored inductor current rings the input
        # network. Amplitude only sets the ring voltage; the measured
        # DECAY CONSTANT is what feeds the blanking requirement.
        {"name": "Ipol", "type": "I", "nodes": ["nc", "nin"],
         "value": "PWL(0 1m 0.4m 1m 0.5m 0 120m 0)"},
    ]
    # REDESIGN.md section 2: a candidate = circuit + estimator + MCU
    # config. The estimator names a C-core variant (fe_binding.ESTIMATORS);
    # mcu carries the capture tick and clock grade. Both are scored axes.
    mcu = mcu or {"tick_s": 8e-9, "clock_ppm": 0.5}
    return {
        "title": label,
        "meta": {"coil": coil, "e_amp": e_amp, "i_amp": i_amp,
                 "tuned": tuned, "preamp_gain": preamp_gain,
                 "estimator": estimator, "mcu": dict(mcu)},
        "components": comps,
        "control": [
            # dec 4000 (~0.6 Hz at 2.1 kHz): the .ac grid must resolve a
            # Q~60 tank (32 Hz BW) well enough that the unwrapped phase
            # and the impulse response h(t) = irfft(H) are faithful --
            # dec 400 left a residual -1.8 mHz grid artifact in the tuned
            # candidate's MC.
            f"ac dec 4000 {SWEEP[0]} {SWEEP[1]}",
            "print vm(adc)",
            "print vp(adc)",          # phase [deg]: complex H for causal filtering
            f"noise v(adc) V1 dec 4000 {SWEEP[0]} {SWEEP[1]} 1",
            "setplot noise1",
            "print inoise_spectrum",
            "setplot noise2",
            "print inoise_total",
            "tran 0.2m 120m",
            "print v(adc)",
        ],
    }


def _backend():
    """Import the shared SPICE backend (project root on sys.path even when
    this file runs as a script from pipeline/)."""
    import sys
    from pathlib import Path
    root = str(Path(__file__).resolve().parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    import backends.spice as _spice
    return _spice


def emit_netlist(spec: dict) -> str:
    """Aliases to the shared backend (A2); kept for fixture/test imports."""
    return _backend().emit_netlist(spec)


def run_ngspice(netlist: str) -> str:
    return _backend().run_ngspice(netlist, workdir=WORKDIR)


def parse_tables(stdout: str) -> dict:
    """Shared pagination-tolerant parser (A2 backend)."""
    return _backend().parse_tables(stdout)


def ringdown_tau(tab, t_min=1.5e-3):
    """Fit the ring-down decay constant from the transient envelope.

    Fail-closed (D5): if the envelope is still above the 2% floor at the
    END of the measured window, the fit only sees a TRUNCATED decay and
    its slope underestimates tau (a 400 ms tank measured over a 120 ms
    window fits tau = 149 ms). Returning the truncated value would let a
    catastrophic tank squeeze past the 5*tau < 0.5*T2* recovery gate, so
    an incomplete decay returns the 1 s ceiling instead -- the recovery
    gate then fails the candidate, which is the honest verdict for a
    ring the .tran window cannot even see finish."""
    t, v = tab
    m = t > t_min
    if m.sum() < 20:
        return 0.0
    t, env = t[m], np.abs(v[m])
    block = max(1, len(t) // 100)
    n_blk = len(t) // block
    be = env[:n_blk * block].reshape(n_blk, block).max(axis=1)
    bt = t[:n_blk * block].reshape(n_blk, block).mean(axis=1)
    keep = be > 0.02 * be.max()
    if keep.sum() < 5:
        return 0.0
    # Fail-closed: decay did not complete inside the window.
    if bt[keep][-1] >= 0.95 * t[-1]:
        return 1.0
    slope = np.polyfit(bt[keep], np.log(be[keep]), 1)[0]
    return float(np.clip(-1.0 / slope, 0.0, 1.0)) if slope < 0 else 0.0


def shape_transfer(ac_tab, freqs):
    """|H(f)| interpolated onto the record's FFT bins (held constant at the
    sweep edges)."""
    f_h, mag = ac_tab
    return np.interp(freqs, f_h, mag)


def simulate(spec: dict) -> dict:
    """Field-independent SPICE leg: run ngspice once, return the complex
    H(f), the EMF-referred noise spectrum, tau_ring, and the noise RMS
    columns. The B-sweep (B8) reuses one simulate() across the field
    range -- per-unit responses do not depend on B."""
    out = run_ngspice(emit_netlist(spec))
    return simulate_from_tabs(spec, parse_tables(out))


def simulate_from_tabs(spec: dict, tabs: dict) -> dict:
    """Build the simulation dict from already-parsed ngspice tables (the
    optimizer's evaluator runs ngspice itself for sim_status capture)."""
    ac_tab = tabs["vm(adc)"]
    n_tab = tabs["inoise_spectrum"]
    f_h, mag_h = ac_tab
    f_n, e_n = n_tab

    # Shaped noise PSD from SPICE: sigma_n^2 = integral e_n(f)^2 df over the
    # whole swept band to Nyquist (aliasing folding approximated by the
    # full-band integral; the AA pole at 7.2 kHz leaves a small residue).
    sigma2 = float(np.trapezoid(e_n**2, f_n)) if hasattr(np, "trapezoid") \
        else float(np.trapz(e_n**2, f_n))
    sigma_in = float(np.sqrt(sigma2))
    # In-band (500-3500 Hz) input-referred RMS: the SNR_rms convention
    # (architecture.md) uses the NOISE_BAND integral, NOT
    # the full sweep -- the two differ by ~5 dB and must never be
    # cross-compared (audit E6: the analog table quoted the full-sweep
    # sigma next to a "SNR_rms" label defined in-band).
    m_band = (f_n >= fid.NOISE_BAND[0]) & (f_n <= fid.NOISE_BAND[1])
    sigma_in_band = float(np.sqrt(np.trapezoid(e_n[m_band]**2, f_n[m_band])))

    # Ring-down from .tran -> required blanking, recovery gate.
    tau_ring = ringdown_tau(tabs["v(adc)"])
    blank_eff = max(BLANKING_S, RINGDOWN_BLANKING_FACTOR * tau_ring)

    # Complex transfer H(f) = |H| e^{j phi} from the .ac run (magnitude +
    # phase in degrees). The MC must apply the CAUSAL filter: convolve the
    # FID (which starts at t=0, inside the blanking window) with the
    # impulse response, THEN slice at blank_eff. Multiplying a record that
    # starts at blank_eff by |H| alone produced a spurious ~-3 mHz
    # "tank pull" (audit E6 round 2: the record-start discontinuity rings
    # the resonator; a causal tank ringed out long before blanking) --
    # an artifact an optimizer would have ground against.
    n_full = int(round((blank_eff + RECORD_S) * FS))
    n_blank = int(round(blank_eff * FS))
    n_rec = int(round(RECORD_S * FS))
    freqs_full = np.fft.rfftfreq(n_full, 1.0 / FS)

    # Causal-IR construction (E3 audit finding 1) -- GROUND TRUTH from
    # SPICE itself, no reconstruction: a second ngspice run replaces the
    # AC source with a unit-area impulse (amplitude 1/T = 20000 V held
    # for one sample period T = 50 us), zeroes the polarization-pulse
    # source, and runs .tran with `linearize` to resample the response
    # onto the exact 20 kS/s grid. That transient IR is the true analog
    # kernel -- all phase included -- with no reconstruction assumptions.
    #
    # History of this leg (each verified by probe):
    #   v1: log-spaced .ac mag+phase edge-held onto the rfft grid ->
    #       ~half the IR energy wrapped to negative times (not causal);
    #   v2: exact linear .ac grid + cepstral minimum-phase from |H|
    #       (scipy.signal.minimum_phase is UNUSABLE here: its output
    #       does not reproduce |H| -- 0.9 vs 12063 at f_L); the cepstral
    #       construction DOES reproduce |H| exactly but its K-K phase
    #       disagrees with SPICE's measured phase by ~65 deg at f_L (the
    #       vp convention is not the K-K phase), giving a +16.5 mHz
    #       systematic the real circuit does not have;
    #   v3 (this): .tran impulse response -- noiseless tank pull
    #       measured 0.01-0.03 mHz (vs 1.2 mHz wrapped / 16.5 mHz
    #       cepstral). Verified 100% of IR energy in the first 100 ms.
    T = 1.0 / FS
    ir_ctrl = [f"tran {T:g} {n_full * T:.6g} 0 10u",
               "linearize",
               "print v(adc)"]
    ir_spec = dict(spec)
    ir_comps = []
    for c in spec["components"]:
        c2 = dict(c)
        if c2["name"] == "V1":
            c2["value"] = (f"PWL(0 0 1n {1.0/T:.6g} {50e-6:.6g} {1.0/T:.6g} "
                           f"{50e-6 + 1e-9:.6g} 0 {(blank_eff + RECORD_S):.6g} 0)")
        if c2["name"] == "Ipol":
            c2["value"] = "DC 0"            # no polarization pulse here
        ir_comps.append(c2)
    ir_spec["components"] = ir_comps
    ir_spec["control"] = ir_ctrl
    out2 = run_ngspice(emit_netlist(ir_spec))
    tabs2 = parse_tables(out2)
    idx2, v2 = tabs2["v(adc)"]
    assert len(idx2) >= n_full, (len(idx2), n_full)
    h_t = np.asarray(v2[:n_full]) * T       # impulse-invariant scaling
    # IR energy concentration: the analog chain's memory is ms-scale
    # (tank tau ~ 11 ms), so the samples must carry their energy early.
    e_tot = float(np.sum(h_t ** 2))
    e_early = float(np.sum(h_t[:int(0.1 * FS)] ** 2))
    ir_causal_frac = e_early / max(e_tot, 1e-300)
    e_bins = np.interp(freqs_full, f_n, e_n)

    return dict(tabs=tabs, h_t=h_t, e_bins=e_bins, f_h=f_h, mag_h=mag_h,
                f_n=f_n, e_n=e_n, sigma_in=sigma_in,
                sigma_in_band=sigma_in_band, tau_ring=tau_ring,
                blank_eff=blank_eff, n_full=n_full, n_blank=n_blank,
                n_rec=n_rec, ir_causal_frac=ir_causal_frac)


# ---------------------------------------------------------------------------
# B8: operating-field sweep + per-band candidate family
# --------------------------------------------------------------------------- #
def coil_model(n_turns: int, radius_m: float, wire_d_mm: float,
               b_pol: float, winding_len_m: float = None) -> dict:
    """Physical solenoid winding model (E6 finding 3): ties V0's drivers
    (n_turns, radius) to the noise drivers (r_coil, l_coil) so an
    optimizer cannot raise signal without paying winding resistance.

    r_coil = rho_cu * N * mean_turn_length / wire_csa
    l_coil = mu0 * N^2 * A_bore / winding_len   (long-solenoid, fill=1)
    Defaults reproduce the tuned-candidate coil class at 1500 turns,
    3 cm bore, 0.2 mm wire.
    """
    rho_cu = 1.724e-8                      # ohm m, copper ~20 C
    wire_d = wire_d_mm * 1e-3
    csa = np.pi * (wire_d / 2.0) ** 2
    mean_turn = 2.0 * np.pi * (radius_m + wire_d / 2.0)
    r_coil = float(rho_cu * n_turns * mean_turn / csa)
    if winding_len_m is None:
        winding_len_m = n_turns * wire_d   # single-layer packing
    l_coil = 1.25663706e-6 * n_turns**2 * (np.pi * radius_m**2) / winding_len_m
    return dict(r_coil=float(r_coil), l_coil=float(l_coil), n_turns=n_turns,
                radius_m=radius_m, b_pol=b_pol)


def _spice_value_to_float(v) -> float:
    """Parse a SPICE value string ('2m', '56n', '1.7k', '120') to float."""
    v = str(v).strip().lower()
    scale = {"t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3,
             "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15, "": 1.0}
    for suf, sc in (("meg", 1e6), ("mil", 25.4e-6)):
        if v.endswith(suf):
            return float(v[:-len(suf)]) * sc
    unit = v[-1] if v[-1].isalpha() else ""
    return float(v[:-1] if unit else v) * scale.get(unit, 1.0)


def tolerance_sweep(spec: dict, k: int = 24, b_earth: float = 50e-6,
                    tol=None) -> dict:
    """B1: Monte-Carlo component-tolerance sweep in the SPICE layer.

    ngspice-native (.control loop + `alter` + `sgauss` + `setseed`; there
    is no `.step` in ngspice): ONE ngspice process perturbs every R/C/L
    by its tolerance, re-runs .ac (single point at f_L) and .noise
    (in-band integrated), and prints (gain at f_L, inoise_total) per
    iteration. Python recomputes the colored CRB per iteration from the
    perturbed gain/noise (the per-iteration estimator MC would multiply
    runtime by k) and reports the worst-case (p95) CRB -- the optimizer
    must survive its parts, not their nominal values.

    Tolerances (1-sigma in the sgauss call): R 0.5%, C 2.5%, L 5%,
    i.e. a 2-sigma tolerance of R 1%, C 5%, L 10% -- generic
    0603/X7R-class numbers.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from backends.spice import run_ngspice_status, parse_tables as _pt

    tol = tol or {"R": 0.005, "C": 0.025, "L": 0.05}
    coil = spec["meta"]["coil"]
    v0 = fid.estimate_v0(b_pol=coil["b_pol"], n_turns=coil["n_turns"],
                         coil_radius_m=coil["radius_m"], b_earth=b_earth)
    f_l = fid.larmor_hz(b_earth)
    n_rec = int(round(RECORD_S * FS))
    t_ax = BLANKING_S + np.arange(n_rec) / FS

    l_coil = _spice_value_to_float(coil["l_coil"])
    lines = ["* tolerance sweep wrapper"]
    for c in spec["components"]:
        lines.append(f"{c['name']} {' '.join(c['nodes'])} {c['value']}")
    lines.append(".control")
    lines.append("setseed 42")
    lines.append(f"let i = 0")
    lines.append(f"dowhile i < {k}")
    for name, val, t in (("R1", 1700.0, tol["R"]), ("R2", 1130.0, tol["R"]),
                         ("R3", 17000.0, tol["R"]),
                         ("Rcoil", float(coil.get("r_coil", 120)), tol["R"]),
                         ("C1", 22e-9, tol["C"]), ("C2", 22e-9, tol["C"]),
                         ("Lcoil", l_coil, tol["L"])):
        lines.append(f"  alter {name} = {val:.6g} * (1 + {t}*sgauss(0))")
    if spec["meta"].get("tuned"):
        c_t = _spice_value_to_float(coil["c_tune"])
        lines.append(f"  alter Ctune = {c_t:.6g} * (1 + {tol['C']}*sgauss(0))")
    # gain(f_L): single-point .ac; noise: full in-band spectrum per
    # iteration. Two ngspice quirks (E3-audit fixes):
    #   (a) noise2's inoise_total scalar is STALE inside a .control loop
    #       (the re-run updates noise1's spectrum, not the old scalar) --
    #       Python integrates each iteration's spectrum slice instead;
    #   (b) a re-run `noise` does NOT refresh the plots unless the old
    #       ones are destroyed first (without `destroy`, every iteration
    #       re-prints iteration 1's spectrum -- verified by probe).
    lines += [
        "  destroy all",
        f"  ac lin 1 {f_l:.4f} {f_l:.4f}",
        "  let gfl = vm(adc)",
        "  print gfl",
        "  noise v(adc) V1 dec 100 500 3500 1",
        "  setplot noise1",
        "  print inoise_spectrum",
        "  let i = i + 1",
        "end",
        ".endc",
        ".end",
    ]
    proc, _ = run_ngspice_status("\n".join(lines) + "\n", timeout_s=600)
    if proc.returncode != 0:
        return {"ok": False, "sim_status": proc.returncode,
                "stderr": proc.stderr[-400:]}

    # parse the K gains + K per-iteration in-band spectra
    text = proc.stdout
    gains = [float(m) for m in
             re.findall(r"gfl\s*=\s*([0-9.eE+-]+)", text)]
    tabs = parse_tables(text)
    if "inoise_spectrum" not in tabs:
        return {"ok": False, "detail": "no inoise_spectrum table parsed"}
    f_sp, e_sp = tabs["inoise_spectrum"]
    # every iteration prints the same 100 pts/decade grid over 500-3500
    # -> reshape the accumulated table into per-iteration spectra
    n_per = len(f_sp) // max(len(gains), 1)
    if n_per == 0 or len(gains) == 0:
        return {"ok": False, "detail": "spectrum rows misaligned"}
    n = min(len(gains), len(f_sp) // n_per)
    gains = gains[:n]
    if n < k // 2:
        return {"ok": False, "detail": f"only {n}/{k} iterations parsed"}

    # per-iteration colored CRB from the perturbed spectrum
    crbs = []
    for it in range(n):
        seg = slice(it * n_per, (it + 1) * n_per)
        f_i = f_sp[seg]
        e_i = e_sp[seg]
        # in-band EMF-referred RMS from the spectrum (trapezoid; the
        # sweep already runs 500..3500)
        sig2 = float(np.trapezoid(e_i ** 2, f_sp[seg]))
        v = crb.freq_crb_colored(t_ax, v0, f_l, T2_STAR, 0.0, FS,
                                 *fid.NOISE_BAND, float(np.sqrt(sig2)))
        crbs.append(v / fid.GAMMA_HZ_PER_NT)
    crbs = np.asarray(crbs)
    return {"ok": True, "k_parsed": n,
            "crb_median_nt": float(np.median(crbs)),
            "crb_p95_nt": float(np.percentile(crbs, 95)),
            "crb_max_nt": float(crbs.max()),
            "gain_fL_median": float(np.median(gains)),
            "gain_fL_p95": float(np.percentile(np.abs(gains), 95)),
            "note": "2-sigma component tolerances (R 1%, C 5%, L 10%)",
            }


def band_candidates(b_fields=(25e-6, 50e-6, 65e-6)) -> list:
    """Per-band candidate family (B8): for each field point, retune the
    input tank to f_L(band) and re-center the MFB bandpass (scale all
    three resistors: f0 ~ 1/k), gains re-staged for the tank step-up.
    Uses the fixed Week3 series-opposed sensing pair."""
    out = []
    for b in b_fields:
        f_l = fid.larmor_hz(b)
        from coil_design import current_coil
        cw = current_coil()
        c_tune = 1.0 / (2.0 * np.pi * f_l) ** 2 / cw["l_coil"]
        k = 2130.0 / f_l                       # MFB recentering factor
        label = (f"band {b*1e6:.0f} uT: tank {f_l:.0f} Hz, "
                 "JFET 1.4 nV, 0.1 pA")
        out.append((label, b, dict(
            e_amp=1.4e-9, i_amp=0.1e-12, tuned=True,
            preamp_gain=4.0, mfb_scale=k,
            coil=dict(cw, c_tune=c_tune))))
    return out


def reference_candidates() -> list:
    """The three reference candidates (one per candidate class) as
    afe_spec kwargs. The D8/D11 fixtures pin their E2E cards."""
    return [
        ("untuned + INA828-class (7 nV, 170 fA)",
         dict(e_amp=7e-9, i_amp=170e-15, tuned=False,
              coil=dict(r_coil=120, l_coil="2m", n_turns=530,
                        radius_m=0.015, b_pol=0.02))),
        ("untuned + TL072-class (18 nV)",
         dict(e_amp=18e-9, i_amp=10e-15, tuned=False,
              coil=dict(r_coil=120, l_coil="2m", n_turns=530,
                        radius_m=0.015, b_pol=0.02))),
        # Tuned candidate on the COUPLED coil (wire geometry derives
        # r_coil/l_coil, c_tune resonates the derived L at 50 uT): the
        # headline must be a winding that actually produces its V0 and
        # its noise (E3 finding 3 / post-redesign audit). 0.56 mm wire
        # over a 0.30 m axis -> r_coil ~ 20 ohm, l_coil ~ 26.6 mH, Q ~ 18.
        ("tuned series-resonant + JFET (1.4 nV, 0.1 pA)",
         dict(e_amp=1.4e-9, i_amp=0.1e-12, tuned=True, preamp_gain=4.0,
              wire_d_mm=0.56, winding_len_m=0.30,
              coil=dict(n_turns=1500, radius_m=0.030, b_pol=0.05,
                        c_tune="210n"))),
    ]


def _round_floats(o):
    """Recursively round floats to 12 significant digits (D11): the .tran
    impulse response's adaptive solver lands on ULP-level different
    internal grids run-to-run; byte-identity needs a stable textual form."""
    if isinstance(o, float) and o == o and o != float("inf"):
        return float(f"{o:.12g}")
    if isinstance(o, dict):
        return {k: _round_floats(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_round_floats(v) for v in o]
    return o


def _print_card(card):
    worst = card["bands"][[c["b_earth_uT"] for c in card["bands"]].index(
        card["worst_band_uT"])]
    g = " ".join(f"{k}:{'ok' if v else 'FAIL'}"
                 for k, v in worst["gates"].items())
    print(f"{card['spec']}  [estimator={card['estimator']}, "
          f"clock={card['mcu']['clock_ppm']}ppm]")
    print(f"  worst band {card['worst_band_uT']:.1f} uT: "
          f"V0={worst['v0_uV']:.2f}uV  "
          f"sigma_in(500-3500)={worst['sigma_in_band_uV']*1e3:.0f}nV  "
          f"gain(fL)={worst['gain_fl']:.0f}  "
          f"SNR_rms(in-band)={worst['snr_rms_band_db']:.1f}dB  "
          f"tau_ring={worst['tau_ring_ms']:.1f}ms")
    print(f"  CRB={worst['crb_nt']:.4f}nT  sigma_B={worst['rms_nt']:.4f}nT "
          f"({worst['rms_nt']/worst['crb_nt']:.2f}x CRB)  "
          f"gross={worst['gross']:.0%}  clip={worst['clip_margin']:.2f}")
    print(f"  gates: {g}")
    print(f"  J (worst band) = {card['J_nt']:.4f} nT   per-band: "
          + "  ".join(f"{b}={j:.4f}" for b, j in card["J_per_band"].items())
          + "\n")


def main():
    import json
    import sys
    import evaluate as ev

    from coil_design import current_candidates
    candidates = reference_candidates() if "--legacy" in sys.argv else current_candidates()
    dump_json = "--json" in sys.argv
    print(f"E2E evaluation of {'legacy' if '--legacy' in sys.argv else 'Week3'} candidates "
          f"(evaluate(): SPICE -> candidate-shaped records -> C estimator; "
          f"N_MC={ev.N_MC}, +/-{ev.MC_SIGMA_REL*100:.0f}% MC sigma; "
          f"J = worst-band sigma_B over 25-65 uT)\n")
    cards = []
    for label, kw in candidates:
        card = ev.evaluate(dict(kw, label=label))
        cards.append(card)
        _print_card(card)

    # The ZC ruling-out as an E2E result (REDESIGN.md section 2), scored
    # through the identical evaluator: on the thin-budget INA circuit the
    # zc variant fails the gross gate; on the fat-SNR tuned circuit the
    # score ranks it orders of magnitude off the bound.
    label, kw = candidates[0]
    zc_ina = ev.evaluate(dict(kw, label=label + " [zc variant]",
                              estimator="zc"),
                         b_fields=(50e-6,))
    zb = zc_ina["bands"][0]
    print(f"{zc_ina['spec']}: gross={zb['gross']:.0%}, J={zc_ina['J_nt']}\n")
    label, kw = candidates[2]
    zc_tuned = ev.evaluate(dict(kw, label=label + " [zc variant]",
                                estimator="zc"),
                           b_fields=(50e-6,))
    zb = zc_tuned["bands"][0]
    print(f"{zc_tuned['spec']}: sigma_B={zb['rms_nt']:.4f} nT "
          f"({zb['rms_nt']/zb['crb_nt']:.0f}x CRB, gross={zb['gross']:.0%}) "
          f"vs zoom {cards[2]['bands'][2]['rms_nt']:.4f} nT "
          f"on the identical circuit\n")

    if dump_json:
        # D8/D11 fixture: full E2E card per reference candidate, without
        # provenance (git SHA/tool versions are per-tree, not per-physics).
        rows = [{k: v for k, v in c.items() if k != "provenance"}
                for c in cards]
        print(json.dumps(_round_floats(rows), indent=1))

    if "--bsweep" in sys.argv:
        # Per-band candidate family (B8, model-consistent coil): each
        # family member at its own field point.
        print("per-band family (B8, model-consistent coil):")
        for label, b, kw in band_candidates():
            card = ev.evaluate(dict(kw, label=label), b_fields=(b,))
            band = card["bands"][0]
            print(f"  {label}: J = {card['J_nt']:.4f} nT "
                  f"(gain(fL)={band['gain_fl']:.0f}, "
                  f"clip={band['clip_margin']:.2f})")


if __name__ == "__main__":
    main()
