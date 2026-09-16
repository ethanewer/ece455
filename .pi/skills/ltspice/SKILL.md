---
name: ltspice
description: Create, run, validate, and capture real LTspice schematics and waveforms on macOS. Use for .asc/.cir models, simulation screenshots, or LTspice GUI automation; do not substitute recreated plots when an LTspice screenshot is requested.
---

# LTspice

Use LTspice itself for requested LTspice figures. A plot recreated with Matplotlib or another renderer is not an LTspice screenshot.

## Setup

- Expect the application at `/Applications/LTspice.app`.
- Confirm it opens with `open -a LTspice <file.asc>`.
- For GUI automation on macOS, enable Accessibility, Automation, and Screen & System Audio Recording for the host process running the agent. The host may be Visual Studio Code, Terminal, or another harness.
- Under Automation, allow the host to control System Events and LTspice.
- Restart the host application after changing privacy permissions.
- Install `ngspice` only when an independent command-line check is useful. It is a validator, not a source of LTspice screenshots.

Read [references/macos-automation.md](references/macos-automation.md) when GUI control or screenshots are required.

## Choose the artifact

- Use `.asc` for an editable LTspice schematic and authentic schematic screenshot.
- Use `.cir` for a portable SPICE netlist or independent batch validation.
- Use `.raw` for LTspice simulation data and `.plt` for saved plot settings.
- Keep node names in `.asc`, `.cir`, `.save`, `.plt`, and slide labels consistent.

## Build readable schematics

- Draw visible `WIRE` connections when the figure must teach circuit topology.
- Use net labels for distant or cross-row connections, not as a replacement for every visible wire.
- Route wires around component bodies. A wire that crosses both terminals of a source or passive shorts it.
- Space values and reference names before capturing a screenshot.
- State when behavioral sources or ideal gain blocks represent a pipeline-equivalent model rather than a fabrication circuit.

## Run and verify

1. Open the `.asc` file in LTspice.
2. Use **View → Zoom to Fit**.
3. Use **Simulate → Run/Pause**.
4. Confirm that the `.raw` and `.log` files were updated.
5. Inspect the log for solver completion and the absence of fatal errors.
6. Confirm the plotted nodes, time range, units, and trace colors match the explanation.

For an independent netlist check, prefer:

```bash
ngspice -b -r /tmp/output.raw -o /tmp/output.log model.cir
```

Using `ngspice -b model.cir` without a `.print`, `.plot`, `.fourier`, or raw-output target can fail even when the circuit is valid.

## Capture figures

- Keep the LTspice title bar or toolbar visible when provenance matters.
- Crop to the application window or waveform pane; do not include unrelated desktop windows.
- Use a schematic screenshot for topology and a separate waveform screenshot for output.
- Inspect the saved PNG at full size for overlaps, clipped axes, and illegible values.

## Claims

- Describe simulation results as simulated or conditional.
- Do not call a circuit a working magnetometer solely because LTspice converges.
- Identify omitted switch parasitics, protection, saturation, recovery, real amplifier behavior, or measured coil data when they affect the claim.
