"""A7: score-guided mutation search over the AFE candidate space.

Run-hygiene requirements (TODO A7), all implemented here:
  * per-candidate timeout + graceful SPICE failure handling: each
    candidate runs in its own subprocess (optimizer/eval_one.py) with a
    wall-clock timeout; a non-converging candidate is a SCORED REJECTION
    (J = inf, sim_status recorded), never a crash of the search;
  * provenance: every score card carries git SHA, tool versions, seeds,
    and the full spec hash (eval_one.provenance);
  * topology-hash dedupe: candidates are keyed by the sha256 of their
    emitted netlist, so a mutation cannot rescore the same circuit;
  * elite archive persisted between runs (JSON in optimizer/runs/).

NO agent/LLM in the loop: score-guided search only.

Usage:
    python3 optimizer/search.py --gens 3 --pop 6 --workers 4
"""
import argparse
import concurrent.futures
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ARCHIVE = ROOT / "optimizer" / "runs" / "elite.json"
PER_CANDIDATE_TIMEOUT_S = 300


def netlist_hash(kwargs: dict) -> str:
    sys.path.insert(0, str(ROOT / "poc"))
    import circuit_spec as cs
    netlist = cs.emit_netlist(cs.afe_spec(**kwargs))
    return hashlib.sha256(netlist.encode()).hexdigest()[:16]


def evaluate(kwargs: dict, fast: bool = True) -> dict:
    """One candidate in a subprocess; returns its score card."""
    args = [sys.executable, str(ROOT / "optimizer" / "eval_one.py"),
            json.dumps(kwargs)] + (["--fast"] if fast else [])
    try:
        proc = subprocess.run(args, capture_output=True, text=True,
                              timeout=PER_CANDIDATE_TIMEOUT_S, cwd=str(ROOT))
    except subprocess.TimeoutExpired:
        return {"spec_title": kwargs.get("label", "?"),
                "kwargs": kwargs, "J_nt": float("inf"),
                "sim_status": "timeout", "spec_hash": "n/a"}
    if proc.returncode != 0:
        # crash inside the evaluator = scored rejection too
        return {"spec_title": kwargs.get("label", "?"),
                "kwargs": kwargs, "J_nt": float("inf"),
                "sim_status": "evaluator_error", "spec_hash": "n/a",
                "stderr": proc.stderr[-300:]}
    line = [l for l in proc.stdout.splitlines() if l.startswith("{")]
    if not line:
        return {"spec_title": kwargs.get("label", "?"),
                "kwargs": kwargs, "J_nt": float("inf"),
                "sim_status": "no_output", "spec_hash": "n/a"}
    return json.loads(line[-1])


def load_archive() -> list:
    if ARCHIVE.exists():
        return json.loads(ARCHIVE.read_text())
    return []


def save_archive(cards: list) -> None:
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVE.write_text(json.dumps(cards, indent=1))


def run(generations: int, pop: int, workers: int) -> list:
    from optimizer.mutations import base_candidates, mutate
    import numpy as np

    rng = np.random.default_rng(2026)
    archive = load_archive()
    seen = {c.get("spec_hash") for c in archive if c.get("spec_hash")}
    if not archive:
        archive = [evaluate(k) for k in base_candidates()]
        for c in archive:
            seen.add(c.get("spec_hash"))
        save_archive(archive)
        print("seed archive:", [(c["spec_title"],
                                 None if c["J_nt"] == float("inf")
                                 else round(c["J_nt"], 4)) for c in archive])

    t0 = time.time()
    for gen in range(generations):
        parents = sorted([c for c in archive if c["J_nt"] != float("inf")],
                         key=lambda c: c["J_nt"])
        if not parents:
            parents = archive[:1]
        # propose pop mutants from the current elites
        mutants = []
        attempts = 0
        while len(mutants) < pop and attempts < pop * 4:
            attempts += 1
            parent = parents[int(rng.integers(min(len(parents), 3)))]["kwargs"]
            child = mutate(parent, rng)
            try:
                h = netlist_hash(child)
            except Exception:
                continue
            if h in seen:
                continue                      # dedupe: no rescoring
            seen.add(h)
            mutants.append(child)
        # fan out with a subprocess pool
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            cards = list(ex.map(lambda kw: evaluate(kw), mutants))
        archive.extend(cards)
        # survivor promotion: keep the top-K distinct-hashed elites
        scored = [c for c in archive if c["J_nt"] != float("inf")]
        scored.sort(key=lambda c: c["J_nt"])
        archive = scored[:12] + [c for c in archive
                                 if c["J_nt"] == float("inf")][-4:]
        save_archive(archive)
        best = scored[0] if scored else None
        print(f"gen {gen}: scored {sum(1 for c in cards if c['J_nt'] != float('inf'))}/{len(cards)}"
              + (f", best J = {best['J_nt']:.4f} nT ({best['spec_title']})"
                 if best else ", all rejected")
              + f" [{time.time()-t0:.0f}s]")
    return archive


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gens", type=int, default=2)
    ap.add_argument("--pop", type=int, default=6)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    arch = run(args.gens, args.pop, args.workers)
    best = min((c for c in arch if c["J_nt"] != float("inf")),
               key=lambda c: c["J_nt"], default=None)
    if best:
        print("best candidate:", best["spec_title"], "J =",
              round(best["J_nt"], 4), "nT")
