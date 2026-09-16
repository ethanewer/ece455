---
name: proton-autoresearch
description: Operate and update the proton-magnetometer auto-research pipeline, evaluate candidate receiver and firmware systems, and run bounded Cursor optimization-agent iterations. Use only for the proton-magnetometer-autoresearch project.
---

# Proton Autoresearch

Work from `/Users/ethanewer/ece455/proton-magnetometer-autoresearch`.

## Setup

Use Python 3.12 and the repository virtual environment when available:

```bash
cd /Users/ethanewer/ece455/proton-magnetometer-autoresearch
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
brew install ngspice
```

The C estimator also requires the local compiler and `make`. KiCad projection requires the setup in the `kicad` skill.

Before changing or running the optimizer, read:

- `README.md` for current status and commands;
- `docs/architecture.md` for the single-evaluator design;
- `docs/runbook.md` for optimizer gates;
- `docs/coil-design-week3.md` for measured facts, assumptions, and open characterization work.

## Preserve the verifier boundary

- The optimizer may change candidate circuit, estimator, MCU, and allowed design parameters.
- It must not change `pipeline/evaluate.py`, scoring gates, constants, test thresholds, or validation fixtures to improve a candidate score.
- Keep candidate generation and verification in separate code paths.
- Treat `hardware_characterized=False` as a production gate, not an optimization variable.
- A demonstration may evaluate a deep-copied in-memory spec with the characterization gate conditionally enabled, but it must report both the conditional simulated result and the production infinite score.

## Update a hardware design

1. Extract explicit dimensions, turns, resistance, inductance, topology, and drive conditions from the source document.
2. Record ambiguous connections and derived values as assumptions.
3. Update the active coil profile and its mapping document together.
4. Preserve legacy fixtures unless the task explicitly replaces them.
5. Add or update focused tests only when model behavior changed.
6. Run reviews only when verifier changes were made, following the `external-review` skill.

## Run the pipeline

Use the narrowest command that proves the intended behavior:

```bash
.venv/bin/python tools/run_working_demo.py
.venv/bin/python -m pytest tests/ -q
make -C firmware/core test
.venv/bin/python tools/reproduce.py
```

Do not run the whole suite repeatedly after an appropriate check passes unless another change invalidates it.

The optimizer skeleton runs with:

```bash
.venv/bin/python optimizer/search.py --gens 2 --pop 4 --workers 4
```

Use a Cursor model as the proposal agent only when requested. Read [references/cursor-optimization.md](references/cursor-optimization.md) for the bounded workflow.

## Report results

- Report the worst-band RMS field error and all gate outcomes.
- Distinguish simulated sensitivity, conditional sensitivity, production eligibility, and measured hardware performance.
- State the field sweep, Monte Carlo trial count, estimator, clock assumption, and coil state.
- Keep candidate files, LTspice/KiCad projections, and slide claims synchronized with the evaluated candidate.
- Never describe a simulated, passive-only, or uncharacterized proposal as a fully working magnetometer.
