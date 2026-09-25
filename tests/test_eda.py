from pathlib import Path
import shutil

import numpy as np
import pytest

from verification_modeling.eda import circuit, ngspice
from verification_modeling.eda.report import build_spice_report

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


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not installed")
def test_report_builder_writes_numeric_and_figure_outputs(tmp_path):
    netlist = tmp_path / "rc.cir"
    netlist.write_text(
        "RC report check\n"
        "V1 source 0 SINE(0 1m 1k) AC 1\n"
        "R1 source out 1k\n"
        "C1 out 0 100n\n"
        ".ac dec 10 10 10k\n"
        ".end\n"
    )
    result = build_spice_report(
        netlist, tmp_path / "report", input_node="source",
        output_positive="out", output_negative="0", resonance_hz=1000,
        transient_stop_s=0.002, max_step_s=10e-6,
    )
    for path in (result.transient_csv, result.response_csv,
                 result.waveforms_png, result.response_png, result.summary_md):
        assert path.exists() and path.stat().st_size > 100
    transient = np.genfromtxt(result.transient_csv, delimiter=",", names=True)
    response = np.genfromtxt(result.response_csv, delimiter=",", names=True)
    assert np.max(np.abs(transient["fid_source_v"])) == pytest.approx(1e-3, rel=0.01)
    at_1khz = int(np.argmin(np.abs(response["frequency_hz"] - 1000)))
    expected_gain_db = 20 * np.log10(1 / np.sqrt(1 + (2 * np.pi * 1000 * 1e3 * 100e-9) ** 2))
    expected_phase_deg = -np.degrees(np.arctan(2 * np.pi * 1000 * 1e3 * 100e-9))
    assert response["gain_db"][at_1khz] == pytest.approx(expected_gain_db, abs=0.03)
    assert response["phase_deg"][at_1khz] == pytest.approx(expected_phase_deg, abs=0.1)


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not installed")
def test_report_builder_differential_output(tmp_path):
    netlist = tmp_path / "biased_rc.cir"
    netlist.write_text(
        "Biased RC report check\n"
        "VBIAS bias 0 0.25\n"
        "V1 source bias SINE(0 1m 1k) AC 1\n"
        "R1 source out 1k\n"
        "C1 out bias 100n\n"
        ".end\n"
    )
    result = build_spice_report(
        netlist, tmp_path / "report", input_node="source",
        output_positive="out", output_negative="bias", resonance_hz=1000,
        transient_stop_s=0.002, max_step_s=10e-6,
    )
    transient = np.genfromtxt(result.transient_csv, delimiter=",", names=True)
    differential = transient["adc_differential_v"]
    assert np.min(differential) < -5e-4
    assert np.max(differential) > 5e-4


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not installed")
def test_active_receiver_passband_and_gain(tmp_path):
    netlist = Path(__file__).parents[1] / "receiver_design/spice/receiver.cir"
    result = build_spice_report(
        netlist, tmp_path / "report", input_node="source",
        output_positive="ads_ain0", output_negative="vref",
        resonance_hz=1792.019986, passband_hz=(1740.0, 1844.0),
    )
    response = np.genfromtxt(result.response_csv, delimiter=",", names=True)
    frequency = response["frequency_hz"]
    gain = 10 ** (response["gain_db"] / 20)

    peak = int(np.argmin(np.abs(frequency - 1792.02)))
    assert 600 < gain[peak] < 900
    for target_hz in (1500, 2500):
        index = int(np.argmin(np.abs(frequency - target_hz)))
        assert gain[index] < 0.25 * gain[peak]
    assert "1792.020 Hz" in result.summary_md.read_text()


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not installed")
def test_jumper_moves_the_peak_to_about_2_1_khz(tmp_path):
    source = Path(__file__).parents[1] / "receiver_design/spice/receiver.cir"
    netlist = tmp_path / "receiver.cir"
    netlist.write_text(source.read_text().replace(".param Vjumper=0", ".param Vjumper=1"))
    result = build_spice_report(
        netlist, tmp_path / "report", input_node="source",
        output_positive="ads_ain0", output_negative="vref",
        resonance_hz=2098.5, passband_hz=(2046.0, 2151.0),
    )
    response = np.genfromtxt(result.response_csv, delimiter=",", names=True)
    frequency = response["frequency_hz"]
    gain = 10 ** (response["gain_db"] / 20)
    band = (frequency > 1500) & (frequency < 2500)
    peak = int(np.argmax(gain[band]))
    assert 2050 < frequency[band][peak] < 2150
    assert gain[band][peak] > 500
    low = int(np.argmin(np.abs(frequency - 1792)))
    assert gain[low] < 0.5 * gain[band][peak]
