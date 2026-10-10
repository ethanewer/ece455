# Verification plan

Use these measurements to replace nominal inputs with evidence. Save raw captures and instrument settings next to the resulting report. Update `verification_modeling/coil.py` and the active design only after recording the measurement conditions.

## Wet FID capture

Measure initial FID amplitude and T2 star with the active sensor pair, water sample, 3 A polarization pulse, 200 ms receiver blanking, and 30 kS/s capture.

Record:

- sensor connection and polarity
- which coils contain liquid
- polarization current, duration, measured field, and T1 saturation fraction
- receiver gain and ADC range
- raw ADC samples and sample clock source
- fitted FID amplitude, frequency, phase, and T2 star with uncertainty

The model predicts a few microvolts at the coil. The active pair's Curie-law estimate is about 3.59 uV at 1765 Hz. The older Hook-Line geometry gives about 0.41 uV at 20 mT. Treat those figures only as an order-of-magnitude check. A disagreement should change the fill, coupling, field, or geometry assumptions, not be hidden in receiver gain.

## Coil characterization

1. Measure each winding's DC resistance, preferably with a four-wire method.
2. Measure each winding's inductance and the mutual inductance in the installed geometry.
3. Measure the external coil assembly's resonance, 3 dB bandwidth, Q, and voltage step-up at each intended Larmor frequency. Fit or change its capacitor outside the receiver using C = 1/(4π²f²L).
4. Capture ring-down after a controlled step and compare the fitted time constant with 2Q divided by angular resonance frequency.
5. Capture the actual 3 A polarizer turnoff at the external sensor output and at the protected receiver input.

The nominal pair is 99.94 ohm and 152.6 mH, series-aiding. The coil assembly's tuning and damping remain separate from the receiver. Measure the source impedance presented to J1 after the external assembly is fitted.

## Receiver transfer and noise

Measure the assembled receiver with a calibrated source and analyzer:

- the AD8421 module as received: chip marking, the input RFI parts and their removal (series input resistance under 50 Ω, under 50 pF from +IN to GND), the fitted RG (gain 100), and the REF jumper on BIAS
- module supply current and both battery voltages under load
- DC levels with J1 shorted: OUT trimmed to 2.50 V, AIN0 ≈ 2.39 V, and a scope check of OUT and AIN0 for oscillation, including with the sensor connected
- complex transfer from 20 Hz to 50 kHz with a calibrated signal at J1; expect about 85 V/V from J1 to AIN0 across 1.6–2.2 kHz (83–87 simulated) and a −3 dB corner near 4.6 kHz, without attributing an external LC peak to the receiver
- attenuation near the ADS1256's 1.92 MHz modulator rate, for example with a 1.918 MHz tone at J1 and the ADC samples inspected for an alias near 2 kHz; require at least 90 dB below in-band gain (about 98 dB simulated)
- input impedance at J1 across 1.5–2.5 kHz, for example by the amplitude change with a known series resistor; require at least 1 MΩ (4.25–7.08 MΩ simulated)
- input-referred noise spectrum with J1 shorted, with a 30 kΩ resistor at J1, and with the coil connected; compare with the simulated 3.6, 23.4, and 3.9 nV/√Hz at 1.88 kHz (ADC included); require at most 5 nV/√Hz with the coil
- the actual 30 kSPS ADS1256 noise with its buffer off and PGA 1
- the largest tone at J1 before OUT or AIN0 clips; require at least 10 mV peak at 50–400 Hz and 2 mV at 8–50 kHz (27.2 and 49.0 mV simulated nominally, 15.7 mV at the worst corner)
- Q1/Q2 clamp current and settling through the real polarizer turnoff; keep the sensor disconnected until its pulse magnitude is known
- the AD8421's recovery after overload, then recovery after the acquisition blank and a short SYNC/PDWN pulse; confirm the first subsequent DRDY marks settled data
- loaded USB 5 V at the lowest expected USB input
- the purchased module's DRDY high level (expect about 3.3 V) before wiring its SPI directly to the XIAO, then scope all six SPI lines at the chosen clock
- noise coupled from the module's BIAS/REF path, which the model omits
- RF rectification with the module's RFI network removed: watch OUT's DC level while a phone or handheld radio transmits nearby, with and without the clip-on ferrites
- CMRR with the installed sensor pair

Export measured transfer and noise data in a text format that tests can load, and compare them with the limits in `receiver_design/requirements.py`. Compare ngspice and measured curves using explicit tolerances. Include the ADS1256's converter noise separately because the SPICE deck models its input loading but not its specified converter noise or digital filter. The AD8421 model uses datasheet noise densities and does not clip or model 1/f noise.

## Frequency estimator

Inject decaying sinusoids at 1064.4, 2128.8, and 2767.5 Hz through a calibrated attenuator. Cover T2 star values of 0.3, 1.5, and 3 seconds and peak-amplitude per-sample SNR values of 0, 10, 20, and 30 dB, where SNR is 20 log10(V0/sigma). This convention is 3.01 dB above RMS signal SNR.

For the operating region, require:

- RMS frequency error no greater than 0.0426 Hz per cycle for the 1 nT target
- gross error rate below 1 percent, where gross means more than 1 Hz
- absolute bias below 20 percent of measured standard deviation
- host C, target firmware, and injected-reference results consistent within stated numeric tolerances

Run `make firmware` before hardware tests. It compiles the same portable C estimator and checks it against hash-pinned vectors and an independent NumPy mirror.

## Clock and interference

Measure oscillator error over supply and temperature. A 20 ppm error produces about 1 nT of absolute field bias at 50 uT. A 0.5 ppm source contributes about 0.025 nT. Keep this deterministic scale error separate from cycle-to-cycle noise.

Repeat the FID test with converter ripple, mains harmonics, digital activity, and polarizer switching active. Inspect for estimator lock onto interference rather than reporting only waveform SNR.

## Layout and hardware review

KiCad DRC checks geometry and connectivity. A reviewer must still inspect sensitive input placement, return paths, grounding, shielding, pulse coupling, protection current paths, creepage, connector pinout, power dissipation, and test access. Do not fabricate the current passive projection until all active parts and interfaces have real symbols, footprints, and reviewed ratings.
