# Auto-research pipeline for the proton-magnetometer receiver

**Scope.** We have a coil and a power source. This pipeline designs and scores
everything downstream of the coil: the analog front end (blanking, preamp,
bandpass, gain, ADC driver), and the microcontroller signal-processing stack
that turns the induced EMF (free induction decay, FID) into a magnetic-field
estimate. Goal sensitivity: **< 1 nT per cycle ⇒ frequency precision
< 0.0426 Hz** (shielded-proton γ′p = 0.0425764 Hz/nT) on a 1–3 kHz decaying
sinusoid of µV amplitude.

**Status: scoring prototype.** What exists and runs today is the objective
function and its three evaluation layers (below), validated by regression
tests (`poc/test_validation.py`). The optimizer loop, part database, SKiDL→KiCad
backend, and C firmware core are designed but not built — do not start a
search agent on the PoC score alone; it is honest about noise but still blind
to several real failure modes (see §2.1 caveats and §4).

This document answers the two framing questions for the `autoresearch` branch:

1. **What circuit representation makes an auto-research loop efficient?**
2. **How do we score circuit + MCU stacks for sensitivity, numerically, without
   hardware?**

It synthesizes four research passes (full reports in
[`docs/research/`](research/)) plus a working proof-of-concept in
[`poc/`](../poc/) that closes the loop on this machine, and incorporates the
v0.0 external audits of both.

---

## 0. The objective function (everything else serves this)

**One** J is implemented, in `poc/circuit_spec.py::score()`:

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
  terms of §3c of `run_scoring.py` as reported biases.

The physics chain:

```
B [T] ──γ′p──> f_L [Hz] ──coil──> FID EMF [µV]
        ──AFE transfer H(f) + noise (SPICE)──> ADC counts
        ──estimator (MCU firmware)──> f̂ ──/γ′p──> B̂
        sigma_B = sigma_f / 0.0425764 Hz/nT
```

Unit warnings (both v0.0 audits caught variants of this): 42.5764 **MHz/T**
= 42.5764 **Hz/µT** = **0.0425764 Hz/nT** — not 42.5764 Hz/nT. And the
42.577478 MHz/T often quoted is the **bare** proton; a water PPM measures the
**shielded** proton, 42.57638474 MHz/T (CODATA 2018; the 2014 value
42.57638507 differs by 7.8 ppb) — 25.7 ppm lower than the bare value, worth
~1.3 nT of scale bias at 50 µT if you use the wrong one for absolute values.
`poc/fid.py` holds the single source of truth.

**What the score means — the conditional headline.** The DSP result people
quote from this repo ("~0.05 nT/cycle") is a *Cramér–Rao bound conditional on
the assumed transducer amplitude*. The transducer model
(`fid.estimate_v0`, spin-1/2 Curie law: M₀ = n·µ_p²·B_pol/(kT) — 3× the
classical Langevin n·µ_p²·B_pol/(3kT) an earlier revision coded; audit E6),
EMF = µ₀·M₀·A·ω·N) says a Hook-Line-class coil (530 turns, 3 cm bore,
20 mT polarization) produces **V₀ ≈ 0.41 µV** — not the 2 µV the first
revision assumed. The honest grid (`run_scoring.py` §2, INA-class e_n,
blanking 200 ms):

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

## 2. Sensitivity evaluation of circuit + MCU stacks

Three evaluation layers, each catching errors the others can't (full reports:
[AFE](research/research-afe-evaluation.md) ·
[frequency estimation](research/research-frequency-estimation.md) ·
[MCU stacks](research/research-mcu-evaluation.md)).

**SNR vocabulary** — the repo reports two named conventions; never
cross-compare them without converting:
- `eta_ps = A_peak / sigma_ps` — per-sample amplitude SNR, used by
  `research-frequency-estimation.md` tables (20 dB ⇔ η = 10);
- `SNR_rms = (V0/√2) / σ_in-band` — record RMS SNR in the noise band
  (`run_scoring.py`, ~3.0 dB lower than η_ps).

### 2.1 Layer A — analog front end, from a SPICE netlist

Per candidate netlist (ngspice, batch; implemented in `poc/circuit_spec.py`):

1. **Normalize**: coil = explicit `L` + series `R` (never lossless `L` — the
   series R *is* the Johnson-noise source; ngspice `L` has no `Rser`).
   Amplifier noise as physical resistors: series `R = e_n²/4kT` for voltage
   noise, parallel `R = 4kT/i_n²` for current noise — vendor PSpice
   macromodels translate unreliably and often lose noise; physical resistors
   are bulletproof and `.noise`-visible.
2. **`.ac` over the full band to Nyquist** → the end-to-end transfer H(f),
   *including any tuned-input resonant step-up*. H(f) is then applied to the
   **signal** in the scoring loop, not just the noise — the netlist's real
   bandpass (MFB in the demo) shapes the FID exactly as the hardware would.
   (The v0.0 PoC brick-walled noise in software and reduced the netlist to a
   scalar gain; fixed.)
