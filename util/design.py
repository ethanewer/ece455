"""Locations of the design files and the values the utilities read from them.

This is the only module that knows where the design lives. The generic
readers (kicad, ltspice, spice, xlsx) take paths or values instead.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from util import kicad, ltspice, xlsx

ROOT = Path(__file__).resolve().parents[1]
AMPLIFIER = ROOT / "ltspice/AmplificationSim.asc"
SIGNAL_BOARD = ROOT / "kicad/signal_control_board"
SIGNAL_SCHEMATIC = SIGNAL_BOARD / "SignalProcessing&ControlBoard.kicad_sch"
SIGNAL_PCB = SIGNAL_BOARD / "SignalProcessing&ControlBoard.kicad_pcb"
SIGNAL_BOM = SIGNAL_BOARD / "SignalProcessing&ControlBoard.csv"
POLARIZATION_BOARD = ROOT / "kicad/polarization_board"
POLARIZATION_SCHEMATIC = POLARIZATION_BOARD / "PolarizationBoard.kicad_sch"
POLARIZATION_PCB = POLARIZATION_BOARD / "PolarizationBoard.kicad_pcb"
FIRMWARE = ROOT / "firmware/PicoProgramECE455.c"
TUNING_WORKBOOK = ROOT / "spreadsheets/TuningCapacitors.xlsx"

# Roles of the elements in ltspice/AmplificationSim.asc.
FID_SOURCE = "V1"            # coil EMF
COIL = ("R5", "L1")          # coil resistance and inductance in series with V1
TANK = "C1"                  # stands in for the switched bank C1-C11 on the board
# Amplifier parts built off the board, between J5 and J6.
AMPLIFIER_PARTS = ("C4", "R8", "U1", "R3", "R4", "C5", "R9", "U2", "R10", "R11", "C6", "R12")
# Simulated parts fitted on the signal board: LTspice reference -> KiCad reference.
BOARD_PARTS = {"C2": "C21", "R2": "R8"}
# Models rather than parts: op-amp input impedance (C8/R14, C9/R15) and the
# ADS1256 inputs (C3/R1 at the signal input, C7/R13 at the 2.5 V input).
MODEL_PARTS = ("C8", "R14", "C9", "R15", "C3", "R1", "C7", "R13")
SUPPLIES = ("V5", "V8", "V9")
# LTspice node -> signal-board net. The tank node is unnamed in the drawing,
# so it is found from TANK. V5's node is a second 2.5 V source.
NET_MAP = {"0": "GND", "5P": "/MCU/5VRail", "25P": "/MCU/2.5VBias",
           "VopAmpOut2": "Signal Processed"}
COIL_NET = "Signal Processing"
# ADC inputs in the drawing: AIN1 is the signal and AIN3 the 2.5 V bias.
ADC_SIGNAL, ADC_REFERENCE = "AIN1", "AIN3"

# HiLetgo ADS1256 module digital header, pin 1 first, as the earlier
# breadboard documentation read it from the seller's photo. J3 follows it.
ADS1256_HEADER = ("5V", "GND", "SCLK", "DIN", "DOUT", "DRDY", "CS", "PDWN")
# Firmware pin macro for each ADS1256 signal it drives or reads.
FIRMWARE_PINS = {"SCLK": "PIN_SCLK", "DIN": "PIN_MOSI", "DOUT": "PIN_MISO",
                 "DRDY": "PIN_DRDY", "CS": "PIN_CS"}


@cache
def amplifier() -> ltspice.Schematic:
    return ltspice.read_asc(AMPLIFIER)


@cache
def signal_board() -> kicad.Netlist:
    return kicad.read_schematic(SIGNAL_SCHEMATIC)


@cache
def polarization_board() -> kicad.Netlist:
    return kicad.read_schematic(POLARIZATION_SCHEMATIC)


@cache
def firmware_constants() -> dict[str, float | str]:
    """`#define NAME value` lines of the firmware, numbers converted."""
    constants: dict[str, float | str] = {}
    for name, value in re.findall(r"^\s*#define\s+(\w+)\s+([^\s/]+)", FIRMWARE.read_text(), re.M):
        number = re.fullmatch(r"([-+]?[0-9.]+(?:[eE][-+]?\d+)?)(?:U?L{0,2}|f)?", value)
        constants[name] = float(number.group(1)) if number else value
    return constants


def adc_full_scale_v() -> float:
    """Differential full scale, +/- 2 VREF / PGA, with the firmware's settings."""
    constants = firmware_constants()
    return 2.0 * constants["ADS_VREF"] / constants["ADS_PGA"]


@dataclass(frozen=True)
class BankCapacitor:
    ref: str
    farads: float
    switch: str      # DIP switch reference
    position: int    # switch number on that DIP switch


@cache
def tuning_bank() -> tuple[BankCapacitor, ...]:
    """Capacitors that a DIP switch connects across the sensing coil.

    Switch k of an N-way DIP switch joins pins k and 2N + 1 - k.
    """
    board = signal_board()
    coil = board.nets[COIL_NET]
    bank = []
    for ref, part in board.parts.items():
        match = re.fullmatch(r"Switch:SW_DIP_x(\d+)", part.lib_id)
        if not match:
            continue
        count = int(match.group(1))
        for position in range(1, count + 1):
            a, b = str(position), str(2 * count + 1 - position)
            if (ref, a) not in coil:
                a, b = b, a
            if (ref, a) not in coil:
                continue
            other = board.nets[board.net_of(ref, b)] - {(ref, b)}
            if len(other) != 1:
                raise ValueError(f"{ref} switch {position} does not lead to one capacitor")
            cap, pin = next(iter(other))
            ground = board.net_of(cap, "2" if pin == "1" else "1")
            if not cap.startswith("C") or ground != "GND":
                raise ValueError(f"{ref} switch {position} does not switch a capacitor to GND")
            bank.append(BankCapacitor(cap, kicad.parse_value(board.parts[cap].value), ref, position))
    return tuple(sorted(bank, key=lambda c: c.farads))


@cache
def _tuning_cells() -> dict[str, str | float]:
    return xlsx.read_workbook(TUNING_WORKBOOK)["LC Tuning - 100 Points"]


def workbook_coil_inductances_h() -> tuple[float, float]:
    """Inductance of each sensing coil, entered in TuningCapacitors.xlsx."""
    cells = _tuning_cells()
    return tuple(float(xlsx.value_beside(cells, f"Coil {n} inductance (mH)")) * 1e-3
                 for n in (1, 2))


def workbook_bank_total_f() -> float:
    """The bank total the workbook uses for its reference row."""
    return float(xlsx.value_beside(_tuning_cells(), "Nominal bank total (nF)")) * 1e-9


def simulated_coil() -> tuple[float, float]:
    """(resistance ohms, inductance henries) of the coil in the LTspice model."""
    elements = amplifier().elements
    return (ltspice.spice_number(elements[COIL[0]].value),
            ltspice.spice_number(elements[COIL[1]].value))
