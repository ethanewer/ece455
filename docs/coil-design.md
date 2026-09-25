# Active coil model

The nominal values come from `CoilDesign.xlsx`. They are winding estimates, not measurements. `verification_modeling/coil.py` is the machine-readable copy. The workbook says to measure L and R after winding and recalculate.

## Polarizer

- Rectangular 140 by 70 mm aperture, 100 mm winding length, 146 by 76 mm bobbin outline
- 331 turns in three layers, 0.714 mm insulated diameter, about 149 m of wire
- 7.905 ohm and 9.835 mH
- 3 A for 5 seconds, 23.7 V and 71.1 W in the winding
- 8.633 mT center-field estimate, scaled from the earlier 342-turn, 8.92 mT geometry
- Stored energy at 3 A is 44.3 mJ
- L/R time constant is 1.244 ms

## Sensor pair

Each sensing coil has a 56 by 56 mm aperture, 100 mm winding length, and a 60 by 60 mm bobbin outline. The estimate is 1477 turns in seven layers of 0.462 mm insulated wire, about 373 m, 49.968 ohm, and 76.284 mH.

The receiver connects the two coils series-aiding and neglects mutual inductance:

- 2954 signal turns, because the workbook counts both windings
- 99.936 ohm series resistance
- 152.568 mH series inductance
- 56 mm square aperture, represented by an equal-area radius
- provisional T2 star of 0.95 seconds

The coil assembly, its tuning capacitor, and any switched damping resistor are outside the receiver. The receiver begins at `J1` and provides a nominal 5.1 megohm input bias return. Coil tuning must be chosen from measured inductance and the desired Larmor frequency using `C = 1/(4π²f²L)`. The example receiver input frequencies, 1765 and 2129 Hz, are test points rather than fitted tank settings.

The Curie-law model gives an open-circuit pair amplitude of about 3.59 µV at 1765 Hz with the 8.633 mT polarizing field. An external tuned network can change the voltage presented to `J1`; its gain and damping must be measured separately. The workbook's 72 µV series-pair figure is an illustrative scaling from a 15 µV baseline, not the receiver stimulus. Both windings contribute Johnson noise. The model grants no common-mode cancellation: the workbook's series-aiding connection adds uniform pickup.

## Measurements still required

Measure DC resistance, inductance, mutual inductance, resonance, Q, ring-down, sample placement, sensing polarity, polarizer field, turnoff transient, FID amplitude, and T2 star. The current values remain conditional until those results update `coil.py` and the external sensor model. The receiver input model should use the measured source impedance. The signal model assumes equilibrium magnetization. Measure water T1 and account for incomplete saturation during the nominal 5 second pulse.
