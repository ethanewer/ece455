# Auto-research pipeline for the proton-magnetometer receiver

**Scope.** We have a coil and a power source. This pipeline designs and scores
everything downstream of the coil: the analog front end (blanking, preamp,
bandpass, gain, ADC driver), and the microcontroller signal-processing stack
that turns the induced EMF (free induction decay, FID) into a magnetic-field
estimate. Goal sensitivity: **< 1 nT per cycle ⇒ frequency precision
< 0.0426 Hz** (shielded-proton γ′p = 0.0425764 Hz/nT) on a 1–3 kHz decaying
sinusoid of µV amplitude.

**Status: gated pre-optimizer.** The pipeline has **one evaluator**: every
score is a single design — one circuit + one estimator implementation (the
shipped C core) + one MCU configuration — evaluated end to end
(`pipeline/evaluate.py`; [`REDESIGN.md`](../REDESIGN.md) states the problem
with the previous three-layer split and the migration). The frozen circuit
IR, the SPICE and KiCad backends (ERC/DRC machine gates), the parts DB, the
score-guided optimizer skeleton, and the portable C estimator core (float +
fixed, emulator-checked) all exist and run, under the standing regression
suite in `tests/` and CI. The E3 deep audit's verified blind spots are
fixed (V₀↔coil coupling, rail-ripple gate, causal `.tran` impulse
response); the score is a validated noise/CRB prior but NOT yet a hardware
objective until the bench capture anchors the coil model (see
docs/runbook.md for the remaining pre-GO gates).

This document answers the two framing questions for the `autoresearch` branch:

1. **What circuit representation makes an auto-research loop efficient?**
2. **How do we score circuit + MCU stacks for sensitivity, numerically, without
   hardware?**

It synthesizes four research passes (full reports in
[`docs/research/`](research/)) plus the working pipeline in
[`pipeline/`](../pipeline/) that closes the loop on this machine, and incorporates the
v0.0 external audits of both.

---

## 0. The objective function (everything else serves this)

**One** J is implemented, in `pipeline/evaluate.py::evaluate()`:

```
J = sigma_B  [nT RMS per cycle]          # primary metric
gates (fail -> J = inf):
  gross-error rate  P(|f_hat - f_L| > 1 Hz) < 1%     # FID detectable & trackable
  ring-down fits inside blanking: 5*tau_ring < 0.5*T2*
  no ADC clipping: peak |v_adc| < 0.9 * FS/2
reported, not gated: dead-time fraction, SNR (both conventions), BOM cost (TODO)
```

Deliberate choices (the two v0.0 audits caught inconsistencies here):

* **No λ_dead term.** Dead time is already inside σ_B via the record start
  time; a separate cost term double-counts. Cycle rate vs tow speed (survey
  productivity) is a *reported* metric, not a cost term, until someone
  specifies the survey requirement.
* **Pd semantics.** The Marcum-Q/erfc detection formulas are for detecting
  *the FID per cycle*; detecting *a 1 nT wreck along a track* is a different
  test (matched filter over the anomaly profile). The gate above uses the
  empirical per-cycle gross-error rate as the FID-detection proxy; the
  along-track problem is out of scope for the circuit score.
* **Absolute vs anomaly accuracy** (decision recorded): a constant scale
  error — wrong γp, clock ppm — subtracts out of along-track anomaly
  contrast (the towfish mission) but NOT out of absolute field intensity.
  σ_B here is per-cycle *precision*; absolute accuracy carries the scale
  terms (clock ppm, reported per score card) as reported biases.

The physics chain (every stage below is the candidate's own — nothing
generic anywhere in the path):

```
B [T] ──γ′p──> f_L [Hz] ──coil──> FID EMF [µV]
        ──THE CANDIDATE's H(f) + noise (SPICE .ac/.noise)──>
        ──convolution with THE CANDIDATE's causal h(t) (SPICE .tran impulse)──>
        ADC rails + quantization ──>
        ──THE CANDIDATE's estimator (the C core, byte-identical to the MCU
          build) ──> f̂ ──/γ′p──> B̂
        sigma_B = sigma_f / 0.0425764 Hz/nT
```

