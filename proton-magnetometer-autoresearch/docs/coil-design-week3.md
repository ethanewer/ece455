# Week3 coil design mapping

Source: `current-work/Week3 # Polarization Coil Design # Hunter_Vania.pptx.pdf`
by Hunter Vania, slides 2–7 (the supplied filename has literal `#` characters).
The source is a proposal, not measured hardware. Machine inputs live in
`pipeline/coil_design.py`; current CLI and optimizer seeds share that profile.

| Input | Source / interpretation |
|---|---|
| Architecture | Separate polarizer, sensing A and noise-reference B (slide 2) |
| Polarizer | 7 × 14 cm cross-section, 10 cm length, 360 turns in 4 layers, 18 AWG, about 144 m wire |
| Polarizer nominal electrical | 3 A, 3 Ω, 15.4 mH, 13.6 mT ideal-solenoid field, pulse at least 5 s |
| Each sensing coil | 6 × 6 cm square, 10 cm height, 22 AWG, 0.7 mm enameled diameter, 4 layers, 135 m wire |
| Sensing turns | **Inferred 138 per layer = 552 per coil**; 552 × 0.24 m ≈ 132.5 m supports the 135 m statement |
| Each sensing coil electrical | 7 Ω, 10–12 mH; use 11 mH midpoint |
| Tuning | 264 nF from slide 7; optimizer may retune this downstream component |

The provisional receiver is a series-opposed pair with negligible mutual
inductance: R = 14 Ω and L = 22 mH. A supplies the proton FID; B supplies
no proton signal. The two uncorrelated winding thermal noises add in power
(the 14 Ω SPICE resistor captures both). Neither thermal noise nor amplifier
noise is canceled. No numerical common-mode interference cancellation credit
is awarded without measurements. Series connection and sample placement are
assumptions awaiting confirmation; slide 8 has no circuit drawing. The score
therefore has a failing `hardware_characterized` gate until the connection,
liquid placement, mutual coupling, and polarizer turnoff are measured.
If both coils contain identically oriented polarized samples, subtraction can
cancel signal as well, so this model would need revising.

The square's 0.0036 m² bore is represented by an equal-area radius, not a
3 cm circular radius. The existing Curie/Faraday approximation uses 552
signal turns, that area, and a conservative 9.38 mT finite-coil centre-field
estimate. The slide's 13.6 mT ideal-solenoid result is retained as provenance.
The polarizer's 360 turns do not count
as pickup turns. Geometry and electrical inputs are fixed in the optimizer;
the old long-solenoid winding formula is not applied to these rectangular
multilayer coils. The nominal R and L remain slide estimates needing bench
verification. Score cards include the full coil profile and its assumptions.

Consistency checks (ideal lumped elements):

- Polarizer L/R = 5.13 ms, not the slide's approximately 3.5 ms.
- Stored energy = LI²/2 = 69.3 mJ, agreeing with the slide.
- Resistive drop = 9 V and dissipation = 27 W during the pulse (135 J over
  5 s); supply compliance must additionally cover switching/driver losses.
- Pair resonance with 264 nF is 2088 Hz (about 49.1 µT), versus 2953 Hz
  for a single 11 mH coil. The ideal relation is
  [f = 1/(2π√LC), Analog Devices](https://wiki.analog.com/university/courses/alm1k/circuits1/alm-cir-lc-resonator).
- Unloaded pair bandwidth R/(2πL) = 101 Hz and amplitude ring-down
  2L/R = 3.14 ms. The slide's 133 Hz and 2.4 ms are not imposed on SPICE;
  loading changes these values. With 10–12 mH per coil, pair resonance
  spans roughly 2000–2190 Hz before mutual coupling or tolerances.

The score remains conditional. It assumes water proton density, equilibrium
polarization, ideal alignment and filling, and provisional T2* = 0.95 s.
The slide's 0.95 s annotation is ambiguous (the callout says T1 while the
body describes precession decay), so it is conservative rather than measured;
its quoted 0.5–2 µV literature amplitudes are not injected as measured V0.
The polarizer field is a finite rectangular-coil centre estimate, not a
measurement. Spatial field/receive sensitivity, mutual inductance,
reference-coil matching and actual liquid placement need characterization.

TVS quenching and amplifier protection are proposed in slide 5, without clamp
voltage, switch details or mutual inductance. The existing 1 mA test pulse
only characterizes the linear receiving network's decay; it is not a 3 A
polarizer turnoff simulation. The existing 200 ms minimum blanking remains.
A passing recovery gate does not establish real amplifier recovery or TVS
sizing. Measure both at turnoff before hardware optimization sign-off.

Run `python3 pipeline/circuit_spec.py --json` for current full-field cards,
`--bsweep` for retuned bands, and `--legacy` for historical reference cards.
`tools/reproduce.py` deliberately regenerates historical regression fixtures.
Optimizer state uses `optimizer/runs/elite-week3-v1.json` to avoid reusing
old-coil parents or scores. Existing wet-capture and sign-off gates still apply.
