"""Cramer-Rao lower bound for Larmor-frequency estimation on a damped FID.

Model: v(t) = A*exp(-t/tau)*sin(2*pi*f*t + phi) + white noise of sigma.

The Fisher information matrix is computed numerically from analytic partial
derivatives (exact, includes cross-terms between amplitude, frequency,
decay, and phase), so dead time, finite records, and parameter coupling are
all handled. The frequency CRB is [J^-1]_ff; validated against Monte-Carlo
variance of the NLLS estimator in run_scoring.py.

Fisher information for additive white Gaussian noise:
    J[i,j] = (1/sigma^2) * sum_k  ds/dtheta_i(t_k) * ds/dtheta_j(t_k)
"""
import numpy as np

import fid

PARAM_ORDER = ("amp", "freq", "tau", "phase")


def signal_model(t, amp, freq, tau, phase):
    return amp * np.exp(-t / tau) * np.sin(2.0 * np.pi * freq * t + phase)


def partials(t, amp, freq, tau, phase):
    """Analytic d(model)/d(param) for each parameter."""
    e = np.exp(-t / tau)
    arg = 2.0 * np.pi * freq * t + phase
    s, c = np.sin(arg), np.cos(arg)
    d_amp = e * s
    d_freq = amp * e * np.cos(arg) * (2.0 * np.pi * t)
    d_tau = amp * e * s * (t / tau**2)
    d_phase = amp * e * np.cos(arg)
    return {"amp": d_amp, "freq": d_freq, "tau": d_tau, "phase": d_phase}


def fim(t, amp, freq, tau, phase, sigma):
    p = partials(t, amp, freq, tau, phase)
    keys = PARAM_ORDER
    j = np.zeros((len(keys), len(keys)))
    for i, ki in enumerate(keys):
        for jj, kj in enumerate(keys):
            j[i, jj] = np.sum(p[ki] * p[kj]) / sigma**2
    return j


def freq_crb(t, amp, freq, tau, phase, sigma):
    """CRLB on the standard deviation of the frequency estimate [Hz].

    White-Gaussian-noise version (sigma = per-sample noise std). For
    band-limited noise use freq_crb_colored.
    """
    j = fim(t, amp, freq, tau, phase, sigma)
    try:
        cov = np.linalg.inv(j)
        return float(np.sqrt(max(cov[1, 1], 0.0)))
    except np.linalg.LinAlgError:
        return float("nan")


def freq_crb_colored(t, amp, freq, tau, phase, fs, f_lo, f_hi, sigma):
    """CRLB for a *band-limited white* noise floor, the honest model for an
    AFE whose bandpass passes [f_lo, f_hi]: per-sample variance sigma^2, but
    spread over the band, so the noise density at the signal is
    sigma^2/(2*(f_hi-f_lo)) (two-sided), not sigma^2/fs.

    Fisher information for Gaussian noise with circulant covariance C:
        J_ij = (F ds_i)^H diag(1/S) (F ds_j),
    computed in the DFT domain. Out-of-band (S = 0) carries no information
    here, which makes the bound slightly conservative (safe for a floor).
    Validated against Monte-Carlo of the NLLS estimator in run_scoring.py.
    """
    p = partials(t, amp, freq, tau, phase)
    n = len(t)
    keys = PARAM_ORDER
    D = {k: np.fft.rfft(p[k]) for k in keys}

    n_bins = len(D["amp"])
    f_bins = np.fft.rfftfreq(n, 1.0 / fs)
    in_band = (f_bins >= f_lo) & (f_bins <= f_hi)
    # Two-sided occupancy: each non-DC/Nyquist bin maps to +/-f.
    occupied = np.zeros(n_bins, dtype=bool)
    occupied[0] = in_band[0]
    occupied[-1] = in_band[-1]
    occupied[1:-1] = in_band[1:-1]
    beta = occupied.mean()          # fraction of two-sided band with noise
    if beta == 0:
        return float("nan")

    # Bin weights: 2x for an occupied +/- pair, 1x for occupied DC/Nyquist,
    # and ZERO for out-of-band bins (S = 0 there: no noise, but we claim no
    # information either, which makes the bound conservative. An earlier
    # revision left unoccupied bins at weight 1 -- immaterial at these
    # parameters (<0.1%, 99.996% of ds/df energy is in-band) but inconsistent
    # with this docstring; fixed per audit v0.0.)
    w = np.where(occupied, 2.0, 0.0)
    if occupied[0]:
        w[0] = 1.0
    if occupied[-1]:
        w[-1] = 1.0

    jj = np.zeros((len(keys), len(keys)))
    for i, ki in enumerate(keys):
        for j, kj in enumerate(keys):
            cross = np.real(np.conj(D[ki]) * D[kj])
            jj[i, j] = beta / (sigma**2 * n) * np.sum(w * cross)
    try:
        cov = np.linalg.inv(jj)
        return float(np.sqrt(max(cov[1, 1], 0.0)))
    except np.linalg.LinAlgError:
        return float("nan")


def crb_nt(t, amp, freq, tau, phase, sigma):
    """CRB converted to field units via f = 0.0425764 Hz/nT [nT]."""
    return freq_crb(t, amp, freq, tau, phase, sigma) / fid.GAMMA_HZ_PER_NT
