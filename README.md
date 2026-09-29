# ECE 455 proton magnetometer

This repository tracks one receiver design. It does not contain automated design search, mutation, candidate ranking, or research loops.

## Repository layout

- `receiver_design/` contains the active ngspice model, generated analysis outputs, KiCad connectivity source, BOM, and design documentation.
- `verification_modeling/` contains reusable physics, coil, CRB, circuit, ngspice, and plotting adapters. These modules do not select or optimize a design.
- `frequency_estimator_firmware/` contains the portable C frequency estimator and host tests.
- `tests/` checks physics, coil assumptions, circuit serialization, ngspice parsing, and report generation.
- `docs/circuit-tooling.md` documents the Python/ngspice/KiCad workflow.
- `docs/verification-plan.md` lists bench measurements needed to replace model assumptions.

## Setup

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
brew install ngspice
```

Install KiCad separately for schematic, PCB, ERC, DRC, rendering, and fabrication exports. LTspice is not part of the active workflow.

## Commands

```sh
make test       # Python tests
make firmware   # compile and test the portable estimator
make figures    # regenerate transient and frequency-response CSV/PNG outputs
make kicad      # regenerate connectivity and run available KiCad CLI checks
make pcb        # require a physical PCB and passing DRC
make eda        # figures, connectivity, and the hard receiver requirement checks
make verify     # all applicable tests and EDA checks
```

## Current status

The active receiver is a minimal discrete low-noise band-pass amplifier: 30 Thomson kit parts between J1 and the already purchased HiLetgo ADS1256, with the XIAO RP2350 wired directly to the ADC's SPI. Its requirements live in `receiver_design/requirements.py`: at least 2000 V/V from J1 to the ADC across 1.6–2.2 kHz, |Z_in| of at least 1 MΩ across 1.5–2.5 kHz, and input noise of at most 5 nV/√Hz with the coil. `make verify` simulates them at nine beta, temperature, and USB-voltage corners and fails if any is missed. Allowed parts, including the two modules, are listed in `new_allowed_components.json`. Gain, input impedance, and noise remain to be measured on hardware.

There is not yet a reviewed graphical KiCad schematic or physical PCB. `make pcb` therefore fails intentionally. A connectivity netlist and simulated figures do not establish fabrication readiness or measured hardware performance. See `receiver_design/README.md` and `docs/verification-plan.md`.
