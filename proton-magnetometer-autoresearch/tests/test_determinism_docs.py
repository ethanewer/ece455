"""D11 + D12: determinism and docs-vs-code consistency.

D11: run_scoring.py stdout and the circuit_spec card set must be
byte-identical to the committed fixtures (a fresh run == committed tree).
The ngspice timestamp lines never reach these outputs (parser consumes
them; asserted in test_ngspice_layer.py).

D12: every headline number quoted in README.md / docs/architecture.md is
extracted and compared with regenerated output within the stated MC CI.
This is the audit finding class "table says 0.044, code prints 0.0435".

Run:  python3 -m pytest tests/test_determinism_docs.py
      (requires ngspice; ~10 min -- regenerates both entrypoints)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest  # noqa: E402

import reproduce  # noqa: E402


@pytest.fixture(scope="module")
def fresh():
    rs = reproduce.regenerate_run_scoring()
    cs_banner, cs_rows = reproduce.regenerate_circuit_spec()
    return rs, cs_banner, cs_rows


def test_run_scoring_byte_identical(fresh):
    """D11: the regenerated stdout equals the committed fixture byte for
    byte (fixed seeds; no wall-clock in the printed tables)."""
    rs, _cs_banner, _cs_rows = fresh
    fixture = (reproduce.FIXTURES / "run_scoring.txt")
    assert fixture.exists(), "missing fixture; run tools/reproduce.py --save"
    assert rs == fixture.read_text(), (
        "run_scoring.py output drifted from the committed fixture (D11)")


def test_circuit_spec_cards_byte_identical(fresh):
    """D11: same for the SPICE candidate score cards."""
    _rs, _cs_banner, cs_rows = fresh
    fixture = (reproduce.FIXTURES / "circuit_spec.json")
    assert fixture.exists(), "missing fixture; run tools/reproduce.py --save"
    import json
    old = json.loads(fixture.read_text())
    assert (json.dumps(cs_rows, indent=1)
            == json.dumps(old, indent=1)), \
        "circuit_spec cards drifted from the committed fixture (D11)"


def test_no_wall_clock_in_printed_tables(fresh):
    """D11's premise: the printed tables must not embed a timestamp."""
    rs, cs_banner, _cs_rows = fresh
    import datetime
    year = str(datetime.date.today().year)
    assert year not in rs, "run_scoring output embeds a date"
    assert "Analysis" not in cs_banner, \
        "circuit_spec stdout leaks ngspice banner text"


def test_docs_headline_numbers_consistent(fresh):
    """D12: every headline number in README + architecture matches the
    regenerated output within the stated MC CI."""
    rs, _cs_banner, cs_rows = fresh
    errors = reproduce.check_docs(rs, cs_rows)
    assert not errors, "\n".join(errors)
