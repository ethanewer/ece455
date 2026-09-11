"""D7 (re-anchored, REDESIGN.md step 4): estimator behavior locks on the
C core.

Post-redesign there is exactly ONE estimator implementation per algorithm
-- the C core in firmware/core/. These tests lock its measured reference
behavior on synthetic unit vectors (fid.generate_record; NOT a design
score -- the design score is poc/evaluate.py over a full candidate):

  * zoom (the shipped baseline): <=1.2x colored CRB, 0% gross;
  * fft (candidate variant):     <=1.2x colored CRB, 0% gross;
  * zc (candidate variant):      >=100x CRB and >=90% gross -- the
    ruling-out must FAIL LOUDLY if someone "fixes" the zero-crossing
    estimator into a better one or the SNR regime silently shifts.

Also locked: port equivalence of the C fft/zc variants against compact
numpy references written in THIS file (the port-time validation of
REDESIGN.md step 2 -- these references are test-local, not a second
scored implementation).

Measured reference at the 2 uV / T2* = 1.5 s / 200 ms blanking point
(eta_ps = 14.2 dB): zoom 1.02x CRB 0% gross; fft 1.05x 0%; zc ~3800x
100% gross.

Run:  python3 -m pytest tests/test_estimator_reference.py
"""
import numpy as np
import pytest

from conftest import POC  # noqa: F401

import crb
import fe_binding
import fid

N_MC = 160                      # MC 1-sigma on a ratio ~ +/-5.6%
ERR_HZ_THRESHOLD = 1.0          # the gross bar

BASE = dict(b_tesla=50e-6, v0=2e-6, tau=1.5, fs=20_000.0, blanking_s=0.2,
            record_s=1.5, r_coil=120.0, l_coil=2e-3, e_amp=7e-9,
            i_amp=0.05e-12, f_lo=fid.NOISE_BAND[0], f_hi=fid.NOISE_BAND[1],
            gain=5000.0, adc_bits=16, adc_fs=2.048)


# ---------------------------------------------------------------------------
# Test-local numpy references (port validation only; never scored)
# --------------------------------------------------------------------------- #
def _np_fft_peak(v, fs, f_lo, f_hi, zero_pad=16):
    """Zero-padded FFT magnitude peak + log-parabolic interpolation."""
    x = v - v.mean()
    n = len(x)
    L = 1 << int(np.ceil(np.log2(zero_pad * n)))
    spec = np.abs(np.fft.rfft(x, L)) ** 2
    freqs = np.fft.rfftfreq(L, 1.0 / fs)
    band = (freqs >= f_lo) & (freqs <= f_hi)
    k = int(np.flatnonzero(band)[np.argmax(spec[band])])
    a, b, c = np.log(spec[k - 1:k + 2])
    delta = np.clip(0.5 * (a - c) / (a - 2 * b + c), -1.0, 1.0)
    return float(freqs[k] + delta * (freqs[1] - freqs[0]))


def _np_zc_fit(v, fs, f_lo, f_hi):
    """Interpolated rising crossings + slope^2-weighted mean period."""
    x = v - v.mean()
    dt = 1.0 / fs
    rising = (x[:-1] < 0) & (x[1:] >= 0)
    if rising.sum() < 8:
        return float("nan")
    dv = (x[1:] - x[:-1])[rising]
    tc = np.flatnonzero(rising) * dt + dt * (-x[:-1][rising]) / \
        np.where(dv == 0, 1e-12, dv)
    periods = np.diff(tc)
    p0 = 1.0 / _np_fft_peak(v, fs, f_lo, f_hi)
    good = (periods > 0.5 * p0) & (periods < 1.5 * p0)
    if good.sum() < 4:
        return float("nan")
    w = np.minimum(dv[:-1], dv[1:])[good] ** 2
    mean_p = float(np.sum(w * periods[good]) / np.sum(w))
    return float(1.0 / mean_p) if mean_p > 0 else float("nan")


