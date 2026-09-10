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
    """Seed population.

    Coil geometry is the ONLY coil input (E3 audit finding 1): wire gauge
    + axis length go to afe_spec, which derives r_coil/l_coil from the
    winding -- the same geometry that sets V0. The optimizer therefore
    cannot raise signal without paying winding resistance (closing the
    E6 finding 3 exploit that elite.json's first run found).
    """
    seeds = [
        dict(label="seed untuned INA", e_amp=7e-9, i_amp=170e-15,
             tuned=False, preamp_gain=100.0, mfb_scale=1.0,
             wire_d_mm=0.15, winding_len_m=0.08,
             coil=dict(n_turns=530, radius_m=0.015, b_pol=0.02)),
        dict(label="seed tuned JFET", e_amp=1.4e-9, i_amp=0.1e-12,
             tuned=True, preamp_gain=4.0, mfb_scale=1.0,
             wire_d_mm=0.56, winding_len_m=0.30,
             coil=dict(n_turns=1500, radius_m=0.030, b_pol=0.05,
                       c_tune="210n")),   # resonance of the derived L
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
                l_coil = _coil_l(child)
                coil["c_tune"] = "%.3g" % (
                    1.0 / (2.0 * np.pi * fid.larmor_hz(50e-6)) ** 2 / l_coil)
        else:
            child.pop("preamp_gain", None)
    elif op == "retune":
        b_new = float(rng.uniform(25e-6, 65e-6))
        l_coil = _coil_l(child)
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


def _coil_l(kwargs: dict) -> float:
    """Coil inductance [H] the candidate will actually run with: derived
    from the winding geometry (the coupled path), falling back to an
    explicit l_coil string/number if present."""
    coil = kwargs["coil"]
    if "l_coil" in coil:
        v = str(coil["l_coil"]).strip().lower()
        scale = {"m": 1e-3, "u": 1e-6, "n": 1e-9, "": 1.0}
        unit = v[-1] if v[-1].isalpha() else ""
        return float(v[:-1] if unit else v) * scale[unit]
    import circuit_spec as _cs
    cw = _cs.coil_model(n_turns=coil["n_turns"], radius_m=coil["radius_m"],
                        wire_d_mm=kwargs["wire_d_mm"], b_pol=coil["b_pol"],
                        winding_len_m=kwargs.get("winding_len_m"))
    return cw["l_coil"]
