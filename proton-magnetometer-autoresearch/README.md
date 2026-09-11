# proton-magnetometer-autoresearch

Auto-research pipeline for the ECE 455 proton-magnetometer towfish receiver:
design and score the filter/amplifier chain (AFE) and the MCU signal-processing
stack that turn the induced FID EMF into a magnetic-field estimate. Coil and
power source are given; everything downstream is generated and scored here.

**Status: gated pre-optimizer.** The pipeline has **one evaluator**: every
score is a single design — one circuit + one estimator implementation (the
shipped C core) + one MCU configuration — evaluated end to end
(`poc/evaluate.py`, see [`REDESIGN.md`](REDESIGN.md)). The circuit IR +
SPICE/KiCad backends, the parts DB, the C estimator core (float + fixed,
emulator-checked), and the score-guided optimizer skeleton are implemented
and regression-tested (see [`docs/architecture.md`](docs/architecture.md) and
[`docs/runbook.md`](docs/runbook.md)). The remaining pre-G2 gates are the wet
capture (F1/F2) and the human sign-offs (B7/C6/D6/E5/G1) — see the runbook.
Do not treat the score as a hardware objective until F2 anchors the coil model.

- **Architecture & findings:** [`docs/architecture.md`](docs/architecture.md)
  — circuit representation (SKiDL → ngspice/KiCad backends), the single E2E
  evaluator, and the honest week-2 alignment table.
- **Research reports:** [`docs/research/`](docs/research/) — formats survey,
  AFE noise evaluation, frequency-estimation CRLB + estimators, MCU-stack
  evaluation.
- **Working proof of concept:** [`poc/`](poc/) — the generate→simulate→score
  loop, closed on this machine with Python + ngspice + the C core.
- **Standing regression tests:** [`poc/test_validation.py`](poc/test_validation.py)
  — white CRB vs Rife–Boorstyn closed form, colored CRB vs an independent
  dense-covariance Fisher, C-estimator-vs-bound, γp constants.

## Run the pipeline

