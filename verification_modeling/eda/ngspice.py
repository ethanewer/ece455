"""Small ngspice adapter for emitting, running, and parsing netlists.

The adapter is independent of the active receiver design:

  * emit_netlist: the JSON-able component/net graph -> ngspice batch
    netlist (including the pagination-tolerant `print`-table convention);
  * run_ngspice / run_ngspice_status: batch subprocess execution; the
    _status variant returns process status without raising;
  * parse_tables: the pagination-tolerant table parser (repeated headers
    are page breaks; `---` rules, node listings, and ngspice wall-clock
    timestamps are skipped; rows carry trailing tabs; the tran axis uses
    `time` where ac/noise use `frequency`).

Unit-tested against the committed stdout fixture in tests/test_eda.py.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

import numpy as np

WORKDIR = Path("/tmp/ece455-ngspice")


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


def run_ngspice(netlist: str, workdir: Path = WORKDIR,
                timeout_s: float = 300.0) -> str:
    """Run ngspice in batch mode; raise RuntimeError on failure."""
    proc, _ = run_ngspice_status(netlist, workdir=workdir,
                                 timeout_s=timeout_s)
    if proc.returncode != 0:
        raise RuntimeError("ngspice failed:\n%s\n%s"
                           % (proc.stdout[-2000:], proc.stderr[-2000:]))
    return proc.stdout


def run_ngspice_status(netlist: str,
                       workdir: Path = WORKDIR,
                       timeout_s: float = 300.0):
    """Batch ngspice without raising. Returns (CompletedProcess, path).

    Each call gets a unique circuit file so independent analyses cannot
    overwrite one another."""
    workdir.mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha256(netlist.encode()).hexdigest()[:16]
    nl = workdir / f"analysis_{os.getpid()}_{tag}.cir"
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
        m = re.match(r"\s*Index\s+(?:frequency\s+|time\s+)?(\S+)", line)
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
            elif len(cols) == 2 and current:
                # 2-column rows: `linearize`'d tran tables print
                # (index, value) with the sample grid implicit
                try:
                    tables[current].append((float(cols[0]), float(cols[1])))
                except ValueError:
                    pass
    out = {k: (np.array([p[0] for p in v]), np.array([p[1] for p in v]))
           for k, v in tables.items()}
    m_tot = re.search(r"inoise_total\s*=\s*([0-9.eE+-]+)", stdout)
    out["inoise_total"] = float(m_tot.group(1)) if m_tot else None
    return out
