from pathlib import Path

from PIL import Image

from receiver_design.export import write_bom_markdown
from receiver_design.schematic import build_receiver_schematic


def test_construction_schematic_is_rendered(tmp_path: Path) -> None:
    svg, png = build_receiver_schematic(tmp_path)

    assert svg.stat().st_size > 10_000
    assert png.stat().st_size > 10_000
    svg_text = svg.read_text()
    assert "OPA4197" in svg_text
    assert "ADS1256" in svg_text
    assert "COIL_HI (untuned)" in svg_text
    assert "1.5-2.5 kHz bandpass" in svg_text
    assert "fill: #ffffff" in svg_text
    with Image.open(png) as image:
        assert image.convert("RGBA").getpixel((0, 0)) == (255, 255, 255, 255)


def test_bom_markdown_preserves_rows(tmp_path: Path) -> None:
    source = tmp_path / "bom.csv"
    source.write_text("Reference,Qty,Value\nR1,1,1 kohm\n")
    output = tmp_path / "bom.md"

    write_bom_markdown(source, output)

    text = output.read_text()
    assert "Reference | Qty | Value" in text
    assert "R1 | 1 | 1 kohm" in text
