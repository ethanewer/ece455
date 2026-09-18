# Active coil model

The nominal values come from `docs/current_work/Week3 # Polarization Coil Design # Hunter_Vania.pptx.pdf`, slides 2 through 7. They describe a proposal, not measured hardware. `verification_modeling/coil.py` is the machine-readable copy.

## Polarizer

- Rectangular 7 by 14 cm cross-section, 10 cm length
- 360 turns in four layers, 18 AWG, about 144 m of wire
- Nominal 3 ohm and 15.4 mH
- 3 A for at least 5 seconds
- 13.6 mT ideal-solenoid estimate
- 9.38 mT finite rectangular-coil center estimate used by the signal model

The nominal L/R time constant is 5.13 ms. Stored energy at 3 A is 69.3 mJ. The winding drops 9 V and dissipates 27 W during the pulse, excluding switching losses.

## Sensor pair

Each sensing coil has a 6 by 6 cm square bore, 10 cm length, four layers of 22 AWG wire, about 135 m of wire, 7 ohm resistance, and 10 to 12 mH inductance. The model infers 138 turns per layer, or 552 turns per coil.

The receiver model assumes a series-opposed pair with negligible mutual inductance. It uses:

- 552 signal turns because only one coil contains the active sample
- 14 ohm series resistance
- 22 mH series inductance
- 264 nF tuning capacitance from the source slides
- 254.062174 nF in the active receiver, retuned to 50 uT
- 0.0036 square meter bore area, represented by an equal-area radius
- provisional T2 star of 0.95 seconds

Both windings contribute Johnson noise. The model grants no common-mode cancellation without measurements. If both coils contain aligned polarized samples, the opposed connection may cancel signal.

The ideal pair resonance with the source's 264 nF is 2088 Hz, about 49.1 uT. The active receiver uses 254.062174 nF for 2128.819 Hz, the shielded-proton frequency at 50 uT. With 10 to 12 mH per coil and the nominal capacitor, resonance spans about 2000 to 2190 Hz before mutual coupling and tolerances. The ideal unloaded bandwidth is 101 Hz and amplitude ring-down is 3.14 ms.

## Measurements still required

Measure DC resistance, inductance, mutual inductance, resonance, Q, ring-down, sample placement, sensing polarity, polarizer field, turnoff transient, FID amplitude, and T2 star. The current values remain conditional until those results update `coil.py`, the LTspice files, and the KiCad design. The signal model assumes equilibrium magnetization. Measure water T1 and account for incomplete saturation during the nominal 5 second pulse.
