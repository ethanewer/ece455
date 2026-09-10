"""End-to-end sensitivity scoring for the magnetometer DSP stack.

Sections (post-audit-v0.0):
  0. SNR vocabulary: this harness reports TWO named conventions -- do not
     cross-compare them with other tables without converting:
       eta_ps  = A_peak / sigma_ps        per-sample amplitude SNR (dB) --
                                          the convention in
                                          research-frequency-estimation.md
       SNR_rms = (V0/sqrt2) / sigma_in    record RMS SNR in the noise band
  1. CRB validation: Monte-Carlo variance of the estimators vs the
     colored-noise Cramer-Rao bound. N_MONTE=400 => ~3.5% relative 1-sigma
     MC uncertainty on every sigma reported here; ratios within ~0.93-1.07
     of the bound are consistent with it.
  2. Physics V0 x T2* grid: headline numbers are CONDITIONAL on the assumed
     transducer amplitude. V0 comes from fid.estimate_v0 (Curie-law coil
     model), not from a chosen "nice" number.
  3. Systematics ablations (the M5 list the research docs specify):
     tau misspecification, in-band mains harmonic (60 Hz 30th = 1.8 kHz),
     and the sampling-clock ppm scale error (a deterministic bias, not
     noise -- it does not average down).

Usage:  python3 run_scoring.py
"""
import numpy as np

import crb
import fid
from estimators import ESTIMATORS

N_MONTE = 400
MC_SIGMA_REL = 1.0 / np.sqrt(2.0 * N_MONTE)      # ~3.5% on sigma
ERR_HZ_THRESHOLD = 1.0                            # "gross error" bar


def rms_error(est_name, **rec_kwargs):
    """Monte-Carlo RMS frequency error, gross-error rate, common seeds.

    The same seeds feed every estimator, so paired comparisons are exact.
    Phase is randomized per run (phase-dependent bias would otherwise hide).
    """
    errs = []
    for i in range(N_MONTE):
        phase = np.random.default_rng(10_000 + i).uniform(-np.pi, np.pi)
        rec = fid.generate_record(rng=i, phase=phase, **rec_kwargs)
        f_hat = ESTIMATORS[est_name](rec)
        errs.append(f_hat - rec["f_larmor"])
    errs = np.asarray(errs)
    gross = float(np.mean(np.abs(errs) > ERR_HZ_THRESHOLD))
    rms_nt = float(np.sqrt(np.mean(errs**2))) / fid.GAMMA_HZ_PER_NT
    return rms_nt, gross


def crb_nt_for(**kw):
    n = int(round(kw["record_s"] * kw["fs"]))
    t = kw["blanking_s"] + np.arange(n) / kw["fs"]
    sigma_in = kw.get("sigma_in") or fid.input_noise_rms(
        kw["r_coil"], kw["l_coil"], kw["e_amp"], kw["i_amp"],
        kw["f_lo"], kw["f_hi"])
    return crb.freq_crb_colored(t, kw["v0"], fid.larmor_hz(kw["b_tesla"]),
                                kw["tau"], 0.0, kw["fs"], kw["f_lo"],
                                kw["f_hi"], sigma_in) / fid.GAMMA_HZ_PER_NT


