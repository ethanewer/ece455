import json
import math
import shutil
from pathlib import Path

import pytest

from util import design, spice
from util.ltspice import OPAMP_SUBCIRCUIT, _orient, ngspice_deck, read_asc, spice_number

FIXTURES = Path(__file__).parent / "fixtures"
needs_ngspice = pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not installed")


def test_spice_numbers():
    assert spice_number("4.6nF") == pytest.approx(4.6e-9)
    assert spice_number("10Meg") == pytest.approx(10e6)
    assert spice_number("1µF") == pytest.approx(1e-6)
    assert spice_number("1T") == pytest.approx(1e12)
    assert spice_number("1K") == pytest.approx(1e3)
    assert spice_number("10uV") == pytest.approx(10e-6)
    with pytest.raises(ValueError):
        spice_number("{Cnom}")


def test_symbol_orientation():
    # C4 is drawn at R90: its pins (16, 0) and (16, 64) land at (0, 16) and (-64, 16).
    assert _orient(16, 0, "R90") == (0, 16)
    assert _orient(16, 64, "R90") == (-64, 16)
    assert _orient(0, 16, "R180") == (0, -16)
    assert _orient(16, 0, "M0") == (-16, 0)


def test_amplifier_topology():
    s = design.amplifier()
    tank = s.node("C1", 1)
    # V1 drives the coil (R5, L1) into the tank capacitor.
    assert s.node("V1", 2) == "0" and s.node("C1", 2) == "0"
    assert s.node("V1", 1) == s.node("R5", 2) and s.node("R5", 1) == s.node("L1", 2)
    assert s.node("L1", 1) == tank == s.node("C4", 2)
    # Stage 1: +IN through C4 and biased by R8; gain set by R3 / R4 to 2.5 V.
    plus, minus, vp, vn, out = s.elements["U1"].nodes
    assert plus == s.node("C4", 1) and {s.node("R8", 1), s.node("R8", 2)} == {plus, "n25P"}
    assert {s.node("R3", 1), s.node("R3", 2)} == {minus, out} and out == "VopAmpOut1"
    assert {s.node("R4", 1), s.node("R4", 2)} == {minus, "n25P"}
    assert (vp, vn) == ("n5P", "0")
    # Stage 2 and the output network.
    plus2, minus2, _, _, out2 = s.elements["U2"].nodes
    assert set(s.elements["C5"].nodes) == {out, plus2}
    assert set(s.elements["C6"].nodes) == {out2, "VopAmpOut2"}
    assert set(s.elements["C2"].nodes) == {"VopAmpOut2", "AIN1"}
    assert s.flags["AIN3"] == s.flags["25P"] == "n25P"
    assert s.unconnected == {"V6"}
    assert s.steps == {"tol": (-0.05, 0.0, 0.05)}
    assert s.params == {"Cnom": "180n"}


def test_every_element_has_one_role():
    s = design.amplifier()
    roles = [design.FID_SOURCE, *design.COIL, design.TANK, *design.AMPLIFIER_PARTS,
             *design.BOARD_PARTS, *design.MODEL_PARTS, *design.SUPPLIES, *s.unconnected]
    assert sorted(roles) == sorted(s.elements)


def test_unknown_symbol_is_rejected(tmp_path):
    asc = tmp_path / "bad.asc"
    asc.write_text("Version 4\nSHEET 1 100 100\nSYMBOL diode 0 0 R0\nSYMATTR InstName D1\n")
    with pytest.raises(ValueError, match="no pin offsets"):
        read_asc(asc)


def test_deck_overrides_parameters_and_marks_ac_source():
    deck = ngspice_deck(design.amplifier(), title="t", params={"tol": 0.05}, ac_source="V1")
    assert ".param tol=0.05" in deck and ".param Cnom=180n" in deck
    assert "V1 r5_2 0 DC 0 SIN(0 10uV 2268 0 1.0526 0) AC 1" in deck
    assert "XU1 c4_1 c8_1 n5P 0 VopAmpOut1 universalopamp2 avol=316k" in deck
    assert "* V6 (SINE(0 100u 60)) is not connected" in deck
    assert "L1 c1_1 L1_rser 28.11m" in deck and "RL1_rser L1_rser l1_2 1m" in deck


@needs_ngspice
def test_ngspice_translation_matches_ltspice():
    """The frozen drawing, simulated in ngspice, agrees with LTspice 17.2.4."""
    s = read_asc(FIXTURES / "ltspice-reference.asc")
    reference = json.loads((FIXTURES / "ltspice-reference.json").read_text())
    deck = ngspice_deck(s, title="reference", params={"tol": 0}, ac_source="V1")
    nodes = {"tank": s.node("C1", 1), "stage1": s.node("U1", 5), "adc": "AIN1"}
    frequencies = [float(f) for f in reference["gain_db"]]
    gains = spice.ac_points(deck, {k: f"db(v({n}))" for k, n in nodes.items()}, frequencies)
    for index, (frequency, expected) in enumerate(reference["gain_db"].items()):
        for key, value in expected.items():
            # LTspice's switch output stage adds a little phase lag near 20 kHz.
            tolerance = 0.002 if float(frequency) <= 5000 else 0.05
            assert gains[key][index] == pytest.approx(value, abs=tolerance), (frequency, key)
    for frequency, expected in reference["noise"].items():
        result = spice.noise(deck, output="AIN1", reference="n25P", source="V1",
                             start_hz=float(frequency), stop_hz=float(frequency),
                             points_per_decade=1)
        assert result.input_v_rt_hz[0] == pytest.approx(expected["input"], rel=2e-4)
        assert result.output_v_rt_hz[0] == pytest.approx(expected["output"], rel=2e-4)
    op = spice.operating_point(deck, [nodes["stage1"], "AIN1", s.node("U1", 2)])
    point = reference["operating_point_v"]
    assert op[nodes["stage1"]] == pytest.approx(point["stage1"], abs=1e-4)
    assert op["AIN1"] == pytest.approx(point["adc"], abs=1e-4)
    assert op[s.node("U1", 2)] == pytest.approx(point["stage1_inverting"], abs=1e-4)


@needs_ngspice
def test_opamp_noise_has_flicker_corner():
    """En with an Enk corner gives density^2 = En^2 (1 + Enk / f) at a unity-gain buffer."""
    deck = ("* buffer\nVin in 0 DC 2.5 AC 1\nVp vp 0 5\n"
            "XU1 in out vp 0 out universalopamp2 en=2.7n enk=240 rin=1e15\n"
            + OPAMP_SUBCIRCUIT + ".end\n")
    for frequency, expected in ((24.0, 2.7e-9 * math.sqrt(11)),
                                (24000.0, 2.7e-9 * math.sqrt(1.01))):
        result = spice.noise(deck, output="out", reference="0", source="Vin",
                             start_hz=frequency, stop_hz=frequency, points_per_decade=1)
        assert result.output_v_rt_hz[0] == pytest.approx(expected, rel=0.01)
