"""D10: fid.py unit tests.

Covers (TODO.md D10):
  * _bandlimited_noise: PSD flat in band / ~zero outside, RMS = sigma within
    tolerance;
  * ADC quantization step and saturation behavior (with the B6 saturation
    model in generate_record);
  * interferer injection lands at the requested amplitude;
  * estimate_v0 vs an independent Curie-law implementation written in this
    test (agreement < 1e-6 relative).

Run:  python3 -m pytest tests/test_fid_units.py
"""
import numpy as np
import pytest

from conftest import POC  # noqa: F401  (installs poc on sys.path)

import fid


# ---------------------------------------------------------------------------
# _bandlimited_noise
# --------------------------------------------------------------------------- #
def test_bandlimited_noise_rms_matches_sigma():
    rng = np.random.default_rng(42)
    for sigma in (1.0, 25.0, 0.01):
        out = fid._bandlimited_noise(2**15, 20_000.0, 500.0, 3500.0,
                                     sigma, rng)
        rms = float(np.sqrt(np.mean(out**2)))
        assert rms == pytest.approx(sigma, rel=0.02), (sigma, rms)


def test_bandlimited_noise_psd_flat_in_band_zero_outside():
    rng = np.random.default_rng(7)
    n, fs, f_lo, f_hi = 2**16, 20_000.0, 500.0, 3500.0
    out = fid._bandlimited_noise(n, fs, f_lo, f_hi, 2.0, rng)
    spec = np.abs(np.fft.rfft(out))**2
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    # Interior bins all carry power; outside bins are ~zero (roundoff floor
    # of the fft->zero->irfft round trip, 20+ orders below in-bin power).
    in_band = (freqs > 600) & (freqs < 3000)
    out_of_band = (freqs > 4500) | (freqs < 300)
    assert np.all(spec[in_band] > 0)
    assert np.max(spec[out_of_band]) < 1e-20 * np.mean(spec[in_band])
    # Flat in band: white PSD => every bin's expected power equal, bin
    # powers exponentially distributed => mean/median -> 1/ln(2) = 1.4427
    # (a shaped or line spectrum would sit far off this).
    p = spec[(freqs > 550) & (freqs < 3450)]
    assert np.mean(p) / np.median(p) == pytest.approx(1.0 / np.log(2.0),
                                                      abs=0.1)


# ---------------------------------------------------------------------------
# ADC quantization + saturation
# --------------------------------------------------------------------------- #
def test_adc_quantization_step_and_error_bound():
    rec = fid.generate_record(v0=2e-6, gain=5000.0, rng=1)
    lsb = rec["lsb"]
    assert lsb == pytest.approx(2.048 / 2**16)
    q = rec["v_adc"] / lsb
    # Every sample sits exactly on a code level.
    assert np.allclose(q, np.round(q), atol=1e-9)
    # Quantization error vs the pre-clip waveform stays under lsb/2.
    err = np.abs(rec["v_adc"] - rec["v"])
    assert np.all(err <= lsb / 2 + 1e-15)


def test_adc_saturation_clips_at_rails():
    """Crank the gain until the ADC must clip: every sample is bounded by
    the rails and the record reports clipping (B6's fail path)."""
    rec = fid.generate_record(v0=2e-6, gain=500_000.0, rng=3)
    rail = 2.048 / 2
    assert rec["n_clipped"] > 0
    assert np.all(np.abs(rec["v_adc"]) <= rail + 1e-12)
    # And the default reference point does NOT clip.
    rec0 = fid.generate_record(rng=3)
    assert rec0["n_clipped"] == 0


def test_adc_saturation_distorts_signal():
    """Clipping is not a silent no-op: with extreme gain the recorded peak
    pins at the rail instead of tracking (signal+noise)*gain."""
    rec = fid.generate_record(v0=2e-6, gain=2_000_000.0, rng=5)
    rail = 2.048 / 2
    assert np.isclose(np.max(np.abs(rec["v_adc"])), rail, atol=rec["lsb"])


