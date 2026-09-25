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

`J4` selects the capacitor across the pair. The rest of the receiver stays fitted.

| `J4` shunt | Capacitors | Capacitance | Resonance with 152.568 mH |
|---|---|---:|---:|
| Pins 1-2, about 1.7 kHz | `C25` 47 nF + `C26` 4.7 nF | 51.7 nF | 1792 Hz, about 42.09 µT |
| Pins 2-3, about 2.1 kHz | `C27` 33 nF + `C28` 4.7 nF | 37.7 nF | 2099 Hz, about 49.3 µT |
| Removed | External capacitor, pin 4 to pin 2 | 1/(4π²f²L) | The measured inductance and the chosen test frequency |

The workbook's exact capacitor for 1795 Hz is 51.53 nF. Unloaded Q at 1792 Hz is 17.19. The half-power width of either tank is R/(2πL), about 104 Hz, and the 1792 Hz amplitude ring-down time constant is 3.05 ms. Fit only one shunt. Two banks in parallel resonate at neither target.

`R2`, 8.2 megohm, is the amplifier load on that tank. With `R1` and `C5` the load is 8.20 megohm at 1792 Hz, inside the 5 to 10 megohm target. The resonant resistance of the pair is about 30 kilohm, so this load leaves Q essentially unchanged.

The Curie-law model gives an open-circuit pair amplitude of 3.64 µV at 1792 Hz with the 8.633 mT polarizing field. The workbook's 72 µV series-pair figure is an illustrative scaling from a 15 µV baseline, not the receiver stimulus. Both windings contribute Johnson noise. The model grants no common-mode cancellation: the workbook's series-aiding connection adds uniform pickup.

## Measurements still required

Measure DC resistance, inductance, mutual inductance, resonance, Q, ring-down, sample placement, sensing polarity, polarizer field, turnoff transient, FID amplitude, and T2 star. The current values remain conditional until those results update `coil.py`, the ngspice model, and the KiCad design. The signal model assumes equilibrium magnetization. Measure water T1 and account for incomplete saturation during the nominal 5 second pulse.
