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
  `docs/architecture.md` and pin Python deps in a `requirements.txt`
  (numpy/scipy float today); smoke-test `kicad-cli sch erc` on a trivial project.
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
  in the loop yet — score-guided search only. Run-hygiene requirements for
  real runs, in the same item: per-candidate timeout + graceful SPICE
  failure/`sim_status` handling (a non-converging candidate is a scored
  rejection, not a crash); provenance stamped into every score card (git SHA,
  tool versions, seeds, full spec hash); topology-hash dedupe so mutations
  can't rescore the same circuit; elite archive persisted between runs.

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
- [ ] **B8 [no-API]** Score across the operating field range, not one point:
  every result today is at B = 50 µT (f_L = 2129 Hz). The mission spans
  25–65 µT ⇒ f_L = 1064–2767 Hz, and the MFB bandpass is fixed near 2.1 kHz.
  Score the B-sweep (amplitude ∝ B through the transducer model; filter
  centering/rolloff at 1.1 and 2.8 kHz; ADC range use), and add either a
  tunable/wider-band filter axis or a per-band candidate family. Without
  this, the optimizer optimizes for one field point.

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

### D+. Full verification of completed work (the audit-fix round)

The v0.0 audits were run against the *pre-fix* tree; the fix commit
(`2d23fb9`) and everything before it carries only partial test coverage.
These items close that gap before any new work builds on it.

Existing-work coverage status: `test_validation.py` covers the CRBs, zoom_fit,
γp constants, and V₀ sanity. **Not yet covered**: zc_fit/nlls_fit/fft_peak
behavior, `circuit_spec.py` end-to-end, the ngspice parser, `ringdown_tau`,
the band-limited noise generator, the Curie-law V₀ against an independent
hand calculation, docs-vs-code numbers, and output determinism.

- [ ] **D7 [no-API]** Estimator test coverage: lock the measured reference
  table into asserts — zoom_fit ≤1.2× CRB with 0% gross; fft_peak ≤1.2× CRB;
  zc_fit ≥100× CRB (the ruling-out must *fail loudly* if someone "fixes" it
  into a worse estimator or the SNR regime shifts); staged nlls_fit ≤1.2× CRB
  on its non-divergent runs with gross rate ≤3%. Phase-randomized, fixed
  seeds, MC CI asserted.
- [ ] **D8 [no-API]** `circuit_spec.py` regression: commit one full score-card
  per candidate class as a fixture; test asserts J/CRB/σ_in/τ_ring reproduce
  within MC tolerance. Guards the SPICE→nT path against silent breakage.
- [ ] **D9 [no-API]** ngspice layer unit tests with committed stdout fixtures:
  pagination-tolerant table parser (repeated headers, `---` rules, trailing
  tabs, tran `time` axis), `ringdown_tau` on a synthetic exponential of known
  τ, `shape_transfer` interpolation at/beyond sweep edges, and the e_n/i_n
  resistor identities (`R = e_n²/4kT` reproduces the datasheet density).
- [ ] **D10 [no-API]** `fid.py` unit tests: `_bandlimited_noise` PSD flat in
  band / ~zero outside, RMS = σ within tolerance; ADC quantization step and
  saturation behavior; interferer injection lands at the requested amplitude;
  `estimate_v0` vs an independent Curie-law implementation written in the
  test (agreement <1e-6 relative).
- [ ] **D11 [no-API]** Determinism: `run_scoring.py` and `circuit_spec.py`
  outputs byte-identical across two clean checkouts (fixed seeds; no
  wall-clock in printed tables — the ngspice timestamp lines must be
  filtered by the parser, which they are; assert it).
- [ ] **D12 [no-API]** Docs-vs-code consistency: a script extracts every
  headline number from README.md + architecture.md tables and checks each
  against regenerated output within the stated MC CI; fails CI on drift.
  (This is the audit finding class "table says 0.044, code prints 0.0435".)
- [ ] **D13 [no-API]** Colored-CRB second independent check: ensemble-
  estimated covariance (Monte-Carlo realizations of the band-limited
  process, `J = dsᵀ C⁺ ds`) alongside the existing dense-covariance test —
  two orthogonal constructions must agree with the DFT shortcut within 10%.
- [ ] **D14 [human]** Physics sanity pass on the completed round's headline
  results: tuned-JFET J ≈ 0.006 nT and the V₀ grid values checked against
  JPM-4 / Koehler / the Overhauser noise-modeling paper by a person, not
  just by the code that produced them.
- [ ] **D15 [no-API]** CI workflow (GitHub Actions, included minutes — no key
  needed): `pip install numpy scipy` + `brew install ngspice` on every push →
  run `test_validation.py` + the D7–D12 suite + fixture diffs. This is what
  turns the items above from one-off checks into standing regressions.
- [ ] **D16 [no-API]** Implement M4 from the scoring-harness spec
  (research-frequency-estimation.md §5), specced but never built: cycle-to-
  cycle repeatability (std of consecutive f̂ in a stationary-field run,
  including estimator 1/f drift behavior) and the averaging-gain check
  (σ of M-cycle averages vs σ/√M — catches correlated residuals the per-cycle
  RMS hides). Land alongside D7 in the estimator suite.

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
  edit; unfixed confirmed findings block G2.
- [ ] **E5 [human]** Read the E3 audit verdict and sign off.
- [ ] **E6 [no-API]** Re-review the already-completed work: run Review 1
  (bugbot) and Review 2 (scientific correctness) — separately — over the
  current committed tree (the fix commit `2d23fb9` + TODO.md). The v0.0
  audits predate the fixes; nothing external has reviewed the fixed code.
  Scope Review 2 explicitly at: shielded-γp value and its uses, the Curie-law
  transducer model, the e_n/i_n resistor-noise modeling, the tuned-network
  netlist physics, and the M5 ablation interpretations. Treat findings per E4.
- [ ] **E7 [no-API]** Checkpoint re-audits after the optimizer starts: the
  skill's review table says the deep audit also runs "periodically as a
  checkpoint". Schedule: after the first 50 scored candidates, then every
  order-of-magnitude of candidate count — verifies the optimizer hasn't
  drifted into exploiting a residual score blind spot (E4 triage applies).

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
  no unresolved high-severity findings, and F2 anchors the coil model. Part of
  the GO action: flip the "do not run a search agent against the PoC score"
  caveats in README.md/architecture.md to the unlocked state, with the E7
  checkpoint cadence recorded.

## H. Repo housekeeping (do first — cheapest, removes ambiguity)

- [ ] **H1 [no-API]** Add a LICENSE (the docs claim "open source end to end";
  the repo itself has none — pick MIT or GPL to match the SKiDL/KiCad stack).
- [ ] **H2 [no-API]** Resolve untracked files: `.claude/`, `.codex/`, `.pi/`,
  `AGENTS.md`, `CLAUDE.md` — commit the harness config deliberately or extend
  `.gitignore`; ambiguous workspace state breaks reproducibility claims
  (D11's "clean checkout" needs a defined tree).

---

Dependency spine: H first (defines the tree) · A1→A2→A4→A7 · B1–B8 before A7 ·
C1→C2→C3 before G · D7–D13 + D16 + E6 (verify the completed round) start
immediately and block G2 · D5 + D8 + E3 before G2. A, B, C, D, E are fully
parallelizable except where noted; F can start anytime hardware is available.
