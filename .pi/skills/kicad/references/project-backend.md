# Proton magnetometer KiCad backend

Use this reference only for `/Users/ethanewer/ece455/proton-magnetometer-autoresearch`.

## Relevant modules

- `backends/kicad.py`: circuit IR to SKiDL, schematic, PCB, ERC, and DRC.
- `backends/kicad_pcb_worker.py`: runs kinet2pcb with KiCad's bundled Python.
- `backends/export.py`: Gerber, drill, STEP, BOM, and candidate-card exports.

The backend expects:

- KiCad at `/Applications/KiCad.app`;
- symbol libraries under the KiCad application bundle;
- KiCad's bundled Python 3.9 for `pcbnew`;
- `kinet2pcb` importable from `/tmp/kicad_pylibs`.

If the temporary dependency directory is absent or incomplete, rebuild it without changing verifier code:

```bash
python3 -m pip install \
  --target /tmp/kicad_pylibs \
  --upgrade \
  --force-reinstall \
  kinet2pcb==1.1.4
```

Run project commands from the repository virtual environment.

## Known projection boundary

Passive R, L, and C components receive real SMD footprints. Voltage sources, current sources, and ideal gain blocks are projected as bench connectors or may lack final footprints. A board generated from the pipeline can therefore be suitable for visualizing passive connectivity while still being incomplete as hardware.

Before calling a generated board complete, verify that the following have real symbols and footprints:

- amplifier and JFET stages;
- tuning and resistor switches;
- ADC and clock circuitry;
- coil, power, programming, and measurement connectors;
- protection and polarization switching parts.

Run `backends.export.export_fab()` only after deciding which routed board is the source of truth. The helper exports the exact PCB path passed to it.
