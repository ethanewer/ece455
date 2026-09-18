"""Tool-independent circuit data and ngspice process adapters."""

from .circuit import IRError, from_json, to_json, validate
from .ngspice import emit_netlist, parse_tables, run_ngspice, run_ngspice_status

__all__ = [
    "IRError",
    "emit_netlist",
    "from_json",
    "parse_tables",
    "run_ngspice",
    "run_ngspice_status",
    "to_json",
    "validate",
]
