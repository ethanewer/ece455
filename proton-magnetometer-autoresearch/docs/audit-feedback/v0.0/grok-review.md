# Audit feedback v0.0 — autoresearch pipeline review

**Scope.** Alignment of `proton-magnetometer-autoresearch` with the week-2
project goals (`week2/report.md`) and with the stated pipeline job: iteratively
improve the analog front end and microcontroller stack that turn FID EMF into
a magnetic-field estimate. Emphasis on whether the **scoring is scientifically
accurate**. No project files were changed as part of this review.

**Method.** Read `docs/architecture.md`, the four reports in `docs/research/`,
and all of `poc/`. Re-derived the white and colored CRBs against the analytic
damped-sinusoid bound; checked gyromagnetic conversion, noise integrals, and the
ngspice `inoise_total` path; ran short Monte-Carlo estimator diagnostics and a
live `circuit_spec.py` SPICE parse (numpy 2.0.2, ngspice on PATH).

---

## 1. Verdict

**The pipeline is pointed at the right slice of the problem, and the core
nT conversion and Cramér–Rao math in `poc/` are correct.** It is not yet a
scientifically faithful design loop. The PoC correctly asks “what RMS field
error does this AFE + estimator get on a decaying ~2 kHz sinusoid?” The week-2
goal is a towfish that actually sees a proton FID and then resolves 1 nT
anomalies. The current score lives in an easy-SNR regime where that second
question is already solved, while the first (does a real µV FID exist and
survive blanking, coupling, and the analog floor?) is assumed away.

The architecture mapping table over-claims that this in-silico harness *is*
week-2 items 1, 3, 6, and 7. It is a useful prior for noise-budget work and
estimator choice. It does not close the physics loop, and it does not yet
score the analog failure modes that killed the prior teams.

**Do not start an optimizer on the PoC score as written.** An agent will
grind amplifier \(e_n\) on an untuned, unfiltered, never-blanked netlist,
report ~0.05 nT, and never pay for a missing bandpass, saturated recovery, or
an optimistic \(V_0\).

---

## 2. What was independently verified

| Check | Result |
|---|---|
| \(\gamma_p/2\pi\) numeric path in `poc/` | `GAMMA_HZ_PER_T = 42.577478e6`; scoring divides Hz by `42.577478e-3` = 0.042577 Hz/nT. 50 µT → 2128.87 Hz. 1 nT ↔ 0.0426 Hz. **Code conversion is correct.** |
| White-noise 4-parameter FIM vs analytic 3-param bound (amp+phase unknown, \(\tau\) known) | Ratio 1.000008 at the PoC operating point. White CRB implementation is right. |
| Colored-noise CRB vs white | Ratio 1.89 = \(\sqrt{1/\beta}\) with \(\beta = 2\cdot 2800/20000 = 0.28\). Matches the “band-limited noise of equal RMS has ~3.5× PSD, ~2× in \(\sigma\)” claim. |
| Occupied-bin weighting (interior out-of-band bins left at \(w=1\)) | Negligible here: 99.996% of \(\partial s/\partial f\) DFT energy is already in-band. Not a material bug at this \(T_2^*\) and bandwidth. |
| Analytic coil + \(e_n\) RMS vs ngspice `inoise_total` | INA-class SPICE 0.389 µV vs analytic 0.391 µV over 500–3500 Hz. The \(R = e_n^2/4kT\) trick works. |
| SPICE gain at \(f_L\) | 959, consistent with noiseless ×1000 and the 1 kΩ + 22 nF anti-alias pole at 7.23 kHz. |
| NLLS vs colored CRB (120 trials) | 0.051 nT RMS vs CRB 0.048 nT ≈ **1.06×**, not the README’s 0.96×. The 0.96× figure is Monte-Carlo luck (N=400 ⇒ ~3.5% relative uncertainty on \(\sigma\)). NLLS does not beat a valid CRB. |
| FFT / zoom / NLLS ranking (40 trials) | All ~0.056 nT. They do not discriminate at the headline SNR; all sit near the bound. |
| `zoom_fit` \(\tau\) misspec (0.5× / 2×, 40 trials) | No material change at this SNR/\(T_2^*\). Oracle \(\tau\) is still a latent issue for short records. |
| \(V_0\) independent of \(B\) | Confirmed: 25 µT vs 65 µT at fixed `v0` does not scale amplitude. Docs say EMF \(\propto B\cdot B_\mathrm{pol}\); the generator does not. |
| ADC range at headline settings | Peak analog ~14 mV on a 2.048 V rail (~0.7% FS). Gain staging and clipping cannot fail. |

