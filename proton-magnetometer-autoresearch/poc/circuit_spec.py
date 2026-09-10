"""Machine-first circuit representation demo: JSON spec -> ngspice -> nT score.

The auto-research loop needs a circuit format that is (a) trivially emitted
and diffed by code, (b) simulatable end-to-end, and (c) compilable to
buildable KiCad artifacts (that leg is SKiDL's job in the real pipeline --
same component/net graph, different backend). This demo implements (a)+(b)
with the audit-v0.0 fixes:

  * the SPICE .ac transfer H(f) shapes BOTH the signal and the noise (an
    earlier revision brick-walled noise in software and reduced the netlist
    to a scalar gain, so the score could not see topology);
  * candidates include a real bandpass and a tuned-input topology (the
    axis that can reorder which amplifier is optimal);
  * amplifier current noise is modeled too (a physical resistor
    R = 4kT/i_n^2 in parallel at the input), which matters once the tuned
    input lifts the source impedance by ~Q;
  * blanking/recovery is scored by an actual .tran run (polarization pulse
    -> ring-down -> measured decay constant), not just deleted samples;
  * V0 comes from fid.estimate_v0 (Curie-law coil model), not a chosen
    number;
  * ONE objective function J is implemented (sigma_B + fail-fast gates).

Amplifier noise the ngspice-native way: voltage noise as a series resistor
R = e_n^2/(4kT) into a noiseless behavioral gain block; current noise as a
parallel resistor R = 4kT/i_n^2. Behavioral sources are noiseless, and
vendor PSpice macromodels often lose their noise sections in translation --
physical resistors are bulletproof.

Run:  python3 circuit_spec.py     (requires ngspice on PATH)
"""
import re
import subprocess
from pathlib import Path

import numpy as np

import crb
import fid
import estimators

K_B = 1.380649e-23
T0 = 300.0
N_MC = 150
MC_SIGMA_REL = 1.0 / np.sqrt(2.0 * N_MC)
ADC_FS = 2.048
ADC_BITS = 16
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
    """Parallel resistor whose Johnson noise equals i_n through 1 ohm... i.e.
    a resistor of value 4kT/i_n^2 in parallel injects current noise i_n
    [A/rtHz]. Returns None if negligible."""
    r = 4.0 * K_B * T0 / i_n**2
    return r if r < 1e9 else None


# ---------------------------------------------------------------------------
# Candidate specs.  coil params feed fid.estimate_v0; e_n/i_n are datasheet
# values; tuned = series-resonant step-up (V_amp = Q * V0 at f0).
# --------------------------------------------------------------------------- #
def mfb_bandpass_components() -> list:
    """Multiple-feedback bandpass, f0 ~= 2.1 kHz, Q ~= 2.5, midband gain -5."""
    return [
        {"name": "R1", "type": "R", "nodes": ["stage1", "nA"], "value": "1.7k"},
        {"name": "R2", "type": "R", "nodes": ["nA", "0"], "value": "1.13k"},
        {"name": "C1", "type": "C", "nodes": ["nA", "ninv"], "value": "22n"},
        {"name": "C2", "type": "C", "nodes": ["nA", "outbp"], "value": "22n"},
        {"name": "R3", "type": "R", "nodes": ["ninv", "outbp"], "value": "17k"},
        {"name": "Ebp", "type": "E", "nodes": ["outbp", "0"],
         "value": "ninv 0 -1e5"},
    ]


def afe_spec(label, e_amp, i_amp, coil, tuned=False) -> dict:
    """FID EMF -> [tuning C] -> amp-noise network -> ideal in-amp (x100)
    -> MFB bandpass -> AA RC -> ideal x10 -> adc."""
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
        comps.append({"name": "Ctune", "type": "C", "nodes": ["nin", "nq"],
                      "value": f"{coil['c_tune']}"})
    else:
        comps.append({"name": "Rlead", "type": "R", "nodes": ["nin", "nq"],
                      "value": "1"})             # lead resistance
        comps.append({"name": "Cstray", "type": "C", "nodes": ["nin", "0"],
                      "value": "100p"})          # coil self-capacitance
    comps += [
        {"name": "Rnoise", "type": "R", "nodes": ["nq", "np"],
         "value": f"{en_r:.1f}"},
        {"name": "E1", "type": "E", "nodes": ["stage1", "0"],
         "value": "np 0 100"},
    ]
    rin = input_resistance_for_i_n(i_amp)
    if rin is not None:
        comps.append({"name": "Rin", "type": "R", "nodes": ["np", "0"],
                      "value": f"{rin:.3e}"})
    comps += mfb_bandpass_components()
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
    return {
        "title": label,
        "coil": coil, "e_amp": e_amp, "i_amp": i_amp, "tuned": tuned,
        "components": comps,
        "control": [
            f"ac dec 400 {SWEEP[0]} {SWEEP[1]}",
            "print vm(adc)",
            f"noise v(adc) V1 dec 400 {SWEEP[0]} {SWEEP[1]} 1",
            "setplot noise1",
            "print inoise_spectrum",
            "setplot noise2",
            "print inoise_total",
            "tran 0.2m 120m",
            "print v(adc)",
        ],
    }


