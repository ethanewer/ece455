"""Lock hardware mapping and guard against returning to old-coil search."""
import copy
import math
import numpy as np
import pytest
from conftest import PIPELINE
import circuit_spec as cs
import fid
from coil_design import current_coil, current_candidates, POLARIZER
from optimizer.mutations import base_candidates, mutate


def test_square_signal_and_pair_noise():
    c = current_coil()
    assert c['n_turns'] == 552
    assert math.pi * c['radius_m']**2 == pytest.approx(0.0036)
    assert c['r_coil'] == 14
    assert c['l_coil'] == 0.022
    assert fid.coil_thermal_noise_density(c['r_coil']) == pytest.approx(
        math.sqrt(2) * fid.coil_thermal_noise_density(7))
    assert 1 / (2 * math.pi * math.sqrt(c['l_coil'] * c['c_tune'])) == pytest.approx(2088, rel=0.001)
    assert POLARIZER['inductance_h'] / POLARIZER['resistance_ohm'] == pytest.approx(0.0051333333)
    assert POLARIZER['field_t'] == pytest.approx(9.38e-3)
    assert POLARIZER['field_t_ideal'] == pytest.approx(13.6e-3)
    assert c['t2_star_s'] == pytest.approx(0.95)
    assert c['hardware_characterized'] is False


def test_mutations_keep_hardware_fixed():
    rng = np.random.default_rng(91)
    for seed in base_candidates():
        child = seed
        for _ in range(100):
            child = mutate(child, rng)
            spec = cs.afe_spec(**child)
            assert {k: v for k, v in spec['meta']['coil'].items() if k != 'c_tune'} == {
                k: v for k, v in current_coil().items() if k != 'c_tune'}
    kw = copy.deepcopy(base_candidates()[0])
    kw['coil']['n_turns'] *= 2
    with pytest.raises(ValueError, match='fixed'):
        cs.afe_spec(**kw)


def test_band_tuning_uses_pair_inductance():
    for label, b, kw in cs.band_candidates():
        cs.afe_spec(label, **kw)
        c = kw['coil']
        assert 1 / (2 * math.pi * math.sqrt(c['l_coil'] * c['c_tune'])) == pytest.approx(fid.larmor_hz(b))
