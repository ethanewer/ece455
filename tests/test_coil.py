import math

import pytest

from verification_modeling import physics
from verification_modeling.coil import (
    POLARIZER, SENSOR, current_coil, tuning_capacitance,
)


def test_active_coil_profile():
    coil = current_coil()
    assert coil["design_id"] == "coil-design-xlsx-v1"
    assert coil["n_turns"] == 2 * 1477
    assert math.pi * coil["radius_m"] ** 2 == pytest.approx(0.056 * 0.056)
    assert coil["r_coil"] == pytest.approx(2 * 49.9679)
    assert coil["l_coil"] == pytest.approx(2 * 76.2841e-3)
    assert coil["f_test_low_hz"] == pytest.approx(1765.0)
    assert coil["f_test_high_hz"] == pytest.approx(2129.0)
    assert "c_tune" not in coil
    assert coil["r_in_ohm"] == pytest.approx(2.1e6)
    assert coil["hardware_characterized"] is False
    assert SENSOR["turns"] == 1477


def test_active_coil_maps_to_receiver_fid_amplitude():
    coil = current_coil()
    v0 = physics.estimate_v0(
        b_pol=coil["b_pol"],
        n_turns=coil["n_turns"],
        coil_radius_m=coil["radius_m"],
        b_earth=coil["f_test_low_hz"] / physics.GAMMA_HZ_PER_T,
    )
    assert v0 == pytest.approx(3.587e-6, rel=1e-3)


def test_pair_noise_and_polarizer_time_constant():
    coil = current_coil()
    single_noise = physics.coil_thermal_noise_density(SENSOR["resistance_ohm"])
    assert physics.coil_thermal_noise_density(coil["r_coil"]) == pytest.approx(
        math.sqrt(2) * single_noise
    )
    assert POLARIZER["inductance_h"] / POLARIZER["resistance_ohm"] == pytest.approx(
        1.244e-3, rel=0.002
    )


def test_external_tuning_capacitor_follows_measured_inductance():
    coil = current_coil()
    exact = tuning_capacitance(2100.0)
    assert exact == pytest.approx(37.648e-9, rel=1e-3)
    # A 10% high inductance needs 10% less capacitance at the same frequency.
    assert tuning_capacitance(2100.0, coil["l_coil"] * 1.1) == pytest.approx(
        exact / 1.1
    )


def test_receiver_input_impedance_barely_loads_tuned_sensor():
    coil = current_coil()
    # A tuned tank near 30 kohm loses under 2% of its voltage to the receiver.
    assert 30e3 / (30e3 + coil["r_in_ohm"]) < 0.02
