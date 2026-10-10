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
    measure_node_gains,
    measure_noise,
    measure_operating_point,
)

# The FID band. Noise is limited across it, and gain is reported over it.
SIGNAL_BAND_HZ = (1600.0, 2200.0)
# 1. Input impedance at J1.
ZIN_MIN_OHM = 1.0e6
ZIN_BAND_HZ = (1500.0, 2500.0)
# 2. Input noise, referred to the untuned coil EMF, everywhere in the signal
# band. 5 nV/rtHz keeps the frequency Cramer-Rao bound near 0.24 nT for the
# pessimistic 0.41 uV FID (1.5 s at 30 kSPS), a 4x margin under 1 nT.
NOISE_MAX_V_RT_HZ = 5.0e-9
# ADS1256 converter noise at PGA 1, 30 kSPS, buffer off (TI Table 4),
# treated as white over the 15 kHz Nyquist band and referred through the
# minimum in-band gain. Low analog gain therefore fails this requirement.
ADC_NOISE_RMS_V = 10.341e-6
ADC_NOISE_BANDWIDTH_HZ = 15e3

# 3. Interference: no stage leaves its linear range for a single tone at J1
# of the given peak amplitude anywhere in each band (mains fundamental and
# harmonics; switching and audio-band pickup). Tolerance at each node is
# its DC headroom divided by its small-signal gain from J1.
INTERFERENCE = (
    ((50.0, 400.0), 10e-3),
    ((8000.0, 50000.0), 2e-3),
)
# AD8421 (Rev. 0 datasheet): input operating range -VS + 2.3 V to
# +VS - 1.8 V, output swing -VS + 1.2 V to +VS - 1.6 V.
AMP_INPUT_MARGIN_V = (2.3, 1.8)
AMP_OUTPUT_MARGIN_V = (1.2, 1.6)
# ADS1256 with the buffer off: AIN0 spans AGND - 0.1 V to AVDD + 0.1 V.
# AIN1 is GND, so AIN0 also stays within the 2 VREF / PGA = 5 V full scale.
ADC_ABSOLUTE_MARGIN_V = 0.1
ADC_FULL_SCALE_V = 5.0
# Linear-range limits for each node, from its DC operating point.
HEADROOM = {
    "receiver_in": lambda v: min(
        v["receiver_in"] - (v["vneg"] + AMP_INPUT_MARGIN_V[0]),
        v["vpos"] - AMP_INPUT_MARGIN_V[1] - v["receiver_in"]),
    "amp_out": lambda v: min(
        v["amp_out"] - (v["vneg"] + AMP_OUTPUT_MARGIN_V[0]),
        v["vpos"] - AMP_OUTPUT_MARGIN_V[1] - v["amp_out"]),
    "ain0": lambda v: min(
        v["ain0"] + ADC_ABSOLUTE_MARGIN_V,
        min(v["vbus5"] + ADC_ABSOLUTE_MARGIN_V, ADC_FULL_SCALE_V) - v["ain0"]),
}

# 4. Anti-aliasing. The ADS1256 modulator samples at fCLKIN/4 = 1.92 MHz.
# Its digital filter repeats there, so tones within the signal band of
# 1.92 MHz fold into the FID band unattenuated. The analog filter must hold
# the J1-to-AIN0 gain there this far below the minimum in-band gain.
ADC_MODULATOR_HZ = 1.92e6
ALIAS_BAND_HZ = (ADC_MODULATOR_HZ - SIGNAL_BAND_HZ[1],
                 ADC_MODULATOR_HZ + SIGNAL_BAND_HZ[1])
ALIAS_REJECTION_MIN_DB = 90.0

INPUT_NODE = "receiver_in"
OUTPUT_POSITIVE = "ain0"
OUTPUT_NEGATIVE = "0"
SOURCE = "Vfid"
FIXTURE = "Rsource source receiver_in 30k"
SUPPLY = "Vusb vbus5 0 5"
BATTERIES = ("Vbat1 vpos 0 9", "Vbat2 0 vneg 9")
BIAS = "Vbias amp_ref 0 2.5"
MODULE = "XMOD2 receiver_in 0 rg_a rg_b amp_out amp_ref vpos vneg AD8421_MODULE"
GAIN_RESISTOR = "R1"
FILTER_CAPACITORS = ("C1", "C2")


