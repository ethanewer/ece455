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

The model predicts microvolt-scale input signals. The older Hook-Line geometry gives about 0.41 uV at 20 mT. Treat 0.1 to 2 uV only as an order-of-magnitude check. A disagreement should change the fill, coupling, field, or geometry assumptions, not be hidden in receiver gain.

## Coil characterization

1. Measure each winding's DC resistance, preferably with a four-wire method.
2. Measure each winding's inductance and the mutual inductance in the installed geometry.
3. Characterize the historical 264 nF tuning option separately, but do not fit it in the active broadband receiver. Measure resonance, 3 dB bandwidth, Q, and voltage step-up.
4. Capture ring-down after a controlled step and compare the fitted time constant with 2Q divided by angular resonance frequency.
5. Capture the actual 3 A polarizer turnoff at the protected receiver input.

The nominal pair is 14 ohm and 22 mH. The source slides' optional 264 nF capacitor would give 2088 Hz ideal resonance and 3.14 ms ideal amplitude ring-down, but the active receiver omits it to cover 1.5 to 2.5 kHz. Aim for 10 percent agreement before adding loss or coupling terms to the model.

## Receiver transfer and noise

Measure the assembled receiver with a calibrated source and analyzer:

- complex gain from 500 to 3500 Hz and beyond the anti-alias corner; verify approximately 2000 V/V coil-source-to-ADC gain at 1.7 and 2.1 kHz, excluding the ADS1256 PGA
- input-referred noise spectrum with the coil connected and replaced by a known impedance
- maximum unclipped input versus frequency
- recovery after protection and blanking switch operation
- PSRR versus frequency, including the 2 kHz converter-ripple case
- CMRR with the installed sensor pair

Export measured transfer and noise data in a text format that tests can load. Compare ngspice and measured curves using explicit tolerances. Do not tune ideal gain blocks to conceal missing amplifier bandwidth or saturation behavior.

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
