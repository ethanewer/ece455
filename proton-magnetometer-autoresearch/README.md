# proton-magnetometer-autoresearch

Auto-research pipeline for the ECE 455 proton-magnetometer towfish receiver:
design and score the filter/amplifier chain (AFE) and the MCU signal-processing
stack that turn the induced FID EMF into a magnetic-field estimate. Coil and
power source are given; everything downstream is generated and scored here.

- **Architecture & findings:** [`docs/architecture.md`](docs/architecture.md)
  — circuit representation (SKiDL → ngspice/KiCad backends) and the
  three-layer sensitivity-evaluation scheme.
- **Research reports:** [`docs/research/`](docs/research/) — formats survey,
  AFE noise evaluation, frequency-estimation CRLB + estimators, MCU-stack
  evaluation.
- **Working proof of concept:** [`poc/`](poc/) — the generate→simulate→score
  loop, closed on this machine with Python + ngspice only.

## Run the PoC

```sh
brew install ngspice          # once
cd poc
python3 run_scoring.py        # CRB validation + estimator/blanking sweeps
python3 circuit_spec.py       # JSON circuit spec -> ngspice -> nT score
```

`run_scoring.py` validates the colored-noise Cramér–Rao bound against
Monte-Carlo (NLLS = 0.96× CRB), ranks estimators (zoom_fit ≈ NLLS ≈ 1.0× CRB;
FFT peak 1.05×; zero-crossing family ~50× worse — unusable), and quantifies
the blanking-vs-precision tradeoff.

`circuit_spec.py` emits ngspice netlists from a declarative JSON circuit spec,
extracts in-band noise + gain from `.ac`/`.noise`, and scores candidates
end-to-end in nT (INA828-class vs TL072-class input stage).

## Results snapshot (2 µV FID, T2* = 1.5 s, 1.5 s record, 200 ms blanking)

| quantity | value |
|---|---|
| CRB (colored noise) | 0.048 nT per cycle |
| zoom_fit / NLLS Monte-Carlo | 0.046 nT |
| FFT peak + parabolic | 0.048 nT |
| INA828-class AFE (SPICE-scored) | 0.050 nT |
| TL072-class AFE (SPICE-scored) | 0.126 nT |

Target is 1 nT: the DSP stack has ~20× margin; the analog noise budget and
systematics (clock ppm, comparator time-walk) are the real battleground.
