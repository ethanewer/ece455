import numpy as np
import pytest

from util import physics


def test_shielded_proton_constants_and_larmor_frequency():
    assert physics.GAMMA_HZ_PER_T == pytest.approx(42.57638474e6, abs=0.05)
    assert physics.GAMMA_HZ_PER_NT == pytest.approx(0.04257638474, abs=1e-11)
    assert physics.larmor_hz(50e-6) == pytest.approx(2128.819237, abs=0.01)
    assert physics.field_nt(physics.larmor_hz(50e-6)) == pytest.approx(50_000.0)


def test_free_proton_ratio_is_25_7_ppm_higher():
    ratio = physics.FREE_PROTON_GAMMA_HZ_PER_T / physics.GAMMA_HZ_PER_T - 1
    assert ratio * 1e6 == pytest.approx(25.7, abs=0.1)


def test_fid_decays_with_tau():
    t = np.array([0.0, 1.0])
    envelope = physics.fid(t, 2.0, 0.25, 1.0, np.pi / 2)
    assert envelope == pytest.approx([2.0, 2.0 * np.exp(-1.0) * np.cos(np.pi / 2 + 0)], abs=1e-12)
