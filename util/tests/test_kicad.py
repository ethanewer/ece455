"""Consistency of the KiCad boards with each other and with the other design files."""
import pytest

from util import design, kicad
from util.ltspice import spice_number


def test_sexpr_parser_unescapes_strings():
    tree = kicad.parse_sexpr('(a "x \\"y\\" z" (b 1 2) c)')
    assert tree == ["a", 'x "y" z', ["b", "1", "2"], "c"]
    with pytest.raises(ValueError):
        kicad.parse_sexpr("(a (b)")


@pytest.mark.parametrize("schematic, board", [
    (design.SIGNAL_SCHEMATIC, design.SIGNAL_PCB),
    (design.POLARIZATION_SCHEMATIC, design.POLARIZATION_PCB),
])
def test_board_matches_schematic(schematic, board):
    sch, pcb = kicad.read_schematic(schematic), kicad.read_board(board)
    assert sch.connections() == pcb.connections()
    # Footprints the schematic does not have are mounting holes without pads on nets.
    extra = {ref for ref in pcb.parts if ref} - set(sch.parts)
    assert extra and all(not any(ref == r for net in pcb.nets.values() for r, _ in net)
                         for ref in extra)
    for ref, part in sch.parts.items():
        assert pcb.parts[ref].value == part.value, ref
        assert pcb.parts[ref].footprint == part.footprint, ref


def test_signal_board_bom_matches_schematic():
    board = design.signal_board()
    bom = kicad.read_bom_csv(design.SIGNAL_BOM)
    fitted = {ref for ref, part in board.parts.items() if part.in_bom and not part.dnp}
    assert set(bom) == fitted
    for ref, row in bom.items():
        part = board.parts[ref]
        assert (row["Value"], row["Footprint"]) == (part.value, part.footprint), ref
        assert row["Description"] == part.description, ref


def test_firmware_spi_pins_reach_the_ads1256_header():
    """J3 follows the module's digital header; each firmware SPI pin lands on its pin."""
    board = design.signal_board()
    constants = design.firmware_constants()
    for position, signal in enumerate(design.ADS1256_HEADER, start=1):
        net = board.net_of("J3", str(position))
        if signal in design.FIRMWARE_PINS:
            gpio = int(constants[design.FIRMWARE_PINS[signal]])
            assert net == board.net_of("A1", board.pin_by_name("A1", f"GPIO{gpio}")), signal
        elif signal == "5V":
            assert net == "/MCU/5VRail"
        elif signal == "GND":
            assert net == "GND"
        else:
            assert len(board.nets[net]) == 1, f"{signal} should be unconnected"
    assert constants["ADS_SPI"] == "spi0"


def test_firmware_start_button_is_sw3():
    board = design.signal_board()
    gpio = int(design.firmware_constants()["PIN_START_BUTTON"])
    pressed = board.net_of("A1", board.pin_by_name("A1", f"GPIO{gpio}_ADC1"))
    assert {board.net_of("SW3", "1"), board.net_of("SW3", "2")} == {pressed, "GND"}
    assert board.parts["SW3"].value == "Button1"


def test_adc_socket_and_bias_network():
    board = design.signal_board()
    # J4 pin 1 carries the amplifier output, pin 3 the buffered 2.5 V bias.
    assert board.net_of("J4", "1") == "/MCU/FinalSignal"
    assert board.net_of("J4", "3") == "/MCU/2.5VBias"
    assert board.net_of("J4", "2") == board.net_of("J4", "4") == "GND"
    # J6 -> C21 -> R9 -> FinalSignal, with R8 to the bias as in the LTspice drawing.
    assert {("J6", "2"), ("C21", "1")} <= board.nets["Signal Processed"]
    assert board.nets["/MCU/FinalSignal"] >= {("R9", "2"), ("R8", "2"), ("J4", "1")}
    assert board.net_of("R8", "1") == "/MCU/2.5VBias"
    # The OPA320 follows the R6/R7 divider of the 5 V rail.
    assert board.net_of("R6", "1") == "/MCU/5VRail" and board.net_of("R7", "2") == "GND"
    assert board.net_of("U2", board.pin_by_name("U2", "+")) == board.net_of("R6", "2")
    out = board.net_of("U2", "1")
    assert out == board.net_of("U2", board.pin_by_name("U2", "-")) == "/MCU/2.5VBias"


