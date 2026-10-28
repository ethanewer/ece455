"""Coil workbook, printed coil forms, and the FID estimate."""
import pytest

from util import coil, design, physics


def test_workbook_method_reproduces_the_workbook():
    plan = design.coil_plan()
    assert plan.sensing_turns == 1477 and plan.polarizing_turns == 331
    assert coil.resistance_ohm(plan.sensing, 1477) == pytest.approx(49.9679, rel=1e-5)
    assert coil.resistance_ohm(plan.polarizing, 331) == pytest.approx(
        plan.polarizing_resistance_ohm, rel=1e-6)
    assert coil.inductance_h(plan.sensing, 1477) == pytest.approx(plan.sensing_inductance_h, rel=1e-9)
    # 1263 ft of wire, 3 % held back for leads, winds 1477 turns.
    usable = 1263 * coil.FOOT * 0.97
    assert coil.wire_length_m(plan.sensing, 1477) <= usable < coil.wire_length_m(plan.sensing, 1478)


def test_as_built_coils_have_about_600_turns():
    planned, by_inductance, by_resistance = design.sensing_coils()
    assert planned.turns == 1477
    assert by_inductance.turns == pytest.approx(628, abs=2)
    assert by_resistance.turns == pytest.approx(594, abs=2)
    # The two independent inferences agree to within 6 %.
    assert by_inductance.turns / by_resistance.turns == pytest.approx(1.0, abs=0.06)


def test_printed_forms_match_the_workbook():
    plan = design.coil_plan()
    for path, bobbin in ((design.SENSING_FORM, plan.sensing),
                         (design.POLARIZING_FORM, plan.polarizing)):
        form = design.coil_form(path)
        assert sorted(form.core) == pytest.approx(
            sorted((bobbin.short_m * 1e3, bobbin.long_m * 1e3)), abs=0.5)
        assert form.winding_length == pytest.approx(bobbin.width_m * 1e3, abs=0.2)
        # The flanges are deep enough for the planned winding.
        depth = bobbin.wire_od_m * 1e3 * coil.layers(
            bobbin, plan.sensing_turns if path == design.SENSING_FORM else plan.polarizing_turns)
        assert (min(form.flange) - min(form.core)) / 2 >= depth


def test_sensing_forms_nest_in_the_polarizing_form():
    sensing, polarizing = design.coil_form(design.SENSING_FORM), design.coil_form(design.POLARIZING_FORM)
    assert sensing.opening == (56.0, 56.0)
    assert max(sensing.flange) <= min(polarizing.opening)
    assert 2 * max(sensing.flange) <= max(polarizing.opening)


def test_curie_law_fid():
    # Independent arithmetic: M0 = n mu^2 B / kT, V0 = mu0 M0 A w N.
    m0 = 6.69e28 * (1.41060679736e-26) ** 2 * 8.6331e-3 / (1.380649e-23 * 293.15)
    assert physics.curie_magnetization(8.6331e-3, 293.15) == pytest.approx(m0, rel=1e-9)
    expected = 1.25663706212e-6 * m0 * 0.056**2 * 2 * 3.141592653589793 * 2268 * 1477
    assert physics.fid_emf(8.6331e-3, 1477, 0.056**2, 2268, 293.15) == pytest.approx(expected)
    assert expected == pytest.approx(2.355e-6, rel=1e-3)