3. **`.noise` over the sweep** → `inoise_spectrum(f)` (EMF-referred); the ADC
   noise = that spectrum × |H(f)|, integrated over the full sweep to Nyquist
   (aliasing folding approximated by the full-band integral; noted residual).
4. **Tuned vs untuned is a first-class axis** (v0.0 audit: it can reorder
   which amplifier is optimal). The demo scores untuned-INA, untuned-TL072,
   and tuned-series-resonant-JFET candidates on the same harness. The tuned
   input is a real series-resonant tank (audit E6: an earlier revision put
   `C_tune` in series toward the high-Z amp tap, Q collapsed to ~1e-3 and
   the step-up vanished; corrected netlist: `C_tune` shunts the amp input
   node — tank gain ≈ 61× loaded Q, τ_ring ≈ 11 ms). Measured result
   (physics V₀, N_MC=150, zoom_fit, in-band σ):
   untuned INA 0.251 nT; untuned TL072 0.645 nT; tuned JFET 0.027 nT — the
   tuned input lifts signal and coil noise together relative to amplifier
   noise, exactly as the Overhauser noise-modeling literature predicts, and
   it *reorders* the amplifier ranking. The tuned JFET's J is limited by a
   scored physical systematic (the fixed tank, detuned +2.0 Hz from f_L,
   pulls the estimate +1.2 mHz — verified against an analytic Lorentzian;
   the scoring path applies the chain causally from t = 0 and slices at
   blanking), and its x100 preamp staging fails the clipping gate —
   `preamp_gain` is a scored candidate axis.
5. **Blanking/recovery as physics, not deleted samples** (v0.0 audit): the
   netlist carries a polarization-coupled current pulse (1 mA collapsing at
   400–500 µs); a `.tran` run measures the input network's ring-down decay
   constant (τ ≈ 0.4–0.5 ms untuned), and the effective blanking is
   `max(chosen, 5·τ_ring)` — gated to stay inside half of T2*. The
   information-theoretic blanking curve (below) complements this; it does
   not replace it.
6. **Clipping gate**: peak ADC excursion vs 0.9·FS/2, enforced in the MC
   (records clip at the rails before quantization) — irrelevant at today's
   gains, decisive once candidates vary gain.
7. **Monte Carlo tolerance sweep** via ngspice `.control` loops with
   `alter`/`sgauss` (no `.step` in ngspice); worst-case via corner limits —
   designed, not yet wired into the demo.

Output: shaped noise σ_in, H(f) on the FFT grid, τ_ring — the numbers the DSP
layer consumes. Standing validation: analytic coil+e_n integration matches
ngspice `inoise_total` to <1% on this machine (0.65% measured for the INA
candidate); regression-tested via the committed ngspice fixture
(`tests/test_ngspice_layer.py`, D1/D9).

**Known blind spots of the current score** (from the audits — the optimizer
must not be run until these are scored): gain split/CMRR/PSRR/1-f/GBW,
pulse-to-receiver coupling and layout EMI, power-rail ripple, saturation
recovery of real amplifier stages, and component tolerances.

### 2.2 Layer B — DSP/estimator, from synthetic records

`fid.py` generates sampled, quantized records exactly as an MCU sees them:
physics (FID amplitude from the Curie-law transducer model, ∝ B_pol·N·r²·B),
band-limited front-end noise, gain, ADC quantization, blanking dead-time
window, optional narrowband interferers. Then:

- **Analytic floor**: colored-noise CRLB from the numeric Fisher information
  (DFT-domain, 1/S(f)-weighted, out-of-band bins carry zero weight — the
  conservative choice). *Both* audits independently validated this
  implementation; `test_validation.py` re-checks it against a dense
  covariance solve every run. Band-limited noise has ~3.5× the spectral
  density of white noise of equal RMS, so the common white-noise CRB is
  ~2× optimistic in σ.
