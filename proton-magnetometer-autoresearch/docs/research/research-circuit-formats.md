# Research: circuit expression formats for auto-research (2026-02 survey)

> Full landscape survey behind the format decision in
> [`../architecture.md`](../architecture.md). Compiled from web research,
> February 2026.

## 1. SPICE netlists as the canonical machine representation

- **ngspice is a direct derivative of SPICE3f5 (UC Berkeley)**; input files
  retain the classic structure (title line, `.end` last) that became the de
  facto netlist standard: https://nmg.gitlab.io/ngspice-manual/startingngspice/compatibility.html,
  https://ngspice.sourceforge.io/docs/ngspice-html-manual/manual.xhtml
- **Portability good but not absolute.** ngspice ships compatibility modes
  (`s3`, `ps`, `hs`, `lt`, `spe`, `ki`, `eg`) with `kiltpsa` (KiCad+LTspice+PSpice)
  commonly recommended: https://spicelib.readthedocs.io/en/latest/classes/ngspice_simulator.html
- **Xyce (Sandia, GPLv3)** warns netlist translation "is not always a
  straightforward exercise" (e.g. leading-whitespace differences vs ngspice):
  https://xyce.sandia.gov/about-xyce/ , https://doi.org/10.2172/1489537
- **Licensing**: ngspice base is new BSD (embeddable); Xyce GPLv3:
  https://github.com/ngspice/ngspice/blob/master/COPYING
- **KiCad↔SPICE round trip is supported**: KiCad 8/9 embed ngspice-44/45.2 as a
  shared library; `kicad-cli sch export netlist --format spice` produces
  netlists for external simulators:
  https://docs.kicad.org/9.0/en/eeschema/eeschema.html ,
  https://docs.kicad.org/7.0/en/cli/cli.html ,
  https://forum.kicad.info/t/simulation-getting-started-with-ngspice/46665 ,
  https://github.com/labtroll/KiCad-Simulations
- **Key limitation**: a netlist cannot reconstruct a graphical schematic (no
  symbols, positions, routing): https://forum.kicad.info/t/import-spice-netlist/12415

## 2. KiCad file formats and headless automation

- Officially documented formats (s-expression intro, board, schematic, symbol,
  footprint): https://dev-docs.kicad.org/en/file-formats/index.html ,
  grammar: https://dev-docs.kicad.org/en/file-formats/sexpr-schematic/index.html .
  Third-party scripts are explicitly told **not** to use `eeschema` as the
  `(generator ...)` identifier.
- Per-family date-stamp versions (schematics/boards versioned separately):
  7.0 = `20230620`, 8.0 = `20231231`, 9.0 dev = `20250610`:
  https://mintlify.wiki/KiCad/kicad-source-mirror/architecture/file-formats
- **No stability guarantee across majors**, no back-conversion; unknown tokens
  cause unpredictable behavior in older parsers:
  https://forum.kicad.info/t/post-v7-file-format-questions/40334 ,
  https://forum.kicad.info/t/can-a-project-edited-with-a-newer-version-of-kicad-be-opened-with-an-older-version/25302 .
  Third-party parsers (kiutils) hedge with `unknown_nodes` capture:
  https://docs.rs/kiutils_kicad/latest/src/kiutils_kicad/lib.rs.html
