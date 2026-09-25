#!/usr/bin/env python3
"""Generate the standard transient and frequency-response receiver report."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from verification_modeling.coil import current_coil, tuning_selection_note
from verification_modeling.eda.report import build_spice_report


def _append_tuning_note(summary) -> None:
    text = summary.read_text()
    note = tuning_selection_note()
    if note not in text:
        summary.write_text(text.rstrip() + "\n\n" + note)

if __name__ == "__main__":
    coil = current_coil()
    # The shaded span is the fixed active filter, which passes both test
    # bands. The marker is J4's default ~1.7 kHz tank.
    result = build_spice_report(
        ROOT / "spice/receiver.cir",
        ROOT / "analysis",
        input_node="source",
        output_positive="ads_ain0",
        output_negative="vref",
        resonance_hz=coil["f_tune_hz"],
        passband_hz=(1500.0, 2500.0),
    )
    _append_tuning_note(result.summary_md)
    print(f"wrote {result.waveforms_png}")
    print(f"wrote {result.response_png}")