Unit warnings (both v0.0 audits caught variants of this): 42.5764 **MHz/T**
= 42.5764 **Hz/µT** = **0.0425764 Hz/nT** — not 42.5764 Hz/nT. And the
42.577478 MHz/T often quoted is the **bare** proton; a water PPM measures the
**shielded** proton, 42.57638474 MHz/T (CODATA 2018; the 2014 value
42.57638507 differs by 7.8 ppb) — 25.7 ppm lower than the bare value, worth
~1.3 nT of scale bias at 50 µT if you use the wrong one for absolute values.
`pipeline/fid.py` holds the single source of truth.

**What the score means — the conditional headline.** The DSP result people
quote from this repo ("~0.05 nT/cycle") is a *Cramér–Rao bound conditional on
the assumed transducer amplitude*. The transducer model
(`fid.estimate_v0`, spin-1/2 Curie law: M₀ = n·µ_p²·B_pol/(kT) — 3× the
classical Langevin n·µ_p²·B_pol/(3kT) an earlier revision coded; audit E6),
EMF = µ₀·M₀·A·ω·N) says a Hook-Line-class coil (530 turns, 3 cm bore,
20 mT polarization) produces **V₀ ≈ 0.41 µV** — not the 2 µV the first
revision assumed. The honest grid (INA-class e_n, blanking 200 ms;
regenerated deterministically by `tools/reproduce.py`):

| coil model | V₀ | CRB @ T2*=0.5 s | 1.5 s | 3.0 s |
|---|---|---|---|---|
| N=300, r=1.0 cm, 10 mT | 0.05 µV | 6.6 nT | 1.9 nT | 1.4 nT |
| N=530, r=1.5 cm, 20 mT | 0.41 µV | 0.83 nT | **0.24 nT** | 0.17 nT |
| N=1500, r=3.0 cm, 50 mT | 11.5 µV | 0.029 nT | 0.008 nT | 0.006 nT |

Read this as: **the analog front end and the polarization chain decide the
mission.** A small coil has ~4× margin on 1 nT/cycle at T2* = 1.5 s but only
~1.2× at T2* = 0.5 s (and none at 0.3 s); a large coil has 100× margin for
the DSP. The first
wet capture (week-2 problem 1) is what pins V₀ and T2*; treat 2 µV-class
amplitudes as achievable only with the bigger coil/polarization row.

This grid is deterministic (CRB only, no MC) and is regenerated and checked
against the docs by `tools/reproduce.py` (D12).

---

## 1. Circuit representation for auto-research

### 1.1 What the loop needs from a format

1. **Emit and diff by code** (the generator/optimizer produces thousands of candidates).
2. **Simulate end-to-end** — gain, phase, *noise*, transient, tolerances.
3. **Compile to buildable artifacts** — schematic + PCB + BOM + Gerbers that a
   student can open in a real EDA tool and fabricate.
4. **Open source, open standard, text-diffable** — no Altium `.SchDoc` (binary),
   no LTspice `.asc` (GUI-only, closed), no Vivado projects. That is precisely
   what all four prior capstone teams used; none of their designs are
   machine-readable today. (Verified by repo file-tree census:
   14× `.SchDoc/.PcbDoc/.BomDoc`, 6× `.asc`, 1× `.sv` — zero open formats.)

### 1.2 Survey verdict (full table in [research/research-circuit-formats.md](research/research-circuit-formats.md))

