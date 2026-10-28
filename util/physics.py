"""Proton precession constants and the free-induction-decay signal.

A water-sample magnetometer measures protons shielded by the water molecule:
gamma'_p / 2 pi = 42.57638474 MHz/T (CODATA 2018), so 0.0425764 Hz/nT. The
free-proton value, 42.5774789 MHz/T, is 25.7 ppm higher and biases an
absolute field reading by about 1.3 nT at 50 uT. The firmware converts
frequency to field with the free-proton value (PROTON_GYROMAGNETIC_HZ_PER_T).
Relative (anomaly) measurements are unaffected; absolute values are not.

A polarizing field magnetizes the water's protons according to Curie's law.
After the pulse, they precess about Earth's field B and induce a decaying
sinusoid in the sensing coil:

    v(t) = V0 exp(-t / tau) sin(2 pi f t + phi),   f = gamma'_p B
"""
from __future__ import annotations

import numpy as np

# Shielded proton in water, CODATA 2018.
GAMMA_HZ_PER_T = 42.57638474e6
GAMMA_HZ_PER_NT = GAMMA_HZ_PER_T * 1e-9
NT_PER_HZ = 1.0 / GAMMA_HZ_PER_NT
# Free proton, CODATA 2014 (the firmware's constant).
FREE_PROTON_GAMMA_HZ_PER_T = 42.57747892e6
K_B = 1.380649e-23                  # J/K
MU_0 = 1.25663706212e-6             # H/m
MU_PROTON = 1.41060679736e-26       # J/T
PROTONS_PER_M3_WATER = 6.69e28      # 2 per molecule at 997 kg/m^3


def larmor_hz(b_tesla: float) -> float:
    return GAMMA_HZ_PER_T * b_tesla


def field_nt(frequency_hz: float) -> float:
    return frequency_hz * NT_PER_HZ


def fid(t: np.ndarray, amplitude: float, frequency_hz: float, tau_s: float,
        phase: float = 0.0) -> np.ndarray:
    """Free induction decay sampled at times t."""
    return amplitude * np.exp(-t / tau_s) * np.sin(2.0 * np.pi * frequency_hz * t + phase)


def curie_magnetization(b_polarizing_t: float, temperature_k: float) -> float:
    """Equilibrium proton magnetization of water, A/m (spin 1/2: n mu^2 B / kT)."""
    return PROTONS_PER_M3_WATER * MU_PROTON**2 * b_polarizing_t / (K_B * temperature_k)


def fid_emf(b_polarizing_t: float, turns: int, sample_area_m2: float, frequency_hz: float,
            temperature_k: float) -> float:
    """Initial FID amplitude induced in a coil wound around the sample, V peak.

    V0 = mu0 M0 A (2 pi f) N: the sample fills the coil's aperture and is
    fully polarized, the polarizing axis is perpendicular to Earth's field,
    and the coil is long compared with its width. Each assumption that fails
    in practice lowers the amplitude.
    """
    return (MU_0 * curie_magnetization(b_polarizing_t, temperature_k) * sample_area_m2
            * 2.0 * np.pi * frequency_hz * turns)
