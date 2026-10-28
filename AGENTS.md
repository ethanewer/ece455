# Project instructions

This repository develops one proton magnetometer design. Do not add automated search, mutation, candidate ranking, or agent-driven research loops to `main`.

Delete obsolete tracked files instead of retaining them as historical context. Git history preserves prior versions, while files left in the working tree consume future agents' context and can be mistaken for active artifacts.

Put uncommitted logs, scratch files, renders, reports, build products, and other pipeline output under `local/`, grouped in task-specific subdirectories. Do not write pipeline output at the repository root. Git tracks `local/.gitkeep` and ignores the rest of `local/`. Keep intentional, reviewable generated artifacts in their documented committed locations.

## Layout and sources of truth

Each design-file type has one top-level folder. These files are the design; edit them with their own tools, not by script:

- `kicad/`: polarization board and signal-processing & control board (KiCad 10), with Gerbers and the signal board's BOM export
- `ltspice/AmplificationSim.asc`: coil, tuning tank, and the off-board amplifier
- `firmware/`: Pico 2 firmware, a copy of `hjvania10-rgb/PicoProgramECE455` (the commit is in `firmware/README.md`)
- `spreadsheets/CoilDesign.xlsx`: planned coil windings and polarizing field; `spreadsheets/TuningCapacitors.xlsx`: measured coil inductances and LC tuning
- `3d_models/`: coil forms (SolidWorks parts and the sliced print files `util/printfile.py` measures)

Everything that reads, simulates, lays out, or tests them lives in `util/`. `docs/design.md` describes the design and its open issues; `docs/verification-plan.md` holds the bench work.

## Utilities

- `util/design.py` is the only module that knows file locations, LTspice part roles, and how drawing nodes map to board nets. The readers (`kicad.py`, `ltspice.py`, `xlsx.py`, `printfile.py`, `spice.py`) take paths and values and must stay independent of this design.
- Simulate from the LTspice drawing through `util/ltspice.py`. Do not hand-copy its netlist into a parallel deck. If the drawing uses a new symbol or model, extend the translator and its tests.
- `util/breadboard.py` holds one fixed layout for the off-board amplifier. Keep it data, not a placer, and keep `check_layout` reproducing the LTspice netlist and the board nets.
- The firmware must keep compiling unchanged against `util/firmware_host/`. Do not edit firmware to suit the tests. When syncing from the upstream repository, record the commit in `firmware/README.md`, copy only the active files, and keep the local changes listed there.
- `make pico` and `make flash` build and flash the Pico; build output goes to `local/firmware-build/`.
- `make sim` and `make breadboard` regenerate `docs/simulation/` and `docs/breadboard/`. Regenerate them after changing the drawing, the boards, the layout, or the generators. Keep generated text deterministic: no timestamps, absolute paths, or trailing whitespace.

Run `make test` for any change, `make firmware` for estimator changes, and `make verify` when a change touches the design files or the generators. Tests that parse KiCad files check connectivity only. They are not KiCad ERC or DRC, and none of this proves the hardware works.

## Hardware cautions

- Before relying on J3 and J4, verify the purchased HiLetgo ADS1256 module's header order and spacing on the module. Logical connector numbering is not physical pinout evidence.
- No op-amp part is chosen. Check the breadboard's assumed DIP-8 pinout against the chosen part.

The `.pi/skills/` files are the shared skill source. `.claude/skills/` and `.codex/skills/` contain relative symlinks. Do not duplicate skill content.

Available project skills:

- `external-review` runs read-only software, scientific, or full design-verification reviews with Cursor CLI.
- `kicad` covers schematic and board validation, rendering, routing, and fabrication export.