| Layer | Choice | Why |
|---|---|---|
| **Design IR (source of truth)** | **SKiDL ≥ 2.3.0** (Python, MIT) | Component/net graph in code; since v2.2.2 (Apr 2026) it generates **real `.kicad_sch` schematics for KiCad 6–10** (`generate_schematic()`, `auto_stub` ERC-fixing), plus `generate_pcb()`, netlists, BOM XML, SVG. One object graph → all backends. |
| **Simulation backend** | **ngspice ≥ 44** driven as a batch subprocess (`ngspice -b`) over emitted netlists | Most stable format in the ecosystem; trivially sandboxed/parallelized; BSD-licensed. (PySpice/InSpice shared-library mode is fragile on macOS — see report.) |
| **Buildable output + verification** | **KiCad 10 + `kicad-cli`** | `sch erc --format json --exit-code-violations`, `pcb drc --schematic-parity`, gerber/drill/STEP/BOM/3D-render export — a machine-checkable compile step with exit codes. |
| **Manufacturing exchange (sink only)** | IPC-2581 / Gerbers via kicad-cli | Open standards for fab handoff; never as design source. |
| **Avoid** | tscircuit as primary IR (mm-vs-50-mil grid bug breaks KiCad round-trip; ngspice engine weeks old); EDIF (dead); ODB++ as source (Siemens-controlled); JITX (proprietary); kicad-skip (stale) | |

**Layered answer to the format question.** No single format does all three jobs
well, so the pipeline uses a layered one:

```
Python component/net graph  (SKiDL Circuit; the git-diffable source of truth)
 ├─→ SPICE backend: emit ngspice netlist → .ac/.noise/.tran → score
 ├─→ KiCad backend: generate_schematic(KICAD10) + generate_pcb() → ERC/DRC → gerbers/BOM
 └─→ docs backend:  netlistsvg / kicad-cli pcb render → candidate cards for humans
```

The SPICE netlist layer doubles as the *lossy fast path*: for the high-rate
generate→simulate→score loop, candidates can be emitted as bare ngspice
netlists first (zero dependencies), and only the survivors get lifted to full
SKiDL → KiCad artifacts. Netlists cannot reconstruct schematics (no
symbols/placement) — that's fine for scoring, fatal as a primary IR.

**Convention over hand-written s-expressions.** Never generate `.kicad_sch`
text by hand: the format is only stable within a KiCad major version
(date-stamped, no back-conversion). Going through SKiDL (or KiCad's own IPC
API) absorbs that churn.

---

## 2. Sensitivity evaluation: one E2E evaluator, plus unit regressions

**One candidate = one circuit spec + one estimator implementation + one MCU
configuration.** Every evaluator takes that whole artifact as input. Nothing
that scores J touches a generic front end, a Python re-implementation of the
estimator, or a record that did not pass through the candidate's circuit
([`REDESIGN.md`](../REDESIGN.md) — the previous three-layer split scored
three different artifacts and is retired).

**SNR vocabulary** — the repo reports two named conventions; never
cross-compare them without converting:
- `eta_ps = A_peak / sigma_ps` — per-sample amplitude SNR, used by
  `research-frequency-estimation.md` tables (20 dB ⇔ η = 10);
- `SNR_rms = (V0/√2) / σ_in-band` — record RMS SNR in the noise band
  (~3.0 dB lower than η_ps).

### 2.1 The single E2E evaluator (`pipeline/evaluate.py::evaluate`)

```
candidate (circuit spec + estimator variant + MCU config)
    │
    ├─ SPICE characterization   (circuit_spec.simulate, 2 ngspice runs)
    │    .ac/.noise             → complex H(f), EMF-referred noise spectrum
    │    .tran polarization     → τ_ring → effective blanking
    │    .tran unit impulse     → causal kernel h(t)   (ground truth)
    │
    ├─ record synthesis         (fid.synthesize_adc_record)
    │    per field point B ∈ 25..65 µT: FID(V₀(B), f_L(B)) ⊛ h(t) from t=0,
    │    noise shaped by the candidate's spectrum through H,
    │    ADC rails + quantization
    │
    ├─ estimation               (firmware/core/ via pipeline/fe_binding.py —
    │                            byte-identical to what ships on the MCU)
    │
    └─ score                    J = worst-band σ_B over the field sweep,
                                gates (clip / ring-down / gross / ripple),
                                CRB for context, provenance incl. the
                                FIRMWARE HASH + spec hash
```

Details that carry the audits:

