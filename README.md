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
make eda        # figures, KiCad generation/checks, connectivity, AC, and noise
make verify     # all applicable tests and EDA checks
```

## Current status

The active receiver uses lab passives, 1N4148 diodes, and 2N3904 transistors around the already purchased HiLetgo ADS1256 and XIAO RP2350 modules. The ADS1256 internal buffer and PGA are the first active analog stage. The passive input protection, 200 ms sample-discard interval, selectable SPI logic voltage, and USB power path are defined. Its reduced sensitivity remains to be measured; the ngspice analog model omits converter noise and digital filtering.

There is not yet a reviewed graphical KiCad schematic or physical PCB. `make pcb` therefore fails intentionally. A connectivity netlist and simulated figures do not establish fabrication readiness or measured hardware performance. See `receiver_design/README.md` and `docs/verification-plan.md`.
