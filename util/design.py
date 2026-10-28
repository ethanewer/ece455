"""Locations of the design files and the values the utilities read from them.

This is the only module that knows where the design lives. The generic
readers (kicad, ltspice, spice, xlsx) take paths or values instead.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from util import coil, kicad, ltspice, printfile, xlsx

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
PLOTTER = ROOT / "firmware/adc_plots.py"
TUNING_WORKBOOK = ROOT / "spreadsheets/TuningCapacitors.xlsx"
COIL_WORKBOOK = ROOT / "spreadsheets/CoilDesign.xlsx"
SENSING_FORM = ROOT / "3d_models/Sensor coil V1.gcode.3mf"
POLARIZING_FORM = ROOT / "3d_models/Polarization Coil V2.gcode.3mf"

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


def plotter_window_s() -> tuple[float, float]:
    """The capture window adc_plots.py zooms to, in seconds from the first sample."""
    text = PLOTTER.read_text()
    start, end = (float(re.search(rf"^FOCUS_{name}_MS\s*=\s*([\d.]+)", text, re.M).group(1))
                  for name in ("START", "END"))
    return start * 1e-3, end * 1e-3


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


@dataclass(frozen=True)
class CoilPlan:
    """CoilDesign.xlsx: the planned windings and the polarizer's predicted operation."""

    sensing: coil.Bobbin
    sensing_turns: int
    sensing_inductance_h: float
    polarizing: coil.Bobbin
    polarizing_turns: int
    polarizing_current_a: float
    polarizing_field_t: float          # center field at that current
    polarizing_inductance_h: float
    polarizing_resistance_ohm: float
    clamp_v: float                     # assumed TVS voltage across the polarizer at turn-off
    turnoff_s: float                   # time for the polarizer current to fall to zero
    temperature_k: float


@cache
def coil_plan() -> CoilPlan:
    sheets = xlsx.read_workbook(COIL_WORKBOOK)
    inputs, summary = sheets["Inputs and method"], sheets["Coil summary"]

    def both(cells, label):
        return [float(v) for v in xlsx.row_beside(cells, label)[:2]]

    long_mm, short_mm = both(inputs, "Bobbin outer long dimension"), both(inputs, "Bobbin outer short dimension")
    width_mm, od_mm = both(inputs, "Winding width"), both(inputs, "Design insulated wire outside diameter")
    ohms = both(inputs, "Copper resistance at 20 °C")
    bobbins = [coil.Bobbin(long_mm[i] * 1e-3, short_mm[i] * 1e-3, width_mm[i] * 1e-3,
                           od_mm[i] * 1e-3, ohms[i]) for i in (0, 1)]
    turns = both(summary, "Estimated total turns")
    return CoilPlan(
        sensing=bobbins[1], sensing_turns=int(turns[1]),
        sensing_inductance_h=float(xlsx.row_beside(summary, "Estimated inductance per coil")[0]) * 1e-3,
        polarizing=bobbins[0], polarizing_turns=int(turns[0]),
        polarizing_current_a=float(xlsx.value_beside(summary, "Operating current")),
        polarizing_field_t=float(xlsx.value_beside(summary, "Estimated center field")) * 1e-3,
        polarizing_inductance_h=float(xlsx.value_beside(summary, "Estimated inductance")) * 1e-3,
        polarizing_resistance_ohm=both(summary, "Estimated DC resistance at 20 °C")[0],
        clamp_v=float(xlsx.value_beside(inputs, "Assumed TVS voltage across coil during turn-off")),
        turnoff_s=float(xlsx.value_beside(summary, "Approximate TVS turn-off time")) * 1e-3,
        temperature_k=float(xlsx.value_beside(inputs, "Noise temperature")),
    )


@dataclass(frozen=True)
class CoilForm:
    """A printed coil form, in mm: the winding core, its opening, and the flanges."""

    core: tuple[float, float]
    opening: tuple[float, float]
    winding_length: float
    flange: tuple[float, float]
    height: float


@cache
def coil_form(path: Path) -> CoilForm:
    """The tallest open section is the winding core; the widest section is a flange."""
    sections = printfile.sections(path)
    core = max((s for s in sections if s.holes), key=lambda s: s.height)
    flange = max(sections, key=lambda s: s.outline[0] * s.outline[1])
    return CoilForm(core.outline, core.holes[0], core.height, flange.outline,
                    sections[-1].z_top)


@dataclass(frozen=True)
class SensingCoil:
    label: str
    turns: int
    inductance_h: float      # per coil
    resistance_ohm: float    # per coil


def sensing_coils() -> tuple[SensingCoil, ...]:
    """The planned sensing coil, and the turn counts the as-built values imply.

    The workbook's method is inverted for the inductances in
    TuningCapacitors.xlsx and for the coil resistance in the LTspice drawing.
    """
    plan = coil_plan()
    bobbin = plan.sensing
    measured = sum(workbook_coil_inductances_h()) / 2
    resistance = simulated_coil()[0] / 2

    def entry(label, turns):
        return SensingCoil(label, turns, coil.inductance_h(bobbin, turns),
                           coil.resistance_ohm(bobbin, turns))

    return (entry("planned (CoilDesign.xlsx)", plan.sensing_turns),
            entry("from the measured inductance (TuningCapacitors.xlsx)",
                  coil.turns_for(coil.inductance_h, bobbin, measured)),
            entry("from the coil resistance (AmplificationSim.asc)",
                  coil.turns_for(coil.resistance_ohm, bobbin, resistance)))
