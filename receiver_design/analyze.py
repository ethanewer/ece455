#!/usr/bin/env python3
"""Generate the standard transient and frequency-response receiver report."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from verification_modeling.coil import current_coil
from verification_modeling.eda.report import build_spice_report

if __name__ == "__main__":
    coil = current_coil()
    # The marker is an example input frequency, not receiver resonance.
    result = build_spice_report(
        ROOT / "spice/receiver.cir",
        ROOT / "analysis",
        input_node="source",
        output_positive="ads_ain0",
        output_negative="vref",
        marker_hz=coil["f_test_low_hz"],
        passband_hz=None,
        transient_start_s=0.200,
        transient_stop_s=0.220,
    )
    result.summary_md.write_text(
        result.summary_md.read_text().rstrip()
        + "\n\nThe source is a 10 µV signal with 30 kohm external source "
        "impedance. Coil tuning and damping are outside this receiver model. "
        "The plotted gain is from the receiver input source to AIN0−AIN1. "
        "The lab-parts analog path has no gain or narrow bandpass; ADS1256 "
        "converter noise and digital filtering are absent from these plots.\n"
    )
    print(f"wrote {result.waveforms_png}")
    print(f"wrote {result.response_png}")
