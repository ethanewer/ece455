"""Copy a UF2 image onto a Raspberry Pi Pico over USB.

Firmware built with the Pico SDK's USB serial reboots into its BOOTSEL drive
when its port is opened at 1200 baud; the image is then copied onto that
drive and the Pico restarts with it. Without a running port, hold BOOTSEL
while plugging the Pico in, then run this again.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

import serial
from serial.tools import list_ports

DRIVES = (Path("/Volumes/RP2350"), Path("/Volumes/RPI-RP2"))
RASPBERRY_PI_VID = 0x2E8A


def drive() -> Path | None:
    return next((path for path in DRIVES if path.is_dir()), None)


def flash(image: Path) -> Path:
    if drive() is None:
        port = next((p.device for p in list_ports.comports() if p.vid == RASPBERRY_PI_VID), None)
        if port is None:
            raise SystemExit("No Pico found. Hold BOOTSEL while plugging it in, then run again.")
        try:
            serial.Serial(port, 1200).close()
        except serial.SerialException as error:
            raise SystemExit(f"Cannot open {port} ({error}). Close the plotter or serial "
                             "monitor using it, then run again.") from None
        deadline = time.time() + 10
        while drive() is None and time.time() < deadline:
            time.sleep(0.25)
    target = drive()
    if target is None:
        raise SystemExit("The Pico did not enter BOOTSEL. Hold BOOTSEL while plugging it in.")
    shutil.copy(image, target)
    return target


if __name__ == "__main__":
    image = Path(sys.argv[1])
    print(f"copied {image} to {flash(image)}")
