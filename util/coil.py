"""Winding geometry, resistance, and inductance by the CoilDesign.xlsx method.

A rectangular bobbin is close-wound: floor(width / wire OD) turns per layer,
the first turn around the bobbin plus one wire OD on each side, and each
further layer adding 8 wire ODs of perimeter. Inductance uses the workbook's
Wheeler multilayer approximation with the equal-area radius of the mean
turn. These functions reproduce the workbook's numbers, and can be inverted
to infer how many turns a finished coil has from its measured inductance or
resistance.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

INCH = 0.0254
FOOT = 0.3048


@dataclass(frozen=True)
class Bobbin:
    long_m: float          # outer winding-core dimensions
    short_m: float
    width_m: float         # axial winding width
    wire_od_m: float       # insulated wire diameter
    ohm_per_kft: float     # copper resistance of the wire

    @property
    def turns_per_layer(self) -> int:
        return int(self.width_m / self.wire_od_m + 1e-9)


def layers(bobbin: Bobbin, turns: int) -> int:
    return math.ceil(turns / bobbin.turns_per_layer)


def wire_length_m(bobbin: Bobbin, turns: int) -> float:
    per_layer = bobbin.turns_per_layer
    first = 2 * (bobbin.long_m + bobbin.short_m + 2 * bobbin.wire_od_m)
    step = 8 * bobbin.wire_od_m
    full, partial = divmod(turns, per_layer)
    return per_layer * (full * first + step * full * (full - 1) / 2) + partial * (first + full * step)


def resistance_ohm(bobbin: Bobbin, turns: int) -> float:
    return wire_length_m(bobbin, turns) / FOOT / 1000 * bobbin.ohm_per_kft


def mean_turn_area_m2(bobbin: Bobbin, turns: int) -> float:
    depth = bobbin.wire_od_m * layers(bobbin, turns)
    return (bobbin.long_m + depth) * (bobbin.short_m + depth)


def inductance_h(bobbin: Bobbin, turns: int) -> float:
    """Wheeler: L [uH] = 0.8 a^2 N^2 / (6a + 9b + 10c), lengths in inches."""
    depth = bobbin.wire_od_m * layers(bobbin, turns)
    radius = math.sqrt(mean_turn_area_m2(bobbin, turns) / math.pi) / INCH
    return (0.8 * radius**2 * turns**2
            / (6 * radius + 9 * bobbin.width_m / INCH + 10 * depth / INCH)) * 1e-6


def turns_for(function, bobbin: Bobbin, target: float, limit: int = 10_000) -> int:
    """The turn count whose `function(bobbin, turns)` is closest to target."""
    return min(range(1, limit), key=lambda turns: abs(function(bobbin, turns) - target))
