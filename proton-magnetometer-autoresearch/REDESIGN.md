# REDESIGN — one candidate, one evaluator, one code path

**Requirement (2026-09-11):** every evaluation must score a single design —
one candidate = **one circuit + one estimator implementation** — end to end.
Multiple evaluators are fine, but each must evaluate the full E2E system.
The estimator code may be Python or C, but there must be exactly **one**
implementation of it in the scoring path, and **every** evaluation must
include the circuit.

This document states the problem with the current three-layer architecture
and the redesign that satisfies that requirement.

---

## 1. The problem: three layers, three different systems

The pipeline currently has three scoring layers. Each answers a useful
question, but they do **not** evaluate the same artifact:

| Layer | Circuit under test | Estimator code under test |
|---|---|---|
| A — Analog (`poc/circuit_spec.py`) | ✅ the actual candidate netlist: its H(f), noise spectrum, τ_ring shape every MC record | ⚠️ **Python** `zoom_fit`/`zc_fit` (`poc/estimators.py`) — not the code that ships |
| B — DSP (`poc/run_scoring.py`, `poc/fid.py`) | ❌ a generic front end (INA-class e_n, brick-wall 500–3500 Hz, scalar gain, no H(f)) | Python estimator family |
| C — Firmware (`firmware/`) | ❌ the same generic front end | ✅ the shipped C core (`freq_est.c`, float + fixed) |

Consequences (each verified during the E3 audit):

1. **The circuit and the firmware never meet.** No evaluation feeds the C
   `freq_est` records shaped by a candidate's SPICE impulse response. A
   candidate can win J while the firmware that would actually run on it was
   never scored against it.
2. **Two estimator implementations exist** — Python `zoom_fit` and C
   `freq_est`. They are spec-level mirrors, not the same code (different
   FIR, different coarse seed). They drift independently; the C core is
   what ships, yet J is computed from the Python one (Layer A) or from
   vectors Layer C happened to be fed.
3. **Layer B is not an evaluation of any design.** It scores estimator
   code against an idealized, candidate-free front end (brick-wall noise
   band, scalar gain). Its tables are research references, but nothing it
   scores corresponds to a buildable artifact.
4. **A J improvement does not imply a better shipped system.** The optimizer
   mutates the circuit; the scored estimator is Python; the firmware is a
   bystander. The three claims "this circuit is good", "this estimator is
   good", "this firmware meets the gate" are each supported, but never
   jointly.

Also implicit in the current split: the Python estimator family
(`zoom_fit`, `fft_peak`, `zc_fit`, `nlls_fit`) and the C core
(`freq_est.c`) are parallel implementations of overlapping algorithms, so
"the estimator" is not a single versioned artifact anywhere in the repo.

## 2. The redesign principle

> **One candidate = one circuit spec + one estimator implementation.**
> Every evaluator takes that whole artifact as input. Nothing that scores
> J may touch a generic front end, a Python re-implementation of the
> estimator, or a record that did not pass through the candidate's circuit.

Concretely:

* **The C core is the single estimator implementation.** It is the code
  that ships to the MCU, so it is the code the score must measure. Python
  keeps the physics and the mathematics (transducer model, CRB, record
  synthesis, scoring) — it is the *harness*, not a second estimator.
  `poc/estimators.py` is retired from all scoring paths: it survives only
  as a research/analysis reference (clearly labeled), and the D7/D16
  estimator locks are re-anchored on the C core through the same gates.
* **A candidate = circuit + estimator + MCU/clock configuration.** The
  optimizer mutates all three axes of the same artifact: topology and
  parts (circuit), estimator variant and parameters (firmware), MCU tick
  and clock grade (target). Every candidate is evaluated by the same E2E
  evaluator; alternative estimator *algorithms* (FFT peak, zero-crossing,
  NLLS) become alternative candidates — implemented once, in C, in the
  same core — not parallel Python references.
* **All evaluation is E2E.** There is exactly one scoring path:

