import math
import shutil

import pytest

from util import design, simulate, spice
from util.design import BankCapacitor


def test_fid_source_from_the_drawing():
    source = simulate.fid_source(design.amplifier())
    assert source.amplitude_v == pytest.approx(10e-6)
    assert source.frequency_hz == pytest.approx(2268.0)
    assert source.tau_s == pytest.approx(1 / 1.0526)


def test_tank_capacitance_evaluates_the_drawing():
    assert simulate.tank_capacitance(design.amplifier()) == pytest.approx(180e-9)


def test_tuning_rows_pick_the_closest_switch_setting():
    bank = (BankCapacitor("Ca", 100e-9, "SW1", 1), BankCapacitor("Cb", 50e-9, "SW1", 2),
            BankCapacitor("Cc", 25e-9, "SW1", 3))
    inductance = 26.58e-3
    target = simulate.resonance_hz(inductance, 150e-9)
    (row,) = simulate.tuning_rows(bank, {"coil": inductance}, [target])
    assert row["bank_nf"] == pytest.approx(150.0)
    assert row["capacitors"] == "Ca Cb" and row["switches"] == "SW1-1 SW1-2"
    assert row["tuned_hz"] == pytest.approx(target)
    assert simulate.resonance_hz(28.11e-3, 175.2e-9) == pytest.approx(2268, abs=1)


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not installed")
def test_amplifier_operating_point_and_gain():
    s = design.amplifier()
    nodes = simulate.nodes(s)
    deck = simulate.decks(s)[0.0]
    op = spice.operating_point(deck, [nodes["stage1"], nodes["adc_p"], nodes["adc_n"]])
    # 0.5 mV of input offset times the stage gain of 51.
    assert op[nodes["stage1"]] == pytest.approx(2.5 + 51 * 0.5e-3, abs=1e-4)
    assert op[nodes["adc_n"]] == pytest.approx(2.5)
    gain = spice.ac_points(deck, {"stage": f"vm({nodes['stage1']})/vm({nodes['tank']})"}, [2268.0])
    # The stage gain is close to 1 + 50k/1k at the FID frequency.
    assert gain["stage"][0] == pytest.approx(51.0, rel=0.01)
    assert 20 * math.log10(gain["stage"][0]) == pytest.approx(34.15, abs=0.1)
