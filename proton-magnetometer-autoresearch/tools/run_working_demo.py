#!/usr/bin/env python3
"""Reproduce the simulation-qualified Week3 receiver demonstration.

The production coil keeps ``hardware_characterized=False``.  This command
also reports a conditional score that treats the simulated coil as ground
truth, so the electrical and estimator portions of the pipeline can be
demonstrated without claiming that hardware has been validated.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import circuit_spec as cs  # noqa: E402
import evaluate as ev  # noqa: E402
import fid  # noqa: E402
from coil_design import current_coil  # noqa: E402


def proposal_states():
    """Return the five switch states of one retunable receiver system."""
    for b_earth in ev.B_SWEEP:
        f_larmor = fid.larmor_hz(b_earth)
        coil = current_coil()
        coil["c_tune"] = 1.0 / (
            (2.0 * math.pi * f_larmor) ** 2 * coil["l_coil"]
        )
        yield b_earth, {
            "label": f"Week3 switched JFET {b_earth * 1e6:g} uT",
            "e_amp": 1.4e-9,
            "i_amp": 0.1e-12,
            "tuned": True,
            "preamp_gain": 4.0,
            "mfb_scale": 2130.0 / f_larmor,
            "estimator": "zoom",
            "mcu": {"tick_s": 8e-9, "clock_ppm": 0.5},
            "coil": coil,
        }


def evaluate_demo(n_mc: int = 40) -> dict:
    """Evaluate production and conditional-simulation status per state."""
    rows = []
    for b_earth, kwargs in proposal_states():
        production_spec = cs.afe_spec(**kwargs)
        sim = cs.simulate(production_spec)
        production = ev.evaluate_with_sim(
            production_spec, sim, b_fields=(b_earth,), n_mc=n_mc
        )

        conditional_spec = copy.deepcopy(production_spec)
        conditional_spec["meta"]["coil"]["hardware_characterized"] = True
        conditional_spec["meta"]["coil"]["model_status"] = (
            "simulation assumption for demonstration"
        )
        conditional = ev.evaluate_with_sim(
            conditional_spec, sim, b_fields=(b_earth,), n_mc=n_mc
        )
        band = conditional["bands"][0]
        rows.append(
            {
                "b_earth_uT": band["b_earth_uT"],
                "c_tune_nF": kwargs["coil"]["c_tune"] * 1e9,
                "mfb_scale": kwargs["mfb_scale"],
                "rms_nt": band["rms_nt"],
                "crb_nt": band["crb_nt"],
                "ripple_rms_nt": band["rms_ripple_nt"],
                "clip_margin": band["clip_margin"],
                "tau_ring_ms": band["tau_ring_ms"],
                "gates": band["gates"],
                "conditional_J_nt": conditional["J_nt"],
                "production_J_nt": production["J_nt"],
                "kwargs": kwargs,
            }
        )
    return {
        "proposal": "Week3 five-state switched tuned-JFET receiver",
        "interpretation": (
            "Conditional simulation result; production remains gated until "
            "the Week3 coil and 3 A turnoff are characterized."
        ),
        "n_mc": n_mc,
        "worst_conditional_J_nt": max(row["conditional_J_nt"] for row in rows),
        "all_simulated_gates_pass": all(
            all(value for name, value in row["gates"].items()
                if name != "hardware_characterized")
            for row in rows
        ),
        "states": rows,
    }


def print_summary(result: dict) -> None:
    print(result["proposal"])
    print(result["interpretation"])
    print(
        "field  Ctune    RMS       CRB       ripple    clip    ring    sim  production"
    )
    for row in result["states"]:
        simulated_pass = all(
            value for name, value in row["gates"].items()
            if name != "hardware_characterized"
        )
        print(
            f"{row['b_earth_uT']:5.1f}  {row['c_tune_nF']:7.1f}nF  "
            f"{row['rms_nt']:8.5f}  {row['crb_nt']:8.5f}  "
            f"{row['ripple_rms_nt']:8.5f}  {row['clip_margin']:6.4f}  "
            f"{row['tau_ring_ms']:5.2f}ms  "
            f"{'PASS' if simulated_pass else 'FAIL':4s}  "
            f"{'GATED' if math.isinf(row['production_J_nt']) else 'PASS'}"
        )
    print(f"worst conditional J = {result['worst_conditional_J_nt']:.5f} nT")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-mc", type=int, default=40)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = evaluate_demo(n_mc=args.n_mc)
    if args.json:
        print(json.dumps(result, indent=2, allow_nan=True))
    else:
        print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
