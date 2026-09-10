"""End-to-end sensitivity scoring for the magnetometer DSP stack.

Runs:
  1. CRB validation: Monte-Carlo variance of the NLLS estimator vs the
     Cramer-Rao bound (estimator should sit on the bound).
  2. Estimator comparison: RMS nT error of each estimator across blanking
     times (the blanking-vs-precision tradeoff the week-2 report flagged).

Usage:  python3 run_scoring.py
"""
import numpy as np

import crb
import fid
from estimators import ESTIMATORS

N_MONTE = 400


def rms_nt_error(est_name, **rec_kwargs):
    """Monte-Carlo RMS field error of one estimator [nT]."""
    errs_hz = []
    for i in range(N_MONTE):
        rec = fid.generate_record(rng=i, **rec_kwargs)
        f_hat = ESTIMATORS[est_name](rec)
        errs_hz.append(f_hat - rec["f_larmor"])
    return float(np.sqrt(np.mean(np.square(errs_hz)))) / 42.577478e-3


def main():
    base = dict(b_tesla=50e-6, v0=2e-6, tau=1.5, fs=20_000.0,
                blanking_s=0.2, record_s=1.5, r_coil=120.0, l_coil=2e-3,
                e_amp=7e-9, i_amp=0.05e-12, f_lo=700.0, f_hi=3500.0,
                gain=5000.0, adc_bits=16, adc_fs=2.048)

    sigma_in = fid.input_noise_rms(base["r_coil"], base["l_coil"],
                                   base["e_amp"], base["i_amp"],
                                   base["f_lo"], base["f_hi"])
    print(f"Input-referred RMS noise in FID band: {sigma_in*1e6:.2f} uV")
    snr = (base["v0"] / np.sqrt(2)) / sigma_in
    print(f"FID amplitude {base['v0']*1e6:.1f} uV peak  ->  "
          f"RMS SNR = {20*np.log10(snr):.1f} dB")

    # ---- 1. CRB validation -------------------------------------------
    t = np.arange(int(1.5 * base["fs"])) / base["fs"] + base["blanking_s"]
    f_l = fid.larmor_hz(base["b_tesla"])
    bound = crb.freq_crb_colored(t, base["v0"], f_l, base["tau"], 0.0,
                                 base["fs"], base["f_lo"], base["f_hi"],
                                 sigma_in) / 42.577478e-3
    print(f"\nColored-noise CRB sigma_f = "
          f"{crb.freq_crb_colored(t, base['v0'], f_l, base['tau'], 0.0, base['fs'], base['f_lo'], base['f_hi'], sigma_in)*1e3:.3f} mHz"
          f"  =  {bound:.4f} nT")

    nlls = rms_nt_error("nlls_fit", **base)
    print(f"NLLS Monte-Carlo ({N_MONTE} runs)  =  {nlls:.4f} nT"
          f"   ({nlls/bound:.2f}x CRB)")

    # ---- 2. Estimator comparison vs blanking time --------------------
    print(f"\n{'blanking':>9} {'CRB [nT]':>9} " + " ".join(f"{k:>12}" for k in ESTIMATORS))
    for tb in (0.05, 0.1, 0.2, 0.3, 0.5):
        kw = dict(base, blanking_s=tb)
        tt = np.arange(int(1.5 * base["fs"])) / base["fs"] + tb
        row = crb.freq_crb_colored(tt, base["v0"], f_l, base["tau"], 0.0,
                                   base["fs"], base["f_lo"], base["f_hi"],
                                   sigma_in) / 42.577478e-3
        ests = {k: rms_nt_error(k, **kw) for k in ESTIMATORS}
        print(f"{tb*1e3:>7.0f}ms {row:>9.4f} " + " ".join(f"{ests[k]:>12.4f}" for k in ESTIMATORS))

    # ---- 3. Amplitude sweep (what the AFE must deliver) --------------
    print(f"\nNLLS RMS nT error vs FID amplitude (blanking 200 ms):")
    for v0_uv in (0.5, 1, 2, 5, 10):
        kw = dict(base, v0=v0_uv * 1e-6)
        print(f"  V0 = {v0_uv:>5.1f} uV -> {rms_nt_error('nlls_fit', **kw):.4f} nT")


if __name__ == "__main__":
    main()
