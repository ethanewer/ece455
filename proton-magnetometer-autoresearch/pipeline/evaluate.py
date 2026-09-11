"""The single E2E evaluator (REDESIGN.md section 4).

One candidate = one circuit spec + one estimator implementation + one MCU
configuration. `evaluate(candidate)` is the ONLY function in this
repository that produces a J; the optimizer (optimizer/eval_one.py), the
CLI (pipeline/circuit_spec.py), and the CI fixtures all call it.

Every J-producing path includes:

  1. SPICE characterization of THE CANDIDATE (circuit_spec.simulate):
     complex H(f), EMF-referred noise spectrum, ring-down tau from .tran,
     and the causal impulse response h(t) from a .tran unit impulse
     (ground truth, no reconstruction);
  2. record synthesis FROM THE CANDIDATE (fid.synthesize_adc_record):
     FID(V0(B), f_L(B)) convolved with h(t) from t=0, noise shaped by the
     candidate's own spectrum through H, ADC rails + quantization;
  3. estimation by the C core (fe_binding -- byte-identical to what ships
     to the MCU; the estimator axis is a candidate attribute, variants
     live in firmware/core/, never in Python);
  4. the candidate's MCU/clock configuration (timestamp quantization is
     reported and asserted negligible; clock ppm is a deterministic scale
     bias, reported in nT, never folded into sigma_B);
  5. the score: J = worst-band RMS sigma_B over the operating field range
     (25-65 uT), with fail-fast gates (clipping / ring-down / gross
     errors / rail-ripple), the colored CRB for context, and provenance
     (git SHA, tool versions, seeds, spec hash, FIRMWARE HASH).

There is no generic front end anywhere in this path. The C-core unit
regressions (firmware/host/, tests/test_estimator_reference.py) exercise
the estimator on synthetic vectors without a candidate -- they are bound-
tracking checks of the estimator build, NOT design scores.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import circuit_spec as cs  # noqa: E402
import crb  # noqa: E402
import fe_binding  # noqa: E402
import fid  # noqa: E402

N_MC = 150
MC_SIGMA_REL = 1.0 / np.sqrt(2.0 * N_MC)          # ~5.8% on sigma
GROSS_HZ = 1.0                                     # gross-error bar
ADC_FS = 2.048
ADC_BITS = 16
# Operating field range (B8/E3): the mission spans 25-65 uT; J is the
# WORST cycle over the sweep, never a single field point.
B_SWEEP = (25e-6, 37.5e-6, 50e-6, 62e-6, 65e-6)

# Default MCU/clock configuration (the candidate axis): RP2040-class 8 ns
# capture tick and a +-0.5 ppm TCXO. The tick's timestamp quantization is
# ~1e-4 of a sample period (asserted negligible); the clock ppm is a
# deterministic scale error, reported as bias, never folded into sigma.
DEFAULT_MCU = {"tick_s": 8e-9, "clock_ppm": 0.5}


def provenance(n_mc: int = N_MC) -> dict:
    """Stamp git SHA + tool versions + seeds + firmware hash into the card
    (REDESIGN.md: the firmware hash proves which estimator build produced
    the number; the optimizer cannot change J without changing either the
    circuit or the shipped code)."""
    root = Path(__file__).resolve().parent.parent

    def git_sha():
        try:
            return subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=str(root),
                capture_output=True, text=True, timeout=5).stdout.strip()
        except Exception:
            return "unknown"

    def ngspice_version():
        try:
            out = subprocess.run(["ngspice", "--version"],
                                 capture_output=True, text=True, timeout=5)
            for line in (out.stdout + out.stderr).splitlines():
                if "ngspice" in line.lower():
                    return line.strip().split()[1]
        except Exception:
            return "unknown"
        return "unknown"

    return {
        "git_sha": git_sha(),
        "ngspice": ngspice_version(),
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "firmware_sha256": fe_binding.firmware_sha256(),
        "mc_seeds": "phase=20000+i, noise rng=7, N_MC=%d" % n_mc,
    }


def spec_hash(spec: dict) -> str:
    """Hash of the FULL candidate: netlist + estimator + MCU config."""
    est = spec["meta"].get("estimator", "zoom")
    mcu = spec["meta"].get("mcu", DEFAULT_MCU)
    blob = (cs.emit_netlist(spec)
            + json.dumps({"estimator": est, "mcu": mcu}, sort_keys=True))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def score_band(sim: dict, spec: dict, b_earth: float,
               n_mc: int = N_MC) -> dict:
    """E2E score at one Earth-field point: candidate-shaped records -> the
    C estimator -> RMS sigma_B + gates. V0 and f_L both scale with b_earth
    through the transducer model; the SPICE characterization (sim) is
    per-unit and reused across the sweep."""
    f_n, e_n = sim["f_n"], sim["e_n"]
    sigma_in = sim["sigma_in"]
    sigma_in_band = sim["sigma_in_band"]
    tau_ring = sim["tau_ring"]
    blank_eff = sim["blank_eff"]
    h_t = sim["h_t"]
    e_bins = sim["e_bins"]

    estimator = spec["meta"].get("estimator", "zoom")
    mcu = spec["meta"].get("mcu", DEFAULT_MCU)

    coil = spec["meta"]["coil"]
    v0 = fid.estimate_v0(b_pol=coil["b_pol"], n_turns=coil["n_turns"],
                         coil_radius_m=coil["radius_m"], b_earth=b_earth)
    f_l = fid.larmor_hz(b_earth)

    # Rail-ripple stress (REDESIGN.md section 4: gates come from the C
    # records): the 100 dB-PSRR-referred buck ripple (50 mV at 2 kHz ->
    # 0.5 uV at the EMF) is INJECTED into a second MC pass through the
    # same candidate response. The ripple and the FID see DIFFERENT gain
    # (the candidate's H(f) shapes both) -- a fixed 2.1 kHz tank
    # near-peak-amplifies a 2 kHz ripple while the FID sits off-resonance
    # at the band edges, which the old V0-vs-0.5 uV proxy could not see.
    ripple = (2000.0, 50.0e-3 * 10.0 ** (-100.0 / 20.0))   # (Hz, V at EMF)
    # In-band tone robustness (reported, not gated): the 30th harmonic of
    # 60 Hz mains at 1.8 kHz, -20 dB relative to V0 at the EMF.
    tone = (1800.0, 0.1 * v0)

    rng0 = np.random.default_rng(7)
    errs, errs_ripple, errs_tone = [], [], []
    peak_adc = 0.0
    n_clip_tot = 0
    for i in range(n_mc):
        phase = np.random.default_rng(20_000 + i).uniform(-np.pi, np.pi)
        w = rng0.normal(0.0, 1.0, len(h_t))
        v_adc, n_clip, peak = fid.synthesize_adc_record(
            v0, f_l, cs.T2_STAR, h_t, e_bins, sigma_in, phase,
            noise_w=w, blank_s=blank_eff, fs=cs.FS,
            adc_bits=ADC_BITS, adc_fs=ADC_FS)
        peak_adc = max(peak_adc, peak)
        n_clip_tot += n_clip
        fh = fe_binding.estimate(estimator, v_adc, cs.FS, blank_eff)
        if not np.isfinite(fh):
            fh = f_l + 10.0 * GROSS_HZ
        errs.append(fh - f_l)
        # Paired record + the referred ripple tone (same realization).
        v_rip, _, _ = fid.synthesize_adc_record(
            v0, f_l, cs.T2_STAR, h_t, e_bins, sigma_in, phase,
            noise_w=w, blank_s=blank_eff, fs=cs.FS,
            adc_bits=ADC_BITS, adc_fs=ADC_FS, ripple=ripple)
        fh_r = fe_binding.estimate(estimator, v_rip, cs.FS, blank_eff)
        if not np.isfinite(fh_r):
            fh_r = f_l + 10.0 * GROSS_HZ
        errs_ripple.append(fh_r - f_l)
        # Paired record + the mains-harmonic tone (reported, not gated).
        v_tone, _, _ = fid.synthesize_adc_record(
            v0, f_l, cs.T2_STAR, h_t, e_bins, sigma_in, phase,
            noise_w=w, blank_s=blank_eff, fs=cs.FS,
            adc_bits=ADC_BITS, adc_fs=ADC_FS, ripple=tone)
        fh_t = fe_binding.estimate(estimator, v_tone, cs.FS, blank_eff)
        if not np.isfinite(fh_t):
            fh_t = f_l + 10.0 * GROSS_HZ
        errs_tone.append(fh_t - f_l)
    errs = np.asarray(errs)
    errs_ripple = np.asarray(errs_ripple)
    errs_tone = np.asarray(errs_tone)
    # Gross errors: the estimator returned NaN (patched to +10 Hz above)
    # or landed more than GROSS_HZ from the truth.
    gross = float(np.mean(np.abs(errs) > GROSS_HZ))
    gross_ripple = float(np.mean(np.abs(errs_ripple) > GROSS_HZ))
    rms_ripple_nt = float(np.sqrt(np.mean(errs_ripple**2))) \
        / fid.GAMMA_HZ_PER_NT
    rms_tone_nt = float(np.sqrt(np.mean(errs_tone**2))) / fid.GAMMA_HZ_PER_NT

    f_h, mag_h = sim["tabs"]["vm(adc)"]
    res = {"spec": spec["title"], "estimator": estimator,
           "b_earth_uT": b_earth * 1e6,
           "v0_uV": v0 * 1e6, "sigma_in_uV": sigma_in * 1e6,
           "sigma_in_band_uV": sigma_in_band * 1e6,
           "gain_fl": float(np.interp(f_l, f_h, mag_h)),
           "tau_ring_ms": tau_ring * 1e3, "blank_eff_ms": blank_eff * 1e3,
           "snr_rms_db": 20 * np.log10((v0 / np.sqrt(2)) / sigma_in),
           "snr_rms_band_db": 20 * np.log10((v0 / np.sqrt(2)) / sigma_in_band)}

    # Reference CRB (context, not the score): the SHAPED Fisher bound from
    # the candidate's own EMF-referred SPICE spectrum S1(f) = e_n(f)^2 --
    # the flat-density approximation is invalid under a tuned tank (audit:
    # it overestimates the bound ~1.4x at resonance; the estimator sat at
    # a spurious 0.72x 'sub-CRB' ratio). The flat freq_crb_colored column
    # is kept alongside for comparison with older cards.
    n_rec = int(round(cs.RECORD_S * cs.FS))
    t_ax = blank_eff + np.arange(n_rec) / cs.FS
    bins = np.fft.rfftfreq(n_rec, 1.0 / cs.FS)
    s1_bins = np.interp(bins, f_n, e_n) ** 2
    res["crb_nt"] = crb.freq_crb_shaped(
        t_ax, v0, f_l, cs.T2_STAR, 0.0, cs.FS, s1_bins
    ) / fid.GAMMA_HZ_PER_NT

    res["rms_nt"] = float(np.sqrt(np.mean(errs**2))) / fid.GAMMA_HZ_PER_NT
    res["gross"] = gross
    res["rms_ripple_nt"] = rms_ripple_nt
    res["gross_ripple"] = gross_ripple
    res["clip_margin"] = peak_adc / (0.9 * ADC_FS / 2)
    res["n_clipped"] = n_clip_tot

    # MCU configuration (candidate axis): clock ppm is a DETERMINISTIC
    # scale bias (does not average down; subtracts out of anomaly contrast
    # -- reported, never folded into sigma_B); the capture tick's
    # timestamp quantization is reported and must be negligible.
    res["clock_bias_nt"] = f_l * mcu["clock_ppm"] * 1e-6 / fid.GAMMA_HZ_PER_NT
    res["timestamp_quant_rel"] = mcu["tick_s"] * cs.FS
    assert res["timestamp_quant_rel"] < 1e-3, \
        "MCU tick is not negligible against the sample period"

    # ONE objective function J (architecture.md section 0):
    #   J = sigma_B [nT] with fail-fast gates; no dead-time cost term
    #   (dead time is already inside sigma_B via the record start time).
    gates = {}
    gates["no_clipping"] = res["clip_margin"] < 1.0
    gates["recovery_inside_blanking"] = blank_eff < 0.5 * cs.T2_STAR
    gates["gross_errors"] = res["gross"] < 0.01
    # Rail-ripple gate (E3 audit finding 5, SCORED per REDESIGN.md section
    # 4): the candidate must survive the 100 dB-PSRR-referred buck ripple
    # in its own records -- no seed hijack (gross) and no more than a 2x
    # sigma_B degradation. The old proxy (V0 vs 0.5 uV) is kept as the
    # ripple_margin design-rule number: it cannot see that the ripple and
    # the FID see different gain through the candidate's H(f).
    ripple_referred_uv = ripple[1] * 1e6                          # 0.5 uV
    res["ripple_margin"] = ripple_referred_uv / max(v0 * 1e6, 1e-9)
    gates["rail_ripple_survivable"] = (res["gross_ripple"] < 0.01
                                       and res["rms_ripple_nt"]
                                       <= 2.0 * res["rms_nt"])
    res["rms_tone_nt"] = rms_tone_nt
    res["gates"] = gates
    res["J_nt"] = res["rms_nt"] if all(gates.values()) else float("inf")
    return res


def evaluate(candidate, b_fields=B_SWEEP, n_mc: int = N_MC,
             with_tolerance: bool = False) -> dict:
    """THE evaluator. One candidate (circuit + estimator + MCU config) in,
    one score card out. J is the WORST-BAND sigma_B over the operating
    field range.

    candidate: either an afe_spec kwargs dict (label, e_amp, i_amp, coil,
    ..., estimator=..., mcu=...) or an already-built spec dict. b_fields:
    the field sweep (default the full operating range); pass a single
    field for a point evaluation (fixtures, per-band families).
    with_tolerance adds the B1 Monte-Carlo tolerance sweep (2-sigma
    component tolerances, p95 CRB) -- expensive; used for survivor
    sign-off, not search-time scoring.
    """
    spec = candidate if "components" in candidate \
        else cs.afe_spec(**candidate)
    sim = cs.simulate(spec)
    return evaluate_with_sim(spec, sim, b_fields=b_fields, n_mc=n_mc,
                             with_tolerance=with_tolerance)


def evaluate_with_sim(spec: dict, sim: dict, b_fields=B_SWEEP,
                      n_mc: int = N_MC, with_tolerance: bool = False
                      ) -> dict:
    """Scoring half of evaluate() given an already-run SPICE
    characterization (the optimizer's subprocess runs ngspice itself for
    sim_status capture)."""
    bands = [score_band(sim, spec, b, n_mc=n_mc) for b in b_fields]
    worst = max(bands, key=lambda c: c["J_nt"])
    est = spec["meta"].get("estimator", "zoom")
    mcu = spec["meta"].get("mcu", DEFAULT_MCU)
    card = {
        "spec": spec["title"],
        "estimator": est,
        "mcu": dict(mcu),
        "spec_hash": spec_hash(spec),
        "J_nt": worst["J_nt"],
        "worst_band_uT": worst["b_earth_uT"],
        "J_per_band": {"%.1fuT" % c["b_earth_uT"]: c["J_nt"] for c in bands},
        "bands": bands,
        "ir_causal_frac": sim.get("ir_causal_frac"),
        "provenance": provenance(n_mc),
    }
    if with_tolerance:
        card["tolerance"] = cs.tolerance_sweep(spec)
    return card