1. **Coil normalization**: explicit `L` + series `R` (never lossless `L` —
   the series R *is* the Johnson-noise source; ngspice `L` has no `Rser`).
   Amplifier noise as physical resistors: series `R = e_n²/4kT` for voltage
   noise, parallel `R = 4kT/i_n²` for current noise — vendor PSpice
   macromodels translate unreliably and often lose noise; physical resistors
   are bulletproof and `.noise`-visible. `.noise` integrates over the full
   sweep to Nyquist (aliasing folding approximated by the full-band
   integral; noted residual).
2. **Tuned vs untuned is a first-class circuit axis** (it reorders which
   amplifier is optimal). The tuned input is a real shunt-C series-resonant
   tank (audit E6: an earlier series-C placement collapsed Q to ~1e-3).
   `preamp_gain` is a scored axis with a clipping gate — the tuned tank's
   step-up fails the ×100 staging on clipping.
3. **V₀↔noise coupling** (E3 finding 3): when a candidate gives winding
   geometry (`wire_d_mm`), `r_coil`/`l_coil` are DERIVED from it
   (`coil_model()`) — the optimizer cannot raise signal without paying
   winding resistance.
4. **Blanking/recovery as physics**: a polarization-coupled current pulse
   rings the input network in `.tran`; the measured decay constant sets
   `blank_eff = max(chosen, 5·τ_ring)`, fail-closed on truncated decays
   (D5). Gated to stay inside half of T2*.
5. **Causal filtering is ground truth**: h(t) comes from a `.tran`
   unit-impulse run — no magnitude/phase reconstruction (earlier
   interpolations produced +1.2 mHz and +16.5 mHz artifacts an optimizer
   would have ground against; noiseless tank pull is now 0.01–0.03 mHz).
6. **The estimator is the shipped C core** (`firmware/core/freq_est.c`,
   float + Q31 fixed builds). Alternative algorithms (`fft`, `zc`) are C
   implementations in the same core, scored as candidate estimator
   VARIANTS through the identical evaluator — never parallel Python
   references. `zoom_fixed` (the Q31 build) is likewise a legal candidate
   estimator for M0+-class targets. A non-converging estimate maps to NaN
   → gross error.
7. **MCU config is a candidate axis**: capture tick (timestamp
   quantization, asserted negligible) and clock grade (ppm → deterministic
   scale bias, reported in nT per card, never folded into σ_B).
8. **Systematics in the records** (REDESIGN.md §4): a paired MC pass
   injects the 100 dB-PSRR-referred buck ripple (50 mV at 2 kHz → 0.5 µV
   at the EMF) through the candidate's own H(f) — the rail-ripple gate is
   SCORED (no seed hijack, σ_B degradation ≤2×), not proxied by V₀ — and
   a mains-harmonic tone (1.8 kHz at −20 dB rel V₀) is reported. Ripple
   and FID see different gain, which is exactly what the proxy missed.
9. **Monte-Carlo tolerance sweep** (`circuit_spec.tolerance_sweep()`,
   optional in `evaluate(with_tolerance=True)`): one ngspice `.control`
   loop with `alter`/`sgauss`/`setseed`, per-iteration in-band spectrum
   integrated in Python (two ngspice quirks handled: stale `inoise_total`
   in control loops; re-runs need `destroy all`); p95 CRB at 2σ tolerances
   (R 1%, C 5%, L 10%).

Measured E2E result (physics V₀, N_MC=150, C zoom estimator): untuned INA /
TL072 fail the scored ripple gate at every band (V₀ ≲ the 0.5 µV referred
tone); the fixed-2.1 kHz tuned JFET fails it at 25 µT — the tank amplifies
the 2 kHz ripple while the FID sits off-resonance — and scores
0.0007–0.0026 nT at 37.5–65 µT, 0.9–1.1× the SHAPED Fisher bound built
from its own SPICE noise spectrum (`crb.freq_crb_shaped`; the flat-density
approximation is invalid at a tank resonance). The per-band family (tank
retuned per field band) passes everywhere: 0.0018/0.0007/0.0005 nT at
25/50/65 µT. The ZC variant
of the thin-budget INA circuit fails the gross gate E2E (100% gross) — the
zero-crossing ruling-out is a pipeline result.

