# ECE 455 proton magnetometer

This repository tracks one receiver design. It does not contain automated design search, mutation, candidate ranking, or research loops.

## Repository layout

- `receiver_design/` contains the active ngspice model, generated analysis outputs, KiCad connectivity source, BOM, and design documentation.
- `amazon_purchases.json` lists everything to buy for the receiver, with Amazon links, prices, and the budget. `new_allowed_components.json` lists the lab inventory and the already purchased modules.
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

The active receiver is a purchased AD8421 instrumentation-amplifier module (gain 100) followed by a two-section RC anti-aliasing filter. It sits between J1 and the already purchased HiLetgo ADS1256, with the XIAO RP2350 wired directly to the ADC's SPI. The module, its cable, and two 9 V batteries cost $48.95 from Amazon (`amazon_purchases.json`), or $86.62 with a recommended spare module and clip-on ferrites; the clamps, gain resistor, and filter are seven lab parts. Its requirements live in `receiver_design/requirements.py`: |Z_in| of at least 1 MΩ across 1.5–2.5 kHz, input noise of at most 5 nV/√Hz with the coil including ADC noise, no clipping for 10 mV interference tones at 50–400 Hz or 2 mV at 8–50 kHz, and at least 90 dB of alias rejection near the ADS1256's 1.92 MHz modulator rate. `make verify` simulates them at ten temperature, supply, battery, trim, and tolerance corners and fails if any is missed. Input impedance, noise, interference tolerance, and alias rejection remain to be measured on hardware.

There is not yet a reviewed graphical KiCad schematic or physical PCB. `make pcb` therefore fails intentionally. A connectivity netlist and simulated figures do not establish fabrication readiness or measured hardware performance. See `receiver_design/README.md` and `docs/verification-plan.md`.