```
candidate (circuit + estimator + MCU config)
    │
    ├─ SPICE characterization  (backends/spice.py, 2 runs, as today)
    │    .ac/.noise            → complex H(f), EMF-referred noise
    │    .tran polarization    → τ_ring → blank_eff
    │    .tran unit impulse    → causal kernel h(t)   (ground truth)
    │
    ├─ record synthesis        (poc/fid.py, reshaped: "synthesize from a
    │    per field point          candidate", see §3)
    │    B ∈ {25..65 µT}: FID(V₀(B), f_L(B)) ⊛ h(t) from t=0,
    │    noise shaped by the candidate's spectrum through H,
    │    ADC rails + quantization, systematics (ripple/time-walk/tones),
    │    MCU timestamp quantization + clock ppm per the candidate config
    │
    ├─ estimation              (firmware/core/freq_est.c via ctypes host
    │                            build — byte-identical to what ships;
    │                            emulator path proves plumbing)
    │
    └─ score                   J = worst-band σ_B from the C output,
                               gates (clip / ring-down / gross / ripple),
                               CRB computed for context, tolerance
                               sweep p95, provenance + spec hash
```

* Evaluators that remain separate are all E2E over this same artifact:
  the **determinism evaluator** (byte-identical cards), the **adversary
  evaluator** (D5 exploits must fail a gate), and the **tolerance
  evaluator** (B1 p95). They differ in *inputs* (adversarial candidates),
  never in *what system they score*.

## 3. What each existing piece becomes

