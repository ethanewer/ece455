# Audit feedback v0.0 — autoresearch pipeline review

**Scope of review:** alignment of `proton-magnetometer-autoresearch` with the
week-2 project goals (`week2/report.md`), with emphasis on whether the
scoring is scientifically accurate. No code was changed. All headline PoC
numbers were re-executed and reproduced on this machine (ngspice present,
numpy 2.0.2 / scipy 1.13.1).

---

## 1. Verdict summary

**The scoring core is scientifically sound and reproduces.** The colored-noise
Cramér–Rao bound, the noise modeling, the estimator rankings, and the
SPICE-to-nT loop are all correct as far as they go, and they are aimed at the
right target (the analog noise budget, which the week-2 report correctly
identifies as the prior teams' binding constraint). The pipeline is well
aligned with the stated goal: iteratively score the AFE + MCU stack that
turns FID EMF into a field estimate.

**One genuine scientific accuracy issue** (the gyromagnetic-ratio constant,
§3.1) and several alignment gaps between what the research docs say dominates
real-world error and what the PoC actually scores (§4) should be addressed
before the optimizer loop starts running.

## 2. What was independently verified

| Check | Result |
|---|---|
| `run_scoring.py` reproduces | CRB 0.0481 nT, NLLS 0.0460 nT (0.96×), blanking sweep, amplitude sweep — all match README/architecture tables |
| `circuit_spec.py` reproduces | INA828-class 0.0499 nT, TL072-class 0.1259 nT, σ_in = 0.389 µV — matches README |
| Colored-noise CRB implementation | Verified against an independent, explicit covariance-matrix Fisher computation (`J = dsᵀ C⁺ ds` from an ensemble-estimated band-limited covariance, 40k realizations): ratio 0.993. The DFT-domain normalization (β, 2× two-sided weighting, DC/Nyquist handling) is correct |
| White-noise CRB sanity | Matches the closed-form Rife–Boorstyn real-tone bound exactly (1.743e-2 Hz vs 1.74e-2 Hz analytic, N=2000) |
| "Colored noise ⇒ white CRB ~2× optimistic" | Correct: band occupancy 2·2800/20000 = 0.28 ⇒ 3.57× PSD ⇒ 1.89× in σ |
| Noise-resistor trick (`R = e_n²/4kT`) | 7 nV/√Hz → 2959 Ω; hand-integration of 4kT·(120+2959) over the band gives 0.39 µV, matching ngspice `inoise_total` |
| Amplitude sweep linearity | 4× amplitude ⇒ 4.02× σ_B — correct far above the Rife–Boorstyn threshold |
| Blanking scaling | 500 ms blanking costs 1.22× σ — confirms the "information ∝ t²e^(−2t/τ), concentrated late" claim; the advice to bias blanking long is sound and directly resolves the week-2 "blanking knife-edge" (problem 3) |
| ngspice mechanics claims (noiseless behavioral sources, frozen switches, no `Rser`, `.noise` band-integration) | All consistent with the ngspice manual and correctly worked around in the PoC |

The central insight of the pipeline — that the estimator is *not* the
bottleneck (CRB-level DSP gives ~0.05 nT, 20× better than the 1 nT target)
and that the analog noise floor + systematics are — is correct and is exactly
the inversion of the prior teams' priorities that the week-2 report calls for.
The zero-crossing autopsy (50–660× CRB, cannot reach the bound) is consistent
with the published PPM literature and is a valuable, quantified answer to
week-2 problem 6.

## 3. Scientific accuracy issues

### 3.1 Gyromagnetic constant: bare proton vs shielded proton in water (most important)

`fid.py` and all conversions use γp/2π = 42.577478 MHz/T — the **bare**
proton value. A water-sample PPM measures the **shielded** proton:
γ′p/2π = 42.57638507 MHz/T (H₂O, 25 °C, CODATA; the IAGA geomagnetic standard
is 0.042576 Hz/nT). The difference is 25.7 ppm — a *deterministic scale
error* that does not average down:

| B | absolute bias from the wrong constant |
|---|---|
| 25 µT | 0.64 nT |
| 50 µT | 1.29 nT |
| 65 µT | 1.67 nT |

**At 50 µT this alone exceeds the entire 1 nT budget** and is ~25× the
claimed 0.05 nT per-cycle precision. Nuance: for the towfish mission
(anomaly *detection* over a mapped background), relative precision is what
matters and a fixed 25.7 ppm scale error is benign; but the pipeline's stated
goal is "outputs magnetic field intensity," and the MCU research doc already
(rightly) makes a fuss about a ±2 ppm TCXO — a 25.7 ppm constant error is 13×
larger than that term. Decide explicitly: if absolute accuracy matters, use
42.5764 (and note its weak temperature dependence); if only anomaly contrast
matters, record that decision in the objective-function doc so the scoring
stops implying sub-0.1 nT absolute capability.

### 3.2 Misleading constant name/comment in `fid.py`

`GAMMA_HZ_PER_NT = GAMMA_HZ_PER_T * 1e-9   # 42.577478 Hz/nT` — the value is
correctly 0.0425775 Hz/nT, but the comment claims 42.577478 Hz/nT (off by
1e9). The *code* everywhere divides by `42.577478e-3`, which is right; only
the comment/name pair is wrong. In a project whose whole purpose is
scientific scoring, this is exactly the kind of comment that will mislead the
next person (or agent) who edits the file.

### 3.3 "NLLS = 0.96× CRB" presented without its caveat

A Monte-Carlo RMS error cannot sit below a valid CRB. The 0.96× is real and
has a correct explanation — the colored bound deliberately discards
out-of-band information (S=0 ⇒ weight 0), making it conservative, while the
time-domain NLLS weakly exploits the (in the simulation, exactly noise-free)
out-of-band leakage. The research doc states this caveat; the README and
architecture tables quote "0.96× CRB" flat. Keep the caveat attached wherever
the number is quoted, and note the bound is *slightly* optimistic in the
opposite sense for real hardware, where out-of-band noise is never exactly
zero — i.e., treat the colored bound as the floor, which the docs already do.

Also note N_MONTE = 400 ⇒ ~±3.5% MC uncertainty on σ estimates; differences
like zoom_fit 0.0446 vs nlls_fit 0.0445 are within MC noise. Fine for
ranking, but report CIs (or fixed common seeds) once the optimizer starts
comparing close candidates.

## 4. Alignment gaps: what the score does not yet include

These are the places where the *as-implemented* PoC score (σ_B from band
noise only) diverges from what the project's own research says determines
real-world error. None are errors — they are the difference between the PoC
and the specced scoring harness — but they matter because the pipeline's
purpose is to let an optimizer iterate, and an optimizer will exploit
whatever the score ignores.

1. **Systematics are specced but not scored.** The AFE research doc itself
   (§2.9, item 10) says systematics "dominate before amplifier noise does —
   0.07–3 nT reported vs pT CRLB": 60 Hz and its harmonics (the 30th harmonic
   at 1.8 kHz sits right in the FID band), comparator time-walk, clock ppm,
   τ mis-specification. The MCU research doc specs these as ablation M5; the
   PoC implements none of them. As written, `J` would rank a comparator
   front-end design and an ADC front-end design purely on Johnson noise and
   could pick the one with the worse real-world systematic. **Recommend the
   60 Hz-sidetone, ppm-scale, and τ-misspec ablations land in the scorer
   before any optimization loop runs** — this is the single biggest alignment
   risk with the "iteratively improve the design" goal.
