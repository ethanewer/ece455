"""D13: second independent colored-CRB check via an ensemble-estimated
covariance.

The two existing constructions of the colored-noise CRB are the DFT-domain
shortcut (crb.freq_crb_colored) and the dense closed-form autocorrelation
covariance (test_validation.test_colored_crb_vs_dense_covariance). This
module adds a THIRD, orthogonal construction: Monte-Carlo realizations of
the band-limited process, an ensemble-estimated Toeplitz covariance, and
J = ds^T C^+ ds through the pseudo-inverse -- no DFT reasoning, and no
closed-form autocorrelation either: C is *measured* from realizations.

Two claims tested:
  1. ensemble J agrees with the DFT shortcut within 10% on sigma_f;
  2. the agreement survives for an in-band signal at two frequencies.

Run:  python3 -m pytest tests/test_crb_ensemble.py
"""
import numpy as np
import pytest

from conftest import POC  # noqa: F401

import crb
import fid


def _bandlimited_ensemble(k, n, fs, f_lo, f_hi, rng):
    """K realizations of unit-density band-limited white noise.

    Same construction as fid._bandlimited_noise (flat spectrum in band,
    zero outside), shaped so the ensemble covariance estimates the
    covariance of a process with one-sided density S1 = 1/(f_hi-f_lo) in
    band. Each realization is scaled to RMS sqrt(S1 * fs / 2)... simpler:
    draw white noise, zero the out-of-band spectrum, and let the ensemble
    covariance absorb the correct scaling -- the Fisher test only needs the
    C that the realizations actually have.
    """
    x = rng.normal(0.0, 1.0, size=(k, n))
    X = np.fft.rfft(x, axis=1)
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    X[:, (freqs < f_lo) | (freqs > f_hi)] = 0.0
    return np.fft.irfft(X, n, axis=1)


def _sigma_f_ensemble(ensemble, n, fs, amp, freq, tau, phase, t):
    """sigma_f from J = ds^T C^+ ds with C estimated from realizations."""
    p = crb.partials(t, amp, freq, tau, phase)
    keys = crb.PARAM_ORDER
    C = np.cov(ensemble, rowvar=False)          # (n, n) Toeplitz estimate
    Cinv_ds = [np.linalg.lstsq(C, p[k], rcond=1e-6)[0] for k in keys]
    j = np.zeros((len(keys), len(keys)))
    for i, ki in enumerate(keys):
        for jj, kj in enumerate(keys):
            j[i, jj] = p[ki] @ Cinv_ds[jj]
    return float(np.sqrt(np.linalg.inv(j)[1, 1]))


@pytest.mark.parametrize("freq", [2128.8, 1064.4])
def test_ensemble_covariance_matches_dft_shortcut(freq):
    fs, n = 20_000, 900
    t = np.arange(n) / fs
    amp, tau, phase = 1e-6, 1.5, 0.0
    k = 3000                                     # ensemble size
    rng = np.random.default_rng(123)

    ens = _bandlimited_ensemble(k, n, fs, *fid.NOISE_BAND, rng)
    # Scale the ensemble to the same in-band one-sided density the shortcut
    # assumes for per-sample sigma: S1 = sigma^2/(f_hi-f_lo).
    # C_true[0] = S1*(f_hi-f_lo) + floor; measured C[0] = mean x^2, so
    # scale so that mean x^2 matches S1*(f_hi-f_lo).
    sigma = 1e-7
    s1 = sigma**2 / (fid.NOISE_BAND[1] - fid.NOISE_BAND[0])
    scale = np.sqrt(s1 * (fid.NOISE_BAND[1] - fid.NOISE_BAND[0])
                    / np.mean(ens**2))
    ens = ens * scale

    got = _sigma_f_ensemble(ens, n, fs, amp, freq, tau, phase, t)
    want = crb.freq_crb_colored(t, amp, freq, tau, phase, fs,
                                *fid.NOISE_BAND, sigma)
    assert abs(got / want - 1.0) < 0.10, (got, want, got / want)
