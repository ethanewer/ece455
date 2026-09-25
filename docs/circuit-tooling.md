# Circuit-design tooling

The receiver workflow uses Python, ngspice, and KiCad. LTspice is not part of the active toolchain.

## One-command outputs

From the repository root:

```sh
make figures   # transient CSV/PNG and AC-response CSV/PNG
make kicad     # regenerate connectivity and run every available KiCad CLI check
make pcb       # require a physical PCB and a zero-violation DRC result
make eda       # figures, KiCad generation/checks, connectivity, AC, and noise
make export    # timestamped engineering report under local/export-YYYYMMDD-HHMMSS
```

`make pcb` intentionally fails until `receiver_design/kicad/receiver.kicad_pcb` exists. This prevents a connectivity netlist from being mistaken for a physical design.

Uncommitted pipeline output belongs under `local/`. SKiDL runtime files go to `local/skidl/`, and KiCad ERC and DRC reports go to `local/kicad/`. Git keeps the `local/` directory but ignores its contents. Committed analysis CSV and PNG files remain under `receiver_design/analysis/` because they are review artifacts, not scratch output.

`make export` runs connectivity and ngspice checks against the current files, then creates a new timestamped directory. The package shares one construction schematic, one BOM, the canonical SPICE deck, and the connectivity netlist. It also writes `1.7kHz/` and `2.1kHz/`, one directory per receiver-input test frequency. Each directory contains a SPICE deck with the same receiver and a different external test frequency, transient and frequency-response CSV/PNG pairs, and an analysis summary. If a PCB exists, the command first requires strict DRC, then includes the `.kicad_pcb` source, a routed-copper SVG, and a KiCad 3D PNG. Until a board exists, it writes `PCB-NOT-AVAILABLE.txt` rather than fabricating an image.

## Simulation architecture

`receiver_design/spice/receiver.cir` is the active circuit model. `receiver_design/analyze.py` invokes the reusable `verification_modeling.eda.report` adapter. The adapter:

1. removes top-level analysis cards from a supplied netlist without changing the circuit;
2. runs a nominal transient analysis and an AC sweep in a temporary directory;
3. exports plain CSV data;
4. renders reviewable PNG figures with Matplotlib; and
5. writes a Markdown summary with calculated gain and waveform amplitudes.

Generated receiver outputs live in `receiver_design/analysis/`:

- `receiver-waveforms.csv` and `.png`
- `receiver-frequency-response.csv` and `.png`
- `README.md`

The plotting adapter accepts paths and node names as arguments and does not import the active receiver design. It contains no component search, value mutation, or candidate ranking.

## KiCad architecture

`receiver_design/kicad/generate.py` remains the fixed-topology Python connectivity source. It emits `receiver.net`. `receiver_design/kicad/validate.py` regenerates that artifact and then uses `kicad-cli` for ERC and DRC whenever graphical schematic and PCB files are present.

The next physical-design step is to add a deterministic generator for `receiver.kicad_sch` and `receiver.kicad_pcb`, or to create those files once in KiCad and maintain them as reviewed source artifacts. In either case, the automated acceptance path is already fixed:

1. regenerate connectivity;
2. compare safety-critical nets in `receiver_design/verify.py`;
3. run schematic ERC;
4. run PCB DRC with `--severity-all --exit-code-violations`;
5. require zero violations and zero unconnected pads before fabrication export.

A passing SPICE analysis or connectivity check is not evidence that a PCB exists or is fabrication-ready.
