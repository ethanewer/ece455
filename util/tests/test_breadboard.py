from dataclasses import replace

import pytest

from util import breadboard, design


def check(**changes):
    saved = {name: getattr(breadboard, name) for name in changes}
    try:
        for name, value in changes.items():
            setattr(breadboard, name, value)
        return breadboard.check_layout(design.amplifier(), design.signal_board())
    finally:
        for name, value in saved.items():
            setattr(breadboard, name, value)


def test_layout_reproduces_the_amplifier_netlist():
    contacts = check()
    s = design.amplifier()
    assert contacts["n5P"] == {"T+", "top17", "top29"}
    assert contacts["n25P"] == {"B+"}
    assert contacts["0"] == {"B-", "bottom19", "bottom31"}
    assert contacts["VopAmpOut2"] == {"top37", "bottom37"}
    assert contacts[s.node("U1", 5)] == {"top18", "top21"}
    assert contacts[s.node("U2", 1)] == {"top25", "bottom25", "bottom30"}


def test_swapped_part_is_rejected():
    parts = tuple(replace(p, holes=p.holes[::-1]) if p.ref == "R8" else p for p in breadboard.PARTS)
    with pytest.raises(ValueError, match="split|shorts"):
        check(PARTS=parts)


def test_missing_jumper_is_rejected():
    wires = tuple(w for w in breadboard.WIRES if (w.start, w.end) != ("g17", "g21"))
    with pytest.raises(ValueError, match="split"):
        check(WIRES=wires)


def test_lead_on_the_wrong_board_net_is_rejected():
    leads = tuple(replace(lead, pin="TP4.1") if lead.pin == "TP5.1" else lead
                  for lead in breadboard.LEADS)
    with pytest.raises(ValueError, match="TP4.1 is on"):
        check(LEADS=leads)


def test_part_over_a_used_hole_is_rejected():
    parts = tuple(replace(p, holes=("j18", "j14")) if p.ref == "R8" else p for p in breadboard.PARTS)
    with pytest.raises(ValueError, match="passes over"):
        check(PARTS=parts)


def test_drawing_is_repeatable(tmp_path):
    first = breadboard.build_breadboard(tmp_path / "a")
    second = breadboard.build_breadboard(tmp_path / "b")
    for a, b in zip(first, second):
        assert a.read_bytes() == b.read_bytes(), a.name
    text = first[2].read_text()
    assert "not an E24 value; nearest 51 kΩ" in text      # R3 and R10 are 50 kΩ
    assert "not an E12 value; nearest 4.7 nF" in text     # C5 is 4.6 nF


def test_standard_values():
    assert breadboard.nearest_standard(50e3, breadboard._E24) == pytest.approx(51e3)
    assert breadboard.nearest_standard(4.6e-9, breadboard._E12) == pytest.approx(4.7e-9)
    assert breadboard.value_text("R8", 1e6) == "1 MΩ"
    assert breadboard.value_text("C5", 4.6e-9) == "4.6 nF"