**Known blind spots of the current score** (from the audits — the optimizer
must not be run until these are scored): gain split/CMRR/1-f/GBW of real
amplifiers (a noiseless preamp means gain is ~free until the clip gate
binds), pulse-to-receiver coupling and layout EMI, a blanking switch with
charge injection and saturated-stage recovery, ripple at frequencies other
than the 2 kHz stress tone / part-specific PSRR(f) curves, and component
tolerances in the default scoring path. V₀/T2* remain model predictions
until the wet capture (F1/F2).

### 2.2 Unit regressions of the C core (NOT design scores)

These exercise the estimator build on synthetic vectors without any
candidate — they are bound-tracking and port-validation checks, and
**nothing they produce is a design score**:

- **Golden vectors** (`firmware/host/run_host_tests.py`, C2): 36
  sha256-pinned records; C float vs the numpy mirror (≤0.01 Hz at
  operating SNR) and float-vs-fixed (≤0.05 Hz). The mirror
  (`tools/freq_est_mirror.py`) is a C-side debugging aid, never scored.
- **Sensitivity matrix** (`firmware/host/sensitivity_score.py`, C3): the
  host-built core over 3 fields × 3 T2* × 4 SNRs, per-MCU timestamp
  quantization (negligible, asserted) and clock ppm reported as
  deterministic bias; gated at 0.0426 Hz for configs above the information
  floor.
- **Behavior locks** (`tests/test_estimator_reference.py`, D7 re-anchored):
  zoom ≤1.2× colored CRB 0% gross, fft ≤1.2×, zc ≥100× with ≥90% gross at
  the η_ps = 14.2 dB reference point (the ruling-out fails loudly if the
  SNR regime shifts), plus port-equivalence of the C fft/zc against
  test-local numpy references.
- **Repeatability** (`tests/test_repeatability_m4.py`, D16 re-anchored):
  cycle-to-cycle σ at the bound, and the 1/√M averaging-gain check that
  catches correlated residuals.

### 2.3 Harness mathematics (unchanged)

- `pipeline/fid.py` — FID physics: γ′p constants, the Curie-law transducer
  model `estimate_v0`, coil/front-end noise integrals, the E2E record
  synthesizer, and `generate_record` for the unit vectors above.
- `pipeline/crb.py` — white + colored-noise CRLB (numeric Fisher); validated
  against a dense-covariance solve and an ensemble-estimated covariance
  (`pipeline/test_validation.py`, `tests/test_crb_ensemble.py`). Band-limited
  noise has ~3.5× the spectral density of white noise of equal RMS, so the
  common white-noise CRB is ~2× optimistic in σ.
- `pipeline/systematics.py` — the analytic terms SPICE cannot see: 1/f flicker
  excess (TI SLVA043B/MT-049 closed form: +0.31% in-band for a 10 Hz
  corner), CMRR/PSRR referred terms.

**Blanking finding** (information-theoretic half; the recovery half is the
`.tran` ring-down): frequency information scales as `t²·e^(−2t/τ)` —
concentrated *late* in the record — so dead time is far cheaper than
intuition suggests: 500 ms of blanking costs 1.35× in CRB σ vs 50 ms
(0.0435→0.0587 nT) and 1.22× vs 200 ms. Bias blanking long, gated by
ring-down. (Deterministic CRB computation, regenerated by
`tools/reproduce.py`.)

### 2.4 Scoring harness spec (the estimator gate)

Per candidate: worst-band RMS σ_B and gross-error rate `P(|err| > 1 Hz)`
(gate < 1%) over the 25–65 µT sweep; the systematics are scored per the
candidate's own gates (rail ripple ≲ V₀ at 100 dB PSRR) and the unit-vector
ablations regenerated through the C core by `tools/reproduce.py` (buck
ripple referred at 50 µV destroys the cycle — the coarse seed hijacks onto
the tone, >100 nT — while 0.5 µV referred survives at baseline; comparator
time-walk at V_n = σ_in moves the baseline 0.05 → ~0.9 nT); the clock-ppm
*deterministic* scale error is reported per card. Pass bar for the
estimator axis: ≤ 1.2× CRB, gross < 1%.