- **Empirical**: Monte-Carlo RMS nT error of the actual estimator code on
  synthetic records (same vectors later feed the MCU firmware's CI). Phase is
  randomized per run; seeds are shared across estimators (paired comparison);
  MC uncertainty ~±3.5% (1σ) at N=400 is stated with every table.

Measured at the reference point (2 µV, T2* = 1.5 s, η_ps = 14.2 dB):

| estimator | × CRB | gross >1 Hz | verdict |
|---|---|---|---|
| NLLS (staged, zoom-seeded) | ~22 (conditioned runs; RMS incl. divergences is tail-dominated and chaotic) | 2% | practical reference; 4-param LSQ is threshold-limited below ~15 dB |
| zoom/matched filter (exp-weighted, FIR-decimated) | 1.02 | 0% | **recommended** |
| zero-padded FFT + log-parabolic | 1.05 | 0% | cheap fallback |
| zero-crossing (interp crossings + WLS mean period) | ~3800 | 100% | **ruled out, in-repo regression** |

The zero-crossing row is the in-repo autopsy of the prior teams' approach
(`zc_fit` implements the *best-practice* variant: interpolated crossings,
variance-optimal slope² weights, cycle-slip filtering). It floors at
σ_f ~ 8 Hz at this SNR because crossing timestamps destroy the inter-sample
phase continuity where the information lives. (The frequency-estimation
research measured 660× CRLB *wideband at higher per-sample SNR*; the 3800×
here is the narrowband case at η_ps = 14.2 dB. Different SNR conventions —
do not compare the numbers directly, compare the conclusion.)
Note a naive crossing-time-on-index regression is far worse still (70%+ gross
from cycle slips); `zc_fit` is already the best-practice version.

**Blanking finding** (information-theoretic half; the recovery half is
Layer A's `.tran`): frequency information scales as `t²·e^(−2t/τ)` —
concentrated *late* in the record — so dead time is far cheaper than
intuition suggests: 500 ms of blanking costs 1.35× in σ_f vs 50 ms
(0.0435→0.0587 nT) and 1.22× vs 200 ms. Bias blanking long, gated by
ring-down.

### 2.2.1 Scoring harness spec (the estimator gate)

Per candidate estimator: RMS nT error and bias over an SNR × T2* × blanking
matrix; gross-error rate `P(|err| > 1 Hz)` (gate < 1%); the M5 ablations —
τ-misspecification (zoom at 0.5×/2× wrong τ: ≤1.07× CRB, measured), in-band
narrowband tones (60 Hz and its 30th harmonic at 1.8 kHz: measured identical
to baseline within MC — 1.8 kHz sits 329 Hz from f_L, outside zoom's ±20 Hz
residual grid), comparator time-walk (B2, scored: zoom 0.049 → 0.89 nT with
V_n = σ_in — the deterministic cost of a ZC front end), supply-rail ripple
through PSRR (B3, scored: a 2.0 kHz buck ripple referred at 50/5 µV destroys
the cycle by hijacking the coarse FFT seed — 3026 nT — while 0.5 µV referred
(PSRR 100 dB) survives at 0.055 nT; design rule: referred ripple ≲ V₀
requires PSRR ≳ 100 dB against 50 mV ripple), and the clock-ppm
*deterministic* scale error (below); the 1/f and CMRR terms are analytic
(`poc/systematics.py`: 1/f excess +0.31% in-band for a 10 Hz corner; 1 V
common-mode at CMRR 100 dB → 10 µV referred — SPICE sees neither);
phase randomized; common seeds; ~3.5% MC CI. Pass bar: ≤ 1.2× CRB, |bias|
< 0.2·σ, gross < 1%.

### 2.3 Layer B′ — MCU stack, without hardware

Architecture that makes sensitivity testable in CI (from the MCU research):

```
core/      portable C99 estimator + shared FID model — NO vendor headers
hal/       thin interfaces: time_source, capture, adc
targets/   rp2040 (PIO timestamping) | stm32 (timer capture) | teensy
sim/       renode/ (STM32)  wokwi-rp2040js/ (PIO-capable)
tools/     gen_fid.py — one generator feeds tests, RESD streams, VCD
```

- **Primary layer — native host tests** (the score lives here): the CI
  `sensitivity-score` job compiles the *same* estimator core for the host,
  runs it over the synthetic-FID matrix with per-MCU timestamp quantization
  (8 ns RP2040 / 5.9 ns STM32 — both negligible) and per-clock ppm error
  injected as a *deterministic scale* (a constant ppm multiplies total field;
  the anomaly bump subtracts — see the ablation table in `run_scoring.py`),
  emits σ_f/bias JSON, gates at 0.0426 Hz.
- **Emulator layer** — plumbing only: Renode (STM32; GPIO/RESD injection,
  Robot Framework CI) and rp2040js/Wokwi (PIO-capable, custom-chip FID
  generator). Renode is *functional, not cycle-accurate* — it cannot predict
  jitter; use it to prove edges/timestamps move correctly through the firmware.
- **HIL bench** — final acceptance: TCXO term, comparator time-walk, EMI.

**The clock is the floor, not the MCU**: ±1 ppm TCXO at 50 µT = 0.05 nT
un-averageable scale error; a ±20 ppm crystal eats a fifth of the 1 nT budget
*as a bias* (and ~the whole budget for absolute accuracy — see §0's
absolute-vs-anomaly decision). Capture jitter is ~4 orders of magnitude below
budget. **Comparator time-walk** (zero-crossing shift ∝ V_noise/(2πf·A(t)),
growing as the FID decays) is a systematic that must be modeled in synthetic
tests — and it is another argument against zero-crossing front ends and for
the ADC path.

---

## 3. Pipeline architecture

```
proton-magnetometer-autoresearch/
├── docs/                    # this doc + research reports
├── poc/                     # working loop, this machine (Python + ngspice)
│   ├── fid.py               # FID physics, Curie-law V0, noise model, records
│   ├── estimators.py        # fft_peak / zoom_fit / zc_fit / nlls_fit
│   ├── crb.py               # white + colored-noise CRLB
│   ├── run_scoring.py       # CRB validation, V0xT2* grid, M5 ablations
│   ├── circuit_spec.py      # JSON spec -> ngspice -> H(f)-shaped MC -> J
│   └── test_validation.py   # standing regression tests (audit v0.0)
├── spec/                    # A1: frozen JSON-able circuit IR + validation
├── backends/                # A2/A4/A5/A6: spice.py, kicad.py(+pcb worker),
│   │                        #   kicad_netlist.py (round-trip), export.py
├── parts/                   # B5: parts DB (e_n, i_n, price, footprint, MPN)
├── optimizer/               # A7: mutations + eval_one + search (subprocess
│   │                        #   pool, dedupe, elite archive, provenance)
├── firmware/                # C1-C4: core/freq_est.c (float+fixed), host
│   │                        #   tests + sensitivity job, targets/rp2040
├── sim/rp2040js/            # C4 emulator runner (not a timing oracle)
├── tests/                   # D-suite: fixtures, gates, exploitability
└── tools/                   # reproduce (D4/D11/D12), vectors, mirror
```

**Data flow per candidate:** `spec → (SPICE: H(f), noise spectrum, τ_ring,
clipping) → (CRB + MC: σ_B, gross rate) → J + gates → score card`; the
optimizer/agent proposes mutations (topology swaps, part swaps, parameter
moves); the scorer prunes; survivors compile to KiCad for human review/build.

### Principles

1. **Open source end to end**: ngspice (BSD), SKiDL (MIT), KiCad (GPL),
   scipy/numpy, Renode/rp2040js (MIT), sigrok. Nothing in the loop requires a
   license server or a GUI click.
2. **One graph, many backends**: the component/net graph is written once;
   SPICE, KiCad, BOM, and docs are all *projections* of it.
3. **Score everything; trust nothing un-scored**: every claim (noise, gain,
   precision) comes from a tool with exit codes or a regression-tested
   analytic model (`test_validation.py`: white CRB vs Rife–Boorstyn closed
   form; colored CRB vs dense-covariance Fisher; zoom vs colored CRB).
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
| 3. Blanking knife-edge | Two halves: `.tran` ring-down τ (recovery physics, gated) + CRB-vs-blanking curve (bias long: 500 ms costs 1.2×) | Switch charge injection, snubber/dummy-coil design |
| 4. Power rails, modular boards | Rail ripple is a SCORED ablation (run_scoring [3e]: 50 mV at 2 kHz referred 50 µV destroys the cycle; PSRR 100 dB survives) and a failing GATE in J (ripple ≲ V₀) | Layout EMI/star grounding still unscored; PSRR uses a flat 100 dB model, not the part's curve |
| 5. Gain and noise budget | Directly scored (e_n AND i_n resistors, real tank, preamp_gain axis with a clipping gate); rail-ripple gate in J | CMRR/PSRR as scored *terms* (analytic only), 1/f analytic (+0.31%), e_nO/GBW of real amplifiers, gain-split optimization |
| 6. Frequency-estimator precision | Estimator family scored against CRB in-repo; crossing family ruled out with a reproducible regression | Real-record validation still requires the wet capture |
| 7. Coil geometry | Coil parameters (R, L, N, tuning C) are scored experiment axes; V₀ derived from the transducer model | Winding/sealing/housing engineering; V₀ anchoring |
| 8. Schedule/procurement | Out of scope | — |

## 5. Immediate next steps

1. **DONE — see TODO.md**: the KiCad backend passes ERC+DRC on an
   INA828-class AFE (`tests/test_kicad_gate.py`); the remaining G2 gates
   are bench/human items (see docs/runbook.md).
2. **Part database** with noise/price pins (INA828, ADA4898, JFET input stage,
   ADS131M04 vs MCU ADC, DG419-class blanking switch) and the Monte-Carlo
   tolerance sweep wired into the score.
3. **Firmware `core/`**: port `zoom_fit` to portable C (fixed-point mixer +
   running weighted sums); wire the CI sensitivity-score job against
   `fid.generate_record` vectors.
4. **Bench closure** (the real FID): use the harness predictions (V₀ grid,
   expected σ) as the acceptance criteria for the first wet capture — that
   capture is also what replaces the transducer model's assumptions with
   measurements.
