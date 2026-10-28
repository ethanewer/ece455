import numpy as np
import pytest

from util import crb, physics


def test_white_crb_matches_real_tone_closed_form():
    fs, n = 20_000.0, 2000
    t = np.arange(n) / fs
    amp, frequency, sigma = 1e-6, 2128.8, 1e-7
    actual = crb.freq_crb(t, amp, frequency, 1e6, 0.0, sigma)
    expected = np.sqrt(
        24 * sigma**2 /
        (amp**2 * (2 * np.pi)**2 * (1 / fs)**2 * n * (n**2 - 1))
    )
    assert actual == pytest.approx(expected, rel=0.02)


def test_crb_in_nanotesla():
    t = np.arange(3000) / 15_000.0
    hz = crb.freq_crb(t, 1e-5, 2268.0, 0.95, 0.3, 1e-7)
    assert crb.crb_nt(t, 1e-5, 2268.0, 0.95, 0.3, 1e-7) == pytest.approx(hz * physics.NT_PER_HZ)
