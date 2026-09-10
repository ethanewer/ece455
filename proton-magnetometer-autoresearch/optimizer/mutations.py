"""A7: mutation operators for the score-guided search.

Mutations act on a candidate kwargs dict (the arguments of
circuit_spec.afe_spec). NO agent/LLM in the loop: score-guided search
only, every operator is deterministic given (parent, rng).

Operators:
  * topology swap: tuned <-> untuned input;
  * tank retune: c_tune moves to a random field point's f_L (B8 axis);
  * gain stage: preamp_gain x {0.5, 1.5, 2};
  * bandpass recenter: mfb_scale x {0.9, 1.1};
  * amplifier swap: e_n/i_n pairs from the parts DB (INA828 <-> ADA4898
    <-> 2N6550-class JFET).
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "poc"))
import fid

ROOT = Path(__file__).resolve().parent.parent

# Amplifier swaps from the parts DB (e_n, i_n pairs with labels).
PARTS_DB = json.loads((ROOT / "parts" / "parts_db.json").read_text())
AMPS = [
    ("INA828-class", 7e-9, 170e-15),
    ("ADA4898-class", 1.1e-9, 2.4e-12),
    ("JFET 2N6550-class", 1.4e-9, 0.1e-12),
]


def base_candidates() -> list:
    """Seed population: the demo candidates + the per-band family."""
    seeds = [
        dict(label="seed untuned INA", e_amp=7e-9, i_amp=170e-15,
             tuned=False, preamp_gain=100.0, mfb_scale=1.0,
             coil=dict(r_coil=120, l_coil="2m", n_turns=530,
                       radius_m=0.015, b_pol=0.02)),
        dict(label="seed tuned JFET", e_amp=1.4e-9, i_amp=0.1e-12,
             tuned=True, preamp_gain=4.0, mfb_scale=1.0,
             coil=dict(r_coil=20, l_coil="100m", c_tune="56n",
                       n_turns=1500, radius_m=0.030, b_pol=0.05)),
    ]
    return seeds


def mutate(parent: dict, rng: np.random.Generator) -> dict:
    """One random mutation of the parent. Returns a NEW kwargs dict."""
    child = copy.deepcopy(parent)
    ops = ["topology", "gain", "bandpass", "amp"]
    if child.get("tuned"):
        ops.append("retune")
    op = rng.choice(ops)
    if op == "topology":
        child["tuned"] = not child.get("tuned", False)
        if child["tuned"]:
            child.setdefault("preamp_gain", 4.0)
            coil = child["coil"]
            if "c_tune" not in coil:
                # retune to the demo's 50 uT tank as a starting point
                l_coil = _coil_l(coil)
                coil["c_tune"] = "%.3g" % (
                    1.0 / (2.0 * np.pi * fid.larmor_hz(50e-6)) ** 2 / l_coil)
        else:
            child.pop("preamp_gain", None)
    elif op == "retune":
        b_new = float(rng.uniform(25e-6, 65e-6))
        l_coil = _coil_l(child["coil"])
        child["coil"]["c_tune"] = "%.3g" % (
            1.0 / (2.0 * np.pi * fid.larmor_hz(b_new)) ** 2 / l_coil)
    elif op == "gain":
        child["preamp_gain"] = float(
            child.get("preamp_gain", 100.0) * rng.choice([0.5, 1.5, 2.0]))
    elif op == "bandpass":
        child["mfb_scale"] = float(
            child.get("mfb_scale", 1.0) * rng.choice([0.9, 1.1]))
    elif op == "amp":
        label, e_n, i_n = AMPS[int(rng.integers(len(AMPS)))]
        child["e_amp"], child["i_amp"] = e_n, i_n
    return child


def _coil_l(coil: dict) -> float:
    """Coil inductance in H from the IR value string ('100m' etc.)."""
    v = str(coil["l_coil"]).strip().lower()
    scale = {"m": 1e-3, "u": 1e-6, "n": 1e-9, "": 1.0}
    unit = v[-1] if v[-1].isalpha() else ""
    return float(v[:-1] if unit else v) * scale[unit]
