# Project instructions

This repository develops one proton magnetometer design. Do not add automated search, mutation, candidate ranking, or agent-driven research loops to `main`.

## Sources of truth

- Active receiver artifacts: `receiver_design/`
- Active coil assumptions: `verification_modeling/coil.py`
- Physics constants and signal model: `verification_modeling/physics.py`
- Bench acceptance work: `docs/verification-plan.md`

Keep analysis modules independent of the active design where possible. Pass values into reusable functions rather than importing design files into EDA adapters. Keep ngspice and circuit serialization under `verification_modeling.eda`; do not couple them to KiCad or LTspice GUI automation.

Run `make test` for analysis changes, `make firmware` for estimator changes, and `make eda` for receiver artifact changes. A clean DRC report proves rule compliance and connectivity only. It does not prove that the receiver is complete or works in hardware.

The `.pi/skills/` files are the shared skill source. `.claude/skills/` and `.codex/skills/` contain relative symlinks. Do not duplicate skill content.

Available project skills:

- `external-review` runs read-only software, scientific, or full design-verification reviews with Cursor CLI.
- `kicad` covers board validation, rendering, routing, and fabrication export.
- `ltspice` covers LTspice simulation, validation, GUI automation, and screenshots.
