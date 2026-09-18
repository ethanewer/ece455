import numpy as np
import pytest

from verification_modeling import crb, physics


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


def test_shaped_crb_reduces_to_flat_bandlimited_case():
    fs, n = 20_000.0, 900
    t = np.arange(n) / fs
    amp, frequency, tau, sigma = 1e-6, 2128.8, 1.5, 1e-7
    low, high = physics.NOISE_BAND
    expected = crb.freq_crb_colored(
        t, amp, frequency, tau, 0.0, fs, low, high, sigma
    )
    bins = np.fft.rfftfreq(n, 1 / fs)
    density = np.where(
        (bins >= low) & (bins <= high), sigma**2 / (high - low), 1e30
    )
    actual = crb.freq_crb_shaped(t, amp, frequency, tau, 0.0, fs, density)
    assert actual == pytest.approx(expected, rel=0.01)
