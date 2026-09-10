"""D16: M4 metrics from the scoring-harness spec
(docs/research/research-frequency-estimation.md, "Scoring harness spec"):

  M4  cycle-to-cycle repeatability (stationary-field run);
      averaging-gain check.

Implementation: K consecutive cycles at an IDENTICAL stationary field
(only noise and phase re-drawn per cycle) -> f_hat_k. The repeatability
sigma_rep = std(f_hat) is the single-cycle precision actually delivered;
the averaging-gain check compares the sigma of M-cycle non-overlapping
averages against sigma_rep/sqrt(M) -- correlated residuals (e.g. a
cycle-independent tau-estimation error leaking into every f_hat) show up
as ratio > 1 and the 1/sqrt(M) averaging law fails.

Run:  python3 -m pytest tests/test_repeatability_m4.py
"""
import numpy as np
import pytest

from conftest import POC  # noqa: F401

import crb
import fid
from estimators import ESTIMATORS

# Reference config 1 from the spec: eta_ps = 20 dB, tau = 1 s, t_d = 0.1 s,
# T = 1.5 s. sigma = A/eta with A = 1e-6 -> sigma = 1e-7.
N_CYCLES = 200
M_GROUPS = (2, 4, 8)


def _run_cycles(est_name, **kw):
    f_hat = []
    for i in range(kw.pop("n_cycles")):
        phase = np.random.default_rng(50_000 + i).uniform(-np.pi, np.pi)
        rec = fid.generate_record(rng=i, phase=phase, **kw)
        f_hat.append(ESTIMATORS[est_name](rec))
    return np.asarray(f_hat)


def test_m4_repeatability_and_averaging_gain():
    base = dict(b_tesla=50e-6, v0=1e-6, tau=1.0, fs=20_000.0, blanking_s=0.1,
                record_s=1.5, r_coil=120.0, l_coil=2e-3, e_amp=7e-9,
                i_amp=0.05e-12, gain=5000.0, adc_bits=16, adc_fs=2.048,
                n_cycles=N_CYCLES)
    # eta_ps = v0/sigma = 20 dB -> sigma_in = 1e-7 V.
    f_hat = _run_cycles("zoom_fit", sigma_in=1e-7, **base)

    f_true = fid.larmor_hz(base["b_tesla"])
    errs = f_hat - f_true
    sigma_rep = float(np.std(errs, ddof=1))
    bias = float(np.mean(errs))

    # Repeatability sits at the colored CRB for this config.
    t = base["blanking_s"] + np.arange(int(base["record_s"] * base["fs"])) \
        / base["fs"]
    crb_nt = crb.freq_crb_colored(t, base["v0"], f_true, base["tau"], 0.0,
                                  base["fs"], *fid.NOISE_BAND,
                                  1e-7) / fid.GAMMA_HZ_PER_NT
    rep_nt = sigma_rep / fid.GAMMA_HZ_PER_NT
    assert rep_nt / crb_nt < 1.3, (rep_nt, crb_nt)      # at the bound
    assert abs(bias) < 0.2 * sigma_rep, (bias, sigma_rep)

    # Averaging-gain check: sigma of M-cycle averages vs sigma/sqrt(M).
    for m in M_GROUPS:
        groups = errs[:N_CYCLES - N_CYCLES % m].reshape(-1, m).mean(axis=1)
        sig_m = float(np.std(groups, ddof=1))
        ratio = sig_m / (sigma_rep / np.sqrt(m))
        assert 0.8 < ratio < 1.25, (m, ratio)   # 1/sqrt(M) law holds


def test_m4_averaging_breaks_on_correlated_residuals():
    """The check must be ABLE to fail: a residual that is CORRELATED across
    consecutive cycles (interference bursts, drift, shared estimator state
    spanning cycles) does not average down as 1/sqrt(M) -- the ratio must
    leave its window. (A constant offset cannot do this: std is
    shift-invariant, so a constant bias shows up in M2 bias, not M4.)"""
    base = dict(b_tesla=50e-6, v0=1e-6, tau=1.0, fs=20_000.0, blanking_s=0.1,
                record_s=1.5, r_coil=120.0, l_coil=2e-3, e_amp=7e-9,
                i_amp=0.05e-12, gain=5000.0, adc_bits=16, adc_fs=2.048,
                n_cycles=N_CYCLES)
    f_hat = _run_cycles("zoom_fit", sigma_in=1e-7, **base)
    f_true = fid.larmor_hz(base["b_tesla"])
    errs = f_hat - f_true
    sigma_rep = float(np.std(errs, ddof=1))

    # A shared component with a correlation length of ~16 cycles and 0.5
    # sigma_rep amplitude: averaging M=8 of it barely reduces it.
    rng = np.random.default_rng(999)
    slow = 0.5 * sigma_rep * np.convolve(
        rng.normal(size=N_CYCLES + 64), np.ones(16) / 16.0,
        mode="valid")[:N_CYCLES]
    slow = 0.5 * sigma_rep * slow / np.std(slow)
    biased = errs + slow
    assert abs(np.std(biased, ddof=1) / sigma_rep - 1.0) < 0.2  # same spread
    m = 8
    groups = biased[:N_CYCLES - N_CYCLES % m].reshape(-1, m).mean(axis=1)
    ratio = float(np.std(groups, ddof=1)) / (sigma_rep / np.sqrt(m))
    assert ratio > 1.4, ratio
