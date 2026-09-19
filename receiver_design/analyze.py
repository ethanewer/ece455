#!/usr/bin/env python3
"""Generate the standard transient and frequency-response receiver report."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from verification_modeling.eda.report import build_spice_report

if __name__ == "__main__":
    result = build_spice_report(
        ROOT / "spice/receiver.cir",
        ROOT / "analysis",
        input_node="source",
        output_positive="ads_ain0",
        output_negative="vref",
        resonance_hz=2128.819237,
        passband_hz=(1500.0, 2500.0),
    )
    print(f"wrote {result.waveforms_png}")
    print(f"wrote {result.response_png}")
