# Auto-research pipeline for the proton-magnetometer receiver

**Scope.** We have a coil and a power source. This pipeline designs and scores
everything downstream of the coil: the analog front end (blanking, preamp,
bandpass, gain, ADC driver), and the microcontroller signal-processing stack
that turns the induced EMF (free induction decay, FID) into a magnetic-field
estimate. Goal sensitivity: **< 1 nT per cycle ⇒ frequency precision < 0.0426 Hz**
(γp = 42.577 Hz/nT) on a 1–3 kHz decaying sinusoid of µV amplitude.

This document answers the two framing questions for the `autoresearch` branch:

1. **What circuit representation makes an auto-research loop efficient?**
2. **How do we score circuit + MCU stacks for sensitivity, numerically, without
   hardware?**

It synthesizes four research passes (full reports in
[`docs/research/`](research/)) plus a working proof-of-concept in
[`poc/`](../poc/) that closes the loop on this machine today.

---

## 0. The objective function (everything else serves this)

Every candidate design — analog or firmware — is scored by one number, plus
gates:

```
J = RMS field error per cycle  σ_B  [nT]
    + λ_dead · (dead_time / T2*)            # blanking eats record
    + λ_cost  · BOM cost
gates: no clipping; Pd > 0.99 @ Pfa 1e-3; DRC/ERC clean; recovery < 20 ms
```

with the physics chain:

```
B [T] ──γp──> f_L [Hz] ──coil──> FID EMF [µV]
        ──AFE transfer H(f) + noise σ_in (SPICE)──> ADC counts
        ──estimator (MCU firmware)──> f̂ ──/γp──> B̂
        σ_B = σ_f / 42.577 Hz/nT
```

**Headline PoC numbers** (2 µV FID, T2* = 1.5 s, 1.5 s record, 200 ms blanking,
0.39 µV in-band noise, 16-bit ADC):

| quantity | value |
|---|---|
| Colored-noise Cramér–Rao bound | 0.048 nT |
| zoom/matched-filter estimator (MC) | 0.046 nT (1.00× CRB) |
| NLLS reference estimator | 0.046 nT (0.96× CRB) |
| zero-padded FFT + parabolic | 0.048 nT (1.05× CRB) |
| wrapped-increment (zero-crossing family) | **~50× worse variance** — cannot reach CRB |

The DSP stack is *not* the bottleneck: with a sane noise budget the CRB gives
**pT-class precision per cycle** — 20× better than the 1 nT target. The budget
is set by the analog chain (FID amplitude vs input-referred noise) and by
systematics (clock ppm, comparator time-walk, 60 Hz harmonics). This inverts
the prior teams' priorities: they agonized over frequency-measurement
precision (FPGA, PIO tricks) while their analog noise floor was the binding
constraint.

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

### 2.1 Layer A — analog front end, from a SPICE netlist

Per candidate netlist (ngspice, batch):

1. **Normalize**: coil = explicit `L` + series `R` (never lossless `L` — the
   series R *is* the Johnson-noise source; ngspice `L` has no `Rser`).
   Replace blanking switches with explicit `RON`/`ROFF` resistors for noise
   runs (`.noise` linearizes at the DC operating point — switches freeze).
   Build filters from real R/L/C: behavioral `E`-Laplace blocks are
   **noiseless and sever noise propagation**.
2. **`.ac`** → end-to-end transfer `H(f)` (signal path, incl. any resonant
   step-up of the tuned coil).
3. **`.noise` over the FID band** (e.g. `dec 100 500 3.5k`) → `inoise_total`
   is *already* the band-integrated RMS input-referred noise — no post-processing.
   `pts_per_summary=1` once to attribute noise per device.
4. Amplifier noise the robust way: **physical resistor `R = e_n²/4kT` in series
   with the input** of a noiseless behavioral gain block (exactly what the PoC
   does). Vendor PSpice macromodels translate unreliably and often lose noise.
5. **ADC contribution**: `(e_adc,inband / G(f_L))²` added to `σ_n²`. At analog
   gain ≥ 1000 a 24-bit ΔΣ (e.g. ADS131M04 ≈ 5.4 nV referred) is negligible; a
   12-bit MCU ADC is a first-order term unless oversampled aggressively.
