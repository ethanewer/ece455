"""B4: analytic systematics layer -- the terms SPICE cannot see.

The SPICE noise model (physical e_n/i_n resistors) captures Johnson noise
only: white, uncorrelated, no low-frequency excess. A real front end adds:

  * 1/f flicker noise of the amplifier (the white e_n resistor in SPICE
    has no flicker mechanism);
  * CMRR-limited pickup of common-mode interference (mains on the shield);
  * PSRR-limited supply-rail ripple (modeled as a scored interferer in
    fid.generate_record -- B3).

This module implements the analytic formulas from the AFE research doc
(TI SLVA043B / ADI MT-049 for flicker; the RTI noise formula in section
2.2 of research-afe-evaluation.md) and reports a noise budget per
candidate so the optimizer sees these terms, not just the SPICE floor.

SPICE-vs-analytic split (documented, not hidden):
  - SPICE .noise sees: coil R thermal (explicit series R), the e_n
    resistor (white only), the i_n resistor, every physical R.
  - SPICE cannot see: amplifier 1/f (no flicker mechanism in a resistor),
    CMRR/PSRR coupling (behavioral E sources are noiseless with ideal
    rejection by construction), and any 1/f corner inside the band.
"""
import numpy as np

import fid


def flicker_excess_rms(e_n_white: float, f_corner: float,
                       f_lo: float, f_hi: float) -> float:
    """In-band RMS of the 1/f EXCESS beyond the white floor [V].

    Density e_n(f) = e_n_white*sqrt(1 + f_c/f); the excess term integrates
    to the closed form (TI SLVA043B / MT-049):
        E = e_n_white * sqrt(f_c * ln(f_H / f_L))
    """
    if f_corner <= 0:
        return 0.0
    return float(e_n_white * np.sqrt(f_corner * np.log(f_hi / f_lo)))


def cmrr_referred(v_common: float, cmrr_db: float) -> float:
    """Input-referred differential error from common-mode interference:
    a common-mode voltage with amplifier CMRR at that frequency appears at
    the differential input as v_common / CMRR [V]."""
    return v_common * 10.0 ** (-cmrr_db / 20.0)


def psrr_referred(v_rail_ripple: float, psrr_db: float) -> float:
    """Input-referred error from supply-rail ripple through PSRR [V]."""
    return v_rail_ripple * 10.0 ** (-psrr_db / 20.0)


def budget(r_coil=120.0, l_coil=2e-3, e_amp=7e-9, i_amp=0.05e-12,
           f_corner=10.0, v_cm_50hz=1.0, cmrr_db_50hz=100.0,
           v_rail_ripple=0.05, psrr_db=60.0) -> dict:
    """Noise budget at the 2 uV reference point: white floor vs systematics.

    Defaults model the INA828-class reference: 1/f corner 10 Hz (INA828's
    0.1-10 Hz spec), 50 Hz common-mode on the shield at CMRR 100 dB, and
    50 mV of switching-regulator ripple at PSRR 60 dB -- the values the
    scored ablations in run_scoring.py use.
    """
    sigma_white = fid.input_noise_rms(r_coil, l_coil, e_amp, i_amp)
    f_lo, f_hi = fid.NOISE_BAND
    e_flicker = flicker_excess_rms(e_amp, f_corner, f_lo, f_hi)
    # Exact in-band integral of the 1/f-inclusive density (white coil +
    # amplifier with flicker): excess fraction beyond the white RMS.
    f_grid = np.linspace(f_lo, f_hi, 4096)
    e_n_full = np.sqrt(
        e_amp**2 * (1.0 + f_corner / f_grid)
        + 4.0 * fid.K_B * fid.T_AMBIENT * r_coil)
    sigma_full = float(np.sqrt(np.trapezoid(e_n_full**2, f_grid)))
    return dict(
        sigma_white_v=sigma_white,
        sigma_with_flicker_v=sigma_full,
        flicker_excess_fraction=sigma_full / sigma_white - 1.0,
        cmrr_referred_v=cmrr_referred(v_cm_50hz, cmrr_db_50hz),
        rail_ripple_referred_v=psrr_referred(v_rail_ripple, psrr_db),
    )
