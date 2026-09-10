"""Frequency estimators for the FID, from cheapest to most expensive.

All operate on the sampled record dict produced by fid.generate_record and
return an estimate of the Larmor frequency in Hz. These are reference
implementations: the MCU firmware ports of the same estimators can be
validated against them on identical synthetic records.

Audits flagged that zoom_fit/nlls_fit were seeded with the TRUE decay
constant from the record dict. All three estimators now estimate tau from
the data (or ignore it); the tau-misspecification ablation in
run_scoring.py measures the residual sensitivity.
"""
import numpy as np


def _estimate_tau(t, v, frac=0.5):
    """Estimate the decay constant from the signal envelope.

    Noise-robust version: block-maxima of the analytic-signal envelope (one
    block per ~2 carrier periods) kill per-sample envelope noise; the log
    fit uses only the contiguous blocks from the peak down to `frac` of it.
    A noise-floor gate is the WRONG criterion here: at these SNRs the FID
    never decays below the noise floor within the record, so floor-based
    masks either empty out (then a naive fallback includes the flat noise
    tail and biases tau high by ~2x, which diverged NLLS) or admit the flat
    tail. Amplitude gating keeps the fit in the >= -6 dB region where the
    envelope is signal-dominated. Returns 1.0 s when the record is too far
    decayed to fit.
    """
    from scipy.signal import hilbert
    env = np.abs(hilbert(v))
    n = len(v)
    block = max(1, n // 256)
    n_blk = n // block
    if n_blk < 8:
        return 1.0
    blk_env = env[:n_blk * block].reshape(n_blk, block).max(axis=1)
    blk_t = t[:n_blk * block].reshape(n_blk, block).mean(axis=1)
    below = np.nonzero(blk_env < frac * blk_env.max())[0]
    end = int(below[0]) if len(below) else n_blk
    mask = np.arange(n_blk) < end
    if mask.sum() < 8:
        return 1.0
    slope = np.polyfit(blk_t[mask], np.log(blk_env[mask]), 1)[0]
    if slope >= 0:
        return 1.0
    return float(np.clip(-1.0 / slope, 0.1, 20.0))


def fft_peak(rec, zero_pad=16):
    """FFT magnitude peak with log-parabolic interpolation.

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
    M4. The decay constant is estimated from the data (analytic-signal
    envelope regression), not taken from the simulation truth.
    """
    from scipy.signal import resample_poly
    v = rec["v_adc"] - rec["v_adc"].mean()
    fs, t = rec["fs"], rec["t"]
    if tau is None:
        tau = _estimate_tau(t, v)

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


def zc_fit(rec):
    """Zero-crossing estimator: interpolated crossings + WLS mean period.

    The best-practice version of what the prior capstone teams built:
    linearly-interpolated rising-edge crossing times, then a weighted mean
    of adjacent periods with variance-optimal weights. The crossing-time
    noise is sigma_v/|dv/dt|, so the weight for the period between two
    crossings is the smaller squared slope of the pair -- which
    automatically downweights the noisy late record where dv/dt collapses.

    Periods physically implausible vs the coarse FFT frequency are dropped
    (robustness against cycle slips: noise-driven missing or double
    crossings). A naive regression of crossing time on crossing INDEX was
    tried first and fails catastrophically (70% gross errors at this SNR):
    a single missed crossing shifts every subsequent index and the fit
    diverges. Kept in-repo (audit: the ruling-out of the crossing family
    must be a regression this tree can run); see run_scoring.py for the
    measured variance gap vs the CRLB.
    """
    v = rec["v_adc"] - rec["v_adc"].mean()
    fs, t = rec["fs"], rec["t"]
    dt = 1.0 / fs

    rising = (v[:-1] < 0) & (v[1:] >= 0)
    if rising.sum() < 8:
        return float("nan")
    dv = (v[1:] - v[:-1])[rising]
    tc = t[:-1][rising] + dt * (-v[:-1][rising]) / np.where(dv == 0, 1e-12, dv)

    periods = np.diff(tc)
    p0 = 1.0 / fft_peak(rec)
    good = (periods > 0.5 * p0) & (periods < 1.5 * p0)
    if good.sum() < 4:
        return float("nan")
    w = np.minimum(dv[:-1], dv[1:])[good] ** 2
    mean_p = float(np.sum(w * periods[good]) / np.sum(w))
    if mean_p <= 0:
        return float("nan")
    return float(1.0 / mean_p)


def nlls_fit(rec, tau=None):
    """Two-stage nonlinear least squares on the damped-sinusoid model.

    Stage 1 fits (a, f, phase) with tau FIXED at the envelope estimate;
    stage 2 refines all four parameters from stage 1. The staged structure
    is not cosmetic: at FID-class SNR (~14 dB per-sample) the 4-parameter
    likelihood surface has local minima in the (f, tau) coupling -- a
    single-shot 4-param LSQ seeded only from the FFT peak diverges on ~10%
    of records (measured), while the staged fit seeded from zoom_fit stays
    on the bound. zoom_fit's basin is enormous, so its solution is the
    right place to start the nonlinear refinement.

    Serves as the practical performance reference; validated against the
    Cramer-Rao bound in crb.py (see test_validation.py).
    """
    from scipy.optimize import least_squares
    v = rec["v_adc"] - rec["v_adc"].mean()
    fs, t = rec["fs"], rec["t"]

    f0 = zoom_fit(rec)
    envelope = np.abs(v) + 1e-12
    a0 = max(np.percentile(envelope, 95), 1e-9)
    if tau is None:
        tau = _estimate_tau(t, v)

    def resid4(p):
        a, f, tau_, ph = p
        return a * np.exp(-t / tau_) * np.sin(2 * np.pi * f * t + ph) - v

    r1 = least_squares(lambda p: p[0] * np.exp(-t / tau) * np.sin(2 * np.pi * p[1] * t + p[2]) - v,
                       x0=[a0, f0, 0.0],
                       bounds=([1e-12, f0 - 200, -np.pi], [np.inf, f0 + 200, np.pi]),
                       x_scale=[a0, f0, 1.0], max_nfev=200)
    r2 = least_squares(resid4, x0=[r1.x[0], r1.x[1], tau, r1.x[2]],
                       bounds=([1e-12, f0 - 200, 0.1, -np.pi],
                               [np.inf, f0 + 200, 20.0, np.pi]),
                       x_scale=[a0, f0, max(tau, 0.5), 1.0], max_nfev=400)
    return float(r2.x[1])


ESTIMATORS = {
    "fft_peak": fft_peak,
    "zoom_fit": zoom_fit,
    "zc_fit": zc_fit,
    "nlls_fit": nlls_fit,
}
