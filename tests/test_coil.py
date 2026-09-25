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
    assert coil["c_tune"] == pytest.approx(51.7e-9)
    assert coil["c_tune_alt"] == pytest.approx(37.7e-9)
    assert coil["f_tune_alt_hz"] == pytest.approx(2098.5, abs=0.5)
    assert coil["r_in_ohm"] == pytest.approx(8.2e6)
    assert coil["hardware_characterized"] is False
    assert SENSOR["turns"] == 1477


def test_active_coil_maps_to_receiver_fid_amplitude():
    coil = current_coil()
    v0 = physics.estimate_v0(
        b_pol=coil["b_pol"],
        n_turns=coil["n_turns"],
        coil_radius_m=coil["radius_m"],
        b_earth=coil["f_tune_hz"] / physics.GAMMA_HZ_PER_T,
    )
    assert coil["f_tune_hz"] == pytest.approx(1792.020, abs=0.01)
    assert v0 == pytest.approx(3.642200856e-6, rel=1e-6)


def test_pair_noise_tank_and_polarizer_time_constant():
    coil = current_coil()
    single_noise = physics.coil_thermal_noise_density(SENSOR["resistance_ohm"])
    assert physics.coil_thermal_noise_density(coil["r_coil"]) == pytest.approx(
        math.sqrt(2) * single_noise
    )
    omega = 2.0 * math.pi * coil["f_tune_hz"]
    q_unloaded = omega * coil["l_coil"] / coil["r_coil"]
    assert q_unloaded == pytest.approx(17.19, abs=0.02)
    loaded = coil["r_in_ohm"] / (coil["r_in_ohm"] + q_unloaded * omega * coil["l_coil"])
    assert loaded == pytest.approx(1.0, abs=0.01)
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


def test_amplifier_load_is_5_to_10_megohm_at_resonance():
    coil = current_coil()
    omega = 2.0 * math.pi * coil["f_tune_hz"]
    # R1 + R2 + C5, the network in parallel with C25 and C26.
    impedance = 1.0e3 + coil["r_in_ohm"] + 1.0 / (1j * omega * 3.3e-9)
    assert 5.0e6 <= abs(impedance) <= 10.0e6