The strategic insight — prior teams treated MCU gate-counting / FPGA
reciprocal counting as the 1 nT bottleneck, while an ADC record with a
phase/NLS fit is not the limit — is sound **conditional on analog SNR**.
Zero-crossing / increment estimators discarding inter-sample phase is a real
information loss and is consistent with the PPM literature cited. That
estimator is **not in `poc/`**, so the 50× / 660× figures are not a regression
the pipeline can re-run (see §5).

---

## 3. Scientific accuracy issues

### 3.1 Documents and code disagree on \(\gamma_p\) by 1000× (highest severity for an agent)

`fid.py` states:

```
gamma_p = 42.577478 MHz/T  =>  42.577478 Hz/nT.
```

MHz/T is **Hz/µT**, not Hz/nT. \(42.577478\times10^6\,\mathrm{Hz/T}\) and
\(1\,\mathrm{T}=10^9\,\mathrm{nT}\) give **0.042577 Hz/nT**. The code constant
`GAMMA_HZ_PER_NT = GAMMA_HZ_PER_T * 1e-9` is right; the comment is not.

The same slip is copied into the objective-function docs:

- `architecture.md`: “\(\gamma_p = 42.577\,\mathrm{Hz/nT}\)” and
  \(\sigma_B = \sigma_f / 42.577\,\mathrm{Hz/nT}\)
- `research-afe-evaluation.md`: \(\sigma_B = \sigma_f/42.577\) (three times)

Those formulas are internally inconsistent with the headline 0.048 nT and
with “1 nT ⇒ 0.0426 Hz.” The week-2 report has the same unit label; the
pipeline inherited it.

**The PoC numbers were produced by the code path and are in the right units.**
An agent that implements \(J\) from `architecture.md` §0 would report nT
**1000× too small**. That is the highest-severity scoring bug if this
document set is meant to drive search. Pick one source of truth
(0.042577 Hz/nT, or equivalently 23.487 nT/Hz) and use it in docs, comments,
and code.

### 3.2 Bare proton vs shielded proton in water (absolute scale)

