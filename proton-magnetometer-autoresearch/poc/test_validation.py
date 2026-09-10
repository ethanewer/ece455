"""Standing regression tests for the scoring harness (audit v0.0 follow-up).

Run:  python3 test_validation.py   (or pytest test_validation.py)

These encode the checks both v0.0 audits ran by hand, so they keep passing
as the harness evolves:
  1. white-noise CRB vs the closed-form Rife-Boorstyn real-tone bound;
  2. colored-noise CRB vs an INDEPENDENT Fisher computation through an
     explicitly constructed dense covariance matrix (no DFT-domain bin
     weighting involved -- the shortcut in crb.py is easy to get wrong);
  3. the recommended estimator (zoom_fit) sits on the colored CRB;
  4. the physics V0 model lands in a physically sensible range;
  5. the gyromagnetic constants are the shielded-proton set.
"""
import numpy as np

import crb
import fid
from estimators import zoom_fit


def test_white_crb_matches_rife_boorstyn():
    """Closed form, real tone, tau >> T:
    var(f) = 24 sigma^2 / (A^2 dt^2 N (N^2-1)) -- 2x the complex-tone
    Rife-Boorstyn bound because a real tone carries half the information."""
    fs, n = 20_000.0, 2000
    t = np.arange(n) / fs
    a, f0, sigma = 1e-6, 2128.8, 1e-7
    got = crb.freq_crb(t, a, f0, 1e6, 0.0, sigma)          # tau huge = undamped
    dt = 1.0 / fs
    # The classic bound is on angular frequency: var(omega) =
    # 24 sigma^2 / (A^2 dt^2 N (N^2-1)); divide by (2 pi)^2 for Hz.
    want = np.sqrt(24 * sigma**2
                   / (a**2 * (2 * np.pi)**2 * dt**2 * n * (n**2 - 1)))
    assert abs(got / want - 1.0) < 0.02, (got, want)


def test_colored_crb_vs_dense_covariance():
    """Independent Fisher information via an explicitly constructed
    covariance matrix (dense solve; no DFT-domain reasoning at all).

    Process: flat one-sided density S1 = sigma^2/(f_hi-f_lo) in band plus a
    small white floor (1e-4 of in-band density) so the covariance is
    positive definite -- an exactly band-limited process is SINGULAR
    (rank ~ 2B n/fs), and its pseudo-inverse is exactly the conservative
    convention the shortcut uses; the floor is also more physical, since no
    real front end has zero out-of-band noise. Autocorrelation of the line
    component: C[m] = S1 [sin(2p f_hi m/fs) - sin(2p f_lo m/fs)]/(2p m/fs).
    """
    fs, n = 20_000, 900
    t = np.arange(n) / fs
    amp, freq, tau = 1e-6, 2128.8, 1.5
    sigma = 1e-7
    f_lo, f_hi = fid.NOISE_BAND

    s1 = sigma**2 / (f_hi - f_lo)
    nz = np.arange(1, n)
    cov = np.empty(n)
    cov[0] = s1 * (f_hi - f_lo) + (s1 * 1e-3) * fs / 2
    cov[1:] = s1 * (np.sin(2 * np.pi * f_hi * nz / fs)
                    - np.sin(2 * np.pi * f_lo * nz / fs)) / (2 * np.pi * nz / fs)
    C = cov[np.abs(np.subtract.outer(np.arange(n), np.arange(n)))]

    p = crb.partials(t, amp, freq, tau, 0.0)
    keys = crb.PARAM_ORDER
    j = np.zeros((4, 4))
    for i, ki in enumerate(keys):
        for jj, kj in enumerate(keys):
            j[i, jj] = p[ki] @ np.linalg.solve(C, p[kj])
    got = np.sqrt(np.linalg.inv(j)[1, 1])

    want = crb.freq_crb_colored(t, amp, freq, tau, 0.0, fs, f_lo, f_hi, sigma)
    assert abs(got / want - 1.0) < 0.10, (got, want)


def test_zoom_sits_on_colored_crb():
    sigma_in = fid.input_noise_rms()
    t = 0.2 + np.arange(30_000) / 20_000.0
    bound_nt = crb.freq_crb_colored(t, 2e-6, fid.larmor_hz(50e-6), 1.5, 0.0,
                                    20_000.0, *fid.NOISE_BAND, sigma_in
                                    ) / fid.GAMMA_HZ_PER_NT
    errs = []
    for i in range(120):
        phase = np.random.default_rng(30_000 + i).uniform(-np.pi, np.pi)
        rec = fid.generate_record(rng=i, phase=phase)
        errs.append(zoom_fit(rec) - rec["f_larmor"])
    rms_nt = float(np.sqrt(np.mean(np.square(errs)))) / fid.GAMMA_HZ_PER_NT
    assert rms_nt / bound_nt < 1.15, (rms_nt, bound_nt)


def test_estimate_v0_sensible():
    # Koehler: "induced voltage of the order of microvolts" for realistic
    # PPM coils; a Hook-Line-class coil at 20 mT should give 0.05-1 uV.
    v0 = fid.estimate_v0(b_pol=0.02, n_turns=530, coil_radius_m=0.015)
    assert 0.03e-6 < v0 < 2e-6, v0
    # Monotone in each driver.
    assert fid.estimate_v0(b_pol=0.05) > fid.estimate_v0(b_pol=0.01)
    assert fid.estimate_v0(n_turns=1000) > fid.estimate_v0(n_turns=500)


def test_gamma_constants_consistent():
    # Shielded-proton value; the bare proton (42.577478e6) is 25.7 ppm higher.
    assert abs(fid.GAMMA_HZ_PER_T - 42.57638507e6) < 1.0
    assert abs(fid.GAMMA_HZ_PER_NT - 0.04257638507) < 1e-9
    assert abs(fid.NT_PER_HZ - 23.4872) < 1e-3
    assert abs(fid.larmor_hz(50e-6) - 2128.82) < 0.01


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
