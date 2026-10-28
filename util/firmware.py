"""Compile the Pico firmware on the host and run its frequency estimator.

util/firmware_host/harness.c includes firmware/PicoProgramECE455.c unchanged,
with stub Pico SDK headers, and feeds it ADC codes from stdin. The compiler is
$CC, else clang or gcc. (A plain `cc` is not tried because it is not always a
C compiler.)
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import numpy as np

from util import design

HARNESS = Path(__file__).resolve().parent / "firmware_host"


def compiler() -> str | None:
    if os.environ.get("CC"):
        return os.environ["CC"]
    return next((name for name in ("clang", "gcc") if shutil.which(name)), None)


def build(output_dir: Path) -> Path:
    """Compile the harness with the firmware; return the executable."""
    cc = compiler()
    if cc is None:
        raise RuntimeError("no C compiler found; set CC")
    output_dir.mkdir(parents=True, exist_ok=True)
    executable = output_dir / "firmware-estimator"
    subprocess.run([cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I", str(HARNESS), "-I", str(design.FIRMWARE.parent),
                    str(HARNESS / "harness.c"), "-o", str(executable)], check=True)
    return executable


def volts_to_codes(volts: np.ndarray) -> np.ndarray:
    """Differential ADC input -> 24-bit codes with the firmware's VREF and PGA, saturating."""
    constants = design.firmware_constants()
    full = constants["ADS_MAX_CODE"]
    codes = np.round(volts * constants["ADS_PGA"] * full / (2.0 * constants["ADS_VREF"]))
    return np.clip(codes, -full - 1, full).astype(np.int64)


def estimate(executable: Path, codes: np.ndarray, sample_rate: float) -> dict[str, float]:
    """Run the firmware's calculate_frequency and calculate_vpp on one record."""
    text = f"{sample_rate!r} {len(codes)}\n" + "\n".join(map(str, codes.tolist())) + "\n"
    process = subprocess.run([str(executable)], input=text, capture_output=True, text=True,
                             check=True)
    return {name: float(value) for name, value in
            (line.split() for line in process.stdout.splitlines())}
