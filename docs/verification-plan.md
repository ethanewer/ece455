# Verification plan

These bench measurements replace modeled values with evidence. Save raw captures and instrument settings under `local/`, grouped by test, and update the design files only after recording the conditions. [`design.md`](design.md) lists the open issues these tests settle.

## Coils and tank

1. Measure each sensing coil's DC resistance and inductance, then the series pair as installed. This settles the tuning workbook's 26.58 mH against the drawing's 28.11 mH and 39 Ω. Count or confirm the turns: those values imply about 600 per coil, not the 1477 that CoilDesign.xlsx plans, and the FID scales with turns.
2. With the pair on J1, set the bank for a target frequency from [`simulation/README.md`](simulation/README.md). Measure the tank's resonance, −3 dB bandwidth, and Q at J5 with a small signal injected in series with the coil. Expect Q near 10.
3. Find the damping setting: with GPIO15 high, adjust RV1 for the fastest ring-down without overshoot after a step, and record the time constant.
4. Measure the polarizing coil's resistance and inductance (planned 7.9 Ω, 9.8 mH), then its current, turn-off transient, and TVS clamp voltage on the polarization board at the chosen battery voltage.
5. With the sensing pair nested in the polarizing coil and disconnected from the signal board, measure the voltage the polarizer's turn-off induces across it, through a probe rated for at least 300 V. The estimate is on the order of 100 V. Choose clamping or switching for J1 from that measurement before connecting the board or the amplifier.

## Signal board bring-up

1. Before fitting the Pico or the ADS1256 module, power J2 and check the 5 V rail (about 5.02 V), its ripple, and `2.5VBias` at TP5.
2. Check the ADS1256 module's two headers against J3 and J4: pin order, spacing, and which AIN pins J4 pins 1 and 3 reach. The firmware measures AIN1 − AIN0.
3. Fit the module and Pico, flash the firmware, and confirm the start-up register dump: STATUS ID nibble 3, ADCON 0x06, DRATE 0xE0. Measure the DRDY rate with a scope (nominal 15 kSPS, about 20 kSPS reported).

## Amplifier

Build [`breadboard/README.md`](breadboard/README.md) and check the op amp's pinout first.

1. With no input, check both stage outputs at about 2.5 V, J6 at 0 V, and no oscillation.
2. With the 1001:1 test divider and the generator at 180 mV peak, measure the gain from the divider output to stage 1, stage 2, and J6 from 500 Hz to 10 kHz. Compare with [`simulation/frequency-response.csv`](simulation/frequency-response.csv): the amplifier alone is each stage column minus the tank column, in dB.
3. With the tuned coil on J5 and no polarization, record the noise spectrum at J6. Compare it with the ADC-input column of [`simulation/noise.csv`](simulation/noise.csv); above a few hertz, J6 and the ADC input differ only by C21 and R8.
4. Measure the FID-sized signal at the ADC input and choose the PGA so the largest expected FID stays within ±2 VREF/PGA. The simulated 10 µV FID needs PGA 16 or less.

## Estimator

Inject decaying sinusoids through the test divider at 1.5, 2.0, 2.27, and 2.5 kHz, with τ near 1 s and several amplitudes. For each setting record:

- the reported frequency against the generator's, over repeated captures;
- the sample rate the firmware measures, against an independent count of DRDY;
- the amplitude at which the reported frequency departs from the generator by more than 0.05 Hz. Low SNR near the band edges is a known weakness (`util/tests/test_firmware.py`).

`make test` already runs the firmware's estimator on synthetic records; repeat any failing bench case there.

## Wet FID

Polarize a water sample, then capture with the tank tuned to the local Larmor frequency. Record the polarizing current and time, the damping and blanking times, the bank setting, the PGA, the raw samples, and the fitted amplitude, frequency, and T2*. The drawing assumes 10 µV at the coil; the measured amplitude sets the PGA and confirms or replaces that assumption.

## Clock and field accuracy

The frequency scale comes from the Pico's crystal: each ppm of clock error is 0.05 nT at 50 µT. Measure it against a reference frequency. Report fields with the shielded-proton ratio, 0.0425764 Hz/nT, or state that the firmware's free-proton value reads 25.7 ppm low.
