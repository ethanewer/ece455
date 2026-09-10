# Runbook — steps to start real auto-research runs

This is the operator's checklist for unlocking the optimizer (TODO G2).
Every "✅" item below is machine-checked in this tree; the gaps that
remain are human decisions (labeled per TODO.md's label scheme).

## 0. What is already standing (do not re-litigate)

| Layer | Status | Proof in-tree |
|---|---|---|
| Circuit IR (A1) | done | `spec/ir.py` — JSON-able graph, targeted validation errors |
| SPICE backend (A2) | done | `backends/spice.py` + pagination-tolerant parser, fixture-tested |
| Toolchain (A3) | done | KiCad 10.0.6 + skidl 2.3.0 pinned in `requirements.txt`/docs |
| KiCad gates (A4) | done | ERC + DRC exit 0 on an INA828-class AFE (`tests/test_kicad_gate.py`) |
| Fab/BOM + cards (A5/A6) | done | `backends/export.py` |
| Optimizer skeleton (A7) | done | `optimizer/` — subprocess pool, timeouts, dedupe, elite archive, provenance |
| Score completion (B1–B8) | done | tolerance sweep in `poc/`+SPICE layers, time-walk, rail ripple, 1/f+CMRR, parts DB, gain staging, B-sweep |
| Firmware core (C1–C4) | done | `firmware/core/freq_est.c` (float + fixed), golden vectors, sensitivity job, RP2040 emulator check |
| Verification (D1–D16) | done | `tests/` suite + CI (`.github/workflows/ci.yml`) |
| External reviews (E0–E6) | done | E6 records in TODO.md; triaged per E4 |

Run the standing suite before anything else:

```sh
pip install -r requirements.txt          # or: python3 -m venv .venv
python3 -m pytest tests/ -q              # full verification suite
make -C firmware/core test               # firmware: host tests + sensitivity gate
python3 tools/reproduce.py               # regenerate + diff every headline number
```

## 1. Remaining gates before GO (all human)

| Item | Decision | Input |
|---|---|---|
| **B7** | Decide whether survey productivity (cycle time vs tow speed) is a scored term or reported-only | The dead-time finding: 500 ms blanking costs only 1.22× in σ_B; a scored cycle-time term needs a survey requirement to score against |
| **C6** | Pick the MCU family + TCXO grade (±0.5 vs ±2 ppm) vs board budget | The ppm table (`run_scoring.py` §3c): ±20 ppm = 1.0 nT bias at 50 µT (eats the whole budget); ±0.5 ppm = 0.025 nT |
| **D6** | Accept the Curie-law transducer model as the interim V₀ anchor — or supply measured coil values | `fid.estimate_v0` (spin-1/2 law); the V₀×T2* grid in architecture.md §0 |
| **E5** | Read the E3 audit verdict and sign off | The audit runs `cursor-agent -p` per `.pi/skills/external-review/SKILL.md`; its record lands in TODO.md |
| **F1–F4** | Bench work (see `docs/experiments.md`) — the wet capture anchors V₀/T2*, the coil measurement anchors R/L/tuning | Acceptance criteria are the harness's predicted ranges |
| **G1** | Pick the search mode for real runs | Score-guided mutation search (A7, reproducible, no keys) vs LLM-proposed candidates (needs a Claude Code session; candidates still pass the identical scorer) |

**G2 (GO) requires**: A–D checked (they are), E3 with no unresolved
high-severity findings, F2 anchors the coil model, and D5's adversaries
still failing (they are; `tests/test_exploitability.py`).

## 2. Unlocking and running the first real search

Once G1/G2 are signed off:

1. **Flip the caveats** in README.md/architecture.md from "do not run a
   search agent against the PoC score" to the unlocked state, with the E7
   checkpoint cadence recorded (below).
2. **Dry run (no scoring budget)**:

   ```sh
   python3 optimizer/search.py --gens 2 --pop 4 --workers 4
   ```

   Watch: every candidate gets a `sim_status` (0 = converged; anything
   else is a scored rejection, never a crash), every card carries
   provenance (git SHA, tool versions, seeds, spec hash), and the elite
   archive persists in `optimizer/runs/elite.json`.
3. **Real run**:

   ```sh
   python3 optimizer/search.py --gens 20 --pop 12 --workers 6
   ```

   Budget: each fast candidate ≈ 6–10 s (ngspice + 40-record MC); full
   scoring of survivors runs with `--gens 0` style promotion via
   `optimizer/eval_one.py` WITHOUT `--fast`.
4. **Per-band families**: the B-sweep score is the worst case over
   25–65 µT (`circuit_spec.score_b_sweep`); run the per-band family
   (`band_candidates()` + `score_at`) before promoting a survivor.
5. **Human review**: survivors compile to candidate cards
   (`backends/export.py::candidate_card` — score table + SVG schematic)
   and fab packages (gerbers/drill/STEP/BOM with indicative costing).

## 3. Checkpoint cadence (E7)

After the optimizer starts, schedule the deep auto-research audit:
- after the first **50 scored candidates**, then
- every **order of magnitude** of candidate count (100, 1000, …).

Each checkpoint: run Review 3 from the external-review skill, triage per
E4 (verify each finding before acting), and confirm the elite archive's
top candidates are not exploiting a residual score blind spot. The D5
adversary suite runs in CI on every push as the standing canary.

## 4. Known limitations (state these with any result)

* The score is **conditional on the transducer model** until F1's wet
  capture replaces V₀ and T2* with measurements.
* SPICE sees white noise + the corrected tuned tank; 1/f and CMRR/PSRR
  are analytic terms (`poc/systematics.py`).
* Layout physics (EMI, grounding, pulse coupling) are NOT in the score —
  the KiCad leg checks ERC/DRC only.
* skidl 2.3.0's schematic router has a non-deterministic junction bug
  (documented in `backends/gate_cli.py`; the gate circuit omits one AA
  cap and retries).
