"""Tool-independent circuit data and ngspice process adapters."""

from .circuit import IRError, from_json, to_json, validate
from .ngspice import emit_netlist, parse_tables, run_ngspice, run_ngspice_status
from .report import ReportResult, build_spice_report

__all__ = [
    "IRError",
    "ReportResult",
    "build_spice_report",
    "emit_netlist",
    "from_json",
    "parse_tables",
    "run_ngspice",
    "run_ngspice_status",
    "to_json",
    "validate",
]
