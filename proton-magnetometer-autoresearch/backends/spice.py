"""A2: SPICE backend -- circuit IR -> ngspice netlist -> run -> parse.

Ported from the poc demo (poc/circuit_spec.py) so the optimizer and the
docs backends share one implementation:

  * emit_netlist: the JSON-able component/net graph -> ngspice batch
    netlist (including the pagination-tolerant `print`-table convention);
  * run_ngspice / run_ngspice_status: batch subprocess execution; the
    _status variant never raises on failure -- a non-converging candidate
    is a scored rejection (returncode + stderr), not a crash (A7's
    sim_status requirement);
  * parse_tables: the pagination-tolerant table parser (repeated headers
    are page breaks; `---` rules, node listings, and ngspice wall-clock
    timestamps are skipped; rows carry trailing tabs; the tran axis uses
    `time` where ac/noise use `frequency`).

Unit-tested against the committed golden netlist + stdout fixture in
tests/test_ngspice_layer.py.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

import numpy as np

WORKDIR = Path("/tmp/poc_circuits")


def emit_netlist(spec: dict) -> str:
    """Circuit IR -> ngspice batch netlist text."""
    lines = [spec["title"]]
    for c in spec["components"]:
        lines.append(f"{c['name']} {' '.join(c['nodes'])} {c['value']}")
    lines.append(".control")
    lines += spec.get("control", [])
    lines.append(".endc")
    lines.append(".end")
    return "\n".join(lines) + "\n"


def run_ngspice(netlist: str, workdir: Path = Path("/tmp/poc_circuits"),
                timeout_s: float = 300.0) -> str:
    """Run ngspice in batch mode; raise RuntimeError on failure."""
    proc, _ = run_ngspice_status(netlist, workdir=workdir,
                                 timeout_s=timeout_s)
    if proc.returncode != 0:
        raise RuntimeError("ngspice failed:\n%s\n%s"
                           % (proc.stdout[-2000:], proc.stderr[-2000:]))
    return proc.stdout


def run_ngspice_status(netlist: str,
                       workdir: Path = Path("/tmp/poc_circuits"),
                       timeout_s: float = 300.0):
    """Batch ngspice without raising. Returns (CompletedProcess, circuit
    path). A non-zero returncode (non-convergence, syntax error, timeout)
    is data for the scorer, not an exception.

    Each call gets a UNIQUE circuit file (E3 audit finding 10: parallel
    scoring workers sharing one candidate.cir clobbered each other's
    netlists, producing cards whose results didn't match their specs)."""
    workdir.mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha256(netlist.encode()).hexdigest()[:16]
    nl = workdir / f"candidate_{os.getpid()}_{tag}.cir"
    nl.write_text(netlist)
    try:
        proc = subprocess.run(["ngspice", "-b", str(nl)], capture_output=True,
                              text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(["ngspice"], returncode=124,
                                           stdout="", stderr="timeout"), nl
    return proc, nl


def parse_tables(stdout: str) -> dict:
    """Parse the (index, x, y) tables emitted by `print` in order of
    appearance: ac vm(adc), noise inoise_spectrum, tran v(adc).

    ngspice paginates long `print` tables, re-emitting the header every 50
    rows -- a repeated header with the SAME variable is a page break (keep
    appending); only a name change starts a new table. Separators
    (`---` rules), node listings, and "Doing analysis" banners are not
    rows; only well-formed (index, x, y) numeric rows are appended. The
    ngspice wall-clock timestamp lines never reach the tables, so parsed
    output is deterministic (D11)."""
    tables, current = {}, None
    for line in stdout.splitlines():
        m = re.match(r"\s*Index\s+(?:frequency|time)\s+(\S+)", line)
        if m:
            current = m.group(1)
            if current not in tables:
                tables[current] = []
            continue
        if current is not None:
            cols = line.replace("\t", " ").split()   # rows carry a trailing tab
            if len(cols) >= 3:
                try:
                    tables[current].append((float(cols[1]), float(cols[2])))
                except ValueError:
                    pass
    out = {k: (np.array([p[0] for p in v]), np.array([p[1] for p in v]))
           for k, v in tables.items()}
    m_tot = re.search(r"inoise_total\s*=\s*([0-9.eE+-]+)", stdout)
    out["inoise_total"] = float(m_tot.group(1)) if m_tot else None
    return out