```sh
pip install -r requirements.txt   # (or python3.12 -m venv .venv for skidl)
brew install ngspice              # once
cd poc
python3 test_validation.py        # ~1 min: bound/estimator regression tests
python3 circuit_spec.py           # E2E cards for the reference candidates
python3 circuit_spec.py --bsweep  # + per-band candidate family

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
(per-sample), `SNR_rms` = (V₀/√2)/σ_in-band; MC uncertainty ~±6% (1σ) at
N=150. Constants: shielded-proton γ′p = 42.57638474 MHz/T = 0.0425764 Hz/nT
(CODATA 2018).

**One candidate = one circuit + one estimator + one MCU config.** Every
number in the analog table below comes from the same E2E path: SPICE
characterization of the candidate netlist (H(f), noise spectrum, ring-down,
causal impulse response) → records synthesized through that characterization
→ the C estimator core (`firmware/core/`, byte-identical to what ships) →
J = worst-band σ_B over the operating field range (25–65 µT), with gates.

**E2E reference candidates** (`poc/circuit_spec.py`; physics V₀, C zoom
estimator, 0.5 ppm TCXO; V₀/σ/τ shown at 50 µT, J is the worst band):

| candidate | V₀ | σ_in (500–3500 Hz) | τ_ring | J = worst-band σ_B |
|---|---|---|---|---|
| untuned + INA828-class | 0.41 µV | 392 nV | 0.4 ms | fails scored ripple gate (all bands; also gross at 25 µT) |
| untuned + TL072-class | 0.41 µV | 989 nV | 0.4 ms | fails scored ripple gate (all bands) |
| tuned series-resonant + JFET | 11.5 µV | 192 nV | 3.1 ms | fails scored ripple gate at 25 µT; 0.0007–0.0026 nT at 37.5–65 µT |

The tuned candidate is wound on the **coupled coil** (0.56 mm wire over a
0.30 m axis → R = 20 Ω, L = 26.6 mH, Q ≈ 18): its V₀ and its noise come
from the same winding geometry, so the headline is a coil that actually
produces both (E3 finding 3).

The rail-ripple gate (week-2 problem 4 — the failure mode that killed two
prior teams) is **scored in the records**, not proxied: a 50 mV buck ripple
at 2 kHz referred through 100 dB PSRR (0.5 µV at the EMF) is injected into
a paired Monte-Carlo pass through the candidate's own H(f), and the
candidate fails if the estimator hijacks (gross) or σ_B degrades >2×.
This catches physics the old V₀-vs-0.5 µV proxy could not: ripple and FID
see *different* gain, so the fixed 2.1 kHz tank — which near-peak-amplifies
the 2 kHz tone while a 25 µT FID sits off-resonance at 1064 Hz — fails at
the band edge, and every small-coil untuned chain (V₀ ≲ 0.5 µV) fails
everywhere (measured: 3026 nT RMS when the seed hijacks). The **per-band
family** (`--bsweep`: tank retuned per field band) is what passes:
J = 0.0018 / 0.0007 / 0.0005 nT at 25 / 50 / 65 µT.

The card's CRB is the **shaped Fisher bound** built from the candidate's
own SPICE noise spectrum (`crb.freq_crb_shaped`) — a flat-density
approximation is invalid under a tuned tank (its EMF-referred density dips
at resonance; the estimator appeared at a spurious 0.72× "sub-CRB" ratio).
Against the shaped bound the C zoom core sits at 0.9–1.1× across the field
range. The scoring path's impulse response is a SPICE `.tran` impulse (no
reconstruction — earlier mag/phase interpolations produced +1.2 mHz and
+16.5 mHz artifacts an optimizer would have ground against): noiseless
tank pull 0.01–0.03 mHz, IR energy 100% causal.

**The estimator axis is scored through the same evaluator.** The C core
carries three estimator variants — `zoom` (exp-weighted matched filter, the
shipped baseline), `fft` (zero-padded FFT peak), `zc` (interpolated
zero-crossing + weighted mean period) — and a candidate's estimator is part
of its spec. On the thin-budget INA circuit the `zc` variant fails the
gross-error gate E2E (100% gross → J = ∞): the zero-crossing ruling-out is
a pipeline result, not a Python-side note. On the fat-SNR tuned circuit the
same variant scores 0.67 nT ≈ 940× the shaped CRB — the score rules it
out by ranking,
which is the honest physics at +32 dB SNR. The C core's bound-riding is
locked on synthetic unit vectors (NOT a design score —
`tests/test_estimator_reference.py`): zoom 1.05× colored CRB 0% gross,
fft 1.08×, zc ~3800× with 100% gross (η_ps = 14.2 dB reference point;
staged NLLS was threshold-limited there and is retired — it was never the
shipped algorithm).

**Blanking:** frequency information concentrates late in the record, so dead
time is cheaper than intuition suggests: 500 ms costs 1.35× in CRB σ vs
50 ms (0.0435 → 0.0587 nT) and 1.22× vs 200 ms. Blanking physics is scored
per candidate from the `.tran` ring-down (fail-closed); bias blanking long,
gated by ring-down.

**Comparator time-walk** (the zero-crossing front end's deterministic
systematic, crossing shift δt(t) = V_n/(2πf·A(t))): injecting it at
V_n = σ_in moves the C zoom core from its 0.05 nT baseline to ~0.9 nT at
the 2 µV unit-vector reference point — regenerated through the single
estimator implementation by `tools/reproduce.py`. This is a front-end
CHOICE argument (ADC path vs comparator), not a candidate score: the
linear walk model itself is only valid while V_n ≪ A(t), which fails at
physics V₀ — another reason the ADC path is the scored architecture.

Clock reality (deterministic, does not average down): ±20 ppm crystal =
1.0 nT bias at 50 µT; ±2 ppm TCXO = 0.1 nT; ±0.5 ppm = 0.025 nT. The clock
grade is a candidate axis (`mcu.clock_ppm`); the bias is reported on every
card, never folded into σ_B.
