from pathlib import Path
import shutil
import tempfile

import numpy as np
import pytest

from verification_modeling.eda import circuit, ngspice
from verification_modeling.eda.report import (
    build_spice_report,
    measure_input_impedance,
    measure_noise,
)
from verification_modeling.coil import current_coil

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
        output_positive="out", output_negative="0", marker_hz=1000,
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
        output_positive="out", output_negative="bias", marker_hz=1000,
        transient_stop_s=0.002, max_step_s=10e-6,
    )
    transient = np.genfromtxt(result.transient_csv, delimiter=",", names=True)
    differential = transient["adc_differential_v"]
    assert np.min(differential) < -5e-4
    assert np.max(differential) > 5e-4


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not installed")
def test_noise_helper_matches_divider_thermal_noise(tmp_path):
    netlist = tmp_path / "divider.cir"
    netlist.write_text(
        "Divider noise check\n"
        "V1 in 0 DC 0 AC 1\n"
        "R1 in out 1k\n"
        "R2 out 0 1k\n"
        ".end\n"
    )
    result = measure_noise(
        netlist, source="V1", output_positive="out", output_negative="0",
        band_hz=(1000.0, 2000.0), spot_hz=1500.0,
    )
    # ngspice uses 27 C. The output sees 500 ohm; the input reference is x2.
    density = np.sqrt(4 * 1.380649e-23 * 300.15 * 500.0)
    assert result.output_density_v_rt_hz == pytest.approx(density, rel=1e-3)
    assert result.input_density_v_rt_hz == pytest.approx(2 * density, rel=1e-3)
    assert result.band_output_rms_v == pytest.approx(density * np.sqrt(1000.0), rel=1e-3)


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not installed")
def test_report_gain_can_reference_an_internal_node(tmp_path):
    netlist = tmp_path / "divider.cir"
    netlist.write_text(
        "Referenced gain check\n"
        "V1 source 0 DC 0 AC 1 SINE(0 1m 1k)\n"
        "Rs source port 1k\n"
        "R1 port 0 1k\n"
        "E1 out 0 port 0 10\n"
        ".end\n"
    )
    result = build_spice_report(
        netlist, tmp_path / "report", input_node="port",
        output_positive="out", output_negative="0", marker_hz=1000,
        gain_input_node="port", transient_stop_s=0.002, max_step_s=10e-6,
    )
    response = np.genfromtxt(result.response_csv, delimiter=",", names=True)
    assert np.allclose(response["gain_db"], 20.0, atol=1e-6)


RECEIVER = Path(__file__).parents[1] / "receiver_design/spice/receiver.cir"
BAND_HZ = (1500.0, 2500.0)


def _receiver_response(tmp_path):
    result = build_spice_report(
        RECEIVER, tmp_path / "report", input_node="receiver_in",
        output_positive="out", output_negative="bias",
        marker_hz=current_coil()["f_test_low_hz"],
        gain_input_node="receiver_in", passband_hz=BAND_HZ,
    )
    response = np.genfromtxt(result.response_csv, delimiter=",", names=True)
    return response["frequency_hz"], 10 ** (response["gain_db"] / 20)


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not installed")
def test_active_receiver_gain_is_at_least_2000_in_band(tmp_path):
    frequency, gain = _receiver_response(tmp_path)
    in_band = (frequency >= BAND_HZ[0]) & (frequency <= BAND_HZ[1])
    # Nominal margin covers beta, temperature, and USB-voltage corners.
    assert gain[in_band].min() >= 2000 * 1.15


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not installed")
def test_active_receiver_attenuates_mains(tmp_path):
    frequency, gain = _receiver_response(tmp_path)
    # The report sweep starts at 100 Hz, just below the second mains harmonic.
    low = int(np.argmin(np.abs(frequency - 100.0)))
    assert gain[low] < 0.1 * gain.max()


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not installed")
def test_active_receiver_input_impedance_exceeds_1_megohm():
    _, impedance = measure_input_impedance(
        RECEIVER, source="Vfid", node="receiver_in", band_hz=BAND_HZ,
    )
    assert impedance.min() >= 1.5e6


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not installed")
def test_input_impedance_helper_matches_resistor(tmp_path):
    netlist = tmp_path / "load.cir"
    netlist.write_text(
        "Load check\nV1 source 0 DC 0 AC 1\nRs source port 1k\n"
        "Rl port 0 250k\n.end\n"
    )
    _, impedance = measure_input_impedance(
        netlist, source="V1", node="port", band_hz=(100.0, 1000.0), points=3,
    )
    assert np.allclose(impedance, 250e3, rtol=1e-6)


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not installed")
def test_active_receiver_noise_supports_1_nt_estimates():
    coil = current_coil()
    text = RECEIVER.read_text()
    fixture = "Rsource source receiver_in 30k"
    assert text.count(fixture) == 1
    untuned = text.replace(
        fixture,
        f"Rsource source coil_mid {coil['r_coil']}\n"
        f"Lsource coil_mid receiver_in {coil['l_coil']}",
    )
    with tempfile.TemporaryDirectory() as directory:
        deck = Path(directory) / "receiver.cir"
        deck.write_text(untuned)
        result = measure_noise(
            deck, source="Vfid", output_positive="out",
            output_negative="bias", band_hz=BAND_HZ, spot_hz=1936.5,
        )
    # 5 nV/rtHz EMF-referred keeps the frequency CRB near 0.25 nT even for
    # the pessimistic 0.41 uV FID; see receiver_design/analysis/README.md.
    assert result.input_density_v_rt_hz < 5e-9
