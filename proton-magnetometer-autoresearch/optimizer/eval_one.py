"""A7: single-candidate evaluator -- run one candidate in a subprocess.

The scoring fan-out spawns one of these per candidate with a per-candidate
timeout; a non-converging SPICE candidate is a SCORED REJECTION (J = inf,
sim_status recorded), not a crash.

The score comes from the single E2E evaluator (poc/evaluate.py,
REDESIGN.md): one candidate = one circuit + one C-core estimator variant +
one MCU config; J = worst-band sigma_B over the operating field range
(E3 audit finding 9), with provenance (git SHA, tool versions, seeds, spec
hash, firmware hash).

Usage:
    python3 optimizer/eval_one.py '<candidate-kwargs-json>' [--fast]

The candidate kwargs are poc/circuit_spec.afe_spec's (label, e_amp, i_amp,
coil, tuned, preamp_gain, mfb_scale, wire_d_mm, winding_len_m, estimator,
mcu).

Prints one JSON line: {"J_nt": ..., "provenance": {...}, ...}
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "poc"))

import circuit_spec as cs  # noqa: E402
import evaluate as ev  # noqa: E402


def main() -> int:
    kwargs = json.loads(sys.argv[1])
    n_mc = 40 if "--fast" in sys.argv else ev.N_MC  # search-time MC

    from backends.kicad import build_circuit  # noqa: F401 (env init only)
    from spec import ir as spec_ir

    spec = cs.afe_spec(**kwargs)
    spec_ir.validate(spec)                       # A1 contract: reject invalid

    from backends.spice import run_ngspice_status
    netlist = cs.emit_netlist(spec)
    proc, _ = run_ngspice_status(netlist, timeout_s=240)
    card = {
        "spec_title": kwargs.get("label", "candidate"),
        "kwargs": kwargs,
        "sim_status": proc.returncode,
    }
    if proc.returncode != 0:
        # scored rejection: non-converging/timeout candidate
        card.update(J_nt=float("inf"), spec_hash="n/a",
                    sim_stderr=proc.stderr[-500:])
        print(json.dumps(card))
        return 0
    tabs = cs.parse_tables(proc.stdout)
    sim = cs.simulate_from_tabs(spec, tabs)
    card.update(ev.evaluate_with_sim(spec, sim, n_mc=n_mc))
    print(json.dumps(card))
    return 0


if __name__ == "__main__":
    sys.exit(main())