def main():
    base = dict(b_tesla=50e-6, v0=2e-6, tau=1.5, fs=20_000.0,
                blanking_s=0.2, record_s=1.5, r_coil=120.0, l_coil=2e-3,
                e_amp=7e-9, i_amp=0.05e-12, f_lo=fid.NOISE_BAND[0],
                f_hi=fid.NOISE_BAND[1], gain=5000.0, adc_bits=16,
                adc_fs=2.048)

    sigma_in = fid.input_noise_rms(base["r_coil"], base["l_coil"],
                                   base["e_amp"], base["i_amp"])
    eta_db = 20 * np.log10(base["v0"] / sigma_in)
    snr_rms_db = 20 * np.log10((base["v0"] / np.sqrt(2)) / sigma_in)
    print(f"Input-referred RMS noise in band {fid.NOISE_BAND}: "
          f"{sigma_in*1e6:.2f} uV")
    print(f"SNR conventions at the reference point: "
          f"eta_ps (A_peak/sigma) = {eta_db:.1f} dB | "
          f"SNR_rms = {snr_rms_db:.1f} dB")
    print(f"gamma'p = {fid.GAMMA_HZ_PER_NT*1e3:.6f} Hz/nT "
          f"(shielded proton in water; 1 Hz = {fid.NT_PER_HZ:.4f} nT)")
    print(f"MC uncertainty on every sigma below: ~+/-{MC_SIGMA_REL*100:.1f}% "
          f"(1-sigma, N={N_MONTE})")

    # ---- 1. CRB validation -------------------------------------------
    bound = crb_nt_for(**base)
    print(f"\n[1] Colored-noise CRB at the reference point: {bound:.4f} nT")
    print(f"    {'estimator':>10} {'RMS [nT]':>9} {'xCRB':>6} "
          f"{'gross>1Hz':>10}")
    for name in ESTIMATORS:
        rms, gross = rms_error(name, **base)
        print(f"    {name:>10} {rms:>9.4f} {rms/bound:>6.2f} "
              f"{gross:>10.1%}")

    # ---- 2. Physics V0 x T2* grid (CRB only; the conditional headline) -
    print("\n[2] CRB [nT] on the physics V0 x T2* grid "
          "(estimate_v0; blanking 200 ms, INA-class e_n)")
    coils = [
        ("N=300,  r=1.0cm, Bpol=10mT", dict(n_turns=300, coil_radius_m=0.010,
                                            b_pol=0.01)),
        ("N=530,  r=1.5cm, Bpol=20mT", dict(n_turns=530, coil_radius_m=0.015,
                                            b_pol=0.02)),
        ("N=1500, r=3.0cm, Bpol=50mT", dict(n_turns=1500, coil_radius_m=0.030,
                                            b_pol=0.05)),
    ]
    print(f"    {'coil':<28} {'V0 [uV]':>8} " +
          " ".join(f"T2*={t:>4.1f}s" for t in (0.5, 1.5, 3.0)))
    for label, ck in coils:
        v0 = fid.estimate_v0(**ck)
        row = [crb_nt_for(**dict(base, v0=v0, tau=t)) for t in (0.5, 1.5, 3.0)]
        print(f"    {label:<28} {v0*1e6:>8.2f} " +
              " ".join(f"{x:>8.3f}" for x in row))

    # ---- 3. Systematics ablations ------------------------------------
    print(f"\n[3a] tau-misspec ablation (zoom_fit fed a WRONG tau; "
          f"true tau = {base['tau']} s, {N_MONTE} runs):")
    for factor in (0.5, 2.0):
        errs = []
        for i in range(N_MONTE):
            phase = np.random.default_rng(10_000 + i).uniform(-np.pi, np.pi)
            rec = fid.generate_record(rng=i, phase=phase, **base)
            f_hat = ESTIMATORS["zoom_fit"](rec, tau=base["tau"] * factor)
            errs.append(f_hat - rec["f_larmor"])
        rms_nt = float(np.sqrt(np.mean(np.square(errs)))) / fid.GAMMA_HZ_PER_NT
        print(f"    tau x{factor:<4}: RMS = {rms_nt:.4f} nT")

    print("\n[3b] In-band narrowband interferers (zoom_fit; input amplitude "
          "relative to V0):")
    v0 = base["v0"]
    for label, inter in [
            ("60 Hz @ -20 dB (out of band)", [(60.0, 0.1 * v0)]),
            ("1.8 kHz @ -40 dB (= 30th of 60 Hz)", [(1800.0, 0.01 * v0)]),
            ("1.8 kHz @ -20 dB", [(1800.0, 0.1 * v0)])]:
        errs = []
        for i in range(N_MONTE):
            phase = np.random.default_rng(10_000 + i).uniform(-np.pi, np.pi)
            rec = fid.generate_record(rng=i, phase=phase, **base,
                                      interferers=inter)
            errs.append(ESTIMATORS["zoom_fit"](rec) - rec["f_larmor"])
        rms_nt = float(np.sqrt(np.mean(np.square(errs)))) / fid.GAMMA_HZ_PER_NT
        print(f"    {label:<38}: RMS = {rms_nt:.4f} nT")

    print("\n[3c] Sampling-clock scale error (deterministic bias; does NOT "
          "average down):")
    print(f"    {'clock':>18} {'bias @ 50uT':>12} {'bias @ 25uT':>12}")
    for label, ppm in [("crystal +/-20ppm", 20.0), ("TCXO +/-2ppm", 2.0),
                       ("TCXO +/-0.5ppm", 0.5)]:
        print(f"    {label:>18} {50.0*ppm/1e3:>10.3f}nT "
              f"{25.0*ppm/1e3:>10.3f}nT")

    # ---- 4. Blanking sweep (info-theoretic; recovery physics is scored
    #         separately by the .tran check in circuit_spec.py) ----------
    print(f"\n[4] Blanking sweep (CRB + all estimators, reference V0):")
    print(f"    {'blanking':>9} {'CRB [nT]':>9} " +
          " ".join(f"{k:>10}" for k in ESTIMATORS))
    for tb in (0.05, 0.1, 0.2, 0.3, 0.5):
        kw = dict(base, blanking_s=tb)
        row = crb_nt_for(**kw)
        ests = {k: rms_error(k, **kw)[0] for k in ESTIMATORS}
        print(f"    {tb*1e3:>7.0f}ms {row:>9.4f} " +
              " ".join(f"{ests[k]:>10.4f}" for k in ESTIMATORS))


if __name__ == "__main__":
    main()
