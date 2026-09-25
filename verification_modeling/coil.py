"""Coil nominals from CoilDesign.xlsx. These are winding estimates, not measurements.

See docs/coil-design.md. After the coils are wound, measure L and R.
Any coil tuning is external to the receiver.
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

# Representative low and high FID input frequencies for receiver evaluation.
# They do not imply an on-board LC network or an accepted external tuning part.
FID_LOW_HZ = 1765.0
FID_HIGH_HZ = 2129.0
R_IN_OHM = 5.1e6


def pair_inductance_h() -> float:
    return 2.0 * SENSOR["inductance_h"]


def tuning_capacitance(frequency_hz: float, inductance_h: float | None = None) -> float:
    """Parallel capacitance that resonates inductance_h at frequency_hz."""
    inductance = pair_inductance_h() if inductance_h is None else inductance_h
    return 1.0 / ((2.0 * math.pi * frequency_hz) ** 2 * inductance)


def tune_frequency_hz(capacitance_f: float, inductance_h: float | None = None) -> float:
    inductance = pair_inductance_h() if inductance_h is None else inductance_h
    return 1.0 / (2.0 * math.pi * math.sqrt(inductance * capacitance_f))


def current_coil():
    """Series-aiding sensing pair outside the receiver.

    The workbook counts both windings in the open-circuit EMF and treats
    mutual inductance as negligible, so L and R are twice one coil. The
    equal-area radius is the 56 mm square aperture. The receiver's 5.1
    megohm input return is supplied for interface calculations.
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
        f_test_low_hz=FID_LOW_HZ,
        f_test_high_hz=FID_HIGH_HZ,
        r_in_ohm=R_IN_OHM,
        polarizer=dict(POLARIZER),
        sensor=dict(SENSOR),
        sensing_connection="series-aiding pair; both windings counted; M=0",
        hardware_characterized=False,
        model_status="workbook estimate, uncalibrated; external sensor tuning is separate",
    )
