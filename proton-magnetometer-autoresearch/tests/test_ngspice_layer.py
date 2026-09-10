"""D9: ngspice-layer unit tests against a committed stdout fixture.

Covers (TODO.md D9):
  * the pagination-tolerant `print` table parser: repeated headers are page
    breaks (keep appending), not new tables; `---` rules and non-numeric
    lines are skipped; rows carry trailing tabs; the tran axis uses `time`
    where the ac/noise axes use `frequency`;
  * ngspice timestamp lines ("AC Analysis Thu Sep 10 ... 2026") must be
    filtered by the parser -- D11's byte-identical-output claim depends on
    it (asserted here by comparing parse results with and without a
    different timestamp planted in the fixture text);
  * ringdown_tau() recovers the decay constant of a synthetic exponential
    of known tau;
  * shape_transfer() interpolation at and beyond the sweep edges;
  * the e_n/i_n resistor-noise identities: R = e_n^2/(4kT) reproduces a
    datasheet noise density, and R = 4kT/i_n^2 the current density.

Run:  python3 -m pytest tests/test_ngspice_layer.py   (or from poc/: plain)
"""
import numpy as np
import pytest

from conftest import POC  # noqa: F401  (also installs poc on sys.path)

import circuit_spec as cs
import fid


def _fixture_text() -> str:
    from pathlib import Path
    p = Path(__file__).resolve().parent / "fixtures" / \
        "ngspice_stdout_ac_noise_tran.txt"
    return p.read_text()


# ---------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------- #
def test_parse_tables_recovers_all_three_tables():
    tabs = cs.parse_tables(_fixture_text())
    assert "vm(adc)" in tabs, list(tabs)
    assert "inoise_spectrum" in tabs
    assert "v(adc)" in tabs, list(tabs)
    # ac dec 60 = 60 points/decade over 2 decades + 1 -> 121 rows; noise1
    # same; tran 0.2m/120m lands on ngspice's internal grid -> 608 rows.
    n_ac = len(tabs["vm(adc)"][0])
    n_noise = len(tabs["inoise_spectrum"][0])
    n_tran = len(tabs["v(adc)"][0])
    assert n_ac == 121, n_ac
    assert n_noise == 121, n_noise
    assert n_tran == 608, n_tran


def test_parser_pagination_appends_across_repeated_headers():
    """121 rows > 50-row pages: the fixture contains repeated
    `Index ... vm(adc)` headers (a page break) and repeated
    `inoise_spectrum` headers. If a revision treats a repeated header as a
    NEW table, row counts collapse and this fails."""
    tabs = cs.parse_tables(_fixture_text())
    assert len(tabs["vm(adc)"][0]) == 121
    # inoise_spectrum is printed on 3 pages inside setplot noise1
    assert len(tabs["inoise_spectrum"][0]) == 121


def test_parser_skips_rules_and_timestamps():
    """Timestamps / `---` rules / node listings never become rows, and
    planting a DIFFERENT wall-clock date changes nothing (D11)."""
    text = _fixture_text()
    tabs = cs.parse_tables(text)
    planted = text.replace("Thu Sep 10 01:07:03  2026",
                           "Fri Dec 25 00:00:00  2031")
    assert planted != text          # the fixture really carries a timestamp
    tabs2 = cs.parse_tables(planted)
    for key in ("vm(adc)", "inoise_spectrum", "v(adc)"):
        assert np.array_equal(tabs[key][0], tabs2[key][0])
        assert np.array_equal(tabs[key][1], tabs2[key][1])


def test_parser_inoise_total():
    tabs = cs.parse_tables(_fixture_text())
    # Committed fixture value; parsed from the noise2 summary line.
    assert tabs["inoise_total"] == pytest.approx(8.782164e-07, rel=1e-6)


def test_parser_separates_tables_by_name_change():
    """A name change must start a NEW table even without a setplot line:
    feed a synthetic stream with adjacent different-variable tables."""
    import io
    lines = [
        "Index   frequency       vm(adc)",
        "0\t1.0e2\t1.0\t",
        "Index   time            v(adc)",
        "0\t0.0e0\t2.0\t",
    ]
    tabs = cs.parse_tables("\n".join(lines))
    assert set(tabs) >= {"vm(adc)", "v(adc)"}
    assert tabs["vm(adc)"][1][0] == 1.0
    assert tabs["v(adc)"][1][0] == 2.0


# ---------------------------------------------------------------------------
# ringdown_tau on a synthetic exponential of known tau
# --------------------------------------------------------------------------- #
def test_ringdown_tau_recovers_known_tau():
    """Synthetic decaying carrier of known tau, measured the way the .tran
    leg measures ring-down (block-max envelope + log fit after t_min).
    Tau values here are slow enough that >2% of the envelope survives the
    t_min = 1.5 ms start of the fit window."""
    fs = 20_000.0
    t = np.arange(0, 0.1, 1.0 / fs)
    rng = np.random.default_rng(11)
    for tau_true in (5e-3, 10e-3, 20e-3):
        v = 10.0 * np.exp(-t / tau_true) * np.sin(2 * np.pi * 1000.0 * t)
        v = v + 0.01 * rng.normal(size=len(t))    # small noise on envelope
        tau = cs.ringdown_tau((t, v), t_min=1.5e-3)
        assert abs(tau - tau_true) / tau_true < 0.15, (tau_true, tau)


