"""Receiver requirements and the corner simulations that enforce them.

`make verify` runs `check_requirements` through verify.py and fails if any
limit is missed at any corner. Tests import the same limits.
"""
from __future__ import annotations

import math
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from verification_modeling.coil import current_coil
from verification_modeling.eda.report import (
    measure_gain,
    measure_input_impedance,
    measure_noise,
)

# 1. Gain from J1 to ADS1256 AIN0-AIN1 everywhere in the FID band.
GAIN_MIN_V_PER_V = 2000.0
GAIN_BAND_HZ = (1600.0, 2200.0)
# 2. Input impedance at J1.
ZIN_MIN_OHM = 1.0e6
ZIN_BAND_HZ = (1500.0, 2500.0)
# 3. Input noise, referred to the untuned coil EMF, everywhere in the gain
# band. 5 nV/rtHz keeps the frequency Cramer-Rao bound near 0.24 nT for the
# pessimistic 0.41 uV FID (1.5 s at 30 kSPS), a 4x margin under 1 nT.
NOISE_MAX_V_RT_HZ = 5.0e-9
# ADS1256 converter noise at PGA 1, 30 kSPS, buffer on (TI Table 1),
# treated as white over the 15 kHz Nyquist band and referred through the gain.
ADC_NOISE_RMS_V = 10.7e-6
ADC_NOISE_BANDWIDTH_HZ = 15e3

INPUT_NODE = "receiver_in"
OUTPUT_POSITIVE = "ain0"
OUTPUT_NEGATIVE = "bias"
SOURCE = "Vfid"
FIXTURE = "Rsource source receiver_in 30k"
SUPPLY = "Vusb vbus5 0 5"


@dataclass(frozen=True)
class Corner:
    name: str
    beta_scale: float = 1.0
    temp_c: float | None = None
    usb_v: float | None = None


CORNERS = (
    Corner("nominal"),
    Corner("beta x0.5", beta_scale=0.5),
    Corner("beta x2", beta_scale=2.0),
    Corner("0 C", temp_c=0.0),
    Corner("50 C", temp_c=50.0),
    Corner("USB 4.75 V", usb_v=4.75),
    Corner("USB 5.25 V", usb_v=5.25),
    Corner("beta x0.5, 0 C, 4.75 V", beta_scale=0.5, temp_c=0.0, usb_v=4.75),
    Corner("beta x0.5, 50 C, 4.75 V", beta_scale=0.5, temp_c=50.0, usb_v=4.75),
)


@dataclass(frozen=True)
class CornerResult:
    corner: Corner
    gain_min: float
    zin_min_ohm: float
    noise_max_v_rt_hz: float

    @property
    def failures(self) -> list[str]:
        failed = []
        if self.gain_min < GAIN_MIN_V_PER_V:
            failed.append(
                f"gain {self.gain_min:.0f} V/V < {GAIN_MIN_V_PER_V:.0f} V/V "
                f"in {GAIN_BAND_HZ[0]:.0f}-{GAIN_BAND_HZ[1]:.0f} Hz"
            )
        if self.zin_min_ohm < ZIN_MIN_OHM:
            failed.append(
                f"|Z_in| {self.zin_min_ohm / 1e6:.2f} Mohm < "
                f"{ZIN_MIN_OHM / 1e6:.2f} Mohm in "
                f"{ZIN_BAND_HZ[0]:.0f}-{ZIN_BAND_HZ[1]:.0f} Hz"
            )
        if self.noise_max_v_rt_hz > NOISE_MAX_V_RT_HZ:
            failed.append(
                f"noise {self.noise_max_v_rt_hz * 1e9:.2f} nV/rtHz > "
                f"{NOISE_MAX_V_RT_HZ * 1e9:.2f} nV/rtHz"
            )
        return failed


def corner_netlist(text: str, corner: Corner) -> str:
    """Apply a transistor-beta, temperature, and USB-voltage corner."""
    text = re.sub(
        r"\bBf=([0-9.eE+-]+)",
        lambda match: f"Bf={float(match.group(1)) * corner.beta_scale:g}",
        text,
    )
    if corner.usb_v is not None:
        if text.count(SUPPLY) != 1:
            raise RuntimeError(f"receiver deck is missing a unique '{SUPPLY}'")
        text = text.replace(SUPPLY, f"Vusb vbus5 0 {corner.usb_v:g}")
    if corner.temp_c is not None:
        end = text.rindex("\n.end")
        text = text[:end] + f"\n.options temp={corner.temp_c:g}" + text[end:]
    return text


def untuned_coil_netlist(text: str) -> str:
    """Replace the 30 kohm fixture with the series coil pair model."""
    coil = current_coil()
    if text.count(FIXTURE) != 1:
        raise RuntimeError("receiver deck is missing its unique source fixture")
    return text.replace(
        FIXTURE,
        f"Rsource source coil_mid {coil['r_coil']:.6g}\n"
        f"Lsource coil_mid receiver_in {coil['l_coil']:.6g}",
    )


def evaluate_corner(netlist: Path, corner: Corner) -> CornerResult:
    text = corner_netlist(netlist.read_text(), corner)
    with tempfile.TemporaryDirectory(prefix="receiver-corner-") as directory:
        deck = Path(directory) / "receiver.cir"
        deck.write_text(text)
        _, gain = measure_gain(
            deck, input_node=INPUT_NODE, output_positive=OUTPUT_POSITIVE,
            output_negative=OUTPUT_NEGATIVE, band_hz=GAIN_BAND_HZ,
        )
        _, zin = measure_input_impedance(
            deck, source=SOURCE, node=INPUT_NODE, band_hz=ZIN_BAND_HZ,
        )
        deck.write_text(untuned_coil_netlist(text))
        noise = measure_noise(
            deck, source=SOURCE, output_positive=OUTPUT_POSITIVE,
            output_negative=OUTPUT_NEGATIVE, band_hz=GAIN_BAND_HZ,
            spot_hz=math.sqrt(GAIN_BAND_HZ[0] * GAIN_BAND_HZ[1]),
        )
    gain_min = float(gain.min())
    adc_density = ADC_NOISE_RMS_V / math.sqrt(ADC_NOISE_BANDWIDTH_HZ)
    total_noise = math.hypot(noise.max_input_density_v_rt_hz,
                             adc_density / gain_min)
    return CornerResult(corner, gain_min, float(zin.min()), total_noise)


def check_requirements(netlist: Path) -> list[CornerResult]:
    return [evaluate_corner(netlist, corner) for corner in CORNERS]
