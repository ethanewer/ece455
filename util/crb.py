"""Cramer-Rao lower bound for the frequency of a damped FID in white noise.

Model: v(t) = A exp(-t/tau) sin(2 pi f t + phi) + white Gaussian noise of
standard deviation sigma per sample. The Fisher information matrix is built
from analytic partial derivatives, including the coupling between amplitude,
frequency, decay, and phase, so finite records and decay are handled. The
frequency bound is the square root of [J^-1]_ff.

    J[i, j] = (1 / sigma^2) sum_k ds/dtheta_i(t_k) ds/dtheta_j(t_k)
"""
import numpy as np

from util import physics

PARAM_ORDER = ("amp", "freq", "tau", "phase")


def partials(t, amp, freq, tau, phase):
    """Analytic d(model)/d(param) for each parameter."""
    envelope = np.exp(-t / tau)
    argument = 2.0 * np.pi * freq * t + phase
    s, c = np.sin(argument), np.cos(argument)
    return {
        "amp": envelope * s,
        "freq": amp * envelope * c * (2.0 * np.pi * t),
        "tau": amp * envelope * s * (t / tau**2),
        "phase": amp * envelope * c,
    }


def fim(t, amp, freq, tau, phase, sigma):
    p = partials(t, amp, freq, tau, phase)
    matrix = np.zeros((len(PARAM_ORDER), len(PARAM_ORDER)))
    for i, ki in enumerate(PARAM_ORDER):
        for j, kj in enumerate(PARAM_ORDER):
            matrix[i, j] = np.sum(p[ki] * p[kj]) / sigma**2
    return matrix


def freq_crb(t, amp, freq, tau, phase, sigma):
    """Lower bound on the standard deviation of the frequency estimate [Hz]."""
    try:
        covariance = np.linalg.inv(fim(t, amp, freq, tau, phase, sigma))
    except np.linalg.LinAlgError:
        return float("nan")
    return float(np.sqrt(max(covariance[1, 1], 0.0)))


def crb_nt(t, amp, freq, tau, phase, sigma):
    """The frequency bound in field units [nT]."""
    return freq_crb(t, amp, freq, tau, phase, sigma) * physics.NT_PER_HZ