| Piece | Today | In the redesign |
|---|---|---|
| `poc/fid.py` | generic-front-end record generator used by Layers B and C | record synthesizer for the E2E path (takes the candidate's h(t) + noise spectrum as inputs) and unit-vector generator for C-core regression tests — no longer a standalone evaluator |
| `poc/estimators.py` (zoom/fft/zc/nlls) | Layers A and B scoring path | **retired from scoring**. Kept as analysis references for research plots; `zc_fit` stays only to preserve the ruled-out regression, re-anchored in C |
| `firmware/core/freq_est.c` (zoom core) | Layer C only | **the** estimator of the E2E score; every candidate names it (or a variant) |
| alternative algorithms (FFT peak, ZC, NLLS) | Python implementations in Layer B | become C implementations in the same core (they are small), scored as *candidate estimator variants* through the identical E2E path; the ZC ruling-out regression re-anchors on the C ZC |
| `firmware/host/sensitivity_score.py` (C3 matrix) | generic vectors | kept as a **unit regression** of the C core (bound-tracking, no candidate), clearly labeled not-a-design-score; the E2E per-candidate scoring is the design score |
| `poc/run_scoring.py` (Layer B tables) | standalone DSP layer | becomes context/tooling: CRB validation and M4/M5 ablation machinery re-pointed at the C core; its tables describe the reference operating point, not a design |
| `poc/crb.py`, `poc/systematics.py` | shared math | unchanged (harness mathematics) |
| `backends/*`, `optimizer/*`, `tests/*` | as today | unchanged in role; `eval_one.py` swaps its scoring call to the E2E path |

## 4. The concrete E2E evaluator (one function, one artifact)

New module `evaluation/e2e.py` (or `poc/evaluate.py`) — the single entry
point both the CLI and the optimizer subprocess call:

```
evaluate(candidate) -> card
  candidate = circuit spec (IR) + estimator name + estimator params
              + mcu config (tick, clock ppm)
  1. simulate(candidate.circuit)          # backends/spice.py, 2 passes
  2. for B in sweep, for systematic in {none, ripple, walk, tone}:
       records = synthesize(FID(V0(B)), h_t, noise_spectrum,
                            adc(rails, lsb), systematics, mcu cfg)
       f_hat[i] = freq_est_<name>(records[i])        # C core, ctypes
  3. J = worst-band RMS σ_B (C output), gates from the C records
     (clipping, ring-down, gross errors, ripple survivability)
  4. card: J, per-band J, gates, CRB (context), tolerances p95,
     provenance (git SHA, tool versions, seeds, spec+firmware hash)
```

Notes:

* **Firmware hash joins the provenance.** The card proves which estimator
  build produced the number; the optimizer cannot change J without
  changing either the circuit or the shipped code.
* **Estimator variants as candidates.** `freq_est` (zoom) is the baseline;
  a C `fft_peak` and a C `zc_fit` let the optimizer (and the D5 adversary
  suite) explore the algorithm axis through the identical evaluator — the
  ZC ruling-out becomes an E2E result instead of a Python-only regression.
* **Python-vs-C numerical differences disappear** as a validity concern:
  there is one estimator, so the "C mirror vs Python zoom" agreement
  question (D2/C2) becomes a build-system check, not a scientific one.
* **Speed:** the C core is ~100× faster than Python `zoom_fit` per record
  (the current 150-record MC is seconds, not minutes), so E2E-for-everyone
  also removes today's fastest-vs-full scoring split.

## 5. Migration plan (ordered, each step keeps the suite green)

1. **Expose the C core to Python scoring** — the ctypes harness
   (`firmware/host/run_host_tests.py`) already loads `libfreq_est.so`;
   factor it into `poc/fe_binding.py` so `evaluate()` can call
   `freq_est_f32` / `freq_est_fixed` on arbitrary arrays.
2. **Port the alternative estimators to C** in the same core
   (`fft_est.c`, `zc_est.c`, optional `nlls` reference stays Python as an
   analysis tool). Unit-test each against its Python counterpart on the
   generic vectors before switching paths — porting validation, not
   dual-run scoring.
3. **Build `evaluate(candidate)`** — assemble the E2E record path from
   `circuit_spec.simulate()` outputs + `fid.py` synthesis + the C binding.
   Gate: for the reference circuit, the E2E card must reproduce the
   current headline (zoom-path σ_B within the stated MC CI) before the
   old path is retired.
4. **Re-anchor the estimator locks** (D7/D16/M5/M4) on the C core via the
   E2E records; move the zc ruling-out to the C zc implementation; keep
   the D5 adversary list and re-verify every adversary still fails ≥1 gate.
5. **Retire the Python estimators from scoring paths**; `poc/estimators.py`
   moves to `poc/analysis/` with a header note (research reference, not
   scored). `run_scoring.py` becomes a CRB/ablation context tool over the
   reference operating point — explicitly not a design evaluation.
6. **Candidate schema gains `estimator` + `mcu` fields** (IR `meta`),
   optimizer mutations extend to estimator variant/parameters and MCU
   config; provenance gains the firmware hash.
7. **Docs + fixtures**: regenerate D8/D11/D12 fixtures from the E2E
   evaluator; rewrite README/architecture §2 around the single evaluator;
   run the E7 re-audit (G2 gate) on the new pipeline.

## 6. Risks / trade-offs

* **Porting cost** — FFT-peak and ZC estimators must exist in C before
  they are legal candidates. Mitigation: they are small; the zoom core
  already provides every building block (Goertzel seed, NCO, decimator,
  parabolic refine).
* **Loss of the Python cross-check** — today the Python estimators
  independently confirm the C core. After the redesign that check becomes
  a *unit* test (port-time equivalence on fixed vectors), not a live
  second opinion. Accepted: one implementation is the requirement; the
  equivalence tests run at port time and in CI against pinned vectors.
* **MC cost** — actually improves: the C estimator is ~100× faster per
  record than Python zoom_fit, so the E2E MC is cheaper than the current
  split (which runs Python zoom 150× per candidate).
* **nlls_fit** has no C port (scipy `least_squares`). It stays an
  analysis/reference tool; it was never the shipped algorithm and is
  threshold-limited anyway.

## 7. Acceptance criteria for the redesign

* `evaluate(candidate)` is the only function that produces a J; the
  optimizer, CLI, and CI all call it.
* Every J-producing path includes: SPICE characterization of the candidate
  (H, noise, ring-down, impulse), candidate-shaped records, the C
  estimator, and the candidate's MCU/clock configuration.
* No scoring path references `poc/estimators.py`.
* The E2E card of the reference candidate reproduces today's headline
  numbers within the stated MC CI; all D-suite gates and D5 adversaries
  pass against the new evaluator; determinism fixtures regenerated.
* The E7 re-audit (G2 gate) re-runs on the single-evaluator pipeline and
  confirms no layer evaluates anything but the full system.