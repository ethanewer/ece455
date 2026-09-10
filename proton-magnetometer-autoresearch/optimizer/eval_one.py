"""A7: single-candidate evaluator -- run one candidate in a subprocess.

The scoring fan-out spawns one of these per candidate with a per-candidate
timeout; a non-converging SPICE candidate is a SCORED REJECTION (J = inf,
sim_status recorded), not a crash.

Usage:
    python3 optimizer/eval_one.py '<candidate-kwargs-json>' [--fast]

Prints one JSON line: {"J_nt": ..., "provenance": {...}, ...}
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "poc"))

import circuit_spec as cs  # noqa: E402


def provenance() -> dict:
    """Stamp git SHA + tool versions + seeds into every score card."""
    def git_sha():
        try:
            return subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                capture_output=True, text=True, timeout=5).stdout.strip()
        except Exception:
            return "unknown"

    def ngspice_version():
        try:
            out = subprocess.run(["ngspice", "--version"], capture_output=True,
                                 text=True, timeout=5)
            for line in (out.stdout + out.stderr).splitlines():
                if "ngspice" in line.lower():
                    return line.strip().split()[1]
        except Exception:
            return "unknown"
        return "unknown"

    return {
        "git_sha": git_sha(),
        "ngspice": ngspice_version(),
        "python": sys.version.split()[0],
        "numpy": __import__("numpy").__version__,
        "mc_seeds": "phase=20000+i, record rng=7 (zoom), N_MC=%d" % cs.N_MC,
    }


def main() -> int:
    kwargs = json.loads(sys.argv[1])
    fast = "--fast" in sys.argv
    if fast:
        cs.N_MC = 40          # search-time MC; survivors get full scoring

    from backends.kicad import build_circuit  # noqa: F401 (env init only)
    from spec import ir as spec_ir

    spec = cs.afe_spec(**kwargs)
    spec_ir.validate(spec)                       # A1 contract: reject invalid
    netlist = cs.emit_netlist(spec)
    spec_hash = hashlib.sha256(netlist.encode()).hexdigest()[:16]

    from backends.spice import run_ngspice_status
    proc, _ = run_ngspice_status(netlist, timeout_s=240)
    card = {
        "spec_title": kwargs.get("label", "candidate"),
        "kwargs": kwargs,
        "spec_hash": spec_hash,
        "sim_status": proc.returncode,
        "provenance": provenance(),
    }
    if proc.returncode != 0:
        # scored rejection: non-converging/timeout candidate
        card.update(J_nt=float("inf"), sim_stderr=proc.stderr[-500:])
        print(json.dumps(card))
        return 0
    tabs = cs.parse_tables(proc.stdout)
    sim = cs.simulate_from_tabs(spec, tabs)
    result = cs.score_at(sim, spec)
    keep = {k: result[k] for k in result
            if k not in ("tabs",)}
    card.update(keep)
    card["J_nt"] = result["J_nt"]
    print(json.dumps(card))
    return 0


if __name__ == "__main__":
    sys.exit(main())