- **`kicad-cli`** (verified against https://docs.kicad.org/master/en/cli/cli.html):
  `sch erc`, `sch export {svg,pdf,png,dxf,ps,hpgl,netlist,bom}`, `pcb drc`,
  `pcb export {gerbers,drill,step,pos,ipc2581,ipcd356,odb,pdf,svg,glb,stl,3dpdf,vrml}`,
  `pcb render`, `gerber`, `jobset`, `sym`, `fp`, and **`api-server`** (headless
  IPC API). ERC/DRC support `--format json` and `--exit-code-violations`
  (exit 0 clean, **exit 5 = violations**) — ideal for CI loops.
- **KiCad 10.0.0 shipped 2026-03-20** (design variants, pin/gate swap,
  graphical DRC rule editor, Allegro/PADS/gEDA-Lepton importers):
  https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/
- Bottom line: documented *internal* format, not an API; hand-writing
  s-expressions inherits version-pinning — use a generator library.

## 3. SKiDL — strongest "code → buildable KiCad" candidate in 2026

- Repo: MIT, 1,650 stars, last push 2026-08-20: https://github.com/devbisme/skidl
- Release history (https://raw.githubusercontent.com/devbisme/skidl/master/HISTORY.md):
  - **2.1.0 (2025-08-30)**: `KICAD9` default; "InSpice has replaced PySpice to
    enable newer ngspice"; hierarchical `netlist_to_skidl`
  - **2.2.0 (2025-11-09)**: SQLite-backed part search + `skidl-part-search` CLI
  - **2.2.2 (2026-04-03)**: **schematic generation for KiCad 6–9**
  - **2.3.0 (2026-07-28)**: **`KICAD10` support**, tool-agnostic
    `SchematicBackend`, `auto_stub` inter-block nets, power-symbol fixes
- **`generate_schematic()`** (https://devbisme.github.io/skidl/api/html/rst_output/skidl.tools.kicad9.gen_schematic.html):
  auto-placement, Manhattan routing, `flatness` (0.0 hierarchical → 1.0 flat),
  `auto_stub=True` converts unroutable nets into global labels and runs a
  KiCad ERC correction loop. Docs recommend `@subcircuit` grouping of 5–15
  parts so each block lands on its own sheet.
- **Output fan-out**: `generate_netlist()`, `generate_xml()` (BOM),
  `generate_pcb()` (writes `.kicad_pcb` directly), `generate_svg()` (netlistsvg,
  needs npm), `generate_dot()`: https://devbisme.github.io/skidl/
- **SPICE simulation from SKiDL** via InSpice + ngspice 44.2+: canonical
  notebook https://github.com/devbisme/skidl/blob/master/tests/examples/spice-sim-intro/spice-sim-intro.ipynb
  (`spinit` containing `set ngbehavior=ps`)
- **PCB workflow**: with 2.2.2+ emitting real `.kicad_sch`, the standard F8
  "Update PCB from Schematic" flow is available to SKiDL-generated designs
  (netlist import no longer needed for KiCad-to-KiCad:
  https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html) — the single biggest
  enabler for this pipeline.
- Documented limitations: https://devbisme.github.io/skidl/ (`netlist_to_skidl`
  KiCad-only; subcircuit contexts not reusable; `+=` only connect operator;
  SVG needs npm).

## 4. PySpice → InSpice

- **PySpice minimally maintained** (1.5 stable, "developed on my free time"):
  https://github.com/pyspice-org/pyspice
- **macOS shared-library mode broken in 1.5**:
  issue #376 (`find_library` passes `libngspice.dylib` → searches
  `liblibngspice.dylib.dylib`; workaround `DYLD_LIBRARY_PATH=/opt/homebrew/lib`):
  https://github.com/PySpice-org/PySpice/issues/376
  issue #379 (Homebrew libngspice 43+ stderr line treated as fatal; fixed in
  1.6 devel): https://github.com/PySpice-org/PySpice/issues/379
  Subprocess fallback: `CircuitSimulator.DEFAULT_SIMULATOR = 'ngspice-subprocess'`:
  https://pyspice.fabrice-salvaire.fr/releases/v1.6/installation.html
- **InSpice = maintained continuation** (Innovoltive, 2025-04-18 fork; PyPI
  `inspice` 1.7.0.4, GPL-3.0, Python ≥3.12, ngspice + Xyce):
  https://github.com/insim-ai/InSpice , https://pypi.org/project/InSpice/
- **Pragmatic CI choice**: drive `ngspice -b` as a subprocess over plain
  netlists — no cffi, no dyld issues, trivially sandboxed. (This is what the
  PoC does.)

## 5. tscircuit

- MIT, ~2,362 stars; React/TS → open **Circuit JSON** IR:
  https://github.com/tscircuit/tscircuit , https://github.com/tscircuit/circuit-json
- Exports KiCad (`tsci export kicad_sch|kicad_pcb|kicad_zip|gerbers|spice|...`),
  `tsci build --kicad-pcm` for KiCad PCM feeds:
  https://docs.tscircuit.com/command-line/tsci-export , https://github.com/tscircuit/cli
- Self-hostable registry (`platform.registryApiUrl`): https://registry.tscircuit.com/ ,
  https://docs.tscircuit.com/guides/running-tscircuit/platform-configuration.md
- SPICE: `tsci simulate` with `"spicey"` (default) or `"ngspice"` (WASM):
  https://docs.tscircuit.com/guides/spice-simulation/introduction — but the
  ngspice engine repo was created 2025-10-23 with 2 stars:
  https://github.com/tscircuit/ngspice-spice-engine/
