---
name: kicad
description: Generate, inspect, route, validate, render, and export KiCad PCBs and fabrication files. Use for .kicad_pcb work, DRC, layer images, 3D renders, Gerbers, or external FreeRouting autorouting through DSN/SES.
---

# KiCad

Treat the board file and KiCad DRC as the source of truth. A visually plausible render does not prove the board is complete or manufacturable.

## Setup

- Expect KiCad at `/Applications/KiCad.app` and `kicad-cli` on `PATH` or at `/Applications/KiCad.app/Contents/MacOS/kicad-cli`.
- Check the installed version with `kicad-cli version` before using version-specific commands.
- On first GUI launch, select the built-in symbol, footprint, and design-block libraries.
- Check that the global library tables do not point into a stale macOS `AppTranslocation` path. Recreate the tables in KiCad or add a project-local `fp-lib-table` using `${KICAD10_FOOTPRINT_DIR}` when standard-library DRC warnings appear.
- For automated GUI screenshots, grant the host process Accessibility, Automation, and Screen & System Audio Recording permissions.
- Use the CLI for deterministic DRC, exports, and renders. Use the GUI when KiCad exposes no equivalent CLI operation.

For this repository's SKiDL/kinet2pcb projection, read [references/project-backend.md](references/project-backend.md).

## Board workflow

1. Confirm the board has a closed `Edge.Cuts` outline, net assignments, footprints, and design rules.
2. Keep the unrouted source board and create a separate routed board.
3. Run DRC before routing to distinguish placement and footprint problems from unrouted items.
4. Route manually or follow [references/autorouting.md](references/autorouting.md).
5. Run strict KiCad DRC on the routed board.
6. Export fabrication files from the exact routed board that passed DRC.
7. Render front and back views when either copper layer contains tracks.

## DRC

Use KiCad's exit code and save the report:

```bash
kicad-cli pcb drc \
  --output board-drc.txt \
  --format report \
  --severity-all \
  --exit-code-violations \
  board.kicad_pcb
```

Do not report success unless the command exits zero and the report states zero violations and zero unconnected pads. Do not weaken board rules merely to make an autorouted result pass; fix the tracks, placement, footprints, or rules based on the actual design requirement.

## Fabrication outputs

Create Gerbers, drill files, and a STEP model from the DRC-clean routed board:

```bash
kicad-cli pcb export gerbers --output fabrication/gerbers --board-plot-params board.kicad_pcb
kicad-cli pcb export drill --output fabrication/gerbers board.kicad_pcb
kicad-cli pcb export step --output fabrication/board.step --force \
  --include-tracks --include-pads board.kicad_pcb
```

Check that the expected `F.Cu`, `B.Cu`, mask, silkscreen, edge, drill, and STEP files are nonempty.

## PCB images

Use KiCad-rendered images rather than reconstructed diagrams:

```bash
kicad-cli pcb render --output front.png --width 1800 --height 1100 \
  --background opaque --quality high --floor --perspective --zoom 2.2 \
  --rotate 315,0,35 board.kicad_pcb

kicad-cli pcb render --output back.png --width 1800 --height 1100 \
  --side bottom --background opaque --quality high --floor --perspective \
  --zoom 2.2 --rotate 315,0,35 board.kicad_pcb
```

- Show both sides when tracks or components appear on both sides.
- Use a PCB Editor screenshot when the user needs active-layer colors, ratsnest lines, track counts, or via counts.
- In a 3D render, copper under soldermask can appear muted. Confirm visually that tracks are visible.
- Do not reuse the same image on multiple slides unless explicitly requested.

## Claims

- Autorouting connects only the nets and footprints already present.
- Missing amplifiers, switches, ADCs, connectors, power parts, or protection remain missing after routing.
- A passive-only DRC-clean board is not a complete magnetometer PCB.
- For sensitive analog inputs, review placement, return paths, ground strategy, coupling, and critical trace geometry manually after autorouting.
