"""Week-3 design inputs; slide values are nominal, not bench measurements.

See docs/coil-design.md for source, interpretation, and open questions.
"""
import math

DESIGN_ID = "week3-hunter-vania-v1"
POLARIZER = dict(turns=360, layers=4, wire_awg=18, wire_length_m=144.0,
                 width_m=0.07, depth_m=0.14, length_m=0.10,
                 resistance_ohm=3.0, inductance_h=15.4e-3,
                 current_a=3.0, field_t_ideal=13.6e-3,
                 # Finite rectangular-coil centre-field estimate. The slide's
                 # 13.6 mT is mu0*N*I/length; retain it as provenance only.
                 field_t=9.38e-3, pulse_s=5.0)
SENSOR = dict(turns_per_layer=138, layers=4, wire_awg=22,
              enamel_diameter_m=0.7e-3, wire_length_m=135.0,
              width_m=0.06, depth_m=0.06, length_m=0.10,
              resistance_ohm=7.0, inductance_h=11e-3,
              inductance_range_h=[10e-3, 12e-3])


def current_coil():
    """Series-opposed pair, one active sample, negligible mutual inductance.

    Both windings contribute Johnson noise; only A contributes FID. No
    unmeasured common-mode rejection benefit is credited in the score.
    Equal-area radius is a compatibility representation of the square bore.
    """
    return dict(design_id=DESIGN_ID, n_turns=552,
                radius_m=math.sqrt(0.06 * 0.06 / math.pi),
                b_pol=POLARIZER["field_t"], t2_star_s=0.95,
                r_coil=14.0, l_coil=22e-3,
                # The active receiver is untuned so it can cover the 1.5 to
                # 2.5 kHz field range. Keep the slide value as provenance.
                c_tune=None,
                c_tune_nominal=264e-9,
                polarizer=dict(POLARIZER), sensor=dict(SENSOR),
                sensing_connection="series-opposed; one active sample; M=0",
                # Do not promote score-card results until this topology and
                # polarizer turnoff are measured on the actual hardware.
                hardware_characterized=False,
                model_status="nominal, uncalibrated; turns and connection inferred")
