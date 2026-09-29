"""Tool-independent circuit data and ngspice process adapters."""

from .circuit import IRError, from_json, to_json, validate
from .ngspice import emit_netlist, parse_tables, run_ngspice, run_ngspice_status
from .report import (
    NoiseResult,
    ReportResult,
    build_spice_report,
    measure_gain,
    measure_input_impedance,
    measure_node_gains,
    measure_noise,
    measure_operating_point,
)

__all__ = [
    "IRError",
    "NoiseResult",
    "ReportResult",
    "build_spice_report",
    "emit_netlist",
    "measure_gain",
    "measure_input_impedance",
    "measure_node_gains",
    "measure_operating_point",
    "measure_noise",
    "from_json",
    "parse_tables",
    "run_ngspice",
    "run_ngspice_status",
    "to_json",
    "validate",
]