2. **Tuned-input topology is excluded from the scored space.** The AFE
   research doc shows the resonant-step-up (tuned coil) is the standard PPM
   front end and *structurally changes* which amplifier is optimal (it lifts
   signal+coil-noise above amplifier e_n). `circuit_spec.py` hard-codes the
   untuned topology (deliberately, per its docstring). But then the
   INA828-vs-TL072 discrimination the PoC demonstrates is only valid for the
   untuned case. Tuning C (with its ring-down τ = 2Q/ω₀ ↔ dead-time cost)
   should be one of the first axes the loop explores, since it can flip the
   part ranking the PoC is showcasing.
3. **Assumed transducer parameters are unanchored.** V0 = 2 µV, R = 120 Ω,
   L = 2 mH, T2* = 1.5 s are plausible (Koehler: "order of microvolts") but
   are not tied to any measured coil, and the score is *linear* in V0 (0.5 µV
   → 0.184 nT). The pipeline declares the coil "given," which conflicts
   mildly with week-2 open problem 7 (settle coil geometry from first
   principles) — acceptable as scope, but the scoring docs should state the
   V0/T2* sensitivity explicitly, since the first wet capture (week-2
   problem 1) is what will actually pin these numbers.
4. **Objective function is partially aspirational.** `J = σ_B + λ_dead·… +
   λ_cost·…` with gates (Pd > 0.99 @ Pfa 1e-3, recovery < 20 ms, clipping,
   DRC/ERC) is documented in `architecture.md` §0, but the PoC score is σ_B
   alone: no dead-time term (though the blanking sweep quantifies it), no Pd
   computation, no clipping check (irrelevant at the current gain/amplitude
   but will matter once candidates vary gain), no cost. Fine at PoC stage;
   just don't let the optimizer run on σ_B alone.
