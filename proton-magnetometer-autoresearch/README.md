# proton-magnetometer-autoresearch

Auto-research pipeline for the ECE 455 proton-magnetometer towfish receiver:
design and score the filter/amplifier chain (AFE) and the MCU signal-processing
stack that turn the induced FID EMF into a magnetic-field estimate. Coil and
power source are given; everything downstream is generated and scored here.

**Status: gated pre-optimizer.** The objective function, its three evaluation
layers, the circuit IR + SPICE/KiCad backends, the parts DB, the portable C
estimator core (float + fixed, emulator-checked), and the score-guided
optimizer skeleton are implemented and regression-tested (see
[`docs/architecture.md`](docs/architecture.md) and
[`docs/runbook.md`](docs/runbook.md)). The E3 deep audit's verified findings
(V₀↔coil coupling, rail-ripple gate, causal impulse response, parallel-eval
isolation) are fixed; the remaining pre-G2 gates are the wet capture (F1/F2)
and the human sign-offs (B7/C6/D6/E5/G1) — see the runbook. Do not treat
the score as a hardware objective until F2 anchors the coil model.

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

## Run the pipeline

```sh
pip install -r requirements.txt   # (or python3.12 -m venv .venv for skidl)
brew install ngspice              # once
cd poc
python3 test_validation.py        # ~1 min: bound/estimator regression tests
python3 run_scoring.py            # CRB validation, V0xT2* grid, ablations
python3 circuit_spec.py           # SPICE candidates -> J (nT)
python3 circuit_spec.py --bsweep  # B8: score across 25-65 uT

cd ..                             # standing verification suite
python3 -m pytest tests/ -q       # D-suite + gates + exploitability canary
make -C firmware/core test        # C core: golden vectors + sensitivity job
python3 tools/reproduce.py        # D4/D11/D12: regenerate + diff fixtures/docs
```

The optimizer entry point and the pre-GO gate checklist live in
[`docs/runbook.md`](docs/runbook.md).

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
applied as the SPICE `.tran` ground-truth impulse response (causal, E3
audit), e_n AND i_n modeled, ring-down measured from `.tran`):

| candidate | V₀ | σ_in (500–3500 Hz) | SNR_rms (in-band) | τ_ring | J = σ_B |
|---|---|---|---|---|---|
| untuned + INA828-class | 0.41 µV | 392 nV | −2.7 dB | 0.4 ms | fails rail-ripple gate |
| untuned + TL072-class | 0.41 µV | 989 nV | −10.8 dB | 0.4 ms | fails rail-ripple gate |
| tuned series-resonant + JFET | 11.5 µV | 192 nV | +32.5 dB | 11.1 ms | **0.0010 nT (= CRB)** |

The rail-ripple gate (E3 audit fix, week-2 problem 4 — the failure mode
that killed two prior teams): a 50 mV buck ripple at 2 kHz referred through
100 dB PSRR is 0.5 µV, which exceeds the small coil's FID amplitude
(V₀ = 0.41 µV) — the coarse FFT seed hijacks onto the tone and the cycle is
destroyed (measured: 3026 nT in `run_scoring.py` [3e]). Small-coil
operation therefore requires better ripple control; the score makes that a
failing gate, not a footnote. The tuned candidate rides its CRB exactly:
with the scoring path's impulse response taken from a SPICE `.tran`
impulse (no reconstruction — earlier mag/phase interpolations produced
+1.2 mHz and +16.5 mHz artifacts an optimizer would have ground against),
the noiseless tank pull is 0.01–0.03 mHz and the IR energy is 100% causal.
Blanking: 500 ms costs 1.35× vs 50 ms and 1.22× vs 200 ms (0.0435 →
0.0587 nT; information concentrates late in the record) — bias blanking
long, gated by ring-down.

Clock reality (deterministic, does not average down): ±20 ppm crystal =
1.0 nT bias at 50 µT; ±2 ppm TCXO = 0.1 nT; ±0.5 ppm = 0.025 nT.
