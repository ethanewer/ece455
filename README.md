# ECE 455 proton magnetometer

This branch tracks one receiver design. It does not contain an automated design search or auto-research loop.

## Repository layout

- `receiver_design/` contains the active LTspice and KiCad files. Edit these files when changing the receiver.
- `verification_modeling/` contains reusable physics, noise, CRB, coil, circuit-format, and ngspice code. These modules do not choose or optimize a design.
- `frequency_estimator_firmware/` contains the portable C frequency estimator and its pinned host-test vectors.
- `tests/` checks units, transducer assumptions, noise generation, CRB mathematics, the active coil profile, circuit serialization, and ngspice parsing.
- `receiver_design/verify.py` runs ngspice and KiCad checks against the active design.
- `docs/verification-plan.md` lists the bench measurements needed to replace model assumptions.
- `.pi/skills/` holds shared Cursor review, KiCad, and LTspice instructions. Claude and Codex use symlinks to the same files.

Historical reports and weekly notes are under `docs/past_work/` and `docs/week_2/`. Supporting papers and links are under `docs/resources/`.

## Setup

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
```

Install external EDA tools separately when needed:

```sh
brew install ngspice
# KiCad and LTspice are macOS applications.
```

## Verification

```sh
make test       # Python tests
make firmware   # compile the C estimator and check pinned vectors
make eda        # ngspice check; KiCad DRC runs when kicad-cli is installed
make verify     # all of the above
```

Use `python3 receiver_design/verify.py --require-tools` when both ngspice and KiCad must be present. CI runs the Python, firmware, and ngspice checks. KiCad DRC remains a local gate because GitHub's standard runners do not include KiCad.

## Current design status

The coil profile and receiver files came from the `autoresearch` branch, but the search and scoring orchestration did not. The receiver simulation uses ideal gain blocks and conditional coil values. The routed KiCad board is a DRC-clean connectivity demonstration, not a fabrication-ready receiver. It lacks final active-device, switching, ADC, protection, power, and connector implementation. See `receiver_design/README.md` and `docs/verification-plan.md` before making hardware claims.