### 2.5 MCU stack, without hardware

Architecture that makes sensitivity testable in CI (from the MCU research):

```
core/      portable C99 estimator + shared FID model — NO vendor headers
hal/       thin interfaces: time_source, capture, adc
targets/   rp2040 (PIO timestamping) | stm32 (timer capture) | teensy
sim/       renode/ (STM32)  wokwi-rp2040js/ (PIO-capable)
tools/     gen_fid.py — one generator feeds tests, RESD streams, VCD
```

- **Primary layer — native host tests**: the same estimator core compiled
  for the host, driven by the golden vectors and the sensitivity matrix
  (§2.2). The DESIGN score (§2.1) calls this same host build through
  `pipeline/fe_binding.py` — the emulator path (rp2040js, `sim/rp2040js/`)
  proves the plumbing end-to-end (cross-compiled byte-identical core on an
  emulated Cortex-M0+ recovers the FID frequency to 0.0002 Hz); it is
  functional, NOT a timing oracle.
- **HIL bench** — final acceptance: TCXO term, comparator time-walk, EMI.

**The clock is the floor, not the MCU**: ±1 ppm TCXO at 50 µT = 0.05 nT
un-averageable scale error; a ±20 ppm crystal eats a fifth of the 1 nT
budget *as a bias*. Capture jitter is ~4 orders of magnitude below budget.
**Comparator time-walk** (zero-crossing shift ∝ V_noise/(2πf·A(t)),
growing as the FID decays) is a scored systematic and another argument
against zero-crossing front ends and for the ADC path.

## 3. Pipeline architecture

```
proton-magnetometer-autoresearch/
├── docs/                    # this doc + research reports
├── pipeline/                     # the scoring pipeline (Python + ngspice + C core)
│   ├── evaluate.py          # THE single E2E evaluator: candidate -> J
│   ├── circuit_spec.py      # candidate circuit specs + SPICE characterization
│   ├── fid.py               # FID physics, Curie-law V0, noise model,
│   │                        #   E2E record synthesis + unit vectors
│   ├── fe_binding.py        # ctypes binding to the C estimator core
│   ├── crb.py               # white + colored-noise CRLB
│   ├── systematics.py       # analytic 1/f + CMRR/PSRR terms
│   └── test_validation.py   # standing regression tests (audit v0.0)
├── spec/                    # A1: frozen JSON-able circuit IR + validation
├── backends/                # A2/A4/A5/A6: spice.py, kicad.py(+pcb worker),
│   │                        #   kicad_netlist.py (round-trip), export.py
├── parts/                   # B5: parts DB (e_n, i_n, price, footprint, MPN)
├── optimizer/               # A7: mutations + eval_one + search (subprocess
│   │                        #   pool, dedupe, elite archive, provenance)
├── firmware/                # C1-C4: THE estimator core (freq_est.c zoom +
│   │                        #   fft_est.c + zc_est.c variants, float+fixed),
│   │                        #   host tests + sensitivity job, targets/rp2040
├── sim/rp2040js/            # C4 emulator runner (not a timing oracle)
├── tests/                   # D-suite: fixtures, gates, exploitability
└── tools/                   # reproduce (D4/D11/D12), vectors, mirror
```

**Data flow per candidate:** `candidate (circuit + estimator + MCU config)
→ (SPICE: H(f), noise spectrum, τ_ring, causal h(t)) → candidate-shaped
records → C estimator core → J (worst-band σ_B) + gates → score card`; the
optimizer/agent proposes mutations on ANY candidate axis (topology, parts,
parameters, estimator variant, clock grade); the scorer prunes; survivors
compile to KiCad for human review/build.

### Principles

1. **Open source end to end**: ngspice (BSD), SKiDL (MIT), KiCad (GPL),
   scipy/numpy, Renode/rp2040js (MIT), sigrok. Nothing in the loop requires a
   license server or a GUI click.
