# Active receiver design

This directory is the single receiver design under development.

## LTspice

- `ltspice/receiver.asc` is the editable 50 uT transient schematic.
- `ltspice/receiver-transfer.asc` is the AC transfer-function schematic.
- `ltspice/receiver.cir` is a portable netlist used for the independent ngspice check.
- `ltspice/receiver.plt` stores LTspice plot settings.

The gain stages are ideal behavioral sources. The noise resistors model selected input voltage and current noise. This is useful for transfer, noise, clipping, and ring-down studies, but it does not model real amplifier bandwidth, saturation recovery, protection, switch charge injection, or frequency-dependent PSRR.

## KiCad

- `kicad/receiver.kicad_pcb` is the current routed board.
- `kicad/receiver.kicad_pro` stores board project settings. There is no KiCad schematic yet.
- `kicad/receiver-drc.txt` is the last committed DRC report.

Run `make eda` after every board or netlist change. Commit a fresh DRC report only after `kicad-cli` reports zero violations and zero unconnected pads.

The current board projects passive connectivity from the simulation. Its resistor and inductor footprints include simulation-only coil and noise-model elements, so its clean DRC result proves only the geometry and connectivity of this passive layout study. It is not ready to fabricate. Add a KiCad schematic and real symbols and footprints for the sensor interface, amplifiers, switching, ADC and clock, protection, power, programming, and coil connections before treating it as receiver hardware.

## Change procedure

1. State the assumption or measured input being changed.
2. Update the LTspice artifact and portable netlist together.
3. Run `make test` and `make eda`.
4. Update the KiCad files if connectivity or component values changed.
5. Run KiCad DRC and inspect layout-sensitive analog paths manually.
6. Record bench evidence in `docs/verification-plan.md` when a measured value replaces a nominal one.
