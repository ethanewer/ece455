"""Numpy mirror of firmware/core/freq_est.c (the C1 estimator algorithm).

The C core and this mirror implement the SAME algorithm (Goertzel coarse
seed -> NCO mix -> windowed-sinc FIR decimate -> envelope tau -> weighted
zoom grid -> log-parabolic refine). The host tests run the C library and
this mirror on identical golden vectors and require agreement, so any C
side bug (fixed-point saturation, NCO table, FIR indexing) shows up as a
C-vs-mirror divergence, and the mirror gives Python-level debugging.

This is deliberately an ALGORITHM mirror, not a wrapper of
poc/estimators.zoom_fit: zoom_fit uses scipy's resample_poly FIR and a
Hilbert-transform tau; the MCU core uses its own windowed-sinc FIR and the
mixed-signal envelope. Both are validated against the CRB gates
(sensitivity-score job), which is the acceptance test that matters.
"""
import numpy as np

FE_DEC = 10
FE_FIR_TAPS = 33
FE_SPAN_HZ = 20.0
FE_STEP_HZ = 0.02
FE_SEED_WINDOW = 8192


def _fir_coeffs(fs):
    n = FE_FIR_TAPS
    mid = (n - 1) // 2
    fc = fs / (2 * FE_DEC)
    i = np.arange(n)
    k = i - mid
    with np.errstate(divide="ignore", invalid="ignore"):
        sinc = np.ones(n)
        nz = k != 0
        sinc[nz] = np.sin(np.pi * k[nz] * 2 * fc / fs) / (np.pi * k[nz])
    win = 0.54 - 0.46 * np.cos(2 * np.pi * i / (n - 1))
    h = 2 * fc / fs * sinc * win
    return h / h.sum()


def _log_parabolic(s, k):
    a, b, c = np.log([max(s[k - 1], 1e-300), max(s[k], 1e-300),
                      max(s[k + 1], 1e-300)])
    den = a - 2 * b + c
    if den == 0:
        return 0.0
    return float(np.clip(0.5 * (a - c) / den, -1.0, 1.0))


def fe_mirror(v: np.ndarray, fs: float, t0: float, f_lo: float, f_hi: float
              ) -> float:
    """Float mirror of freq_est_f32 (v: float32 ADC-domain samples)."""
    n = len(v)
    x = v.astype(np.float64) - v.mean()

    # coarse seed
    nseed = min(n, FE_SEED_WINDOW)
    df_bin = fs / nseed
    k = np.arange(int(np.ceil(f_lo / df_bin)), int(np.floor(f_hi / df_bin)) + 1)
    ang = 2 * np.pi * np.outer(k, np.arange(nseed)) / nseed
    # Goertzel == DFT bin for real input; vectorize in blocks to bound RAM
    best = -1.0
    best_k = k[0]
    for kk in np.array_split(k, max(1, len(k) // 128)):
        a = 2 * np.pi * np.outer(kk, np.arange(nseed)) / nseed
        sp = np.abs(np.exp(-1j * a) @ x[:nseed]) ** 2
        j = int(np.argmax(sp))
        if sp[j] > best:
            best = sp[j]
            best_k = kk[j]
    if k[0] < best_k < k[-1]:
        a = 2 * np.pi * np.outer(best_k - 1 + np.arange(3), np.arange(nseed)) / nseed
        s3 = np.abs(np.exp(-1j * a) @ x[:nseed]) ** 2
        f0 = best_k * df_bin + _log_parabolic(s3, 1) * df_bin
    else:
        f0 = best_k * df_bin

    # NCO mix
    t = t0 + np.arange(n) / fs
    z = x * np.exp(-2j * np.pi * f0 * t)

    # FIR lowpass + decimate
    h = _fir_coeffs(fs)
    m = (n - FE_FIR_TAPS) // FE_DEC + 1
    zb = np.empty(m, dtype=complex)
    for i in range(m):
        zb[i] = np.dot(h, z[i * FE_DEC:i * FE_DEC + FE_FIR_TAPS])

    # tau from block maxima of |zb|
    dtb = FE_DEC / fs
    blk = m // 256
    n_blk = m // blk if blk > 0 else 0
    if n_blk < 8:
        tau = 1.0
    else:
        env = np.abs(zb[:n_blk * blk]).reshape(n_blk, blk).max(axis=1)
        mx = env.max()
        below = np.nonzero(env < 0.5 * mx)[0]
        end = int(below[0]) if len(below) else n_blk
        if end < 8:
            tau = 1.0
        else:
            bt = (np.arange(end) + 0.5) * blk * dtb
            slope = np.polyfit(bt, np.log(np.maximum(env[:end], 1e-300)), 1)[0]
            tau = float(np.clip(-1.0 / slope, 0.1, 20.0)) if slope < 0 else 1.0

    # weighted zoom grid
    tb = t0 + np.arange(m) * dtb
    w = np.exp(-tb / tau)
    grid = np.arange(-FE_SPAN_HZ, FE_SPAN_HZ + FE_STEP_HZ / 2, FE_STEP_HZ)
    s = np.empty(len(grid))
    for i, df in enumerate(grid):
        s[i] = np.abs(np.sum(w * zb * np.exp(-2j * np.pi * df * tb))) ** 2
    kg = int(np.argmax(s))
    if kg <= 0 or kg >= len(s) - 1:
        return f0 + grid[kg]
    return f0 + grid[kg] + _log_parabolic(s, kg) * FE_STEP_HZ
