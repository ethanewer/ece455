"""D11 + D12: determinism and docs-vs-code consistency.

D11: the E2E card set must be byte-identical to the committed fixture (a
fresh run == committed tree). The ngspice timestamp lines never reach the
output (parser consumes them; asserted in test_ngspice_layer.py).

D12: every headline number quoted in README.md / docs/architecture.md is
extracted and compared with regenerated output within the stated MC CI.
This is the audit finding class "table says 0.044, code prints 0.0435".

Run:  python3 -m pytest tests/test_determinism_docs.py
      (requires ngspice; ~4 min -- regenerates the E2E cards + ablations)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest  # noqa: E402

import reproduce  # noqa: E402


@pytest.fixture(scope="module")
def fresh():
    banner, cards = reproduce.regenerate_cards()
    return banner, cards


def test_e2e_cards_byte_identical(fresh):
    """D11: the regenerated E2E cards equal the committed fixture byte for
    byte (fixed seeds; no wall-clock in the printed tables)."""
    _banner, cards = fresh
    errors = reproduce.check_fixtures(cards)
    assert not errors, "\n".join(errors)


def test_no_wall_clock_in_printed_tables(fresh):
    """D11's premise: the printed tables must not embed a timestamp or
    leak the ngspice banner."""
    banner, _cards = fresh
    import datetime
    year = str(datetime.date.today().year)
    assert year not in banner, "E2E output embeds a date"
    assert "Analysis" not in banner, \
        "circuit_spec stdout leaks ngspice banner text"


def test_docs_headline_numbers_consistent(fresh):
    """D12: every headline number in README + architecture matches the
    regenerated output within the stated MC CI."""
    banner, cards = fresh
    errors = reproduce.check_docs(banner, cards)
    assert not errors, "\n".join(errors)
