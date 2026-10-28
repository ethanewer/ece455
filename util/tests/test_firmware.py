"""The firmware's frequency estimator, compiled unchanged on the host."""
import numpy as np
import pytest

from util import design, firmware, physics

pytestmark = pytest.mark.skipif(firmware.compiler() is None, reason="no C compiler")
TAU_S = 0.95
RECORD_S = TAU_S * np.log(10.0)   # the firmware stops at 10% of the initial amplitude


@pytest.fixture(scope="module")
def estimator(tmp_path_factory):
    return firmware.build(tmp_path_factory.mktemp("firmware"))


def record(frequency_hz, amplitude_v, noise_v, sample_rate, seed=0):
    t = np.arange(int(RECORD_S * sample_rate)) / sample_rate
    rng = np.random.default_rng(seed)
    volts = physics.fid(t, amplitude_v, frequency_hz, TAU_S, 0.7) + rng.normal(0, noise_v, t.size)
    return firmware.volts_to_codes(volts)


@pytest.mark.parametrize("sample_rate", [15000.0, 20000.0])
@pytest.mark.parametrize("frequency_hz", [1500.0, 2000.0, 2268.0, 2500.0])
def test_clean_fid_across_the_band(estimator, frequency_hz, sample_rate):
    result = firmware.estimate(estimator, record(frequency_hz, 0.04, 0.0, sample_rate), sample_rate)
    assert result["valid"] == 1
    assert result["frequency_hz"] == pytest.approx(frequency_hz, abs=1e-3)
    assert result["rejected"] == 0


# The as-built Curie-law FID (about 2 uV at the coils) is 30-40 mV at the ADC,
# with about 1 mV RMS of wideband noise (docs/simulation/README.md).
AS_BUILT_V, NOISE_V = 0.030, 1e-3


def test_as_built_fid_near_the_tuned_frequency(estimator):
    errors = [firmware.estimate(estimator, record(2268.0, AS_BUILT_V, NOISE_V, 15000.0, seed),
                                15000.0)["frequency_hz"] - 2268.0 for seed in range(5)]
    assert np.max(np.abs(errors)) * physics.NT_PER_HZ < 0.1


def test_clipping_keeps_frequency_but_not_vpp(estimator):
    """The simulated FID is about three times the PGA 64 full scale."""
    full_scale = design.adc_full_scale_v()
    result = firmware.estimate(estimator, record(2268.0, 3 * full_scale, 0.0, 15000.0), 15000.0)
    assert result["frequency_hz"] == pytest.approx(2268.0, abs=1e-3)
    assert result["vpp_v"] == pytest.approx(2 * full_scale, rel=1e-6)


def test_field_conversion_uses_the_free_proton_ratio(estimator):
    result = firmware.estimate(estimator, record(2268.0, 0.04, 0.0, 15000.0), 15000.0)
    assert design.firmware_constants()["PROTON_GYROMAGNETIC_HZ_PER_T"] == pytest.approx(
        physics.FREE_PROTON_GAMMA_HZ_PER_T)
    assert result["bfield_nt"] == pytest.approx(
        result["frequency_hz"] / physics.FREE_PROTON_GAMMA_HZ_PER_T * 1e9, rel=1e-9)
    # The shielded-proton field is 25.7 ppm higher: about 1.4 nT here.
    shielded = physics.field_nt(result["frequency_hz"])
    assert shielded - result["bfield_nt"] == pytest.approx(1.37, abs=0.02)


@pytest.mark.xfail(strict=True, reason=(
    "Known firmware limitation: a missed crossing is converted to whole cycles with "
    "EXPECTED_FREQ_CENTER_HZ, so near 1.5 kHz two periods count as three and the fit is "
    "biased high once noise approaches the decayed amplitude."))
def test_as_built_fid_at_the_band_edge(estimator):
    errors = [firmware.estimate(estimator, record(1500.0, AS_BUILT_V, NOISE_V, 15000.0, seed),
                                15000.0)["frequency_hz"] - 1500.0 for seed in range(5)]
    assert np.max(np.abs(errors)) < 0.1
