# Physical experiments to validate the pipeline

The harness is an in-silico prior. These experiments replace its
assumptions with measurements, in priority order. Each experiment lists:
what it anchors, the harness's *predicted* values (acceptance criteria),
and what to do when measurement and prediction disagree.

**Conditioning reminder**: every harness number is conditional on the
transducer model (`fid.estimate_v0`, spin-1/2 Curie law) until E1 pins
V₀ and T2* with measurements.

---

## 1. First wet FID capture (F1 — week-2 problem 1)

**Purpose**: measure V₀ and T2*; replace the transducer model's
assumptions with measurements. This is the single most decision-relevant
missing number in the whole pipeline.

**Setup**: Hook-Line-class coil (530 turns, 3 cm bore), polarization
pulse 20 mT, water sample, ADC capture with the reference AFE staging
(preamp ×100, INA828-class), 200 ms blanking, 1.5 s record, 20 kS/s.

**Acceptance criteria** (harness predictions to reproduce —
architecture.md §0 grid, INA-class e_n):

| quantity | harness prediction | acceptance band |
|---|---|---|
| V₀ (Hook-Line coil, 20 mT pol) | 0.41 µV | 0.1–2 µV (order-of-magnitude anchor; the model's assumptions — fill factor, coil axis, no t=0 loading — are explicitly OOM) |
| T2* (tap water) | 0.5–3.0 s assumed | measure; the σ_B grid scales as T2*^(−3/2) |
| σ_B per cycle (zoom path, measured SNR) | 0.048 nT × (2 µV/V₀_measured) | within the MC CI of the CRB once V₀/T2* are measured |
| SNR_rms (in-band) | −2.7 dB at V₀ = 0.41 µV (INA-class) | measure and back-compute the real e_n + i_n budget |

**If V₀ disagrees**: the fill factor / coupling assumptions are wrong;
update `fid.estimate_v0`'s assumptions (documented, not hidden), re-run
`run_scoring.py` §2, and regenerate every conditional headline.

## 2. Real coil measurement (F2)

**Purpose**: the coil is *given*, not designed — measure it so the
candidate space's noise drivers stop being injections (E6 finding 3:
V₀ and noise drivers must be coupled).

**Measurements**:
1. **R_coil**: DC resistance (4-wire if < 20 Ω). Predicted 20–120 Ω for
   the two candidate windings.
2. **L_coil**: LCR meter or the ring-down method (resonate with a known
   C, measure f₀ → L = 1/(ω₀²C)). Predicted 2 mH (Hook-Line) / 26.6 mH
   (model-consistent 1500-turn winding).
3. **Tuning-C sweep**: parallel-capacitor sweep across 25–65 µT's band;
   measure the tank's Q (3-dB bandwidth) and the step-up |H(f₀)|.
   Prediction: Q ≈ ω₀L/R_coil (≈ 18 for the model coil, ≈ 67 for the
   20 Ω/100 mH hand-spec) and step-up ≈ Q.
4. **τ_ring**: from the tuning-C ring-down after a step — must match
   2Q/ω₀ (the recovery gate's input).

**Feedback loop**: measured (R, L, C_sweep) goes back into the coil
model (`circuit_spec.coil_model` is calibrated by it) and the whole
grid re-scores: `python3 circuit_spec.py --bsweep`.

**Acceptance**: SPICE-predicted f₀, Q, step-up within ~10% of measured;
otherwise the netlist's ideal L/C model needs loss terms (add Rser to
the tank C, core losses).

## 3. Traceable reference injection (F3)

**Purpose**: on-target estimator validation without a field campaign.

**Setup**: signal generator disciplined by GPS 1PPS (or GPSDO) injects
a synthetic decaying sinusoid at 1064/2128.8/2767 Hz, known amplitudes
(µV-class through a calibrated attenuator), into the receiver's input;
the MCU/firmware path runs the shipped `freq_est.c`.

**Acceptance criteria** (from `firmware/host/sensitivity_report.json`,
the CI-scored matrix):
- σ_f ≤ 0.0426 Hz at η_ps ≥ 20 dB, T2* ≥ 0.5 s (the CRB-gated configs);
- |bias| < 0.2 σ;
- gross-error rate < 1% at operating SNR;
- the TCXO term appears as a pure scale error (B·ppm), not added noise.

**Comparator checks** (bench-only, NOT in the score): comparator
time-walk — feed amplitudes spanning 44× (the 25–65 µT swing) and
measure the crossing-time drift vs the model δt(t) = V_n/(2πf·A(t)).

## 4. Long-lead orders (F4 — parallel with 1–3)

Parts from `parts/parts_db.json` (prices are indicative; verify):
- TCXO ±0.5 ppm and ±2 ppm candidates (the single hardware decision that
  most affects the 0.0426 Hz target — C6's input);
- INA828, ADA4898, 2N6550-class JFET, ADS131M04, DG419 (blanking).

**Acceptance for the clock decision**: the measured TCXO error over a
temperature sweep must sit inside its ppm class; ±20 ppm class crystals
fail the absolute-accuracy budget by themselves.

## 5. What the harness cannot validate on a bench

* Layout EMI, star grounding, pulse-to-receiver coupling (week-2
  problem 2) — layout is not in the score; the KiCad leg checks
  ERC/DRC only.
* Saturation recovery of real amplifier stages (the .tran leg models
  the input network's ring, not amplifier overload recovery).
* Switch charge injection and snubber/dummy-coil design (the blanking
  knife-edge's analog half).

These remain bench work with the harness providing expected ranges, not
replacements.