@dataclass(frozen=True)
class Corner:
    name: str
    temp_c: float | None = None
    usb_v: float | None = None
    battery_v: float | None = None
    bias_v: float | None = None
    filter_c_scale: float = 1.0
    rg_scale: float = 1.0


CORNERS = (
    Corner("nominal"),
    Corner("0 C", temp_c=0.0),
    Corner("50 C", temp_c=50.0),
    Corner("USB 4.75 V", usb_v=4.75),
    Corner("batteries 6.0 V", battery_v=6.0),
    Corner("batteries 9.6 V", battery_v=9.6),
    Corner("C -10%, R1 -5%", filter_c_scale=0.9, rg_scale=0.95),
    Corner("C +10%, R1 +5%", filter_c_scale=1.1, rg_scale=1.05),
    Corner("50 C, 4.75 V, 6 V, BIAS 2.75 V, C -10%, R1 -5%", temp_c=50.0,
           usb_v=4.75, battery_v=6.0, bias_v=2.75, filter_c_scale=0.9,
           rg_scale=0.95),
    Corner("50 C, BIAS 2.25 V, C +10%, R1 +5%", temp_c=50.0, bias_v=2.25,
           filter_c_scale=1.1, rg_scale=1.05),
)


@dataclass(frozen=True)
class CornerResult:
    corner: Corner
    gain_min: float
    zin_min_ohm: float
    noise_max_v_rt_hz: float
    # Per interference band: (largest tolerable tone at J1 [V], limiting node).
    interference: tuple[tuple[float, str], ...]
    alias_rejection_db: float

    @property
    def failures(self) -> list[str]:
        failed = []
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
        for ((low, high), required), (tolerance, node) in zip(
                INTERFERENCE, self.interference):
            if tolerance < required:
                failed.append(
                    f"{node} clips for a {tolerance * 1e3:.1f} mV tone in "
                    f"{low:.0f}-{high:.0f} Hz (< {required * 1e3:.0f} mV)"
                )
        if self.alias_rejection_db < ALIAS_REJECTION_MIN_DB:
            failed.append(
                f"alias rejection {self.alias_rejection_db:.1f} dB < "
                f"{ALIAS_REJECTION_MIN_DB:.0f} dB near "
                f"{ADC_MODULATOR_HZ / 1e6:g} MHz"
            )
        return failed


def _spice_number(text: str) -> float:
    """Parse a SPICE value such as 22n, 1k, 4.7Meg, or 100."""
    match = re.fullmatch(r"([-+0-9.eE]+)(meg|[fpnumkg])?", text, re.I)
    if match is None:
        raise ValueError(f"unparseable SPICE value {text!r}")
    scale = {None: 1.0, "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6,
             "m": 1e-3, "k": 1e3, "meg": 1e6, "g": 1e9}
    suffix = match.group(2).lower() if match.group(2) else None
    return float(match.group(1)) * scale[suffix]


def _scale_element(text: str, ref: str, factor: float) -> str:
    """Multiply a two-terminal element's value by factor."""
    pattern = rf"(?m)^({ref}\s+\S+\s+\S+\s+)(\S+)\s*$"
    match = re.search(pattern, text)
    if match is None:
        raise RuntimeError(f"receiver deck has no element {ref}")
    value = _spice_number(match.group(2)) * factor
    return text[:match.start()] + f"{match.group(1)}{value:.6g}" + text[match.end():]


def _replace_unique(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"receiver deck is missing a unique '{old}'")
    return text.replace(old, new)


