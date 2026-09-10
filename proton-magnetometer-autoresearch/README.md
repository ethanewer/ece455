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
(`fid.estimate_v0`, Curie law) — the first wet capture replaces its
assumptions with measurements. SNR conventions: `eta_ps` = A_peak/σ
(per-sample), `SNR_rms` = (V₀/√2)/σ_in-band; MC uncertainty ~±3.5% (1σ) at
N=400. Constants: shielded-proton γ′p = 42.57638507 MHz/T = 0.0425764 Hz/nT.

**DSP at the 2 µV reference point** (T2* = 1.5 s, 1.5 s record, 200 ms
blanking, η_ps = 14.2 dB): colored-noise CRB 0.048 nT/cycle; zoom_fit 1.02×
CRB (0% gross errors); fft_peak 1.05×; zero-crossing family ~3800× CRB with
100% gross errors — ruled out, reproducibly, in `poc/estimators.py::zc_fit`.
The "20× margin on 1 nT" this implies holds **only for coils delivering
~2 µV**; the physics grid says a Hook-Line-class coil (530 turns, 3 cm,
20 mT polarization) gives V₀ ≈ 0.14 µV and only ~0.7 nT/cycle — the analog
budget is the mission.

**Analog candidates scored from SPICE** (`circuit_spec.py`; physics V₀, H(f)
shapes signal and noise, e_n AND i_n modeled, ring-down measured from `.tran`):

| candidate | V₀ | σ_in | SNR_rms | τ_ring | J = σ_B |
|---|---|---|---|---|---|
| untuned + INA828-class | 0.14 µV | 713 nV | −17.5 dB | 0.4 ms | 0.731 nT |
| untuned + TL072-class | 0.14 µV | 1797 nV | −25.5 dB | 0.4 ms | **fails gates** |
| tuned series-resonant + JFET | 3.8 µV | 158 nV | +24.7 dB | 0.5 ms | **0.0057 nT** |

The tuned input reorders the amplifier ranking (as the AFE research predicts)
and is the axis an optimizer must explore first. Blanking: 500 ms costs only
1.2× in σ_B (information concentrates late in the record) — bias blanking
long, gated by ring-down.

Clock reality (deterministic, does not average down): ±20 ppm crystal =
1.0 nT bias at 50 µT; ±2 ppm TCXO = 0.1 nT; ±0.5 ppm = 0.025 nT.
