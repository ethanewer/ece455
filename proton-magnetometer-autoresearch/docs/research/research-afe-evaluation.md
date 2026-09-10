# Research: evaluating the analog front end for sensitivity

> How to score an AFE design (blanking → preamp → bandpass → gain → ADC) for
> a proton-precession magnetometer using open-source tools. Full procedure is
> implemented in `poc/circuit_spec.py`; this is the research basis.
> Compiled February 2026.

## 1. Executive summary

- The score decomposes into three computed numbers per candidate netlist:
  (1) total RMS noise in the FID band referred to the coil EMF (ngspice
  `.noise` + `.ac`), (2) end-to-end signal gain/phase for the FID (`.ac`
  against the coil's Lorentzian signal spectrum), (3) dead time from the
  blanking transient (`.tran`). Those map to σ_B = σ_f/0.0425764 via the
  Cramér–Rao bound; the Marcum-Q/erfc ROC formulas below are for detecting
  the FID PULSE PER CYCLE -- detecting a 1 nT wreck anomaly along a survey
  track is a different test (matched filter over the anomaly profile), out
  of this pipeline's scope.
- **ngspice reality check:** `.noise` only propagates noise from devices that
  have noise models (R, diodes, BJTs, JFETs, MOSFETs, lossy L via series R).
  Behavioral `B`/`E`-Laplace blocks are **noiseless and break noise
  propagation**; `.noise` linearizes at the DC operating point, so a blanking
  switch is frozen in whatever state the OP leaves it. Practical consequence:
  model filters as physical R-L-C, model op-amp noise with an explicit noise
  subcircuit or analytically in Python, and replace switches with explicit
  `RON`/`ROFF` resistors for noise runs.
- ADC choice is second-order if analog gain ≥ 1000 (ADS131M04 referred through
  G=1000 ≈ 5 nV — far below coil noise); a 12-bit MCU ADC (~46 µV in 2 kHz
  band) is right at the coil-noise line and *does* matter at low gain.

## 2. Baseline physics and formulas

### 2.1 Coil Johnson noise and the resonant step-up

- Thermal noise of winding resistance: `e_r = √(4kTr)`; 4 nV/√Hz per kΩ;
  200 Ω → 1.8 nV/√Hz → **80 nV RMS over a 1–3 kHz band**; 500 Ω → 127 nV.
- Standard PPM/Overhauser front end parallels the coil with a tuning capacitor
  resonant at f₀ inside the 1–3 kHz band. The
  [Noise Modeling of the Overhauser Magnetometer paper (Sensors, 2025)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12737282/)
  gives transfers of every source to the preamp input, notably:
  - Coil thermal noise at preamp input:
    `e²_r,INP = e²_r / [(1 + r/R − ω²/ω₀²)² + ω²(Cr + L/R)²]`
  - Preamplifier current noise at input:
    `e²_i,INP = i²_n·(r² + ω²L²)·[same denominator]`
- **Structural fact:** coil noise and current noise are multiplied by the
  resonant impedance step-up; the preamp's voltage noise is not. A tuned input
  raises signal *and* suppresses the relative importance of e_n. Their
  optimized coil: r = 22.5 Ω, L = 33.5 mH, R_match = 100 kΩ, Q ≈ 23, JFET
  2N6550 (1.4 nV/√Hz, 0.1 pA/√Hz). The [JPM-4 PPM paper](https://doi.org/10.18494/sam3719)
  uses the same topology, 1 nV/√Hz JFET, 2 µV simulated Larmor injection, SNR ≈ 31.
- Tuned-circuit ring-down after the pulse: envelope decays as `e^(−ω₀t/2Q)` →
  τ = 2Q/ω₀. At f₀ = 2.3 kHz, Q = 23 → **τ ≈ 3.2 ms (~15–20 ms dead time)** —
  a small fraction of T2* = 0.5–3 s.

### 2.2 Amplifier-chain noise budget (RTI)

Input-referred density with source impedance Z(f) — [INA828 datasheet](https://www.ti.com/lit/ds/symlink/ina828.pdf),
[Renesas R13AN0011](https://www.renesas.com/en/document/apn/r13an0011-noise-calculations-instrumentation-amplifier-circuits-rev100):

```
e_RTI(f) = √[ e_nI²(f) + (e_nO/G)² + (i_n(f)·|Z_s(f)|)² + 4kT·Re{Z_s(f)} + Σ(4kT·R_ext) ]
```

- INA828 @ 1 kHz: e_nI = 7 nV/√Hz, e_nO = 90 nV/√Hz, i_n = 170 fA/√Hz. At
  Z_s = 200 Ω the current-noise term is irrelevant; it matters only for
  kΩ-class source impedances (whose own 4kTR then dominates anyway).
- Candidate comparisons @ 1 kHz: [ADA4898-1](https://www.analog.com/en/products/ada4898-1.html)
  0.9 nV/√Hz / 2.4 pA/√Hz; [OPA827](https://www.ti.com/lit/ds/symlink/opa827.pdf)
  JFET 4 nV/√Hz / 2.2 fA/√Hz; ADA4528-1 zero-drift 5.6 nV/√Hz, **no 1/f**
  ([AN-1114](https://www.analog.com/en/resources/app-notes/an-1114.html));
  [OPA2277](https://www.ti.com/lit/ds/symlink/opa2277.pdf) 8 nV/√Hz; OP07
  9.6 nV/√Hz. PPM literature lands on JFETs at ~1–1.4 nV/√Hz because coil Z is
  low and the band is above 1/f corners.
- Cascade combination: RSS stage contributions through gains; or Friis:
  `F_tot = F₁ + (F₂−1)/G₁ + (F₃−1)/(G₁G₂) + …`
  ([TI SLYT094](https://www.ti.com/lit/an/slyt094/slyt094.pdf))
- 1/f over the band if the corner matters: `E_flicker = e_n,BB·√(f_c·ln(f_H/f_L))`
  ([TI SLVA043B](https://www.ti.com/lit/an/slva043b/slva043b.pdf),
  [MT-049](https://www.bdtic.com/download/adi/MT-049.pdf),
  [TI Precision Labs noise deck](https://www.ti.com/content/dam/videos/external-videos/en-us/1/3816841626001/4078839879001.mp4/subassets/opamps-noise-calculating-total-noise-presentation-quiz.pdf),
  [OPAMP-NOISECALC](https://www.ti.com/tool/OPAMP-NOISECALC))

### 2.3 ADC contribution

- Quantization: `q/√12`; with oversampling+decimation
  `SNR = 6.02N + 1.76 + 10·log₁₀(fs/2BW)` ([ADI MT-001](https://www.analog.com/media/en/training-seminars/tutorials/MT-001.pdf)).
  Filter **before** decimating or noise aliases back
  ([ADI NSD article](https://www.analog.com/en/resources/technical-articles/use-noise-spectral-density-to-evaluate-adcs-in-software-defined-systems.html)).
- [ADS131M04](https://www.ti.com/lit/ds/symlink/ads131m04.pdf) Table 7-1:
  5.35 µV RMS @ 4 kSPS gain 1 (VREF = 1.2 V); 1.20 µV @ gain 128.
  A [SAR needs an external filter to match](https://www.ti.com/lit/ml/slap103/slap103.pdf).
- Rule: `e_adc,coilequiv = e_adc,inband / G_analog`. At G = 1000, ADS131M04
  ≈ 5.4 nV (negligible); a 12-bit MCU ADC ≈ 46 nV referred — same order as
  coil noise. **ΔΣ ⇒ ADC a non-issue; MCU ADC ⇒ first-order term unless G is
  large or oversampling is aggressive.**

### 2.4 From noise to the headline metrics

- Matched-filter in-band SNR:
  `SNR = ∫|H(f)|²·S_sig(f)df / ∫|H(f)|²·S_n(f)df`, FID PSD Lorentzian:
  `S_sig(f) ∝ 1/[(2π(f−f_L))² + (1/T2*)²]`
- Frequency CRLB: [Rife & Boorstyn 1974](https://doi.org/10.1109/TIT.1974.1055282);
  damped variants [IEEE T-SP 1997](https://doi.org/10.1109/78.376840),
  [Measurement 2025](https://doi.org/10.1016/j.measurement.2025.119637).
  σ_f,min ≈ √3/(2π·T_obs·√(ρ·N)) for ρ = per-sample SNR; σ_B = σ_f/0.0425764.
  Sanity: T_obs = 1 s, N = 2000, ρ = 100 (23 dB) → σ_f ≈ 6e-4 Hz → 14 pT.
  Real PPM papers report 0.07–3 nT, systematics-limited:
  [TIM 2024 zero-crossing+LSR](https://doi.org/10.1109/tim.2024.3436094),
  [TIM 2025 CZT](https://doi.org/10.1109/tim.2025.3645916),
  [JMR 2021 Hilbert](https://doi.org/10.1016/j.jmr.2021.107020)
- Detection: coherent `Pd = ½·erfc(erfc⁻¹(2Pfa) − √SNR)`; unknown-phase
  noncoherent `Pd = Q₁(√(2·SNR), √(−2·ln Pfa))`
  ([MathWorks ROC](https://www.mathworks.com/help/phased/ref/rocsnr.html)).
  Pfa = 1e-6 needs ~13.5 dB single-pulse SNR.

## 2.5. ngspice noise mechanics

```
.noise v(output <,ref>) src ( dec|lin|oct ) pts fstart fstop <pts_per_summary>
```
- Two plots: `noise1` (`onoise_spectrum`, `inoise_spectrum` — inoise = output
  noise ÷ gain from `src`, i.e. referred to the coil EMF) and `noise2`
  (`onoise_total`, `inoise_total` = PSD integrated over fstart…fstop).
- **Trick:** set fstart/fstop to the FID band; `onoise_total` *is* the in-band
  RMS noise. For band-weighted scoring, export the spectrum + `.ac` transfer
  and integrate in numpy (lets you weight by the FID Lorentzian).
- `set sqrnoise` → V²/Hz; `pts_per_summary=1` dumps per-device contributions
  (use once to find the dominant element). Manual:
  https://nmg.gitlab.io/ngspice-manual/analysesandoutputcontrol_batchmode/analyses/noise_noiseanalysis.html
- Transient noise for switched circuits: `trnoise(NA NT NALPHA ALPHA RTSAM …)`
  on V/I sources (white + 1/f Kasdin + RTS), `setseed` for reproducibility,
  `NT ≈ 1/(10·f_max)`; experimental but the only way to see noise in a
  *switched* circuit:
  https://nmg.gitlab.io/ngspice-manual/analysesandoutputcontrol_batchmode/analyses/transientnoiseanalysis_atlowfrequency.html

### Gotchas that bite the scoring pipeline

1. **Behavioral sources are silent in `.noise`** — B/E-Laplace (`s_xfer`) have
   no noise model and sever propagation. Build filters from real R/L/C; get
   op-amp noise from an explicit noise subcircuit or analytically.
   (https://ngspice.sourceforge.io/docs/ngspice-html-manual/manual.xhtml)
2. **`.noise` linearizes at DC OP** — switches never toggle; ROFF = 1/GMIN
   leaves a 1e12 Ω leak; check OP with `keep_opinfo` or replace the blanking
   switch with an explicit resistor for noise runs (an explicit R also
   guarantees its 4kTR appears; SW elements are not noise generators:
   https://nmg.gitlab.io/ngspice-manual/circuitelementsandmodels/elementarydevices/switchmodel_sw_csw.html ;
   LTI noise can't handle switching: [Kundert, PNoise](https://kenkundert.com/docs/cicc96a.pdf))
3. **ngspice inductors have no `Rser`** (that's LTspice) — add explicit series
   R in the coil subcircuit; that R is the coil's noise source, never use a
   lossless L for the pickup coil. Behavioral resistors need `noisy=1`.
4. Vendor PSpice macromodels translate inconsistently and often **lose noise
   generation** (https://e2e.ti.com/support/amplifiers-group/amplifiers/f/amplifiers-forum/1522979/ina826-ina826-spice-model-stopped-working-with-ltspice ;
   ADI translation page: https://www.analog.com/en/resources/pspice-model-translation-for-ngspice.html).
   The reliable pattern (what TI/ADI models do internally): diode pair
   (shot noise √(2qI), KF/AF for flicker) + `h`-source scaled to the datasheet
   e_n, injected in series with a noiseless gain block; mirrored `f`-source
   for i_n. Equivalent ngspice-native trick: physical resistor
   `R = e_n²/(4kT)` in series with a high-Z input node.
5. `trnoise` is transient-only/experimental; shot noise synthesized with a
   B-source if needed.

## 2.6 Blanking / polarization transient modeling

- Switch specs ([Vishay DG417-419](https://www.vishay.com/docs/61565/dg417.pdf),
  [ADI DG419](https://www.analog.com/en/products/dg419.html)): tON 175 ns /
  tOFF 145 ns, charge injection 60 pC (10 pC ADI redesign), off-isolation
  60–80 dB, off-capacitance 8 pF. Glitch ≈ Q/C_node: 60 pC into 1 nF = 60 mV —
  blanking must stay closed through the glitch; the 8 pF off-cap is part of
  the tuning-capacitor budget.
- [JPM-4](https://doi.org/10.18494/sam3719): cut polarization current within
  ~400 µs. NMR receiver practice
  ([passive limiter](https://doi.org/10.1063/1.1136608),
  [biased T/R switches](https://www.sciencedirect.com/science/article/abs/pii/S1090780715003171)):
  never let the preamp *saturate* — biased diode limiters ahead of each stage
  so only the limiters clip; recovery is then µs–tens of µs vs ms when
  saturated.
- SPICE pattern: polarization transient = PWL/PULSE current source into the
  coil + S-switch opening at t=0; FID = damped-sinusoid B source; blanking
  switch = S with RON/ROFF (replaced by explicit R for `.noise`); recovery =
  `.measure tran` of output re-entering ±1 LSB-equivalent.

## 2.7 Scoring procedure (per candidate netlist)

Inputs: netlist + part DB (e_n, i_n, e_nO, GBW, corner per device) + constants
(T, B₀ → f_L, T2*, amplitude scale).

1. **Normalize**: coil = subcircuit `L1` + explicit series `r` (+ parallel
   Cpar, optional tuning C and matching R) —
   [Intusoft real-inductor recipe](http://intusoft.com/articles/inductor.pdf).
   Switches → RON/ROFF resistors (two runs: receiving/blanked). No behavioral
   source in the signal path of the noise analysis.
2. **AC transfer**: `.ac dec 200 100 10k`; export `V(adc)/V(src)` via
   `wrdata` or [spicelib RawRead](https://spicelib.readthedocs.io/en/latest/modules/read_rawfiles.html).
3. **Noise**: `.noise v(adc_in) V_fid dec 200 500 5k 1` (receiving-state and
   blanked-state); `inoise_spectrum(f)`; with `pts_per_summary=1` once,
   decompose per device; optionally re-run with the amp ideal to isolate coil noise.
4. **Band-integrated metrics in Python**:
   ```
   σ_n²  = ∫ |H(f)|²·S_n,eq(f) df          # referred to coil EMF
   P_sig = ∫ |H(f)|²·S_fid(f) df           # S_fid = Lorentzian ∝ 1/[(2π(f−f_L))²+1/T2*²]
   SNR   = P_sig/σ_n² ;  σ_n² += (e_adc,inband/G(f_L))²
   σ_f   = √3/(2π·T_eff·√(SNR·N_eff)) ;  σ_B = σ_f/0.0425764
   Pd    = Q₁(√(2·SNR), √(−2 ln Pfa))
   ```
5. **Monte Carlo tolerance sweep** (manual §25.5,
   https://nmg.gitlab.io/ngspice-manual/statisticalcircuitanalysis/monte-carlosimulation.html ,
   [MC_ring.sp example](https://github.com/imr/ngspice/blob/master/examples/Monte_Carlo/MC_ring.sp)):
   `.control` loop, `define gauss(nom,var,sig) (nom + nom*var/sig*sgauss(0))`,
   `alter`/`altermod`, `setseed`, skip failed runs (`sim_status`); `.sens` for
   worst-case ranking. No `.step` in ngspice — that's LTspice.
6. **Transient verification**: `.tran` with pulse + switch + `trnoise` +
   injected FID; measure recovery/clipping; confirm time-domain SNR matches
   frequency-domain prediction.
7. **Closed-loop co-sim**: export sampled waveform to numpy, run the actual
   estimator over MC realizations for empirical σ_f/Pd (captures Rife–Boorstyn
   threshold effects).

**Score (single source of truth: `poc/circuit_spec.py::score()`)**:
`J = σ_B [nT]` with fail-fast gates -- gross-error rate P(|f̂−f_L| > 1 Hz) < 1%,
ring-down inside blanking (5·τ_ring < 0.5·T2*; the earlier "recovery < 20 ms"
gate was mis-specified -- the requirement is that recovery fits inside the
blanking window, not a fixed 20 ms), no ADC clipping. No dead-time cost term:
dead time is already inside σ_B via the record start (the earlier w₃ term
double-counted). The w₁..w₅ weighting form is superseded.

Worked illustration (analytic, 200 Ω coil, 2 kHz band, FID 1 µV RMS, G = 1000):
coil-only noise 80 nV → SNR 22 dB; INA828 (7 nV/√Hz) adds 316 nV → 8.5 dB
(marginal); JFET 1.4 nV/√Hz adds 63 nV → 18.5 dB; a tuning-cap step-up (Q≈20)
lifts signal and coil noise together relative to amp noise → coil-dominated
operation, σ_B ≈ tens of pT at T_obs = 1 s.

## 2.8 Tooling

| Tool | Use | URL |
|---|---|---|
| ngspice manual | `.noise`, `trnoise`, Monte Carlo §25.5 | [noise](https://nmg.gitlab.io/ngspice-manual/analysesandoutputcontrol_batchmode/analyses/noise_noiseanalysis.html) · [trnoise](https://nmg.gitlab.io/ngspice-manual/analysesandoutputcontrol_batchmode/analyses/transientnoiseanalysis_atlowfrequency.html) · [MC](https://nmg.gitlab.io/ngspice-manual/statisticalcircuitanalysis/monte-carlosimulation.html) |
| spicelib (Nuno Brum) | read ngspice raw as numpy; batch parameter runs | https://github.com/nunobrum/spicelib |
| PyLTSpice | same harness + `NGspiceSimulator`, parallel MC | https://pyltspice.readthedocs.io/en/stable/modules/run_simulations.html |
| PySpice | Python→ngspice shared lib (macOS caveats) | https://pyspice.fabrice-salvaire.fr/releases/latest/index.html |
| ahkab | pure-Python; **no noise analysis**, dormant | https://ahkab.readthedocs.io/en/latest/ |

## 2.9 Gotchas checklist

1. `.noise` runs on the DC-op linearized circuit — switches frozen; use
   explicit resistors, verify OP (`keep_opinfo`).
2. `B`/`E`-Laplace blocks carry zero noise and sever propagation — use RLC.
3. Behavioral resistors noiseless unless `noisy=1`; no `Rser` on L.
4. TI/ADI models: syntax often fixable, noise may not survive; use datasheet-
   noise subcircuits or Python-side amp noise.
5. `trnoise`: transient-only, experimental, `NT ≈ 1/(10 f_max)`, `setseed`.
6. No `.step`/`.mc` — `.control` loops with `alter`/`sgauss`; handle
   non-convergence (`sim_status`); `set appendwrite` + spicelib multi-plot reads.
7. ADC µV-RMS specs are VREF- and ENBW-specific — rescale before comparing;
   refer through G(f_L).
8. Score with dead time included: blanking + tank ring-down (2Q/ω₀) + amp
   recovery all eat T_obs; σ_f ∝ 1/(T_obs·√N).
9. Paper specs assume above the Rife–Boorstyn outlier threshold; below it σ_f
   explodes — empirical MC scoring is the honest number.
10. Systematics (50/60 Hz + harmonics, microphonics, clock jitter, gradients)
    dominate before amplifier noise does — 0.07–3 nT reported vs pT CRLB.