6. **`.tran` verification** (catches what LTI can't): polarization transient +
   blanking switch opening + `trnoise` sources; measure recovery dead time,
   clipping, ring-down (tuned-circuit ring-down τ = 2Q/ω₀ — a Q=23 tank costs
   ~15 ms, cheap; saturated amplifier stages cost 10–100 ms, not cheap).
7. **Monte Carlo tolerance sweep** via ngspice `.control` loops with
   `alter`/`sgauss` (no `.step` in ngspice); worst-case via corner limits.

Output: `σ_in` (RMS noise referred to coil EMF) and `H(f_L)` — the two numbers
the DSP layer consumes.

### 2.2 Layer B — DSP/estimator, from synthetic records

`fid.py` generates sampled, quantized records exactly as an MCU sees them:
physics (FID amplitude ∝ B·B_pol), band-limited front-end noise, gain, ADC
quantization, blanking dead-time window. Then:

- **Analytic floor**: colored-noise CRLB computed from the numeric Fisher
  information (DFT-domain, `1/S(f)`-weighted — *band-limited* noise has
  3.5× the spectral density of white noise of equal RMS, so the common
  white-noise CRB is ~2× optimistic in σ; our implementation matches
  Monte-Carlo ground truth to 0.96×).
- **Empirical**: Monte-Carlo RMS nT error of the actual estimator code on
  synthetic records (the same vectors later feed the MCU firmware's CI).

PoC-verified estimator ranking (this is the pipeline's DSP knowledge base):

| estimator | × CRB | MCU cost | verdict |
|---|---|---|---|
| NLLS (4-param damped sinusoid) | 0.96 | high | reference bound |
| exponential-weighted zoom (matched filter, FIR-decimated) | 1.00 | ~few M MACs | **recommended** |
| zero-padded FFT + log-parabolic | 1.05 | one FFT | cheap fallback, excellent |
| wrapped-increment / zero-crossing family | ~50–100 | lowest | **unusable** at these SNRs |

The zero-crossing result is a quantified autopsy of the prior teams' approach:
increment estimators discard inter-sample phase continuity; their error floors
at `σ_φ·√(fs)/(2π√T_eff)` regardless of record SNR — the information is in the
coherent phase, which crossing timestamps destroy. (Independent corroboration:
the frequency-estimation research measured zero-crossing at **660× CRLB
wideband** in its own Monte Carlo, and the 2023–24 PPM literature has moved to
phase-fitting for the same reason.)

**Blanking finding** (for the blanking-timing knife-edge the week-2 report
flagged): frequency information scales as `t²·e^(−2t/τ)` — concentrated
*late* in the record — so dead time is far cheaper than intuition suggests:
500 ms of blanking costs only ~1.2× in σ_f (0.044→0.059 nT). Blanking can be
generous; short T2* is the real killer.

### 2.2.1 Scoring harness spec (the estimator gate)

Per candidate estimator: RMS nT error and bias over an SNR × T2* × blanking
matrix, gross-error rate (`P(|err| > 1 Hz)`, gate < 1%), ablations (60 Hz
sidetone, TCXO ppm as deterministic scale error, τ mis-specification), and
MACs/call cost. Pass bar: ≤ 1.2× CRB, |bias| < 0.2·σ.

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
  injected as a scale factor, emits σ_f/bias JSON, gates at 0.0426 Hz.
- **Emulator layer** — plumbing only: Renode (STM32; GPIO/RESD injection,
  Robot Framework CI) and rp2040js/Wokwi (PIO-capable, custom-chip FID
  generator). Renode is *functional, not cycle-accurate* — it cannot predict
  jitter; use it to prove edges/timestamps move correctly through the firmware.
- **HIL bench** — final acceptance: TCXO term, comparator time-walk, EMI.

**The clock is the floor, not the MCU**: ±1 ppm TCXO at 50 µT = 0.05 nT
un-averageable scale error (a ±20 ppm crystal alone eats the entire 1 nT
budget); capture jitter is ~4 orders of magnitude below budget. **Comparator
time-walk** (zero-crossing shift ∝ V_noise/(2πf·A(t)), growing as the FID
decays) is a systematic that must be modeled in synthetic tests — and it is
another argument against zero-crossing front ends and for the ADC path.

---

## 3. Pipeline architecture

```
proton-magnetometer-autoresearch/
├── docs/                    # this doc + research reports
├── poc/                     # working loop, this machine (Python + ngspice)
│   ├── fid.py               # FID physics + AFE noise model + record generator
│   ├── estimators.py        # fft_peak / zoom_fit / nlls_fit
│   ├── crb.py               # white + colored-noise CRLB
│   ├── run_scoring.py       # CRB validation + estimator/blanking sweeps
│   └── circuit_spec.py      # JSON spec -> ngspice -> nT  (the loop, closed)
└── (planned)
    ├── spec/                # component/net graph JSON (the IR source of truth)
    ├── backends/spice.py    # spec -> ngspice netlist (done in poc)
    ├── backends/kicad.py    # spec -> SKiDL -> .kicad_sch/.kicad_pcb -> kicad-cli
    ├── scoring/             # objective fn: σ_B, Pd, dead time, cost gates
    ├── parts/               # part DB: e_n, i_n, GBW, price, footprint
    ├── firmware/core/       # portable C99 estimator (pytest/Unity, CI-scored)
    └── experiments/         # auto-generated candidate cards (sim + render + score)
```

**Data flow per candidate:** `spec → (SPICE: σ_in, H(f), dead time) →
(CRB + MC: σ_B, Pd) → (cost, DRC) → score card`; the optimizer/agent proposes
mutations (topology swaps, part swaps, parameter moves); the scorer prunes;
survivors compile to KiCad for human review/build.

### Principles

1. **Open source end to end**: ngspice (BSD), SKiDL (MIT), KiCad (GPL),
   scipy/numpy, Renode/rp2040js (MIT), sigrok. Nothing in the loop requires a
   license server or a GUI click.
2. **One graph, many backends**: the component/net graph is written once;
   SPICE, KiCad, BOM, and docs are all *projections* of it.
3. **Score everything; trust nothing un-scored**: every claim (noise, gain,
   precision) comes from a tool with exit codes or a validated analytic model
   (the CRB is Monte-Carlo-validated at 0.96–1.00×; treat NLLS-vs-CRB agreement
   as a standing regression test).
4. **Model what emulators can't**: comparator time-walk, clock ppm, blanking
   timing — expressed in the synthetic-signal generator, scored natively.
5. **Human-buildable output**: every surviving candidate emits KiCad
   schematic + PCB + BOM + gerbers (the thing the prior teams actually needed
   and the one thing their Altium/LTspice files can't give the next team).

---

## 4. Mapping to the week-2 open problems

| Week-2 open problem | Pipeline mechanism |
|---|---|
| Close the physics loop on the bench first | The scoring harness *is* the physics loop in silico; the CRB/MC results above set the analog-noise target (≈0.39 µV in-band → 0.05 nT) before any hardware is touched |
| Fix the gain and noise budget | Layer A scores it directly (PoC: INA-class 0.050 nT vs TL072 0.126 nT) |
| Blanking timing knife-edge | CRB-vs-blanking curve: 500 ms blanking costs 1.2×, so bias blanking *long* and safe |
| Validate frequency estimator on real, noisy FID | Layer B' MC harness; zero-crossing family formally ruled out (50–660× CRB) |
| Settle one coil geometry | Coil (R, L, tuning C, ring-down τ=2Q/ω₀) is a scored experiment axis, not a re-derivation |
| Modular boards, test points | Every candidate ships ERC/DRC-clean KiCad + BOM from the same graph |

## 5. Immediate next steps

1. **Port the spec→SKiDL→KiCad backend** (spec schema exists in `circuit_spec.py`;
   SKiDL 2.3 `generate_schematic()` is the enabler). Emit one INA828-class AFE
   and verify `kicad-cli sch erc` + `pcb drc` pass with exit codes.
2. **Part database** with noise/price pins (INA828, ADA4898, JFET input stage,
   ADS131M04 vs MCU ADC, DG419-class blanking switch) so candidates pick real parts.
3. **Firmware `core/`**: port `zoom_fit` to portable C (fixed-point mixer +
   running weighted sums); wire the CI sensitivity-score job against
   `fid.generate_record` vectors.
4. **Bench closure** (the real FID): use the harness predictions (expected FID
   amplitude, expected σ) as the acceptance criteria for the first wet capture.
