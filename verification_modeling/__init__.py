"""Analysis and verification code for the active proton magnetometer design."""

from .coil import current_coil
from .physics import GAMMA_HZ_PER_NT, GAMMA_HZ_PER_T, larmor_hz

__all__ = ["GAMMA_HZ_PER_NT", "GAMMA_HZ_PER_T", "current_coil", "larmor_hz"]