- **KiCad export weak for analog**: coordinate-precision wire disconnects
  (issue #292), **0.1 mm vs 50-mil grid mismatch breaks Update-PCB-from-
  Schematic** (issue #3084), non-standard lib_ids render as "?" (issue #257):
  https://github.com/tscircuit/circuit-json-to-kicad/issues/292 ,
  https://github.com/tscircuit/tscircuit/issues/3084 ,
  https://github.com/tscircuit/circuit-json-to-kicad/issues/257

## 6. Other candidates

| Tool | Verdict | Evidence |
|---|---|---|
| **atopile** (`.ato`, MIT, v0.15.x) | Most philosophically aligned "code-first EDA with verification": constraint solver picks parts; SPICE woven into assertions (`assert ripple < 30mV`, `verify`/`simulate`, CI); updates KiCad via IPC API (v0.5.0 bindings, Oct 2025); MCP support. Heavier/opinionated. | https://github.com/atopile/atopile , https://pypi.org/project/atopile/ , https://github.com/atopile/atopile/discussions/1815 |
| **circuit-synth** (Python→KiCad, MIT, 270 stars, push 2026-03) | decorators → `.kicad_pro/.kicad_sch/.kicad_pcb`, bidirectional import, AI agents; smaller than SKiDL; its `kicad-sch-api` does byte-exact `.kicad_sch` round-trips | https://github.com/circuit-synth/circuit-synth , https://github.com/circuit-synth/kicad-sch-api |
| **kicad-skip** | parser-manipulator, **stale (2024-05)** | https://github.com/psychogenic/kicad-skip |
| **Horizon EDA** | JSON-per-element + SQLite pool; own format by design; small scripting ecosystem | https://github.com/horizon-eda/horizon , https://docs.horizon-eda.org/en/v2.5.0/version.html |
| **LibrePCB** | human-readable, VCS-diffable; small ecosystem, no Python bridge | https://librepcb.org/ |
| **Lepton EDA (gEDA/gaf)** | alive; ASCII gaf; `lepton-netlist` 30+ formats; KiCad importers | https://github.com/lepton-eda/lepton-eda |
| **EDIF** | dead (body dissolved 1996) | https://en.wikipedia.org/wiki/EDIF |
| **IPC-2581 vs ODB++** | IPC-2581 = open consortium XML (fab/assembly exchange); ODB++ Siemens-controlled. Manufacturing *sinks*, not design sources. KiCad 10 exports both. | https://ipc2581.com/ , https://www.flowcad.eu/en/odb%2B%2B-vs-ipc-2581 |
| **JITX** | proprietary (~$1k/seat/mo; free tier forces CERN-OHL-P) | https://www.jitx.com/plans |
| netlist↔schematic converters | `nl2sch`, `LTspice2Kicad`, `kicad-spice-extras`, netlistsvg | https://github.com/tpecar/nl2sch , https://github.com/laurentc2/LTspice2Kicad , https://github.com/vlad-ivanov-name/kicad-spice-extras , https://github.com/nturley/netlistsvg |

## 7. Comparison table

| Format / tool | Text? | Simulatable? | Buildable output | Maturity | License | LLM/programmatic suitability |
|---|---|---|---|---|---|---|
| SPICE netlist | Yes | **Native** | Netlist only | De facto standard since ~1990s | BSD | **Excellent** emit; can't compile to schematic alone |
| KiCad s-expr | Yes | via netlist export + embedded ngspice | **Full** | Dominant open EDA; KiCad 10 (2026-03) | GPL / CC-BY-SA docs | Medium (version-pinned; use generator) |
| **SKiDL 2.3.0** | Python | Yes (InSpice + ngspice; SPICE netlist export) | **Now full** (sch + pcb + BOM + SVG) | Very active; schematic gen new Apr 2026 | MIT | **Excellent** |
| PySpice 1.5 / InSpice | Python | Yes | No | PySpice stale; InSpice active | GPL-3.0 | Good; macOS dyld fragility; prefer subprocess |
| tscircuit | TSX + JSON IR | Yes (young engines) | Yes, grid bugs open | Young (2.4k stars) | MIT | Great DX, **risky for µV analog today** |
| atopile | Yes | SPICE in assertions | Yes (IPC API) | Active, v0.15.x | MIT | Very good; heavier paradigm |
| circuit-synth | Python | Partial | Yes | Smaller | MIT | Good; overlaps SKiDL |
| kicad-sch-api / kicad-skip | s-expr manipulation | No | Edit-level | sch-api active; skip stale | MIT / LGPL | Low-level writer |
| Horizon / LibrePCB / Lepton | Yes | Limited | Yes | Maintained, small ecosystems | Apache/GPL | Medium |
| EDIF | — | — | — | Dead | — | No |
| IPC-2581 / ODB++ | Yes | No | Mfg-exchange only | IPC-2581 active | Free / proprietary | Sink-only |

## 8. Architecture options considered

### Option A (chosen): SKiDL IR + ngspice physics + kicad-cli verifier
```
Python generator → SKiDL Circuit
 ├─→ ngspice batch → .ac/.noise/.tran → score
 ├─→ generate_schematic(KICAD10) → .kicad_sch (hierarchical, auto_stub)
 ├─→ generate_pcb() / netlist / BOM XML
 └─→ kicad-cli: sch erc → pcb drc --schematic-parity → gerbers/BOM (exit codes gate the loop)
```
Pros: one MIT Python IR → all backends; hierarchical `@subcircuit` sheets map
onto AFE blocks; ERC/DRC exit codes close the loop; KiCad 6–10 targets.
Cons: `generate_schematic` ~5 months old (expect "acceptable, not pretty"
placement); InSpice macOS quirks (mitigate: subprocess); pin KICAD10.

### Option B: raw SPICE netlist IR
Simplest sim loop; but netlists can't reconstruct schematics, and the lift to
KiCad still runs through SKiDL — Option A's schematic problem plus a
representation gap. Fine as the **fast pre-filter** layer.

### Option C: tscircuit / Circuit JSON
Best DX; but mm-vs-mil grid bug breaks KiCad round-trip (#3084), wire
precision (#292), ngspice engine weeks old — wrong risk profile for µV analog.

(Honorable mention: **atopile** if verification semantics are first-class;
but its constraint-solver paradigm fights a generator that wants to control
topology itself.)
