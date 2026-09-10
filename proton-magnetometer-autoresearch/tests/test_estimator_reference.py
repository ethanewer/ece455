"""D7: estimator reference table locked into asserts.

Locks the measured reference table (README/architecture, run_scoring §1)
into hard asserts so the ruling-out and the bound-riding claims FAIL
LOUDLY if an estimator is "fixed" into something different, or the SNR
regime silently shifts. Phase-randomized, fixed seeds, MC CI asserted
(the windows below are the measured value +/- the MC 1-sigma of ~5.6% at
N=160, widened to a defensible guard band).

Measured reference at the run_scoring.py reference point (B=50 uT,
V0 = 2 uV, T2* = 1.5 s, 1.5 s record, 200 ms blanking, INA-class e_n,
N=400): zoom 1.02x CRB 0% gross; fft_peak 1.05x 0%; zc_fit 3802x 100%;
staged nlls_fit diverges on 1.5% of runs (RMS incl. divergences 1347x;
on its non-divergent runs it sits at the bound).

Run:  python3 -m pytest tests/test_estimator_reference.py
"""
import numpy as np
import pytest

from conftest import POC  # noqa: F401

import crb
import fid
from estimators import ESTIMATORS

N_MC = 160                      # MC 1-sigma on a ratio ~ +/-5.6%
ERR_HZ_THRESHOLD = 1.0          # run_scoring's gross bar

BASE = dict(b_tesla=50e-6, v0=2e-6, tau=1.5, fs=20_000.0, blanking_s=0.2,
            record_s=1.5, r_coil=120.0, l_coil=2e-3, e_amp=7e-9,
            i_amp=0.05e-12, f_lo=fid.NOISE_BAND[0], f_hi=fid.NOISE_BAND[1],
            gain=5000.0, adc_bits=16, adc_fs=2.048)


def _reference_table():
    """(errors per estimator, crb_nt) at fixed seeds -- the same seed scheme
    as run_scoring.rms_error (phase = 10_000+i, record rng = i)."""
    crb_nt = crb_nt_reference()
    errs = {name: [] for name in ESTIMATORS}
    for i in range(N_MC):
        phase = np.random.default_rng(10_000 + i).uniform(-np.pi, np.pi)
        rec = fid.generate_record(rng=i, phase=phase, **BASE)
        for name, fn in ESTIMATORS.items():
            f_hat = fn(rec)
            errs[name].append(f_hat - rec["f_larmor"])
    table = {}
    for name, e in errs.items():
        e = np.asarray(e)
        fin = np.isfinite(e)
        table[name] = dict(
            rms_nt=float(np.sqrt(np.mean(e[fin] ** 2))) / fid.GAMMA_HZ_PER_NT,
            gross=float(np.mean(np.abs(e) > ERR_HZ_THRESHOLD)),
            n_finite=int(fin.sum()),
        )
    return table, crb_nt


def crb_nt_reference():
    n = int(round(BASE["record_s"] * BASE["fs"]))
    t = BASE["blanking_s"] + np.arange(n) / BASE["fs"]
    sigma_in = fid.input_noise_rms(BASE["r_coil"], BASE["l_coil"],
                                   BASE["e_amp"], BASE["i_amp"])
    return crb.freq_crb_colored(t, BASE["v0"],
                                fid.larmor_hz(BASE["b_tesla"]), BASE["tau"],
                                0.0, BASE["fs"], *fid.NOISE_BAND,
                                sigma_in) / fid.GAMMA_HZ_PER_NT


@pytest.fixture(scope="module")
def table():
    return _reference_table()


def test_zoom_and_fft_sit_at_crb(table):
    """The recommended estimators ride the bound: <=1.2x CRB, 0% gross --
    and NOT impossibly below it (>15% under the bound would mean the bound
    or the harness is broken, not a better estimator)."""
    tab, crb_nt = table
    for name in ("zoom_fit", "fft_peak"):
        ratio = tab[name]["rms_nt"] / crb_nt
        assert 0.85 < ratio <= 1.2, (name, ratio)
        assert tab[name]["gross"] == 0.0, (name, tab[name]["gross"])
        assert tab[name]["n_finite"] == N_MC      # no NaNs tolerated


def test_zc_fit_is_ruled_out(table):
    """The zero-crossing family must STAY catastrophic at this SNR: >=100x
    CRB and >=90% gross errors. If a change makes zc_fit good (or the SNR
    regime shift makes it artificially fail), this pins it -- compare the
    measured 3802x / 100% at N=400."""
    tab, crb_nt = table
    ratio = tab["zc_fit"]["rms_nt"] / crb_nt
    assert ratio >= 100.0, ratio          # the ruling-out holds
    assert ratio <= 10_000.0, ratio       # ...and nothing worse crept in
    assert tab["zc_fit"]["gross"] >= 0.9, tab["zc_fit"]["gross"]


def test_staged_nlls_threshold_limited(table):
    """Staged nlls_fit at the reference point (eta_ps = 14.2 dB) is
    THRESHOLD-LIMITED, as the research doc states for 4-parameter LSQ below
    ~15 dB. Measured (N=400, run_scoring seeds): 1.5% of runs diverge past
    the 1 Hz gross bar, and the remaining (conditioned) runs sit at ~22x
    CRB in RMS -- local minima in the (f, tau) coupling leave ~0.1-0.35 Hz
    errors on a non-trivial fraction of records even when they 'converge'.

    TODO.md D7's original drafting assumed <=1.2x CRB on conditioned runs;
    the measured table does not support that, and this test locks the
    MEASURED value instead (window: 10-35x, gross <=3%). A rewrite that
    makes nlls genuinely sit at the bound should UPDATE this window and the
    docs together -- an unexplained pass below 10x would mean the harness
    or the bound changed."""
    tab, crb_nt = table
    errs = []
    for i in range(N_MC):
        phase = np.random.default_rng(10_000 + i).uniform(-np.pi, np.pi)
        rec = fid.generate_record(rng=i, phase=phase, **BASE)
        f_hat = ESTIMATORS["nlls_fit"](rec)
        e = f_hat - rec["f_larmor"]
        if np.isfinite(e) and abs(e) <= ERR_HZ_THRESHOLD:
            errs.append(e)
    cond = np.asarray(errs)
    rms_nt = float(np.sqrt(np.mean(cond ** 2))) / fid.GAMMA_HZ_PER_NT
    ratio = rms_nt / crb_nt
    gross = 1.0 - len(errs) / N_MC
    assert 10.0 <= ratio <= 35.0, (ratio, crb_nt)
    assert gross <= 0.03, gross
