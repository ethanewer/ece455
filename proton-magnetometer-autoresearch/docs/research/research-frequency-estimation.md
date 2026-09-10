# Research: frequency-estimation bounds and estimators for the FID

> Compiled February 2026. The estimators named here are implemented in
> `poc/estimators.py` (fft_peak, zoom_fit, zc_fit, nlls_fit) and
> regression-tested in `poc/test_validation.py` (audit v0.0 follow-up: the
> research pass originally left its scratch scripts in /tmp; they are now
> in-repo). SNR convention in this report: eta = A0/sigma, PER-SAMPLE
> amplitude SNR (20 dB <=> eta = 10) -- distinct from the record RMS SNR
> (V0/sqrt2)/sigma_in used in run_scoring.py output.

## Bottom line

With a 1.5 s usable FID at SNR 20 dB (τ = 1 s), the CRLB is σ_f ≈ 0.76 mHz ≈
**0.018 nT** per cycle — 2–50× better than the <1 nT / <0.1 nT targets. A
two-stage "FFT seed → IQ demodulate → unwrap → exponential-weighted linear
phase fit" (or 3-parameter Gauss–Newton NLS) measures **0.94–1.05× the CRLB**
in Monte Carlo and is cheap enough for an STM32-class MCU. Zero-crossing
counting only approaches this if band-limited before detection *and* outliers
policed; wideband ZC was **660× the CRLB** in their MC. The practical floor is
the **TCXO, not the estimator**: ±1 ppm at 50 µT = 0.05 nT un-averageable.

## 1. Signal model and conventions

- `s(t) = A₀·e^(−t/τ)·sin(2πf_L·t + φ) + white Gaussian noise`, τ = T2*,
  window `[t_d, T]` after dead time `t_d`.
