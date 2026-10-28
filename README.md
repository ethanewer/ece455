# ECE 455 proton magnetometer

One proton precession magnetometer design: a polarization board, a signal-processing and control board with a Raspberry Pi Pico 2 and an ADS1256 ADC, an off-board two-stage amplifier, the sensing and polarizing coils, and the Pico firmware. [`docs/design.md`](docs/design.md) describes how they fit together and lists open issues.

## Layout

Design files, one folder per type:

| Folder | Contents | Edit with |
|---|---|---|
| [`kicad/`](kicad/) | Polarization board and signal-processing & control board: schematics, PCBs, Gerbers, BOM | KiCad 10 |
| [`ltspice/`](ltspice/) | `AmplificationSim.asc`: coil, tuning tank, and the off-board amplifier | LTspice |
| [`firmware/`](firmware/) | Pico 2 ADS1256 capture and frequency firmware, and its serial plotter | Pico SDK 2.3.1 |
| [`spreadsheets/`](spreadsheets/) | `TuningCapacitors.xlsx`: coil inductances and LC tuning | Excel |
| [`3d_models/`](3d_models/) | Sensing coil V1 and polarizing coil V2: SolidWorks parts and print files | SolidWorks |

Everything else:

- [`util/`](util/) reads those files and holds the simulation, breadboard layout, firmware host harness, and tests.
- [`docs/`](docs/) has the design description, the verification plan, generated simulation and breadboard reports, datasheets, and references.
- `local/` is for uncommitted output.

## Setup

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
brew install ngspice        # or: sudo apt-get install ngspice
```

`make firmware` and `make test` compile the firmware on the host with `$CC`, or clang or gcc.

## Commands

```sh
make test         # all tests: board/schematic/BOM/firmware consistency, LTspice translation, breadboard, estimator
make firmware     # only the firmware estimator tests
make sim          # simulate ltspice/AmplificationSim.asc and regenerate docs/simulation/
make breadboard   # check the breadboard layout and regenerate docs/breadboard/
make verify       # test, sim, and breadboard
```

## Status

Both PCBs match their schematics, and the firmware's SPI pins match the ADS1256 header on J3. The amplifier exists only as an LTspice drawing and a breadboard layout; no op amp has been chosen. Simulated with the drawing's 10 µV FID, the signal at the ADC is about three times the firmware's PGA 64 full scale. The firmware does not yet drive damping or polarization. Nothing here has been measured on hardware; see [`docs/verification-plan.md`](docs/verification-plan.md).