# ---------------------------------------------------------------------------
# Reference table through the C core
# --------------------------------------------------------------------------- #
def _reference_table():
    """(errors per estimator, crb_nt) at fixed seeds -- the same seed
    scheme as the pre-redesign table (phase = 10_000+i, record rng = i)."""
    crb_nt = crb_nt_reference()
    errs = {name: [] for name in fe_binding.ESTIMATORS}
    for i in range(N_MC):
        phase = np.random.default_rng(10_000 + i).uniform(-np.pi, np.pi)
        rec = fid.generate_record(rng=i, phase=phase, **BASE)
        for name in errs:
            f_hat = fe_binding.estimate(name, rec["v_adc"], rec["fs"],
                                        rec["blanking_s"])
            errs[name].append(f_hat - rec["f_larmor"])
    table = {}
    for name, e in errs.items():
        e = np.asarray(e)
        fin = np.isfinite(e)
        table[name] = dict(
            rms_nt=float(np.sqrt(np.mean(e[fin] ** 2))) / fid.GAMMA_HZ_PER_NT
            if fin.sum() else float("inf"),
            gross=float(np.mean(~fin | (np.abs(np.where(fin, e, 1e9))
                                          > ERR_HZ_THRESHOLD))),
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
    """The shipped zoom core and the fft variant ride the bound: <=1.2x
    CRB, 0% gross -- and NOT impossibly below it (>15% under the bound
    would mean the bound or the harness is broken)."""
    tab, crb_nt = table
    for name in ("zoom", "fft"):
        ratio = tab[name]["rms_nt"] / crb_nt
        assert 0.85 < ratio <= 1.2, (name, ratio)
        assert tab[name]["gross"] == 0.0, (name, tab[name]["gross"])
        assert tab[name]["n_finite"] == N_MC      # no NaNs tolerated


def test_zc_fit_is_ruled_out(table):
    """The zero-crossing family must STAY catastrophic at this SNR: >=100x
    CRB and >=90% gross errors. If a change makes the C zc good (or the
    SNR regime shift makes it artificially fail), this pins it -- compare
    the measured ~3800x / 100% at N=400 pre-redesign."""
    tab, crb_nt = table
    ratio = tab["zc"]["rms_nt"] / crb_nt
    assert ratio >= 100.0, ratio          # the ruling-out holds
    assert ratio <= 1e9, ratio            # finite, just catastrophic
    assert tab["zc"]["gross"] >= 0.9, tab["zc"]["gross"]


def test_c_fft_matches_port_reference():
    """Port validation (REDESIGN.md step 2): the C fft variant agrees with
    the numpy zero-padded-FFT reference on the same vectors to a fraction
    of a bin (grid differences: C uses the next pow2 length)."""
    for seed in (0, 1, 2):
        rec = fid.generate_record(rng=seed, phase=0.7, **BASE)
        f_c = fe_binding.estimate("fft", rec["v_adc"], rec["fs"],
                                  rec["blanking_s"])
        f_py = _np_fft_peak(rec["v_adc"], rec["fs"], *fid.NOISE_BAND)
        assert abs(f_c - f_py) < 0.02, (seed, f_c, f_py)   # << 1 Hz gross bar


def test_c_zc_matches_port_reference():
    """Port validation: the C zc variant agrees with the numpy crossing
    reference within the estimator's own (large) variance."""
    for seed in (0, 1, 2, 3):
        rec = fid.generate_record(rng=seed, phase=0.7, **BASE)
        f_c = fe_binding.estimate("zc", rec["v_adc"], rec["fs"],
                                  rec["blanking_s"])
        f_py = _np_zc_fit(rec["v_adc"], rec["fs"], *fid.NOISE_BAND)
        assert np.isfinite(f_c) == np.isfinite(f_py), (seed, f_c, f_py)
        if np.isfinite(f_c):
            # zc's own sigma here is ~8 Hz; agreement must be far tighter
            # than that or the port diverged from the reference algorithm.
            assert abs(f_c - f_py) < 1.0, (seed, f_c, f_py)


def test_fft_lands_on_clean_tone():
    """The C fft variant must be exact on a clean in-band tone (any
    bin/grid bug shows up as an offset >> the parabolic refinement)."""
    fs, n = 20_000.0, 30_000
    t = np.arange(n) / fs
    v = 1e-3 * np.exp(-t / 1.5) * np.sin(2 * np.pi * 2128.8192 * t + 0.7)
    f = fe_binding.estimate("fft", v, fs, 0.2)
    assert abs(f - 2128.8192) < 0.001, f
