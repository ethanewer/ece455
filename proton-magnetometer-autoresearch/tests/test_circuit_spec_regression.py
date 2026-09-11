"""D8 (re-anchored, REDESIGN.md step 7): E2E score-card regression against
committed fixtures.

One full E2E card per reference candidate class is committed
(tests/fixtures/score_cards/reference_cards.json); this test re-evaluates
each candidate through the single E2E evaluator (pipeline/evaluate.py: SPICE ->
candidate-shaped records -> the C estimator core) and asserts the
worst-band J / CRB / sigma_in / tau_ring and the per-band Js reproduce
within Monte-Carlo tolerance. Guards the SPICE -> C-core -> nT path
against silent breakage.

Also locked: the zero-crossing ruling-out is an E2E result -- the SAME
reference circuit with estimator="zc" must fail the gross gate.

Regenerate the fixture with:  python3 tools/reproduce.py --save

Run:  python3 -m pytest tests/test_circuit_spec_regression.py
      (requires ngspice on PATH; ~2 min)
"""
import json
from pathlib import Path

import numpy as np
import pytest

from conftest import PIPELINE  # noqa: F401

import circuit_spec as cs
import evaluate as ev
import fid

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "score_cards" / \
    "reference_cards.json"

CANDIDATES = cs.reference_candidates()

# MC tolerance: N_MC=150 -> ~6% 1-sigma on the MC-estimated RMS values;
# 15% guard band. Deterministic columns (V0, gain, tau_ring, CRB) are tight.
BAND_TOL = dict(
    v0_uV=1e-9,            # deterministic (Curie model)
    sigma_in_uV=0.02,      # SPICE-parsed integral, deterministic per netlist
    sigma_in_band_uV=0.02,
    gain_fl=0.01,          # SPICE-parsed H, deterministic
    tau_ring_ms=0.20,      # envelope fit on tran data, tolerance for fit
    crb_nt=0.02,           # deterministic given parsed spectra
    rms_nt=0.15,           # MC (N=150): ~6% 1-sigma -> 15% guard
)
J_TOL = 0.15


@pytest.fixture(scope="module")
def fixture_cards():
    return {c["spec"]: c for c in json.loads(FIXTURE.read_text())}


def test_fixture_has_all_candidate_classes(fixture_cards):
    assert len(fixture_cards) == len(CANDIDATES)


@pytest.mark.parametrize("label,kw", CANDIDATES, ids=lambda v: str(v)[:24])
def test_score_card_reproduces(fixture_cards, label, kw):
    got = ev.evaluate(dict(kw, label=label))
    want = fixture_cards[label]
    assert got["spec"] == want["spec"]
    assert got["estimator"] == want["estimator"] == "zoom"
    # Worst-band J and the per-band Js.
    if np.isinf(want["J_nt"]):
        assert np.isinf(got["J_nt"]), got["J_nt"]
    else:
        assert got["J_nt"] == pytest.approx(want["J_nt"], rel=J_TOL), \
            (label, got["J_nt"], want["J_nt"])
    for band, j in want["J_per_band"].items():
        gj = got["J_per_band"][band]
        if np.isinf(j):
            assert np.isinf(gj), (label, band, gj)
        else:
            assert gj == pytest.approx(j, rel=J_TOL), (label, band, gj, j)
    # Per-band deterministic + MC columns, and exact gates.
    want_bands = {c["b_earth_uT"]: c for c in want["bands"]}
    for band in got["bands"]:
        w = want_bands[band["b_earth_uT"]]
        for key, tol in BAND_TOL.items():
            assert band[key] == pytest.approx(w[key], rel=tol), \
                (label, band["b_earth_uT"], key, band[key], w[key])
        assert band["gates"] == w["gates"]


def test_zc_variant_ruled_out_e2e():
    """REDESIGN.md: the ZC ruling-out is an E2E result, scored through the
    identical evaluator -- not a Python-only regression.

    (a) On the thin-budget INA circuit (the SNR regime the ruling-out was
        measured in) the zc variant must fail the gross gate -> J = inf.
    (b) On the fat-SNR tuned circuit the zc variant no longer trips the
        1 Hz gross bar (honest physics: crossing-time noise shrinks with
        amplitude) -- but the SCORE ranks it orders of magnitude off the
        zoom candidate on the identical circuit."""
    label, kw = CANDIDATES[0]                  # untuned INA reference
    card = ev.evaluate(dict(kw, label=label + " [zc variant]",
                            estimator="zc"),
                       b_fields=(50e-6,), n_mc=40)
    band = card["bands"][0]
    assert card["estimator"] == "zc"
    assert band["gates"]["gross_errors"] is False
    assert card["J_nt"] == float("inf")
    assert band["gross"] >= 0.9, band["gross"]

    label, kw = CANDIDATES[2]                  # tuned JFET reference
    zc = ev.evaluate(dict(kw, label=label + " [zc variant]",
                          estimator="zc"),
                     b_fields=(50e-6,), n_mc=40)
    band = zc["bands"][0]
    assert band["rms_nt"] > 100 * band["crb_nt"], \
        (band["rms_nt"], band["crb_nt"])


def test_fixture_matches_current_curie_law(fixture_cards):
    """The fixture's V0 must equal the current transducer model exactly
    (guards against a fixture regenerated with stale physics)."""
    for label, kw in CANDIDATES:
        card = fixture_cards[label]
        v0 = fid.estimate_v0(b_pol=kw["coil"]["b_pol"],
                             n_turns=kw["coil"]["n_turns"],
                             coil_radius_m=kw["coil"]["radius_m"])
        band50 = next(c for c in card["bands"]
                      if c["b_earth_uT"] == pytest.approx(50.0))
        # rel=1e-9: the fixture is rounded to 12 significant digits (D11);
        # a stale-physics revert moves V0 by 3x, so this is plenty tight.
        assert band50["v0_uV"] == pytest.approx(v0 * 1e6, rel=1e-9)