# ---------------------------------------------------------------------------
# Interferer injection
# --------------------------------------------------------------------------- #
def test_interferer_lands_at_requested_amplitude():
    """A single tone out of the FID band, measured on the generated record
    with the signal and noise known: the tone appears at the input amplitude
    times gain."""
    v0, gain = 2e-6, 1000.0
    a_tone = 0.1 * v0
    f_tone = 60.0
    rec = fid.generate_record(v0=v0, gain=gain, rng=9,
                              interferers=[(f_tone, a_tone)])
    # Project the record on the known tone to recover its amplitude.
    t = rec["t"]
    proj = 2.0 * np.mean(rec["v"] * np.sin(2 * np.pi * f_tone * t))
    assert proj == pytest.approx(a_tone * gain, rel=0.05), proj


# ---------------------------------------------------------------------------
# estimate_v0 vs an independent Curie-law implementation
# --------------------------------------------------------------------------- #
def test_estimate_v0_matches_independent_curie_law():
    """Independently re-derive V0 from first principles (SI units, no reuse
    of fid constants beyond CODATA values) and require <1e-6 relative
    agreement.

    M0 = n mu_p^2 B_pol / (k T)           [A/m]     spin-1/2 Curie law
    (the classical Langevin n mu^2 B/(3kT) form is exactly 1/3 of this for
    I = 1/2 -- audit E6 caught the earlier revision using it.)
    EMF = mu0 * M0 * (N * pi r^2) * omega * N ... via Faraday:
        Phi = B_sample * A_eff * N, B_sample = mu0 * M0 (long solenoid),
        EMF_peak = N * A_eff * dPhi/dt / A_eff ... the precessing M rotates
        at omega = 2 pi f_L, so dPhi/dt_peak = mu0 * M0 * A_eff * N * omega.
    """
    k_B = 1.380649e-23
    T = 300.0
    n_water = 6.7e28
    mu_p = 1.4106e-26
    mu0 = 1.25663706e-6

    def v0_independent(b_pol, n_turns, r, b_earth):
        m0 = n_water * mu_p**2 * b_pol / (k_B * T)   # spin-1/2, NOT /3
        omega = 2.0 * np.pi * (42.57638474e6 * b_earth)
        return mu0 * m0 * (np.pi * r**2) * omega * n_turns
        return mu0 * m0 * (np.pi * r**2) * omega * n_turns

    cases = [
        dict(b_pol=0.02, n_turns=530, r=0.015, b_earth=50e-6),
        dict(b_pol=0.05, n_turns=1500, r=0.030, b_earth=50e-6),
        dict(b_pol=0.01, n_turns=300, r=0.010, b_earth=25e-6),
        dict(b_pol=0.05, n_turns=1500, r=0.030, b_earth=65e-6),
    ]
    for kw in cases:
        got = fid.estimate_v0(b_pol=kw["b_pol"], n_turns=kw["n_turns"],
                              coil_radius_m=kw["r"], b_earth=kw["b_earth"])
        want = v0_independent(kw["b_pol"], kw["n_turns"], kw["r"],
                              kw["b_earth"])
        assert abs(got - want) / want < 1e-6, (kw, got, want)


def test_estimate_v0_scales_as_b_earth_b_pol():
    """FID amplitude ~ omega_L * M0 ~ B_earth * B_pol (both couplings)."""
    b1 = fid.estimate_v0(b_pol=0.02, b_earth=50e-6)
    b2 = fid.estimate_v0(b_pol=0.02, b_earth=25e-6)
    assert abs(b1 / b2 - 2.0) < 1e-9          # halving B_earth halves V0
    p1 = fid.estimate_v0(b_pol=0.01, b_earth=50e-6)
    assert abs(b1 / p1 - 2.0) < 1e-9          # halving B_pol halves V0
