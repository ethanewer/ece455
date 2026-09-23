import numpy as np
import pytest

from verification_modeling import physics


def test_shielded_proton_constants_and_larmor_frequency():
    assert physics.GAMMA_HZ_PER_T == pytest.approx(42.57638474e6, abs=0.05)
    assert physics.GAMMA_HZ_PER_NT == pytest.approx(0.04257638474, abs=1e-11)
    assert physics.larmor_hz(50e-6) == pytest.approx(2128.819237, abs=0.01)


def test_v0_matches_independent_spin_half_curie_law():
    b_pol, turns, radius, b_earth = 0.02, 530, 0.015, 50e-6
    m0 = 6.7e28 * (1.4106e-26) ** 2 * b_pol / (1.380649e-23 * 300.0)
    expected = (1.25663706e-6 * m0 * np.pi * radius**2 *
                2 * np.pi * 42.57638474e6 * b_earth * turns)
    actual = physics.estimate_v0(b_pol, turns, radius, b_earth=b_earth)
    assert actual == pytest.approx(expected, rel=1e-6)
    assert actual == pytest.approx(0.4054e-6, rel=0.01)


def test_bandlimited_noise_has_requested_rms_and_band():
    fs, n = 20_000.0, 2**15
    out = physics._bandlimited_noise(
        n, fs, 500.0, 3500.0, 2.0, np.random.default_rng(42)
    )
    assert np.sqrt(np.mean(out**2)) == pytest.approx(2.0, rel=0.02)
    spectrum = np.abs(np.fft.rfft(out)) ** 2
    frequencies = np.fft.rfftfreq(n, 1 / fs)
    in_band = (frequencies > 600) & (frequencies < 3000)
    out_of_band = (frequencies < 300) | (frequencies > 4500)
    assert np.max(spectrum[out_of_band]) < 1e-20 * np.mean(spectrum[in_band])


def test_front_end_noise_includes_bias_resistor():
    density = physics.front_end_noise_density(2128.819237)
    # Coil, 1 kohm, 100 kohm through C5, and 5.5 nV/sqrt(Hz), at 300 K.
    assert density == pytest.approx(11.5e-9, rel=0.05)
    coil_only = physics.input_noise_density(
        np.array([2128.819237]), 14.0, 22e-3, 5.5e-9, 1.5e-15
    )[0]
    assert density > coil_only


def test_adc_quantization_and_clipping():
    nominal = physics.generate_record(rng=3)
    assert nominal["n_clipped"] == 0
    assert np.allclose(nominal["v_adc"] / nominal["lsb"],
                       np.round(nominal["v_adc"] / nominal["lsb"]), atol=1e-9)

    clipped = physics.generate_record(v0=2e-6, gain=2_000_000.0, rng=5)
    assert clipped["n_clipped"] > 0
    assert np.max(np.abs(clipped["v_adc"])) == pytest.approx(2.048 / 2)
