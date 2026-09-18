import math

import pytest

from verification_modeling import physics
from verification_modeling.coil import POLARIZER, current_coil


def test_active_coil_profile():
    coil = current_coil()
    assert coil["design_id"] == "week3-hunter-vania-v1"
    assert coil["n_turns"] == 552
    assert math.pi * coil["radius_m"] ** 2 == pytest.approx(0.0036)
    assert coil["r_coil"] == 14.0
    assert coil["l_coil"] == 22e-3
    assert coil["hardware_characterized"] is False


def test_active_coil_maps_to_receiver_fid_amplitude():
    coil = current_coil()
    v0 = physics.estimate_v0(
        b_pol=coil["b_pol"],
        n_turns=coil["n_turns"],
        coil_radius_m=coil["radius_m"],
        b_earth=50e-6,
    )
    assert v0 == pytest.approx(1.008442079e-6, rel=1e-8)


def test_pair_noise_resonance_and_polarizer_time_constant():
    coil = current_coil()
    single_noise = physics.coil_thermal_noise_density(7.0)
    assert physics.coil_thermal_noise_density(coil["r_coil"]) == pytest.approx(
        math.sqrt(2) * single_noise
    )
    resonance = 1 / (2 * math.pi * math.sqrt(coil["l_coil"] * coil["c_tune"]))
    assert coil["c_tune_nominal"] == pytest.approx(264e-9)
    assert resonance == pytest.approx(physics.larmor_hz(50e-6), rel=1e-9)
    assert POLARIZER["inductance_h"] / POLARIZER["resistance_ohm"] == pytest.approx(
        0.0051333333
    )
