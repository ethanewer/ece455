from pathlib import Path

from PIL import Image

from receiver_design.export import fid_amplitude, select_j4, write_bom_markdown
from verification_modeling.coil import current_coil
from receiver_design.schematic import build_receiver_schematic


def test_construction_schematic_is_rendered(tmp_path: Path) -> None:
    svg, png = build_receiver_schematic(tmp_path)

    assert svg.stat().st_size > 10_000
    assert png.stat().st_size > 10_000
    svg_text = svg.read_text()
    assert "OPA4197" in svg_text
    assert "ADS1256" in svg_text
    assert "COIL_HI" in svg_text
    assert "8.2M" in svg_text
    assert "C25 47n" in svg_text
    assert "C27 33n" in svg_text
    assert "J4" in svg_text
    assert "1.5-2.5 kHz bandpass" in svg_text
    assert "fill: #ffffff" in svg_text
    with Image.open(png) as image:
        assert image.convert("RGBA").getpixel((0, 0)) == (255, 255, 255, 255)


def test_j4_export_decks_select_each_shunt() -> None:
    coil = current_coil()
    source = (Path(__file__).parents[1] / "receiver_design/spice/receiver.cir").read_text()
    low = select_j4(
        source, jumper=0, frequency_hz=coil["f_tune_hz"],
        amplitude_v=fid_amplitude(coil, coil["f_tune_hz"]),
    )
    high = select_j4(
        source, jumper=1, frequency_hz=coil["f_tune_alt_hz"],
        amplitude_v=fid_amplitude(coil, coil["f_tune_alt_hz"]),
    )

    assert ".param Vjumper=0" in low
    assert f".param fL={coil['f_tune_hz']:.6f}" in low
    assert ".param V0=3.642200856u" in low
    assert ".param Vjumper=1" in high
    assert f".param fL={coil['f_tune_alt_hz']:.6f}" in high
    assert ".param Vjumper=0" not in high
    assert low.count(".param Vjumper=") == 1
    assert high.count(".param Vjumper=") == 1


def test_bom_markdown_preserves_rows(tmp_path: Path) -> None:
    source = tmp_path / "bom.csv"
    source.write_text("Reference,Qty,Value\nR1,1,1 kohm\n")
    output = tmp_path / "bom.md"

    write_bom_markdown(source, output)

    text = output.read_text()
    assert "Reference | Qty | Value" in text
    assert "R1 | 1 | 1 kohm" in text
