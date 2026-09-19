# Project instructions

This repository develops one proton magnetometer design. Do not add automated search, mutation, candidate ranking, or agent-driven research loops to `main`.

Delete obsolete tracked files instead of retaining them as historical context. Git history preserves prior versions, while files left in the working tree consume future agents' context and can be mistaken for active artifacts.

Put uncommitted logs, scratch files, renders, reports, build products, and other pipeline output under `local/`, grouped in task-specific subdirectories. Do not write pipeline output at the repository root. Git tracks `local/.gitkeep` and ignores the rest of `local/`. Keep intentional, reviewable generated artifacts in their documented committed locations.

## Sources of truth

- Active receiver artifacts: `receiver_design/`
- Active coil assumptions: `verification_modeling/coil.py`
- Physics constants and signal model: `verification_modeling/physics.py`
- Bench acceptance work: `docs/verification-plan.md`

Keep analysis modules independent of the active design where possible. Pass values into reusable functions rather than importing design files into EDA adapters. Keep ngspice and circuit serialization under `verification_modeling.eda`; do not couple them to KiCad or LTspice GUI automation.

Run `make test` for analysis changes, `make firmware` for estimator changes, and `make eda` for receiver artifact changes. Run `make verify` when a change spans these areas. A clean DRC report proves rule compliance and connectivity only. It does not prove that the receiver is complete or works in hardware.

## Receiver workflow

- The active simulator is ngspice. `receiver_design/spice/receiver.cir` is the circuit source. Do not restore the retired LTspice files as active artifacts.
- `receiver_design/kicad/generate.py` defines fixed-topology connectivity. It generates `receiver.net`; do not hand-edit the netlist.
- `receiver_design/analyze.py` generates the committed CSV, PNG, and Markdown files in `receiver_design/analysis/`. Regenerate them after changing the SPICE model or report adapter.
- `make export` tests the active receiver and creates a timestamped review package under `local/`. Never create PCB images when the physical board is absent; the export must record that status explicitly.
- There is no accepted graphical schematic or PCB yet. `make pcb` must fail until `receiver.kicad_pcb` exists and passes strict DRC.
- Before creating the PCB footprint or adapter layout, verify the exact purchased HiLetgo ADS1256 module header order and dimensions. Logical connector numbering is not physical pinout evidence.
- Keep generated text deterministic. Remove timestamps, working-directory-dependent paths, CRLF endings, and trailing whitespace in generators rather than patching generated files.

The `.pi/skills/` files are the shared skill source. `.claude/skills/` and `.codex/skills/` contain relative symlinks. Do not duplicate skill content.

Available project skills:

- `external-review` runs read-only software, scientific, or full design-verification reviews with Cursor CLI.
- `kicad` covers schematic and board validation, rendering, routing, and fabrication export.
