# TODO — gate to first real auto-research run

Everything that must land before an optimizer is allowed to iterate on the
score. Ordered by phase; items within a phase are roughly priority order.
Labels:

- **[no-API]** — fully autonomous: no API keys, no cloud accounts, no human
- **[API]** — needs an API key or cloud account (or uses an existing one)
- **[human]** — needs a person: a decision, hardware action, or sign-off

Auditing uses the external-review skill
(`~/.pi/skills/external-review/SKILL.md`): `cursor-agent` runs locally with
its existing authentication, so reviews are **[no-API]** unless the CLI is
unauthenticated — check once with the E0 smoke run. Reviews return text only;
the reviewer never edits files.

---

## A. Implementation — IR and backends (currently "planned" in architecture.md §3)

- [ ] **A1 [no-API]** Freeze the circuit IR: promote the `circuit_spec.py` spec
  dict into `spec/` (JSON-able component/net graph, documented schema,
  validation errors on unknown types/nodes).
- [ ] **A2 [no-API]** `backends/spice.py`: port the poc emit/run/parse path
  (including the pagination-tolerant table parser), unit-tested against a
  golden netlist and a known-good ngspice output fixture.
- [ ] **A3 [no-API]** Toolchain pins: `pip install skidl` (≥2.3.0),
  `brew install --cask kicad` (10.x); record versions in
  `docs/architecture.md`; smoke-test `kicad-cli sch erc` on a trivial project.
- [ ] **A4 [no-API]** `backends/kicad.py`: spec → SKiDL → `generate_schematic()`
  + `generate_pcb()` → `kicad-cli sch erc` / `pcb drc --schematic-parity
  --exit-code-violations` as machine gates. Exit criteria: one INA828-class
  AFE passes ERC+DRC with exit code 0 from a clean tree.
- [ ] **A5 [no-API]** Fab/BOM export leg: `pcb export gerbers/drill/step`,
  `sch export bom`; BOM cost extracted from the parts DB (B5).
- [ ] **A6 [no-API]** Docs backend for candidate cards: `generate_svg()` or
  `kicad-cli pcb render` + score table, one directory per candidate.
- [ ] **A7 [no-API]** Optimizer skeleton: mutation operators (topology swap:
  tuned/untuned, bandpass order; part swap via parts DB; parameter moves),
  scoring fan-out (subprocess pool over A2), survivor promotion. NO agent LLM
  in the loop yet — score-guided search only.

## B. Score completion — close the audit blind-spot list before optimizing

- [ ] **B1 [no-API]** Monte-Carlo tolerance sweep in the SPICE layer
  (`.control` loop, `alter`/`sgauss`, `setseed`, `sim_status` handling) —
  report σ_B at 2σ component tolerances, not just nominal.
- [ ] **B2 [no-API]** Comparator time-walk model in `fid.py` (bias
  ∝ V_n/(2πf·A(t))) so the zero-crossing path is scored with its real
  systematic, not just its variance.
- [ ] **B3 [no-API]** Rail-ripple / PSRR interferer model: supply ripple
  inside the FID band killed two prior teams; it must be a scored ablation.
- [ ] **B4 [no-API]** 1/f noise and CMRR terms (analytic layer per the AFE
  research formulas; document what SPICE cannot see).
- [ ] **B5 [no-API]** Parts DB (`parts/`): e_n, i_n, GBW, price, footprint,
  MPN for the shortlist (INA828, ADA4898, 2N6550-class JFET, ADS131M04,
  DG419, ±0.5 ppm and ±2 ppm TCXOs). Prices hand-entered from datasheets
  (no scraping); optional DigiKey API sync later is **[API]**.
- [ ] **B6 [no-API]** Gain staging in the candidate space + clipping gate
  exercised (candidates that vary gain must be able to fail on clipping).
- [ ] **B7 [human]** Decide whether survey productivity (cycle time vs tow
  speed) is a scored term or stays reported-only; if scored, specify the
  requirement it is scored against.

## C. Firmware core (the MCU half of the score)

- [ ] **C1 [no-API]** `firmware/core/freq_est.c`: port `zoom_fit` to portable
  C99 (NCO + FIR decimator + running weighted sums); float32 and 64-bit
  fixed-point builds behind one compile switch. No vendor headers.
- [ ] **C2 [no-API]** Host test harness: same estimator core built for the
  host, driven by golden vectors exported from `poc/fid.py` (pytest+ctypes or
  Unity). Golden-vector hash pinned.