5. **Estimator τ knowledge.** `zoom_fit` uses the true τ from the record;
   the research docs show fitting τ costs nothing at the bound, but the
   τ-misspecification ablation (M5) is what would prove it for the *weighted*
   estimator. NLLS does fit τ. Minor.

## 5. Reproducibility concerns (not accuracy, but they protect accuracy)

- **The frequency-estimation research says its MC-verified reference
  implementation lives in `/tmp/fid_bench.py`, `/tmp/run_bench.py`,
  `/tmp/zc_compare.py`** — ephemeral. The zero-crossing 660×/50–100× numbers
  cited in `architecture.md`'s "PoC-verified estimator ranking" are *not* in
  `poc/` (which has only fft/zoom/nlls). Port the ZC estimator and the bench
  into the repo; right now the pipeline's most decision-relevant result (the
  formal ruling-out of the prior teams' estimator family) is not
  re-runnable.
- **Band-edge inconsistency:** analytic noise integration uses 700–3500 Hz;
  the SPICE `.noise` run uses 500–3500 Hz. Effect is small (0.380 vs
  0.389 µV) but should be harmonized so the analytic and SPICE paths are
  comparable by construction.
- The single-pole AA filter (7.2 kHz) leaves out-of-band noise above 3.5 kHz
  unintegrated; at fs = 20 kHz the aliased residue is small but nonzero.
  Worth one line in the model doc.
- Minor numeric drift: `architecture.md` quotes blanking 0.044→0.059 nT; the
  PoC prints 0.0435→0.0587. Also `B = f/0.042577` vs "23.4875 nT/Hz" in the
  research doc (1/0.042577478 = 23.4870). Cosmetic, but keep one source of
  truth for constants.

## 6. Alignment with week-2 goals (overall assessment)

| Week-2 priority | Pipeline status |
|---|---|
| 1. Close the physics loop on the bench | Correctly treated as out-of-sim scope; the harness *outputs* (expected V0, expected σ, SNR targets) are exactly the right acceptance criteria for the first wet capture. Good. |
| 2. Leave breadboards / layout | Represented only via the future KiCad backend (ERC/DRC gates). Appropriately deferred. |
| 3. Blanking knife-edge | **Resolved in principle** by the CRB-vs-blanking result (bias blanking long; 500 ms costs 1.2×). One of the strongest outputs. |
| 4. Power-rail / modular-board discipline | Future KiCad backend + gates. Appropriately deferred. |
| 5. Gain/noise budget | Directly scored; INA-vs-TL072 PoC discrimination reproduces. Caveat: tuned-input axis (§4.2) may reorder the conclusion. |
| 6. Frequency-estimator precision | **Resolved with margin**; correct estimator family identified; ZC formally ruled out. Caveat: port the ZC bench into the repo (§5). |
| 7. Coil geometry | Explicitly out of scope ("coil is given"). Acceptable, but note the V0/T2* anchoring issue (§4.3). |
| 8. Schedule/procurement | Out of scope. |

**Bottom line:** the scoring math is right and verified; the physics constant
in §3.1 needs a decision; and the scorer needs the systematics/ablation layer
its own research docs specify before the score can be trusted to steer an
optimizer toward designs that survive the bench.
