"""D8: circuit_spec.py regression against committed score-card fixtures.

One full score card per candidate class is committed
(tests/fixtures/score_cards/reference_cards.json); this test re-scores each
candidate through the real SPICE path and asserts J / CRB / sigma_in /
tau_ring reproduce within Monte-Carlo tolerance. Guards the SPICE -> nT
path against silent breakage.

Run:  python3 -m pytest tests/test_circuit_spec_regression.py
      (requires ngspice on PATH; ~1 min)
"""
import json
from pathlib import Path

import numpy as np
import pytest

from conftest import POC  # noqa: F401

import circuit_spec as cs
import fid

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "score_cards" / \
    "reference_cards.json"

CANDIDATES = [
    ("untuned + INA828-class (7 nV, 170 fA)",
     dict(e_amp=7e-9, i_amp=170e-15, tuned=False,
          coil=dict(r_coil=120, l_coil="2m", n_turns=530,
                    radius_m=0.015, b_pol=0.02))),
    ("untuned + TL072-class (18 nV)",
     dict(e_amp=18e-9, i_amp=10e-15, tuned=False,
          coil=dict(r_coil=120, l_coil="2m", n_turns=530,
                    radius_m=0.015, b_pol=0.02))),
    ("tuned series-resonant + JFET (1.4 nV, 0.1 pA)",
     dict(e_amp=1.4e-9, i_amp=0.1e-12, tuned=True, preamp_gain=4.0,
          coil=dict(r_coil=20, l_coil="100m", c_tune="56n", n_turns=1500,
                    radius_m=0.030, b_pol=0.05))),
]

# MC tolerance: N_MC=150 -> ~6% 1-sigma on the MC-estimated RMS values;
# 15% guard band. Deterministic columns (V0, gain, tau_ring, CRB) are tight.
TOL = dict(
    v0_uV=1e-9,            # deterministic (Curie model)
    sigma_in_uV=0.02,      # SPICE-parsed integral, deterministic per netlist
    sigma_in_band_uV=0.02,
    gain_fl=0.01,          # SPICE-parsed H, deterministic
    tau_ring_ms=0.20,      # envelope fit on tran data, tolerance for fit
    crb_nt=0.02,           # deterministic given parsed spectra
    rms_zoom_fit=0.15,     # MC (N=150): ~6% 1-sigma -> 15% guard
    J_nt=0.15,
)


@pytest.fixture(scope="module")
def fixture_cards():
    return {c["spec"]: c for c in json.loads(FIXTURE.read_text())}


def test_fixture_has_all_candidate_classes(fixture_cards):
    assert len(fixture_cards) == len(CANDIDATES)


@pytest.mark.parametrize("label,kw", CANDIDATES, ids=lambda v: str(v)[:24])
def test_score_card_reproduces(fixture_cards, label, kw):
    spec = cs.afe_spec(label, **kw)
    got = cs.score(spec)
    want = fixture_cards[label]
    assert got["spec"] == want["spec"]
    for key, tol in TOL.items():
        wv, gv = want[key], got[key]
        if np.isinf(wv):                       # gated-out candidate: J = inf
            assert np.isinf(gv), (key, gv)
            continue
        assert gv == pytest.approx(wv, rel=tol), (label, key, gv, wv)
    # Gates must match exactly (same candidate, same deterministic gates).
    assert got["gates"] == want["gates"]


def test_fixture_matches_current_curie_law():
    """The fixture's V0 must equal the current transducer model exactly
    (guards against a fixture regenerated with stale physics)."""
    cards = json.loads(FIXTURE.read_text())
    coil_keys = [("r_coil", "l_coil", "n_turns", "radius_m", "b_pol")]
    for label, kw in CANDIDATES:
        card = next(c for c in cards if c["spec"] == label)
        v0 = fid.estimate_v0(b_pol=kw["coil"]["b_pol"],
                             n_turns=kw["coil"]["n_turns"],
                             coil_radius_m=kw["coil"]["radius_m"])
        assert card["v0_uV"] == pytest.approx(v0 * 1e6, rel=1e-12)
