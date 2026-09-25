"""Coil nominals from CoilDesign.xlsx. These are winding estimates, not measurements.

See docs/coil-design.md. After the coils are wound, measure L and R and
retune with J4. The formula is C = 1/(4*pi^2*f^2*L).
"""
from __future__ import annotations

import math

DESIGN_ID = "coil-design-xlsx-v1"

# Polarizer scaling retained from the workbook: the earlier 342-turn,
# 8.92 mT, 10.5 mH finite-geometry estimate, scaled to this winding.
_POL_TURNS = 331
_POL_REF_TURNS = 342
_POL_REF_FIELD_T = 8.92e-3
_POL_REF_L_H = 10.5e-3

POLARIZER = dict(
    turns=_POL_TURNS,
    layers=3,
    wire_od_m=0.714e-3,
    wire_length_m=149.292,
    width_m=0.140,
    depth_m=0.070,
    length_m=0.100,
    resistance_ohm=7.9054,
    inductance_h=_POL_REF_L_H * (_POL_TURNS / _POL_REF_TURNS) ** 2,
    current_a=3.0,
    field_t=_POL_REF_FIELD_T * (_POL_TURNS / _POL_REF_TURNS),
    pulse_s=5.0,
)

# One sensing bobbin. The receiver model uses the series-aiding pair.
SENSOR = dict(
    turns=1477,
    layers=7,
    wire_od_m=0.462e-3,
    wire_length_m=373.198,
    width_m=0.056,
    depth_m=0.056,
    length_m=0.100,
    resistance_ohm=49.9679,
    inductance_h=76.2841e-3,
)

# J4 selects one of these banks. Both use the estimated pair inductance.
# 47 nF + 4.7 nF is the workbook ~1.7 kHz test. 33 nF + 4.7 nF is the ~2.1 kHz test.
C_TUNE_F = 51.7e-9
C_TUNE_ALT_F = 37.7e-9
R_IN_OHM = 8.2e6


def pair_inductance_h() -> float:
    return 2.0 * SENSOR["inductance_h"]


def tuning_capacitance(frequency_hz: float, inductance_h: float | None = None) -> float:
    """Parallel capacitance that resonates inductance_h at frequency_hz."""
    inductance = pair_inductance_h() if inductance_h is None else inductance_h
    return 1.0 / ((2.0 * math.pi * frequency_hz) ** 2 * inductance)


def tune_frequency_hz(capacitance_f: float, inductance_h: float | None = None) -> float:
    inductance = pair_inductance_h() if inductance_h is None else inductance_h
    return 1.0 / (2.0 * math.pi * math.sqrt(inductance * capacitance_f))


def tuning_selection_note() -> str:
    """How J4 moves the tank between the two test bands."""
    low = tune_frequency_hz(C_TUNE_F)
    high = tune_frequency_hz(C_TUNE_ALT_F)
    return (
        "J4 fits one shunt. Pins 1-2 connect C25 (47 nF) and C26 (4.7 nF), "
        f"resonant at {low:.0f} Hz. Pins 2-3 connect C27 (33 nF) and C28 "
        f"(4.7 nF), resonant at {high:.0f} Hz. The amplifier, blanking, and "
        "1.5-2.5 kHz filter stay fitted for both. With the shunt removed, an "
        "external capacitor from J4 pin 4 to pin 2 uses "
        "C = 1/(4*pi^2*f^2*L) when the measured inductance differs. Each "
        "tank's half-power width is R/(2*pi*L), about 104 Hz.\n"
    )


def current_coil():
    """Series-aiding sensing pair and the receiver tank connected across it.

    The workbook counts both windings in the open-circuit EMF and treats
    mutual inductance as negligible, so L and R are twice one coil. The
    equal-area radius is the 56 mm square aperture. The 8.2 megohm figure
    is the amplifier load on that tank, not the tuning capacitor.
    """
    inductance_h = pair_inductance_h()
    return dict(
        design_id=DESIGN_ID,
        n_turns=2 * SENSOR["turns"],
        radius_m=math.sqrt(SENSOR["width_m"] * SENSOR["depth_m"] / math.pi),
        b_pol=POLARIZER["field_t"],
        t2_star_s=0.95,
        r_coil=2.0 * SENSOR["resistance_ohm"],
        l_coil=inductance_h,
        c_tune=C_TUNE_F,
        c_tune_alt=C_TUNE_ALT_F,
        f_tune_hz=tune_frequency_hz(C_TUNE_F, inductance_h),
        f_tune_alt_hz=tune_frequency_hz(C_TUNE_ALT_F, inductance_h),
        r_in_ohm=R_IN_OHM,
        polarizer=dict(POLARIZER),
        sensor=dict(SENSOR),
        sensing_connection="series-aiding pair; both windings counted; M=0",
        hardware_characterized=False,
        model_status="workbook estimate, uncalibrated; retune after measuring L and R",
    )
