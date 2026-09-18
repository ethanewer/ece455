# KiCad autorouting with FreeRouting

KiCad does not provide a built-in batch autorouter. It supports external autorouters through Specctra DSN and SES files. See the [KiCad PCB Editor manual](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.pdf) and [FreeRouting CLI documentation](https://github.com/freerouting/freerouting/blob/master/docs/command_line_arguments.md).

## Preconditions

Before exporting:

- Place every footprint that belongs in the board.
- Define the board outline and net classes.
- Set minimum track widths, clearances, and via sizes.
- Save an unrouted source board.
- Identify sensitive analog, clock, high-current, or controlled-impedance nets that require manual routing or special rules.

FreeRouting cannot create missing components, repair the schematic, or infer protection and power circuitry.

## Install FreeRouting without changing system Java

Check the current FreeRouting release and its Java requirement. Prefer the official release JAR with a portable JRE when the installed Java is too old.

The workflow was verified with FreeRouting 2.4.1 and Temurin JRE 25 on Apple Silicon. Treat these as tested versions, not permanent latest versions.

Official release sources:

- `https://github.com/freerouting/freerouting/releases`
- `https://api.adoptium.net/v3/assets/latest/25/hotspot?architecture=aarch64&image_type=jre&os=mac&vendor=eclipse`

Keep downloaded runtimes and JARs in a temporary tool directory unless the user requests a persistent installation.

## Export DSN from KiCad

In KiCad 10.0.6, `kicad-cli` does not expose Specctra DSN export. Use the PCB Editor:

1. Open the unrouted board.
2. Select **File → Export → Specctra DSN…**.
3. Save `board.dsn` beside the board.

## Run FreeRouting

Use the portable Java executable that matches the downloaded release:

```bash
/path/to/java -jar /path/to/freerouting.jar \
  -de board.dsn \
  -do board-routed.ses \
  -mp 20 \
  -mt 4 \
  --gui.enabled=false
```

Require the router summary to report zero unrouted items and zero router violations before importing. Increase passes only when placement and rules are reasonable; repeated passes do not fix missing footprints or impossible geometry.

FreeRouting supports layer controls such as:

```bash
--router.layers.routable=true,false
--router.layers.preferred_direction_horizontal=true,false
```

Use them only when the board's layer strategy requires them.

## Import SES into a separate board

1. Return to the same KiCad board used for DSN export.
2. Select **File → Import → Specctra Session…**.
3. Choose `board-routed.ses`.
4. Save a copy as `board-routed.kicad_pcb`.
5. Preserve the original unrouted board.

KiCad imports tracks and vias only. The footprints, nets, and outline must still match the DSN source.

## Validate and repair

Run strict DRC on the routed copy. If FreeRouting selects a width below the KiCad minimum, widen or reroute the affected segments. Do not lower the minimum merely to clear DRC.

The tested demonstration initially produced four 0.15 mm segments against a 0.20 mm minimum. Widening those segments to 0.20 mm produced zero DRC violations and zero unconnected pads.

Inspect the result for:

- unnecessary fanout vias on single-pad nets;
- long detours and excessive layer changes;
- analog input coupling and return paths;
- ground and power distribution;
- component accessibility and board-edge clearance;
- tracks that terminate at vias because the real destination footprint is missing.

## Present the result

- Capture a PCB Editor view showing the routed tracks, via count, segment count, and zero unrouted items.
- Generate separate front and back renders whenever both layers carry copper.
- State whether the route covers the full design or only a partial demonstration.
- Re-export Gerbers, drill, and STEP files from the routed, DRC-clean board. Do not reuse fabrication files exported from the unrouted board.