def corner_netlist(text: str, corner: Corner) -> str:
    """Apply a temperature, supply, trim, and tolerance corner."""
    if corner.usb_v is not None:
        text = _replace_unique(text, SUPPLY, f"Vusb vbus5 0 {corner.usb_v:g}")
    if corner.battery_v is not None:
        text = _replace_unique(text, BATTERIES[0],
                               f"Vbat1 vpos 0 {corner.battery_v:g}")
        text = _replace_unique(text, BATTERIES[1],
                               f"Vbat2 0 vneg {corner.battery_v:g}")
    if corner.bias_v is not None:
        text = _replace_unique(text, BIAS, f"Vbias amp_ref 0 {corner.bias_v:g}")
    if corner.rg_scale != 1.0:
        text = _scale_element(text, GAIN_RESISTOR, corner.rg_scale)
    if corner.filter_c_scale != 1.0:
        for ref in FILTER_CAPACITORS:
            text = _scale_element(text, ref, corner.filter_c_scale)
    if corner.temp_c is not None:
        end = text.rindex("\n.end")
        text = text[:end] + f"\n.options temp={corner.temp_c:g}" + text[end:]
    return text


def untuned_coil_netlist(text: str) -> str:
    """Replace the 30 kohm fixture with the series coil pair model."""
    coil = current_coil()
    return _replace_unique(
        text, FIXTURE,
        f"Rsource source coil_mid {coil['r_coil']:.6g}\n"
        f"Lsource coil_mid receiver_in {coil['l_coil']:.6g}",
    )


def adc_noise_density_v_rt_hz() -> float:
    """ADS1256 converter noise density at AIN0."""
    return ADC_NOISE_RMS_V / math.sqrt(ADC_NOISE_BANDWIDTH_HZ)


def evaluate_corner(netlist: Path, corner: Corner) -> CornerResult:
    text = corner_netlist(netlist.read_text(), corner)
    with tempfile.TemporaryDirectory(prefix="receiver-corner-") as directory:
        deck = Path(directory) / "receiver.cir"
        deck.write_text(text)
        _, gain = measure_gain(
            deck, input_node=INPUT_NODE, output_positive=OUTPUT_POSITIVE,
            output_negative=OUTPUT_NEGATIVE, band_hz=SIGNAL_BAND_HZ,
        )
        _, alias = measure_gain(
            deck, input_node=INPUT_NODE, output_positive=OUTPUT_POSITIVE,
            output_negative=OUTPUT_NEGATIVE, band_hz=ALIAS_BAND_HZ,
        )
        _, zin = measure_input_impedance(
            deck, source=SOURCE, node=INPUT_NODE, band_hz=ZIN_BAND_HZ,
        )
        levels = measure_operating_point(deck, ["vpos", "vneg", "vbus5",
                                                *HEADROOM])
        interference = []
        for (low, high), _required in INTERFERENCE:
            frequency, gains = measure_node_gains(
                deck, input_node=INPUT_NODE, nodes=list(HEADROOM),
                band_hz=(low / 1.01, high * 1.01),
            )
            in_band = (frequency >= low) & (frequency <= high)
            interference.append(min(
                (HEADROOM[node](levels) / float(gains[node][in_band].max()), node)
                for node in HEADROOM
            ))
        deck.write_text(untuned_coil_netlist(text))
        noise = measure_noise(
            deck, source=SOURCE, output_positive=OUTPUT_POSITIVE,
            output_negative=OUTPUT_NEGATIVE, band_hz=SIGNAL_BAND_HZ,
            spot_hz=math.sqrt(SIGNAL_BAND_HZ[0] * SIGNAL_BAND_HZ[1]),
        )
    gain_min = float(gain.min())
    total_noise = math.hypot(noise.max_input_density_v_rt_hz,
                             adc_noise_density_v_rt_hz() / gain_min)
    rejection = 20 * math.log10(gain_min / float(alias.max()))
    return CornerResult(corner, gain_min, float(zin.min()), total_noise,
                        tuple(interference), rejection)


def check_requirements(netlist: Path) -> list[CornerResult]:
    return [evaluate_corner(netlist, corner) for corner in CORNERS]