- **B[nT] = f_L[Hz]/0.0425764** (shielded proton in water; 1 Hz = 23.4872 nT);
  σ_B[nT] = 23.4872·σ_f[Hz] — "to measure 1 nT
  you must measure frequency to 0.0426 Hz" —
  [Koehler, Proton Precession Magnetometers Rev 2](https://alexmumm.de/ppm/KoehlerMag.pdf)
- η = A₀/σ per-sample amplitude SNR (20 dB ⇔ η = 10); invariant quantity is
  the two-sided noise PSD N₀ = 2σ²/f_s.

## CRLB for a damped sinusoid (with dead time)

Exact closed form (validated to 4 digits against a numeric Fisher matrix and
against Monte Carlo; reduces exactly to Rife–Boorstyn for T ≪ τ):

```
var(f̂) ≥ σ²·Δ / (2π²·A₀²·S₂c) = N₀ / (4π²·A₀²·S₂c)
S₂c = ∫[t_d→T] (t − t̄)²·e^(−2t/τ) dt ,  t̄ = ∫ t·e^(−2t/τ) dt / ∫ e^(−2t/τ) dt
∫t²e^(−at)dt → [e^(−a·t_d)(a²t_d²+2a·t_d+2) − e^(−a·T)(a²T²+2aT+2)]/a³ , a = 2/τ
```

The `(t − t̄)` centering is the phase-unknown correction (Rife & Boorstyn's
t₀ = −(N−1)/2 trick); omitting it is optimistic by up to 2×. Limiting cases:

- Record ≳ 2τ: S₂c → τ³/8 ⇒ **σ_f ≈ 2/(π·η·√f_s·τ^(3/2))** — the τ^(−3/2) law
  (matches [RASER-NMR scaling](https://doi.org/10.1007/s00723-023-01597-w),
  [arXiv:1305.3676](https://ar5iv.labs.arxiv.org/html/1305.3676) — note that
  source's Eq. 25 differs only by a √2 convention factor).
- Record ≪ τ: var(f̂) = 24σ²/(A²Δ²N(N²−1)) — exactly 2× the Rife–Boorstyn
  complex-tone bound (real tone = half the information):
  [Rife & Boorstyn 1974](https://doi.org/10.1109/TIT.1974.1055282)
- Frequency information is weighted by **t²·e^(−2t/τ)** — concentrated *late*
  in the record, so dead time hurts less than expected, but the late low-SNR
  tail is where naive (ZC) estimators die.
- Damping is the ultimate limit: for T → ∞, var(f) = 4σ²Δ/(π²A²τ³); intrinsic
  noiseless bias |δf/f| ~ 1/(8π²f₀²T₂²) is negligible here
  ([arXiv:1305.3676](https://ar5iv.labs.arxiv.org/html/1305.3676)).
- General refs: [Yao & Pandit 1995](https://doi.org/10.1109/78.376840),
  [Wigren & Nehorai 1991](https://doi.org/10.1109/78.80943),
  [Measurement 2025](https://doi.org/10.1016/j.measurement.2025.119637),
  [VUW CRLB thesis](https://doi.org/10.26686/wgtn.17136080).

### Worked CRLB table (numeric 3-param FIM; τ known; fs = 20 kS/s)

| SNR | τ | t_d | T | σ_f [Hz] | σ_B [nT] |
|----|----|----|----|---------|---------|
| 20 dB | 1.0 s | 0.1 s | 1.5 s | **0.00076** | **0.018** |
| 20 dB | 1.0 s | 0.5 s | 1.5 s | 0.00152 | 0.036 |
| 20 dB | 1.0 s | 0.1 s | 2.0 s | 0.00062 | 0.015 |
| 20 dB | 2.0 s | 0.1 s | 3.0 s | 0.00025 | 0.006 |
| 14 dB | 1.0 s | 0.1 s | 1.5 s | 0.00151 | 0.036 |
| 14 dB | 0.5 s | 0.3 s | 1.5 s | **0.00398** | **0.093** |
| 26 dB | 1.0 s | 0.1 s | 1.5 s | 0.00038 | 0.009 |
| 30 dB | 2.0 s | 0.1 s | 3.0 s | 0.00008 | 0.002 |

Dead time of 0.5 s costs only ×1.3–2; short T2* is the real killer. Fitting τ
as a 4th parameter costs nothing (bound and MC unchanged). MC ground truth:
NLS and gated-IQ estimators measured 0.94–1.05× CRLB from 20 dB down to 0 dB
(200–300 trials/config), **0% gross failures (>1 Hz) at ≥0 dB SNR**.

## Estimator comparison (MC-verified on synthetic FIDs)

| Method | Bias (damped) | Variance vs CRLB | MCU cost | Robustness |
|---|---|---|---|---|
| **Zero-crossing + interp + regression** | ~0 if crossings clean; heavy-tailed outliers from spurious/missed crossings (200 extra crossings/record at 20 dB wideband) | Wideband: **660× CRLB** (34% gross fail). Narrowband pre-filter: 2.7× @30 dB, 8–100× @20 dB | Lowest | Poor — fails first in the late, information-rich tail. Why 2023–24 PPM papers replace it ([TIM 2024](https://doi.org/10.1109/tim.2024.3436094), [IEEE Sensors 2023](https://doi.org/10.1109/jsen.2023.3307871), [MST 2014](https://doi.org/10.1088/0957-0233/25/5/055103)) |
| **FFT peak + Jacobsen** | small w/ rect window (windowed variants need Candan correction: [Jacobsen 2015](http://www.ericjacobsen.org/Files/Jacobsen_2015_estimator_comparison.pdf), [Candan](https://doi.org/10.17482/uumfd.1583908)) | 1.35–1.6× (rect) | One FFT | excellent coarse seed |
| **IQ demod → decimate → unwrap → exp-weighted phase fit** | none observed (+0.01 mHz) | **0.94–2.2×** (2.2× at 14 dB from tail gating) | very low (NCO, CIC, atan2, running sums; same arch as published STM32H7 phase-noise analyzers [TIM 2023](https://doi.org/10.1109/tim.2023.3288255); phase-slope regression patented for this use [US 5,019,823](https://www.freepatentsonline.net/5019823.html); [NTNU IQ notes](https://htorp.folk.ntnu.no/Undervisning/TTK10/IQdemodulation.pdf)) | good with SNR gating; unwrap errors the failure mode — gate blocks \|z\| < 3σ |
| **NLS / Gauss–Newton** | none | **0.94–1.05×** | moderate (5–8 iter × 3×3 normal equations; or run on decimated IQ, 10–50× cheaper) | needs seed; basin ≈ 1/(2T); free to fit τ |
| **Prony / matrix pencil / ESPRIT** | unbiased above threshold | ~CRLB above threshold ([Hua & Sarkar](https://escholarship.org/uc/item/2n45r2z5)) | high (Hankel SVD) — overkill for a single mode | [EFE-HMC](https://doi.org/10.1109/tim.2023.3241977) reaches <0.03 Hz at SNR < −10 dB |
| **Phase-difference of two half-blocks** | none | ~2–4× (half the lever arm) | trivial | validator/fallback |
| **Kalman/EKF/PLL** | loop lag biases under decay | near-CRLB steady-state | low-medium | wrong shape for a batch decaying record; 2nd-order PLL ≡ steady-state KF |

**Recommended for RP2040/STM32-class:** FFT (rect, coarse) → IQ demod →
CIC/boxcar decimate ×20–100 → gated unwrap + weighted linear phase fit with
running sums; optional 2–3 Gauss–Newton refinements on decimated data with τ
fitted. Expect ~0.9–1.1× CRLB. RP2040 (no FPU): Q15 through mixer/decimator,
integer final regression; STM32F4/G4/H7: float fine.

## Practical precision killers

| Source | Effect | Magnitude / fix |
|---|---|---|
| **TCXO ±0.5–2 ppm** | multiplicative scale error δB = B·ppm | ±0.025 / ±0.05 / **±0.1 nT** @ 50 µT; does not average down. 0.01 nT class needs ≤0.2 ppm (OCXO/GPS) ([GEM accuracy paper](https://www.gemsys.ca/pdf/Requirements_for_Obtaining_High_Accuracy_with_Proton_Magnetometers.pdf), [JPM-4 2 ppm TCXO](https://sensors.myu-group.co.jp/sm_pdf/SM2789.pdf)) |
| Sampling jitter | slope error | 10 ns rms/1.5 s ≈ 1e-7 Hz — negligible |
| ADC quantization | white floor | 12-bit @ 80% FS = 81 dB SNR/sample ≫ 20–30 dB FID SNR — never the limit if gain staged to fill range (AGC advisable; amplitude swings 44% across 25–65 µT) |
| Non-white noise (60 Hz, VLF, tank ring-down) | biases peak/phase; false locks | [JINST 2017 noise model](https://doi.org/10.1088/1748-0221/12/07/P07019): accuracy saturates ≈ 0.04 Hz above 30 dB SNR. Mitigate: tank Q, digital band-limiting, notch/QC; 60 Hz 30th harmonic = 1.8 kHz! |
| Amplitude-decay bias | pure e^(−t/τ)·sin preserves crossing times; one-sided exponential peak symmetric | FFT bias ≤ +0.08 mHz at rect window; dominant ZC error is noise-driven, not decay |
| Suboptimal weighting | 2–4× variance loss | optimal WLS weight ∝ local SNR² = e^(−2t/τ) (phase fit) / amplitude² (crossings); fit τ too (free) |
| Threshold/outliers | Rife–Boorstyn MSE ≈ q·(fs²/12) + (1−q)·CRLB | FFT coarse search has 45 dB processing gain; 0% gross failures to 0 dB measured |

**Amplitude physics:** FID EMF ∝ ω·M⊥ ∝ B·B_p — scales with measured field and
polarization. JPM-4: 2.3 V initial amplitude, τ ≈ 0.95 s, SNR ≈ 31, 0.04 nT at
5 s cycling, turn-off < 400 µs ([JPM-4](https://doi.org/10.18494/SAM3719)).
Koehler: "induced voltage of the order of microVolts"; T2 = 2.1 s (oxygenated
distilled water) to 3.1 s (deoxygenated). Dead time composition: field
collapse (<0.4 ms) + tank ring-down (~Q/(πf₀) ≈ 4 ms at Q=25) + amplifier
overload recovery (10–100 ms). Spin-echo refocusing can recover T2* → T2
([RSI 2020](https://doi.org/10.1063/5.0011082)). Overhauser: RF polarization
during readout ⇒ 5 Hz+ cycles, ~1 W, no polarize dead time
([GEM overview](https://www.gemsys.ca/pdf/Overhauser_Magnetometers_Brief_Overview.pdf));
a 2026 Sensors paper cuts re-polarization to 3 ms with 90° pulses for
0.02 nT @ 1 Hz ([Sensors 2026](https://doi.org/10.3390/s26082347)).

## Scoring-harness spec

```
gen_fid(fs, T, t_d, A0, tau, f0, sigma, ntrial, rng, phi0~U):
    s(t) = A0·exp(−t/τ)·sin(2πf0·t+φ0) + σ·N(0,1),  t ∈ [t_d, T]  (absolute time)
Metrics per estimator E:
  M1  σ_f,cycle = RMSE(f̂−f0), excluding gross |err|>1 Hz → nT: ×23.4872; report ×CRLB
  M2  bias = mean(f̂−f0)
  M3  gross-error rate = P(|f̂−f0|>1 Hz); detection threshold = lowest SNR with P<1%
  M4  cycle-to-cycle repeatability (stationary-field run); averaging-gain check
  M5  ablations: +60 Hz@−40 dB sidetone, harmonic near f0, TCXO ppm as f0·(1+δ),
      τ mis-specification ±10%, t_d mis-set ±20 ms
  M6  cost: cycles/call on target (or MACs/sample proxy)
Reference configs: (20 dB, τ=1, t_d=0.1, T=1.5), (14 dB, τ=0.5, t_d=0.3, T=1.5),
(30 dB, τ=2, t_d=0.1, T=3.0), SNR sweep for M3.
Pass bar: σ_E ≤ 1.2×CRLB, |bias| < 0.2σ_E, gross < 1% at operating SNR.
```

Open-source analogues: [nmrglue `proc_lp.lp_model`](https://nmrglue.readthedocs.io/en/latest/reference/generated/nmrglue.process.proc_lp.lp_model.html)
(SVD/Hankel-SVD linear prediction → {f, damping, amp, phase}),
[lmfit](https://lmfit.github.io/lmfit-py/) for NLS;
a CRLB-benchmarked FID frequency estimator with published comparison data:
[arXiv:1305.3676](https://ar5iv.labs.arxiv.org/html/1305.3676).

## Commercial devices (precision vs cycle time)

| Device | Type | Sensitivity | Resolution/Accuracy | Fastest cycle | Source |
|---|---|---|---|---|---|
| GEM GSM-19T | Proton PPM | 0.1 nT @ 1 s | 0.01 nT res; ±(0.2–1) nT acc | ~3–5 s | [gemsys.ca](https://www.gemsys.ca) |
| GEM GSM-19 | Overhauser | 0.022 nT @ 1 Hz | 0.01 nT res; ±0.1 nT acc | 0.2 s (5 Hz) | [GEM datasheets](https://www.gemsys.ca) |
| SeaSPY | Overhauser | 0.01 nT (≤0.015 nT/√Hz @1 Hz) | 0.001 nT res; 0.1 nT acc | 4 Hz | [marinemagnetics.com](https://marinemagnetics.com/magnetometers/seaspy) |
| Geometrics G-882 | Cesium (contrast) | 0.004 nT/√Hz | <1 nT heading; <2 nT acc | 20 Hz | [Geometrics](https://www.geometrics.com/wp-content/uploads/2025/05/G-882-Spec-Sheet_0825.pdf) |
| GEOMAG SM90R | Overhauser (observatory) | — | 0.1 nT res | 8 s/56 s | [GFZ](https://doi.org/10.1186/bf03351971) |
| JPM-4 | Proton PPM (lab) | 0.04 nT @ 5 s cycle | SNR≈31, A=2.3 V, τ=0.95 s | 5 s | [doi:10.18494/SAM3719](https://doi.org/10.18494/SAM3719) |
| 90°-pulse fast PPM (2026) | Proton PPM | 0.02 nT @ 1 Hz | 3 ms polarization | 1 Hz | [doi:10.3390/s26082347](https://doi.org/10.3390/s26082347) |

Pattern: commercial "0.01 nT" figures are resolution/sensitivity at 1 Hz
bandwidth, not absolute accuracy (±0.1–1 nT); consistent with the CRLB table
(0.01–0.1 nT per 1–3 s cycle at 20–30 dB SNR).
