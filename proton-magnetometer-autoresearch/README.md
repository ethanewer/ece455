# proton-magnetometer-autoresearch

Auto-research pipeline for the ECE 455 proton-magnetometer towfish receiver:
design and score the filter/amplifier chain (AFE) and the MCU signal-processing
stack that turn the induced FID EMF into a magnetic-field estimate. Coil and
power source are given; everything downstream is generated and scored here.

**Status: scoring prototype.** The objective function and its three evaluation
layers are implemented and regression-tested. The optimizer loop, part
database, SKiDL→KiCad backend, and C firmware core are designed (see
[`docs/architecture.md`](docs/architecture.md)) but not yet built — do not run
a search agent against the PoC score alone.

- **Architecture & findings:** [`docs/architecture.md`](docs/architecture.md)
  — circuit representation (SKiDL → ngspice/KiCad backends), the three-layer
  sensitivity-evaluation scheme, and the honest week-2 alignment table.
- **Research reports:** [`docs/research/`](docs/research/) — formats survey,
  AFE noise evaluation, frequency-estimation CRLB + estimators, MCU-stack
  evaluation.
- **Working proof of concept:** [`poc/`](poc/) — the generate→simulate→score
  loop, closed on this machine with Python + ngspice only.
- **Standing regression tests:** [`poc/test_validation.py`](poc/test_validation.py)
  — white CRB vs Rife–Boorstyn closed form, colored CRB vs an independent
  dense-covariance Fisher, estimator-vs-bound, γp constants.

## Run the PoC

```sh
brew install ngspice          # once
cd poc
python3 test_validation.py    # ~1 min: bound/estimator regression tests
python3 run_scoring.py        # CRB validation, V0xT2* grid, ablations
python3 circuit_spec.py       # JSON circuit spec -> ngspice -> J (nT)
```

## Results snapshot

All numbers below are **conditional on the transducer model**
(`fid.estimate_v0`, spin-1/2 Curie law) — the first wet capture replaces its
assumptions with measurements. SNR conventions: `eta_ps` = A_peak/σ
(per-sample), `SNR_rms` = (V₀/√2)/σ_in-band; MC uncertainty ~±3.5% (1σ) at
N=400. Constants: shielded-proton γ′p = 42.57638474 MHz/T = 0.0425764 Hz/nT
(CODATA 2018).

**DSP at the 2 µV reference point** (T2* = 1.5 s, 1.5 s record, 200 ms
blanking, η_ps = 14.2 dB): colored-noise CRB 0.048 nT/cycle; zoom_fit 1.02×
CRB (0% gross errors); fft_peak 1.05×; zero-crossing family ~3800× CRB with
100% gross errors — ruled out, reproducibly, in `poc/estimators.py::zc_fit`.
Staged NLLS is threshold-limited at η_ps = 14.2 dB (2% divergent; the tail
dominates its RMS — see `run_scoring.py` §1). The "20× margin on 1 nT" this
implies holds **only for coils delivering ~2 µV**; the physics grid says a
Hook-Line-class coil (530 turns, 3 cm, 20 mT polarization) gives V₀ ≈ 0.41 µV
and ~0.24 nT/cycle — workable, with the analog budget still setting the
mission (audit E6 corrected the Curie law to the spin-1/2 form, 3× the
classical Langevin value the first revision coded).

**Analog candidates scored from SPICE** (`circuit_spec.py`; physics V₀, H(f)
shapes signal and noise (complex, causal), e_n AND i_n modeled, ring-down
measured from `.tran`):

| candidate | V₀ | σ_in (500–3500 Hz) | SNR_rms (in-band) | τ_ring | J = σ_B |
|---|---|---|---|---|---|
| untuned + INA828-class | 0.41 µV | 392 nV | −2.7 dB | 0.4 ms | 0.251 nT |
| untuned + TL072-class | 0.41 µV | 989 nV | −10.8 dB | 0.4 ms | 0.645 nT |
| tuned series-resonant + JFET | 11.5 µV | 192 nV | +32.5 dB | 11.1 ms | **0.027 nT** |

The tuned input is a REAL series-resonant step-up (audit E6: the first
revision's netlist had Q ≈ 0.001 — `C_tune` in series toward a high-Z tap —
and no step-up; the corrected parallel tank gives a tank gain ≈ 61× (loaded
Q), chain gain(f_L) = 12056 at the x4 preamp staging, and τ_ring ≈ 11 ms)
and it reorders the amplifier ranking (as the AFE research predicts). Its J
is limited by a *physical systematic*: the fixed tank (2126.8 Hz, detuned
+2.0 Hz from f_L = 2128.8 Hz) pulls the estimate +1.2 mHz (0.027 nT ≈ 27×
its CRB; verified against an analytic Lorentzian tank, and absent when the
tank is exactly on f_L — audit E6 round 2 confirmed the pull is filter
physics after the scoring path was made causal: the FID is convolved from
t = 0 with the chain impulse response and sliced at blanking). Retuning
`C_tune` is the optimizer's first move; across the 25–65 µT field range the
fixed 2.1 kHz tank must be re-centered per band (TODO B8). Blanking: 500 ms
costs only 1.22× in σ_B (200→500 ms; information concentrates late in the
record) — bias blanking long, gated by ring-down.

Clock reality (deterministic, does not average down): ±20 ppm crystal =
1.0 nT bias at 50 µT; ±2 ppm TCXO = 0.1 nT; ±0.5 ppm = 0.025 nT.
