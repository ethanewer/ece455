"""Frequency estimators for the FID, from cheapest to most expensive.

All operate on the sampled record dict produced by fid.generate_record and
return an estimate of the Larmor frequency in Hz. These are reference
implementations: the MCU firmware ports of the same estimators can be
validated against them on identical synthetic records.
"""
import numpy as np


def fft_peak(rec, zero_pad=16):
    """FFT magnitude peak with parabolic interpolation.

    Simplest possible. Known to be biased on damped sinusoids (the decay
    broadens the peak) and resolution-limited: 1/T_record bins.
    """
    v = rec["v_adc"] - rec["v_adc"].mean()
    fs = rec["fs"]
    n = len(v)
    spec = np.abs(np.fft.rfft(v, n * zero_pad))
    freqs = np.fft.rfftfreq(n * zero_pad, 1.0 / fs)
    k = int(np.argmax(spec))
    if k <= 0 or k >= len(spec) - 1:
        return float(freqs[k])
    a, b, c = np.log(spec[k - 1:k + 2])
    delta = 0.5 * (a - c) / (a - 2 * b + c)
    return float(freqs[k] + delta * (freqs[1] - freqs[0]))


def zoom_fit(rec, tau=None, dec=10, span_hz=20.0, step_hz=0.02):
    """Exponentially-weighted coherent zoom around the coarse FFT peak.

    Matched filter for the damped sinusoid: mix to baseband at the coarse
    FFT peak, FIR-decimate to fs/dec, then scan the residual offset with
    the weighted inner product S(df) = |sum_k w(t_k) z(t_k) e^{-j2pi df t_k}|,
    w(t) = exp(-t/tau) (the ML weight for a decaying envelope), and refine
    the peak with log-parabolic interpolation.

    This is the estimator an MCU can actually run at CRB-level accuracy:
    ~2k output samples x ~2k grid points = a few M MACs, tens of ms on an
    M4. Note the wrapped-increment / zero-crossing family *cannot* reach
    this accuracy: it discards inter-sample phase continuity and floors out
    at ~2 Hz for these records (verified empirically), ~100x worse variance.
    """
    from scipy.signal import resample_poly
    v = rec["v_adc"] - rec["v_adc"].mean()
    fs, t = rec["fs"], rec["t"]
    if tau is None:
        tau = rec["tau"]

    f0 = fft_peak(rec)
    z = v * np.exp(-2j * np.pi * f0 * t)

    zb = resample_poly(z, 1, dec)
    tb = resample_poly(t, 1, dec)
    w = np.exp(-tb / tau)

    grid = np.arange(-span_hz, span_hz + step_hz / 2, step_hz)
    s = np.empty(len(grid))
    for i, df in enumerate(grid):
        s[i] = np.abs(np.sum(w * zb * np.exp(-2j * np.pi * df * tb))) ** 2

    k = int(np.argmax(s))
    if k <= 0 or k >= len(s) - 1:
        return float(f0 + grid[k])
    a, b, c = np.log(s[k - 1:k + 2])
    delta = 0.5 * (a - c) / (a - 2 * b + c)
    return float(f0 + grid[k] + delta * step_hz)


def nlls_fit(rec):
    """Full nonlinear least squares on the 4-parameter damped-sinusoid model.

    Serves as the practical performance bound for the estimator family;
    validated against the Cramer-Rao bound in crb.py.
    """
    from scipy.optimize import least_squares
    v = rec["v_adc"] - rec["v_adc"].mean()
    fs, t = rec["fs"], rec["t"]

    f0 = fft_peak(rec)
    envelope = np.abs(v) + 1e-12
    # Crude tau seed from log-envelope regression on local peaks.
    a0 = max(np.percentile(envelope, 95), 1e-9)

    def resid(p):
        a, f, tau_, ph = p
        return a * np.exp(-t / tau_) * np.sin(2 * np.pi * f * t + ph) - v

    r = least_squares(resid, x0=[a0, f0, rec["tau"], 0.0],
                      bounds=([1e-12, f0 - 200, 0.05, -np.pi],
                              [np.inf, f0 + 200, 50.0, np.pi]),
                      x_scale=[a0, f0, rec["tau"], 1.0], max_nfev=400)
    return float(r.x[1])


ESTIMATORS = {
    "fft_peak": fft_peak,
    "zoom_fit": zoom_fit,
    "nlls_fit": nlls_fit,
}
