from dataclasses import replace
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
    assert "AD8421 module" in svg_text
    assert "G = 1 + 9.9 kΩ/R1 = 100" in svg_text
    assert "ADS1256 AIN0" in svg_text
    assert "ADS1256 AIN1 → GND" in svg_text
    assert "J1 signal" in svg_text
    for text in ("R1 100 Ω", "R2 1 kΩ", "R3 10 kΩ", "C1", "22 nF", "C2",
                 "2.2 nF", "BT1 9 V", "BT2 9 V", "Q1", "Q2"):
        assert text in svg_text
    assert "buffer off, PGA 1" in svg_text
    assert "remove the module's input RFI parts" in svg_text
    assert "No level translation" in svg_text
    assert "tuning capacitor, and damping resistor are external" in svg_text
    assert "fill: #ffffff" in svg_text
    with Image.open(png) as image:
        assert image.convert("RGBA").getpixel((0, 0)) == (255, 255, 255, 255)


def test_construction_schematic_svg_is_repeatable(tmp_path: Path) -> None:
    first, _ = build_receiver_schematic(tmp_path / "a")
    second, _ = build_receiver_schematic(tmp_path / "b")

    assert first.read_bytes() == second.read_bytes()


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
    assert "AD8421 module" in svg_text
    assert "ADS1256 module" in svg_text
    assert "XIAO" in svg_text
    assert "Function generator signal" in svg_text
    assert "BT1" in svg_text and "BT2" in svg_text
    assert "<dc:date>" not in svg_text
    text = placement.read_text()
    assert "Q1 | 2N3904 | C b17, B b18, E b19" in text
    assert "R1 | 100 Ω | module GAIN footprint" in text
    assert "RT1 | 100 kΩ | b5, b11" in text
    assert "a26 | W1 signal lead" in text
    assert "e35 | ADS1256 AIN0" in text
    assert "D8 | h57 | j57 | ADS1256 SCLK" in text
    assert "GND | h61 | j61 | ADS1256 GND (digital header)" in text
    with Image.open(png) as image:
        assert image.convert("RGBA").getpixel((0, 0)) == (255, 255, 255, 255)


def test_breadboard_svg_is_repeatable(tmp_path: Path) -> None:
    first, _, _ = build_receiver_breadboard(tmp_path / "a")
    second, _, _ = build_receiver_breadboard(tmp_path / "b")

    assert first.read_bytes() == second.read_bytes()


def _check_breadboard() -> None:
    breadboard.check_layout(breadboard.SPICE_NETLIST.read_text(),
                            breadboard.KICAD_NETLIST.read_text())


@pytest.mark.parametrize(
    ("ref", "holes", "message"),
    [
        ("R2", ("b26", "b30"), "split"),            # lead moved to the wrong strip
        ("Q1", ("b19", "b18", "b17"), "split"),     # collector and emitter swapped
        ("R3", ("c31", "c34"), "split"),
        ("C2", ("a35", "T-36"), "holds both"),      # on the ADS1256 AIN1 lead
        ("R3", ("b31", "b35"), "holds both"),
        ("C1", ("a31", "T-32"), "rail gap"),
        ("Q2", ("d15", "d16", "d18"), "adjacent"),
        ("Q2", ("d16", "d15", "d17"), "middle lead"),
        ("C2", ("a35", "T+35"), "split"),           # the + rail row, not GND
    ],
)
def test_breadboard_check_rejects_wrong_holes(monkeypatch, ref, holes, message) -> None:
    parts = tuple(
        breadboard.Placement(p.ref, p.kind, holes) if p.ref == ref else p
        for p in breadboard.PARTS
    )
    monkeypatch.setattr(breadboard, "PARTS", parts)

    with pytest.raises(ValueError, match=message):
        _check_breadboard()


def test_breadboard_check_rejects_a_test_part_on_the_wrong_rail(monkeypatch) -> None:
    rt1, rt2 = breadboard.TEST_PARTS
    moved = breadboard.Placement(rt2.ref, rt2.kind, ("a11", "T+11"), rt2.nodes, rt2.value)
    monkeypatch.setattr(breadboard, "TEST_PARTS", (rt1, moved))

    with pytest.raises(ValueError, match="split"):
        _check_breadboard()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"ADS1256 SCLK": "j58", "ADS1256 DOUT": "j57"}, "split"),  # SCLK and DOUT swapped
        ({"ADS1256 PDWN": "d58"}, "XIAO body"),                      # under the XIAO
        ({"ADS1256 DRDY": None}, "no lead reaches"),                 # wire left off
    ],
)
def test_breadboard_check_rejects_wrong_xiao_wiring(monkeypatch, changes, message) -> None:
    leads = tuple(
        replace(t, hole=changes[t.text]) if changes.get(t.text) else t
        for t in breadboard.OFF_BOARD
        if not (t.text in changes and changes[t.text] is None)
    )
    monkeypatch.setattr(breadboard, "OFF_BOARD", leads)

    with pytest.raises(ValueError, match=message):
        _check_breadboard()