def emit_netlist(spec: dict) -> str:
    lines = [spec["title"]]
    for c in spec["components"]:
        lines.append(f"{c['name']} {' '.join(c['nodes'])} {c['value']}")
    lines.append(".control")
    lines += spec["control"]
    lines.append(".endc")
    lines.append(".end")
    return "\n".join(lines) + "\n"


def run_ngspice(netlist: str) -> str:
    WORKDIR.mkdir(exist_ok=True)
    nl = WORKDIR / "afe.cir"
    nl.write_text(netlist)
    proc = subprocess.run(["ngspice", "-b", str(nl)],
                          capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"ngspice failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
    return proc.stdout


def parse_tables(stdout: str) -> dict:
    """Parse the (index, x, y) tables emitted by `print` in order of
    appearance: ac vm(adc), noise inoise_spectrum, tran v(adc).

    ngspice paginates long `print` tables, re-emitting the header every 50
    rows -- a repeated header with the SAME variable is a page break (keep
    appending), only a name change starts a new table."""
    tables, current = {}, None
    for line in stdout.splitlines():
        m = re.match(r"\s*Index\s+(?:frequency|time)\s+(\S+)", line)
        if m:
            current = m.group(1)
            if current not in tables:
                tables[current] = []
            continue
        # Header switches the sink; separators and non-numeric lines between
        # tables (--- rules, "Doing analysis", OP node listings) are simply
        # not rows. Only well-formed (index, x, y) rows are appended.
        if current is not None:
            cols = line.replace("\t", " ").split()   # rows carry a trailing tab
            if len(cols) >= 3:
                try:
                    tables[current].append((float(cols[1]), float(cols[2])))
                except ValueError:
                    pass
    out = {k: (np.array([p[0] for p in v]), np.array([p[1] for p in v]))
           for k, v in tables.items()}
    m_tot = re.search(r"inoise_total\s*=\s*([0-9.eE+-]+)", stdout)
    out["inoise_total"] = float(m_tot.group(1)) if m_tot else None
    return out


def ringdown_tau(tab, t_min=1.5e-3):
    """Fit the ring-down decay constant from the transient envelope."""
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
    slope = np.polyfit(bt[keep], np.log(be[keep]), 1)[0]
    return float(np.clip(-1.0 / slope, 0.0, 1.0)) if slope < 0 else 0.0


def shape_transfer(ac_tab, freqs):
    """|H(f)| interpolated onto the record's FFT bins (held constant at the
    sweep edges)."""
    f_h, mag = ac_tab
    return np.interp(freqs, f_h, mag)


def score(spec: dict) -> dict:
    """netlist -> ngspice (H, noise spectrum, ring-down) -> MC -> J."""
    out = run_ngspice(emit_netlist(spec))
    tabs = parse_tables(out)
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

    # Ring-down from .tran -> required blanking, recovery gate.
    tau_ring = ringdown_tau(tabs["v(adc)"])
    blank_eff = max(BLANKING_S, RINGDOWN_BLANKING_FACTOR * tau_ring)

    # Transfer onto FFT bins, then shape signal AND noise by H(f).
    coil = spec["coil"]
    v0 = fid.estimate_v0(b_pol=coil["b_pol"], n_turns=coil["n_turns"],
                         coil_radius_m=coil["radius_m"])
    f_l = fid.larmor_hz(50e-6)
    n_rec = int(round(RECORD_S * FS))
    freqs = np.fft.rfftfreq(n_rec, 1.0 / FS)
    h_bins = shape_transfer(ac_tab, freqs)
    e_bins = np.interp(freqs, f_n, e_n)

    rng0 = np.random.default_rng(7)
    # zoom_fit and zc_fit only: nlls_fit is the staged reference scored in
    # run_scoring.py (its zoom seeding makes it ~4x slower; it adds nothing
    # beyond zoom here, which already sits at 1.02x CRB).
    errs = {name: [] for name in ("zoom_fit", "zc_fit")}
    gross = {name: 0 for name in errs}
    peak_adc = 0.0
    lsb = ADC_FS / (2 ** ADC_BITS)
    for i in range(N_MC):
        phase = np.random.default_rng(20_000 + i).uniform(-np.pi, np.pi)
        t = blank_eff + np.arange(n_rec) / FS
        # EMF-domain signal, then through the netlist transfer H(f) (which
        # includes every stage's gain) to the ADC node.
        sig = v0 * np.exp(-t / T2_STAR) * np.sin(2 * np.pi * f_l * t + phase)
        sig_adc = np.fft.irfft(np.fft.rfft(sig) * h_bins, n_rec)
        # EMF-referred noise shaped by the SPICE inoise spectrum, then
        # through H(f) once more (e_in x |H| = onoise at the ADC node).
        w = rng0.normal(0.0, 1.0, n_rec)
        noise_emf = np.fft.irfft(np.fft.rfft(w) * e_bins, n_rec)
        rms = float(np.sqrt(np.mean(noise_emf**2)))
        if rms > 0:
            noise_emf *= sigma_in / rms
        noise_adc = np.fft.irfft(np.fft.rfft(noise_emf) * h_bins, n_rec)
        v_ad = np.round((sig_adc + noise_adc) / lsb) * lsb
        peak_adc = max(peak_adc, float(np.max(np.abs(v_ad))))
        rec = {"t": t, "v_adc": v_ad, "f_larmor": f_l, "fs": FS,
               "tau": T2_STAR}
        for name in errs:
            fh = estimators.ESTIMATORS[name](rec)
            if not np.isfinite(fh):
                gross[name] += 1
                fh = f_l + 10.0
            errs[name].append(fh - f_l)

    res = {"spec": spec["title"], "v0_uV": v0 * 1e6, "sigma_in_uV": sigma_in * 1e6,
           "gain_fl": float(np.interp(f_l, f_h, mag_h)),
           "tau_ring_ms": tau_ring * 1e3, "blank_eff_ms": blank_eff * 1e3,
           "snr_rms_db": 20 * np.log10((v0 / np.sqrt(2)) / sigma_in)}

    # Reference CRB: in-band noise density around f_L from the SPICE spectrum.
    band = (f_l - 300, f_l + 300)
    m = (f_n >= band[0]) & (f_n <= band[1])
    e_bar = float(np.sqrt(np.mean(e_n[m]**2))) if m.sum() else sigma_in / np.sqrt(fid.NOISE_BAND[1] - fid.NOISE_BAND[0])
    t_ax = blank_eff + np.arange(n_rec) / FS
    res["crb_nt"] = crb.freq_crb_colored(
        t_ax, v0, f_l, T2_STAR, 0.0, FS, fid.NOISE_BAND[0],
        fid.NOISE_BAND[1], e_bar * np.sqrt(fid.NOISE_BAND[1] - fid.NOISE_BAND[0])
    ) / fid.GAMMA_HZ_PER_NT

    # ONE objective function J (architecture.md section 0):
    #   J = sigma_B  [nT]   with fail-fast gates; no dead-time cost term
    #   (dead time is already inside sigma_B via the record start time).
    gates = {}
    for name in errs:
        rms_nt = float(np.sqrt(np.mean(np.square(errs[name])))) / fid.GAMMA_HZ_PER_NT
        g = float(np.mean(np.abs(errs[name]) > 1.0))
        res[f"rms_{name}"] = rms_nt
        res[f"gross_{name}"] = g
    res["clip_margin"] = peak_adc / (0.9 * ADC_FS / 2)
    gates["no_clipping"] = res["clip_margin"] < 1.0
    gates["recovery_inside_blanking"] = blank_eff < 0.5 * T2_STAR
    gates["gross_errors"] = res["gross_zoom_fit"] < 0.01
    res["gates"] = gates
    res["J_nt"] = res["rms_zoom_fit"] if all(gates.values()) else float("inf")
    return res


def main():
    candidates = [
        ("untuned + INA828-class (7 nV, 170 fA)",
         dict(e_amp=7e-9, i_amp=170e-15, tuned=False,
              coil=dict(r_coil=120, l_coil="2m", n_turns=530,
                        radius_m=0.015, b_pol=0.02))),
        ("untuned + TL072-class (18 nV)",
         dict(e_amp=18e-9, i_amp=10e-15, tuned=False,
              coil=dict(r_coil=120, l_coil="2m", n_turns=530,
                        radius_m=0.015, b_pol=0.02))),
        ("tuned series-resonant + JFET (1.4 nV, 0.1 pA)",
         dict(e_amp=1.4e-9, i_amp=0.1e-12, tuned=True,
              coil=dict(r_coil=20, l_coil="100m", c_tune="56n", n_turns=1500,
                        radius_m=0.030, b_pol=0.05))),
    ]
    print(f"Scoring AFE candidates from SPICE (N_MC={N_MC}, "
          f"+/-{MC_SIGMA_REL*100:.0f}% MC sigma; V0 from fid.estimate_v0; "
          f"H(f) shapes signal and noise)\n")
    rows = []
    for label, kw in candidates:
        spec = afe_spec(label, **kw)
        r = score(spec)
        rows.append(r)
        g = " ".join(f"{k}:{'ok' if v else 'FAIL'}" for k, v in r["gates"].items())
        print(f"{r['spec']}")
        print(f"  V0={r['v0_uV']:.2f}uV  sigma_in={r['sigma_in_uV']*1e3:.0f}nV  "
              f"gain(fL)={r['gain_fl']:.0f}  SNR_rms={r['snr_rms_db']:.1f}dB  "
              f"tau_ring={r['tau_ring_ms']:.1f}ms  blank_eff={r['blank_eff_ms']:.0f}ms")
        print(f"  CRB={r['crb_nt']:.4f}nT  zoom={r['rms_zoom_fit']:.4f}nT  "
              f"zc={r['rms_zc_fit']:.4f}nT  clip={r['clip_margin']:.2f}")
        print(f"  gates: {g}   J = {r['J_nt']:.4f} nT\n")


if __name__ == "__main__":
    main()
