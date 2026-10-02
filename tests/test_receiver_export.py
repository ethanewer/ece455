from pathlib import Path

import pytest
from PIL import Image

from receiver_design import breadboard
from receiver_design.breadboard import build_receiver_breadboard

from receiver_design.export import set_test_source, write_bom_markdown
from verification_modeling.coil import current_coil
from receiver_design.schematic import build_receiver_schematic


def test_construction_schematic_is_rendered(tmp_path: Path) -> None:
    svg, png = build_receiver_schematic(tmp_path)

    assert svg.stat().st_size > 10_000
    assert png.stat().st_size > 10_000
    svg_text = svg.read_text()
    assert "Discrete band-pass" in svg_text
    assert "Gain ≥ 2000 V/V" in svg_text
    assert "ADS1256 AIN0" in svg_text
    assert "ADS1256 AIN1" in svg_text
    assert "J1 signal" in svg_text
    assert "C1 100 nF" in svg_text
    assert "R7 5.1 kΩ" in svg_text
    assert "C8 6.8 nF" in svg_text
    assert "Q8" in svg_text
    assert "Q7" in svg_text
    assert "No level translation" in svg_text
    assert "J4" not in svg_text
    assert "tuning capacitor, and damping resistor are external" in svg_text
    assert "fill: #ffffff" in svg_text
    with Image.open(png) as image:
        assert image.convert("RGBA").getpixel((0, 0)) == (255, 255, 255, 255)


def test_export_decks_change_only_the_external_test_source() -> None:
    coil = current_coil()
    source = (Path(__file__).parents[1] / "receiver_design/spice/receiver.cir").read_text()
    low = set_test_source(source, frequency_hz=coil["f_test_low_hz"], amplitude_v=10e-6)
    high = set_test_source(source, frequency_hz=coil["f_test_high_hz"], amplitude_v=10e-6)

    assert f".param fL={coil['f_test_low_hz']:.6f}" in low
    assert f".param fL={coil['f_test_high_hz']:.6f}" in high
    assert ".param V0=10.000000000u" in low
    assert ".param Vjumper=" not in low + high


def test_bom_markdown_preserves_rows(tmp_path: Path) -> None:
    source = tmp_path / "bom.csv"
    source.write_text("Reference,Qty,Value\nR1,1,1 kohm\n")
    output = tmp_path / "bom.md"

    write_bom_markdown(source, output)

    text = output.read_text()
    assert "Reference | Qty | Value" in text
    assert "R1 | 1 | 1 kohm" in text


def test_breadboard_matches_spice_and_is_rendered(tmp_path: Path) -> None:
    svg, png, placement = build_receiver_breadboard(tmp_path)

    assert svg.stat().st_size > 10_000
    assert png.stat().st_size > 10_000
    svg_text = svg.read_text()
    assert "830-point" in svg_text
    assert "ADS1256 AIN0" in svg_text
    assert "J1 signal" in svg_text
    assert "<dc:date>" not in svg_text
    text = placement.read_text()
    assert "Q1 | 2N3904 | C c15, B c16, E c17" in text
    assert "C6 | 470 µF | + B+9, − B-9" in text
    with Image.open(png) as image:
        assert image.convert("RGBA").getpixel((0, 0)) == (255, 255, 255, 255)


def test_breadboard_svg_is_repeatable(tmp_path: Path) -> None:
    first, _, _ = build_receiver_breadboard(tmp_path / "a")
    second, _, _ = build_receiver_breadboard(tmp_path / "b")

    assert first.read_bytes() == second.read_bytes()


@pytest.mark.parametrize(
    ("ref", "holes", "message"),
    [
        ("R7", ("f19", "e18"), "split"),            # lead moved to the wrong strip
        ("Q1", ("c17", "c16", "c15"), "split"),     # collector and emitter swapped
        ("C4", ("T-21", "a20"), "split"),           # electrolytic reversed
        ("R3", ("d31", "d36"), "split"),            # BIAS end left floating
        ("R12", ("f21", "f22"), "split"),
        ("R1", ("b16", "b18"), "split"),
        ("R2", ("c19", "c25"), "split"),
        ("C1", ("d12", "d15"), "shorts q1_col to q1_base"),
        ("R6", ("j19", "B+19"), "split"),           # to VA instead of GND
        ("R2", ("c19", "c32"), "passes over Q4"),
        ("C9", ("i21", "i30"), "holds both"),
    ],
)
def test_breadboard_check_rejects_wrong_holes(monkeypatch, ref, holes, message) -> None:
    parts = tuple(
        breadboard.Placement(p.ref, p.kind, holes) if p.ref == ref else p
        for p in breadboard.PARTS
    )
    monkeypatch.setattr(breadboard, "PARTS", parts)

    with pytest.raises(ValueError, match=message):
        breadboard.check_layout(breadboard.SPICE_NETLIST.read_text())