2. **One graph, many backends**: the component/net graph is written once;
   SPICE, KiCad, BOM, and docs are all *projections* of it.
3. **Score everything; trust nothing un-scored**: every claim (noise, gain,
   precision) comes from a tool with exit codes or a regression-tested
   analytic model (`test_validation.py`: white CRB vs Rife–Boorstyn closed
   form; colored CRB vs dense-covariance Fisher; the C zoom core vs the
   colored CRB).
4. **Model what emulators can't**: comparator time-walk, clock ppm, blanking
   timing — expressed in the synthetic-signal generator, scored natively.
5. **State the assumptions with the number**: V₀, T2*, SNR convention, and MC
   uncertainty are quoted next to every headline figure. A conditional CRB is
   not a measured sensitivity.
6. **Human-buildable output**: every surviving candidate emits KiCad
   schematic + PCB + BOM + gerbers (the thing the prior teams actually needed
   and the one thing their Altium/LTspice files can't give the next team).

---

## 4. Mapping to the week-2 open problems (honest version)

What the harness *is*: a validated in-silico prior for noise budgeting,
estimator choice, and acceptance targets. What it is **not**: the bench
physics loop, and not yet a layout/coupling simulator. Mapping:

| Week-2 open problem | Pipeline contribution | Not covered by the harness |
|---|---|---|
| 1. Close the physics loop on the bench | Acceptance numbers for the first wet capture (expected V₀ grid, expected σ, SNR targets); V₀×T2* grid shows how much margin each coil class buys | The capture itself; V₀/T2* remain model predictions until then |
| 2. Leave breadboards; layout/EMI | Future KiCad backend with ERC/DRC gates | Pulse-to-receiver coupling, star grounding, shielding — layout physics are not in the score |
| 3. Blanking knife-edge | Two halves: `.tran` ring-down τ (recovery physics, gated) + CRB-vs-blanking curve (bias long: 500 ms costs 1.35×) | Switch charge injection, snubber/dummy-coil design |
| 4. Power rails, modular boards | Rail ripple is a SCORED ablation (regenerated through the C core by `tools/reproduce.py`: 50 mV at 2 kHz referred 50 µV destroys the cycle; PSRR 100 dB survives) and a failing GATE in J (ripple ≲ V₀) | Layout EMI/star grounding still unscored; PSRR uses a flat 100 dB model, not the part's curve |
| 5. Gain and noise budget | Directly scored (e_n AND i_n resistors, real tank, preamp_gain axis with a clipping gate); rail-ripple gate in J | CMRR/PSRR as scored *terms* (analytic only), 1/f analytic (+0.31%), e_nO/GBW of real amplifiers, gain-split optimization |
| 6. Frequency-estimator precision | The estimator is the shipped C core, scored E2E against its CRB on every candidate; the crossing family is ruled out by the pipeline itself (E2E gross-gate failure + bound-ratio ranking) | Real-record validation still requires the wet capture |
| 7. Coil geometry | Coil parameters (R, L, N, tuning C) are scored experiment axes; V₀ derived from the transducer model | Winding/sealing/housing engineering; V₀ anchoring |
| 8. Schedule/procurement | Out of scope | — |

## 5. Immediate next steps

1. **DONE — see TODO.md**: the KiCad backend passes ERC+DRC on an
   INA828-class AFE (`tests/test_kicad_gate.py`); the remaining G2 gates
   are bench/human items (see docs/runbook.md).
2. **Part database** with noise/price pins (INA828, ADA4898, JFET input stage,
   ADS131M04 vs MCU ADC, DG419-class blanking switch) and the Monte-Carlo
   tolerance sweep wired into the score.
3. **Firmware `core/`** (DONE): the estimator IS the portable C core
   (`firmware/core/`, float + Q31 fixed); the CI sensitivity-score job and
   the E2E evaluator both run it — there is no Python estimator to port.
4. **Bench closure** (the real FID): use the harness predictions (V₀ grid,
   expected σ) as the acceptance criteria for the first wet capture — that
   capture is also what replaces the transducer model's assumptions with
   measurements.