def test_simulated_board_parts_match_the_board():
    amplifier, board = design.amplifier(), design.signal_board()
    for lt_ref, kicad_ref in design.BOARD_PARTS.items():
        assert spice_number(amplifier.elements[lt_ref].value) == pytest.approx(
            kicad.parse_value(board.parts[kicad_ref].value)), lt_ref


def test_amplifier_nets_reach_the_board():
    board = design.signal_board()
    assert board.net_of("J5", "2") == design.COIL_NET == board.net_of("J1", "2")
    assert board.net_of("J6", "2") == design.NET_MAP["VopAmpOut2"]
    assert board.net_of("TP4", "1") == design.NET_MAP["5P"]
    assert board.net_of("TP5", "1") == design.NET_MAP["25P"]


def test_tuning_bank():
    bank = design.tuning_bank()
    assert [c.ref for c in bank] == [f"C{n}" for n in range(1, 12)]
    assert [round(c.farads * 1e9, 2) for c in bank] == [
        0.47, 1.0, 2.2, 3.3, 4.7, 10.0, 22.0, 47.0, 82.0, 100.0, 150.0]
    assert {(c.switch, c.position) for c in bank} == (
        {("SW2", k) for k in range(1, 9)} | {("SW1", k) for k in range(1, 4)})


def test_damping_switch():
    """GPIO15 drives two back-to-back NMOS switches that load the coil through R1 and RV1."""
    board = design.signal_board()
    gates = board.net_of("Q1", "2")
    assert gates == board.net_of("Q2", "2") == board.net_of("R2", "1")
    assert board.net_of("R2", "2") == board.net_of("A1", board.pin_by_name("A1", "GPIO15"))
    assert board.net_of("R3", "2") == "GND" and board.net_of("Q2", "3") == "GND"
    assert board.net_of("Q1", "1") == board.net_of("Q2", "1")
    assert board.net_of("R1", "1") == design.COIL_NET


def test_polarization_board_switches_the_coil_from_the_mcu():
    board = design.polarization_board()
    assert board.net_of("J3", "1") == board.net_of("R4", "2")
    assert board.net_of("R4", "1") == board.net_of("U2", "2")          # TC4420 input
    assert board.net_of("U2", "6") == board.net_of("R2", "2")          # driver output
    assert board.net_of("R2", "1") == board.net_of("Q1", "1")          # NMOS gate
    assert board.net_of("Q1", "2") == board.net_of("J2", "1")          # coil low side
    assert board.net_of("Q1", "3") == "GND"
    # The TVS clamps the coil, and the fuse feeds the coil and the 12 V regulator.
    assert {board.net_of("D1", "1"), board.net_of("D1", "2")} == {
        board.net_of("J2", "1"), board.net_of("J2", "2")}
    assert board.net_of("F1", "2") == board.net_of("J2", "2") == board.net_of("U1", "1")


def test_workbook_and_board_values():
    l1, l2 = design.workbook_coil_inductances_h()
    assert (l1, l2) == (pytest.approx(13.45e-3), pytest.approx(13.13e-3))
    # The workbook's reference bank total predates the fitted bank.
    assert design.workbook_bank_total_f() == pytest.approx(392.67e-9)
    assert sum(c.farads for c in design.tuning_bank()) == pytest.approx(422.67e-9)


@pytest.mark.parametrize("text, value", [
    ("4.7nF", 4.7e-9), ("2.2u", 2.2e-6), ("220n", 220e-9), ("24.9k", 24.9e3),
    ("1K Potentiometer", 1e3), ("510", 510.0), ("0.1u", 1e-7),
])
def test_parse_value(text, value):
    assert kicad.parse_value(text) == pytest.approx(value)
