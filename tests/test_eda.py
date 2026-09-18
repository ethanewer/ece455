from pathlib import Path

import numpy as np
import pytest

from verification_modeling.eda import circuit, ngspice

FIXTURE = Path(__file__).parent / "fixtures" / "ngspice_stdout_ac_noise_tran.txt"


def test_circuit_ir_round_trip():
    spec = {
        "title": "RC check",
        "components": [
            {"name": "V1", "type": "V", "nodes": ["in", "0"], "value": "AC 1"},
            {"name": "R1", "type": "R", "nodes": ["in", "out"], "value": "1k"},
            {"name": "C1", "type": "C", "nodes": ["out", "0"], "value": "10n"},
        ],
        "control": ["ac dec 10 100 10k", "print vm(out)"],
    }
    restored = circuit.from_json(circuit.to_json(spec))
    assert restored == circuit.validate(spec)
    assert "R1 in out 1k" in ngspice.emit_netlist(restored)


def test_circuit_ir_rejects_duplicate_references():
    component = {"name": "R1", "type": "R", "nodes": ["a", "0"], "value": 10}
    with pytest.raises(circuit.IRError, match="duplicate component"):
        circuit.validate({"title": "bad", "components": [component, component]})


def test_ngspice_parser_handles_pagination_and_timestamps():
    text = FIXTURE.read_text()
    tables = ngspice.parse_tables(text)
    assert len(tables["vm(adc)"][0]) == 121
    assert len(tables["inoise_spectrum"][0]) == 121
    assert len(tables["v(adc)"][0]) == 608
    assert tables["inoise_total"] == pytest.approx(8.782164e-7, rel=1e-6)

    changed = ngspice.parse_tables(
        text.replace("Thu Sep 10 01:07:03  2026", "Fri Dec 25 00:00:00  2031")
    )
    for name in ("vm(adc)", "inoise_spectrum", "v(adc)"):
        assert np.array_equal(tables[name][0], changed[name][0])
        assert np.array_equal(tables[name][1], changed[name][1])
