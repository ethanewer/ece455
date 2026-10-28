# Utilities

Python tools that read the design files, simulate, lay out, and test them. Run from the repository root.

| Module | Purpose |
|---|---|
| `design.py` | The one place that knows where the design files are, the roles of the LTspice parts, and how the drawing's nodes map to board nets |
| `kicad.py` | Parses KiCad schematics, boards, and BOM exports into parts and nets, without kicad-cli |
| `ltspice.py` | Parses an LTspice `.asc` drawing into a netlist and writes an ngspice deck, including an equivalent of LTspice's UniversalOpAmp2 |
| `xlsx.py` | Reads cell values from an `.xlsx` workbook |
| `spice.py` | Runs ngspice operating-point, AC, noise, and transient analyses |
| `physics.py`, `crb.py` | Proton precession constants, the FID model, and the frequency Cramér–Rao bound |
| `simulate.py` | `make sim`: writes `docs/simulation/` from the LTspice drawing, the tuning bank, and the firmware's ADC settings |
| `breadboard.py` | `make breadboard`: checks the fixed breadboard layout against the LTspice netlist and board nets, then writes `docs/breadboard/` |
| `firmware.py`, `firmware_host/` | Compile the Pico firmware on the host with stub SDK headers and run its estimator |
| `tests/` | `make test` |

The readers (`kicad`, `ltspice`, `xlsx`, `spice`) take paths and values and know nothing about this design. `tests/fixtures/` holds a frozen copy of the LTspice drawing with LTspice 17.2.4's results for it, so the translation is tested against LTspice even after the live drawing changes.