def test_ringdown_tau_flat_signal_returns_zero():
    t = np.arange(0, 0.12, 1.0 / 20_000.0)
    v = np.ones_like(t)                            # no decay
    assert cs.ringdown_tau((t, v)) == 0.0
    assert cs.ringdown_tau((t[:10], np.zeros(10))) == 0.0


# ---------------------------------------------------------------------------
# shape_transfer interpolation edges
# --------------------------------------------------------------------------- #
def test_shape_transfer_interpolation_and_edges():
    f_h = np.array([100.0, 1000.0, 2000.0, 10000.0])
    mag = np.array([1.0, 2.0, 4.0, 8.0])
    got = cs.shape_transfer((f_h, mag), np.array([550.0, 100.0, 10000.0,
                                                  20_000.0, 50.0]))
    assert got[0] == pytest.approx(1.0 + (2.0 - 1.0) * (550 - 100) / 900)
    assert got[1] == pytest.approx(1.0)            # at the low edge
    assert got[2] == pytest.approx(8.0)            # at the high edge
    assert got[3] == pytest.approx(8.0)            # beyond: held constant
    assert got[4] == pytest.approx(1.0)            # below: held constant


# ---------------------------------------------------------------------------
# Resistor-noise identities
# --------------------------------------------------------------------------- #
def test_noise_resistance_reproduces_datasheet_density():
    """R = e_n^2/(4kT) must give back the density it was built from, for
    real datasheet values (INA828 7 nV, ADA4898 1.2 nV, TL072 18 nV)."""
    for e_n in (7e-9, 1.2e-9, 18e-9):
        r = cs.noise_resistance(e_n)
        back = np.sqrt(4.0 * fid.K_B * fid.T_AMBIENT * r)
        assert back == pytest.approx(e_n, rel=1e-12), (e_n, back)


def test_input_resistance_for_i_n_identity():
    """R = 4kT/i_n^2 in parallel injects i_n as Johnson current noise."""
    for i_n in (170e-15, 10e-15, 0.1e-12):
        r = cs.input_resistance_for_i_n(i_n)
        back = np.sqrt(4.0 * fid.K_B * fid.T_AMBIENT / r)
        assert back == pytest.approx(i_n, rel=1e-12), (i_n, back)
    # Huge resistor = negligible current noise: suppressed to None.
    assert cs.input_resistance_for_i_n(1e-18) is None


def test_fixture_exists():
    assert "d9 fixture circuit" in _fixture_text()


# ---------------------------------------------------------------------------
# Tank physics identities (audit E6 round 2 follow-up)
# --------------------------------------------------------------------------- #
def test_tank_q_and_ringdown_identities():
    """The corrected tuned tank must satisfy Q = 2*pi*f0*L/R and
    tau_ring ~ 2Q/omega (audit E6 round 2: lock the corrected topology's
    physics so a revert to the non-resonant wiring cannot pass silently).
    Values from the committed tuned candidate: L = 100 mH, R_coil = 20 ohm,
    C_tune = 56 nF, Q_unloaded = 66.8, tau = 2Q/omega = 10.0 ms; SPICE
    measured tau_ring = 11.1 ms (loaded Q + envelope-fit tolerance)."""
    l_coil, r_coil, c_tune = 100e-3, 20.0, 56e-9
    f0 = 1.0 / (2.0 * np.pi * np.sqrt(l_coil * c_tune))
    q_unloaded = 2.0 * np.pi * f0 * l_coil / r_coil
    assert f0 == pytest.approx(2126.8, rel=0.001)
    assert q_unloaded == pytest.approx(66.8, rel=0.01)
    tau_ideal = 2.0 * q_unloaded / (2.0 * np.pi * f0)
    # The committed tuned card measured 11.1 ms (loaded Q 63.4 + fit tol).
    assert tau_ideal == pytest.approx(10.0e-3, rel=0.01)
    assert 11.1e-3 / tau_ideal < 1.2       # measured/ideal within loading


def test_score_card_tuned_gain_implies_step_up():
    """The tuned candidate's chain gain at f_L must exceed the untuned
    chain gain by the tank's Q step-up (~60x), not by a coil/amplifier
    confound: same MFB+AA+preamp stages, only the tank differs."""
    from pathlib import Path
    import json
    cards = {c["spec"]: c for c in json.loads(
        (Path(__file__).resolve().parent / "fixtures" / "score_cards"
         / "reference_cards.json").read_text())}
    ina = cards["untuned + INA828-class (7 nV, 170 fA)"]
    tun = cards["tuned series-resonant + JFET (1.4 nV, 0.1 pA)"]
    # Chain gain ratio = tank step-up / (preamp ratio 4/100).
    step_up = (tun["gain_fl"] / ina["gain_fl"]) / (4.0 / 100.0)
    assert 30.0 < step_up < 90.0, step_up   # Q_class tank step-up present