- [ ] **C3 [no-API]** CI `sensitivity-score` job: synthetic-FID matrix
  (1064/2133/2767 Hz × T2* 0.3–3 s × SNR sweep), timestamp quantization per
  MCU, clock ppm as scale error; gate at 0.0426 Hz; emits σ_f/bias JSON.
- [ ] **C4 [no-API]** Emulator plumbing check: Renode (STM32) with a RESD FID
  stream, or rp2040js locally (MIT, no quota). Proves timestamps move through
  the firmware; explicitly NOT a timing/sensitivity oracle.
- [ ] **C5 [API]** Optional: Wokwi cloud CI (`wokwi-cli`, free tier 50 min/mo,
  requires account token) — skip if C4's local rp2040js path is sufficient.
- [ ] **C6 [human]** Target selection: MCU family + TCXO grade (±0.5 vs ±2 ppm)
  vs board budget; the ppm table in `run_scoring.py` §3c is the input.

## D. Verification — prove the score before trusting it

- [ ] **D1 [no-API]** Keep `test_validation.py` green in CI; add a
  SPICE-vs-analytic noise cross-check per new candidate class (the INA-class
  check exists; generalize).
- [ ] **D2 [no-API]** Determinism test: two clean checkouts produce
  byte-identical score cards (fixed seeds; no wall-clock in outputs).
- [ ] **D3 [no-API]** Round-trip invariant: the netlist KiCad exports from a
  generated project simulates to the same H(f)/noise as the emitted netlist.
- [ ] **D4 [no-API]** One-command reproduction: a script regenerates every
  headline number in README + architecture tables from a fresh tree; outputs
  diffed against committed fixtures.
- [ ] **D5 [no-API]** Optimizer-exploitability self-test: adversarial
  candidates (bandpass removed, gain cranked, blanking deleted, TL072
  resurrected) must each fail ≥1 gate. If any passes, the score is not ready.
- [ ] **D6 [human]** Accept the transducer model (V₀ from `estimate_v0`) as
  the interim anchor until F1 pins it, or supply measured coil values.

## E. Auditing — external-review skill, before the optimizer starts

- [ ] **E0 [no-API]** Smoke test the reviewer CLI once (`cursor-agent -p -f
  --trust --workspace /Users/ethanewer/ece455 "reply OK"`). If this needs a
  login/key, reclassify E1–E3 as **[API]** and do it before anything else.
- [ ] **E1 [no-API]** Review 1 (bugbot) on the diff before every commit in
  phases A–C (separate invocation; never combined with Review 2).
- [ ] **E2 [no-API]** Review 2 (scientific correctness) on every diff that
  touches constants, noise parameters, scoring/estimator math, or physics
  claims in docs — mandatory before B-phase items merge.
- [ ] **E3 [no-API]** Review 3 (deep auto-research audit) over the whole
  pipeline when A–D are done: independently re-executes headline numbers,
  re-derives bounds, checks alignment and completeness. This is the v0.0-style
  audit that caught the γp and V₀ problems.
- [ ] **E4 [no-API]** Triage discipline per skill "Treating results": every
  finding independently verified (agree with evidence or refute) before any
  edit; unfixed confirmed findings block G1.
- [ ] **E5 [human]** Read the E3 audit verdict and sign off.

## F. Bench — the parts no simulation replaces (human/hardware)

- [ ] **F1 [human]** First wet FID capture (week-2 problem 1): measured V₀ and
  T2* replace the transducer model's assumptions; acceptance criteria are the
  harness's predicted ranges.
- [ ] **F2 [human]** Measure the real coil: R, L, and tuning-C sweep; feed
  back into the coil model and re-score the grid.
- [ ] **F3 [human]** Traceable reference injection (disciplined generator or
  GPSDO) for on-target estimator validation; bench HIL acceptance per the MCU
  research doc.
- [ ] **F4 [human]** Long-lead orders (TCXO, ADC/AFE parts) started in
  parallel with F1/F2 — week-2 problem 8.

## G. Go/no-go

- [ ] **G1 [human]** Decide search mode for "real" runs: score-guided mutation
  search (A7, no LLM, fully reproducible) vs LLM-proposed candidates (needs
  model access — e.g. Claude Code session, no separate key — but candidates
  must still pass the identical scorer).
- [ ] **G2 [human]** GO: optimizer unlocked only when A–D are checked, E3 has
  no unresolved high-severity findings, and F2 anchors the coil model.

---

Dependency spine: A1→A2→A4→A7 · B1–B6 before A7 · C1→C2→C3 before G ·
D5 + E3 before G2. A, B, C, D, E are fully parallelizable except where noted;
F can start anytime hardware is available.