Even the *numeric* constant 42.577478 MHz/T is the **unshielded** (bare)
proton \(\gamma_p/2\pi\). A water-sample PPM measures the **diamagnetically
shielded** proton in H₂O, \(\gamma'_p/2\pi \approx 42.5764\,\mathrm{MHz/T}\)
(CODATA / IAGA, ~0.042576 Hz/nT). The difference is ~26 ppm:

| \(B\) | scale bias from using the bare constant |
|---|---|
| 25 µT | ~0.64 nT |
| 50 µT | ~1.3 nT |
| 65 µT | ~1.7 nT |

At 50 µT this exceeds the 1 nT budget as **absolute** error. For the towfish
mission (anomaly contrast on a mapped total-field line) a *fixed* scale error
is largely benign: a 1 nT bump is still ~1 nT. It is not benign if the
pipeline’s stated product is “magnetic field intensity,” and it is
inconsistent with the MCU note’s emphasis on a ±2 ppm TCXO (a 26 ppm
constant is an order of magnitude larger).

**Decision required, then encode it.** If absolute nT is in \(J\), use the
shielded water value and its weak temperature dependence. If only
cycle-to-cycle / along-track contrast matters, say so in the objective
function so the score stops implying sub-0.1 nT absolute accuracy.

### 3.3 The 0.05 nT / “20× margin” number is not a property of the DSP

Colored CRB at the PoC coil + INA-class noise, 1.5 s record, 200 ms blanking,
\(T_2^*=1.5\,\mathrm{s}\):

| Assumed coil EMF \(V_0\) | Colored CRB |
|---|---|
| 2.0 µV (headline) | 0.048 nT |
| 0.5 µV | 0.19 nT |
| 0.1 µV | **0.96 nT** |

CRB \(\propto 1/V_0\) at fixed noise. `generate_record` takes `v0` and
`b_tesla` as independent knobs. Polarization current is declared “given”
and then unused. \(R=120\,\Omega\), \(L=2\,\mathrm{mH}\), \(V_0=2\,\mu\mathrm{V}\),
\(T_2^*=1.5\,\mathrm{s}\) are not derived from a coil + fluid + \(B_\mathrm{pol}\)
model.

2 µV is a literature **injection** (e.g. JPM-4 simulated Larmor source), not
a prediction from this coil. Prior teams never captured a proton FID. If
the real EMF is even ~10× weaker than the headline, the DSP margin is gone
and the analog floor is the whole problem — which is exactly week-2.

Treating 2 µV as ground truth makes every AFE look like it already beats 1 nT.
The amplitude sweep in `run_scoring.py` exists; the README/architecture
headlines do not lead with it. Score a \(V_0\times T_2^*\) grid, or compute
\(V_0\) from the given coil, and treat 2 µV as an optimistic bound.

### 3.4 The circuit score does not see analog design

`circuit_spec.py` is a noiseless behavioral gain of 100, an RC at ~7.2 kHz,
and another noiseless ×10. Amplifier voltage noise is a single resistor.
Then `generate_record` **always** bricks noise to 700–3500 Hz, independent of
the netlist, and uses only scalar \(|H(f_L)|\) as gain.

The score cannot reward or punish:

- a real bandpass (week-2: no excess gain before the FID is isolated)
- gain split, CMRR, PSRR, 1/f, GBW, saturation
- a tuning capacitor (the AFE research itself says resonance is how you
  stop \(e_n\) from dominating)
- blanking, DG419, snubber, ring-down, recovery

INA vs TL072 (headline 0.050 vs 0.126 nT) only tests datasheet \(e_n\) on an
**untuned** source. That is a slice of the Larmor Lads mistake, not the
failure (breadboard pickup, rail ripple in-band, CMRR, pulse coupling). Both
results are ≪ 1 nT, so under the mission gate they are tied. An optimizer will
grind \(e_n\) and ignore topology.

The AFE note already says a tuned input lifts signal and coil noise together
relative to \(e_n\) and can **reorder** which amplifier is optimal. Excluding
that axis while advertising INA-vs-TL072 as “the way a bench would”
discriminate is scientifically incomplete.

Layer mismatch: SPICE integrates 500–3500 Hz; `fid.generate_record` defaults
to 700–3500 Hz. Small (~3–4% in RMS) but the two layers are not one model.

The AFE research specifies the right integrals,
\(\mathrm{SNR}=\int |H|^2 S_\mathrm{sig}/\int |H|^2 S_n\) with a Lorentzian
FID spectrum. The PoC does not implement them.

### 3.5 Blanking is scored as “delete samples,” not as recovery physics

The CRB-vs-blanking curve is valid information theory: frequency information
weights \(t^2 e^{-2t/\tau}\), so 500 ms of dead time is cheap **after** the
record is already a clean damped sinusoid. Week-2’s knife-edge is the
opposite: too short and the front end is still dead or ringing; too long and
\(T_2^*\) ate the FID.

There is no `.tran`, no switch, no clipping gate, no recovery `< 20\,\mathrm{ms}`
even though those appear in \(J\). “Bias blanking long and safe” is a
dangerous recommendation if the agent never pays for saturation or coupled
polarization transients. The information-theoretic curve should stay; it
must sit next to a recovery/clipping measurement, not replace it.

### 3.6 \(J\) is not implemented, and the written \(J\) is inconsistent

`architecture.md` §0:

```
J = σ_B + λ_dead · (dead_time / T2*) + λ_cost · BOM
gates: no clipping; Pd > 0.99 @ Pfa 1e-3; DRC/ERC clean; recovery < 20 ms
```

`research-afe-evaluation.md`:

```
J = w1·log10(σ_B/1nT) + w2·(1−Pd) + w3·(t_dead/T2*)
    + w4·clipping_margin + w5·gain_flatness_error
```

Weights are unspecified. Dead time is already inside \(\sigma_B\) via the
time vector; adding \(\lambda_\mathrm{dead}\) double-counts unless it is meant
as survey productivity (cycle time vs tow speed), which is never stated.

**Pd > 0.99 @ Pfa \(10^{-3}\)** is Marcum-Q / erfc for *detecting the FID
pulse*, not for detecting a 1 nT wreck along a track. Those are different
tests. Neither is coded. Gross-error rate \(P(|\Delta f|>1\,\mathrm{Hz})\)
is specified in the estimator harness and not coded. The PoC score is RMS nT
alone.

### 3.7 SNR vocabulary is not the same across documents

`run_scoring.py` prints “RMS SNR” as \((V_0/\sqrt{2})/\sigma_\mathrm{in}\) ≈
**11.5 dB** at the headline point (2 µV peak, 0.38 µV in-band RMS).

`research-frequency-estimation.md` tables use \(\eta = A_0/\sigma\)
per-sample, 20 dB \(\Leftrightarrow \eta=10\), and a **white** CRB of 0.018 nT
at a different \((\tau, t_d, T)\).

Conflating those rows with the PoC 0.048 nT colored bound will mis-set analog
targets. Name the SNR definition at every table.

### 3.8 Systematics the docs call “the real battleground” are not in the score

Clock ppm, comparator time-walk, 60 Hz and the 1.8 kHz (30th) harmonic,
phase randomization, \(\tau\) mismatch as a scored ablation: specified in the
MCU / frequency-estimation harness (M5), absent from `poc/`.

A static clock scale error matters less for **anomaly** hunting than the MCU
note implies (constant ppm multiplies total field; the bump still subtracts).
Temperature drift along a tow line would matter; that is also absent.

Comparator time-walk \(\propto V_n/(2\pi f A(t))\) is a real argument against
zero-crossing front ends. The MCU research still centers PIO/timer **edge**
capture and a square-wave FID chip, while the DSP recommendation is ADC +
zoom/NLS. If the loop is supposed to improve microcontroller code that outputs
\(B\), there is no `firmware/core/` — only Python references.

---

## 4. Alignment with week-2 goals

Week-2 priority order vs what the pipeline actually does:

| Week-2 open problem | Pipeline vs goal |
|---|---|
| 1. Close the physics loop on the bench; capture a genuine FID | **Not addressed, and over-claimed.** The harness is a synthetic physics loop. Useful as *acceptance numbers* for the first wet capture (expected \(V_0\), expected \(\sigma\)). It cannot substitute for that capture, and the default 2 µV operating point creates false confidence. |
| 2. Leave breadboards; layout, star ground, shielding | KiCad/ERC/DRC planned, not present. Layout EMI and pulse-to-receiver coupling are not physics in the score. |
| 3. Blank with a timed analog switch; damp ringing at the source | Information-theoretic dead-time curve only. No switch, TVS, snubber, dummy coil, or `.tran` recovery. |
| 4. Power regulation, modular boards | Out of PoC scope; future backend. Fine as deferral. |
| 5. Fix gain and noise budget (INA, band-limited gain, no excess early gain) | **Partially.** \(e_n\) on an untuned source is scored. Gain distribution and the bandpass are invisible. Tuned vs untuned is explicitly left out, which is the axis that changes the noise ranking. |
| 6. Validate the frequency estimator on real, noisy FID | Synthetic only. FFT/zoom/NLS ranking is real at high SNR. Zero-crossing “formally ruled out” is not re-runnable from this repo. Week-2 asked for validation on **real** records. |
| 7. Settle one coil geometry | README: coil is given. `architecture.md` §4: coil is a scored experiment axis. Those cannot both be true. \(V_0\) is not computed from the given coil in either reading. |
| 8. Long-lead parts / housing in parallel | Out of scope. |

The user’s stated pipeline goal (circuit + MCU from EMF to \(B\), coil given)
is a reasonable cut. Alignment with *that* sentence is good. Alignment with
the week-2 priority list is only strong on “stop obsessing over FPGA counting”
and weakly strong on “INA-class vs discrete op-amp \(e_n\).”

---

## 5. Reproducibility and “pipeline” completeness

- **Zero-crossing / wrapped-increment is not in `poc/`.**
  `ESTIMATORS = {fft_peak, zoom_fit, nlls_fit}`. The frequency-estimation
  report points at `/tmp/fid_bench.py`, `/tmp/run_bench.py`,
  `/tmp/zc_compare.py`. The most decision-relevant DSP result (ruling out the
  prior teams’ estimator family) is not a test this tree can reproduce.
  Port it.
- **There is no iterative loop.** Two hardcoded AFE candidates, Python
  estimators, no mutation, no part database, no SKiDL, no KiCad, no C99
  `core/`, no CI `sensitivity-score` job. This is a scoring prototype plus
  research memos. The docs read as if the loop already discriminates designs
  the way a bench would.
- **`zoom_fit` / `nlls_fit` are seeded with the true \(\tau\)** from the
  record. At headline SNR this did not matter in a short check; at short
  \(T_2^*\) it will. The specced \(\tau\)-misspec ablation is the right gate.
- **Phase is not randomized** (`phase=0` default). Fine for variance near
  the CRB; can hide phase-dependent FFT bias.
- **Signal is not passed through \(H(f)\); only noise is band-limited.** At
  this bandwidth the FID is almost entirely in-band, so NLLS vs CRB barely
  moves. It is still the wrong generative model once the agent can propose
  narrow or poorly centered filters.
- Minor: `np.trapz` on a future numpy; duplicated magic `42.577478e-3`
  instead of `fid.GAMMA_HZ_PER_NT`; `architecture.md` vs PoC blanking table
  (0.044→0.059 vs 0.0435→0.0587).

---

## 6. What is already good (keep)

1. **Layered IR plan** (Python component graph → ngspice for the fast loop →
   SKiDL/KiCad for survivors) is the right answer to “prior teams left
   Altium/LTspice files nobody can machine-read.” Driving `ngspice -b` as a
   subprocess is the pragmatic macOS choice.
2. **White + colored CRB with a 4-parameter FIM**, dead time on the absolute
   time axis, and Monte-Carlo of the same records the estimator sees, is the
   right sensitivity skeleton.
3. **Physical \(e_n\) resistor instead of vendor macromodels** is correct
   and empirically matches `.noise`.
4. **ADC vs comparator as the recommended path**, with time-walk called out
   as a systematic, is the right DSP architecture even though firmware is
   not written yet.
5. **Explicit “coil series R is the Johnson source; ngspice L has no
   `Rser`; E-Laplace is noiseless”** gotchas are accurate and worth keeping
   as hard rules for any generated netlist.

---

## 7. What to fix before the score may steer design search

In priority order:

1. **One \(\gamma_p\)** in docs, comments, and code (0.042577 Hz/nT or the
   shielded-water value, with an explicit absolute-vs-anomaly decision).
2. **Predict \(V_0\) from the given coil + polarization**, or score a
   \(V_0\times T_2^*\) grid and stop headlining 2 µV as if it were measured.
3. Put the **same \(H(f)\)** on signal and noise (SPICE `.ac` + `.noise`
   spectrum, not a software brick-wall that ignores the netlist). Include a
   real bandpass in the candidate space.
4. Score **blanking as `.tran` recovery + CRB**, not dead time alone.
5. Make **tuned vs untuned** (and ring-down \(\tau=2Q/\omega_0\)) a scored
   axis before treating INA-vs-TL072 as the analog result.
6. Implement **one** \(J\), with gates that match week-2 (clipping, in-band
   interferers, FID detection at low \(V_0\)). Do not double-count dead
   time unless cycle-time / tow sampling is an explicit term.
7. Land **60 Hz sidetone, clock-as-scale, \(\tau\) misspec** in the scorer
   (already specified as M5) so the optimizer cannot ignore the systematics the
   research says dominate published 0.07–3 nT floors.
8. Put a **zero-crossing estimator in-repo** if the pipeline is going to
   forbid it.
9. Do not tell the agent that 0.05 nT means the analog problem is done. At
   unvalidated \(V_0\), that number is a conditional CRB, not a measured
   sensitivity.

The research notes are stronger than the PoC: they already say tuned input +
JFET, systematics 0.07–3 nT vs pT CRLBs, and that commercial “0.01 nT” is
not absolute accuracy. The running score has not absorbed those caveats. If
the loop optimized what is implemented today, it would ship an untuned INA,
a missing bandpass, generous blanking, and a Python NLS fit, and report
~0.05 nT — while still not knowing whether a proton FID is there.
