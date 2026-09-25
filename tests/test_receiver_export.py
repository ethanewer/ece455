from pathlib import Path

from PIL import Image

from receiver_design.export import set_test_source, write_bom_markdown
from verification_modeling.coil import current_coil
from receiver_design.schematic import build_receiver_schematic


def test_construction_schematic_is_rendered(tmp_path: Path) -> None:
    svg, png = build_receiver_schematic(tmp_path)

    assert svg.stat().st_size > 10_000
    assert png.stat().st_size > 10_000
    svg_text = svg.read_text()
    assert "No external op-amp or LC tank" in svg_text
    assert "ADS1256" in svg_text
    assert "J1 signal" in svg_text
    assert "R2+R3 2 MΩ" in svg_text
    assert "C5 22 nF" in svg_text
    assert "Q1 SCLK" in svg_text
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
