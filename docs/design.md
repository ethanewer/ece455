# Design

The magnetometer polarizes a water sample, lets the protons precess about Earth's field, tunes and amplifies the free-induction decay (FID) from two series sensing coils, digitizes it with an ADS1256, and fits its frequency on a Raspberry Pi Pico 2. This page describes what the design files contain. Where the files disagree, or a decision is still open, it says so. Reference designators are per board, so `R8` on the signal board and `R8` in the LTspice drawing are different parts.

```
battery ─ polarization board ─ polarizing coil
                ▲ J3 (MCU control, not yet wired to the Pico)
sensing coils ─ J1 ┐ signal-processing & control board
                   ├ tuning bank C1–C11 (SW1, SW2), damping switch Q1/Q2 (GPIO15)
                   ├ J5 ─► off-board amplifier (breadboard, ltspice/AmplificationSim.asc) ─► J6
                   ├ C21, R9, clamps, 2.5 V bias ─► J4 ─► HiLetgo ADS1256 module ─► J3 SPI ─► Pico 2
                   └ J2 power ─► LMR36510 buck ─► 5 V rail
```

## Polarization board

`kicad/polarization_board/` (schematic dated 2026-09-18, rev 1.0; Gerbers exported 2026-10-01).

- Battery input on J1 and J4 in parallel, fused by F1, feeds the polarizing coil (J2) and U1, an LM340T-12 regulator (symbol L7812). The battery voltage is not specified. The regulator needs about 14.5 V or more.
- Q1, an NMOS low-side switch (the part is not named in the schematic), returns the coil (J2 pin 1) to ground. D1, an SMCJ58CA bidirectional TVS (symbol SMAJ7.0CA), clamps the turn-off flyback across the coil.
- U2, a TC4420 gate driver (symbol TC4422) powered from the 12 V rail, drives the gate through R2 (22 Ω); R1 (10 kΩ) holds the gate low. The driver input comes from J3 pin 1 ("Microcontroller") through R4 (100 Ω), with R3 (10 kΩ) pulling it low.
- C1 (0.22 µF), C2/C3 (100 nF), and C4 (1 µF) decouple the input and 12 V rails. R5 (2.2 kΩ) loads the 12 V rail.

The signal board has no connector dedicated to J3's control line, and the firmware does not drive one yet. J7 brings GPIO0 and GPIO1 out with 5 V and ground.

## Signal-processing and control board

`kicad/signal_control_board/`, three sheets (schematic saved 2026-10-27; board and Gerbers 2026-10-16; `make test` confirms that the board's nets still match the schematic). The BOM export is `SignalProcessing&ControlBoard.csv`.

Root sheet:

- J1 takes the series sensing coils: pin 2 is the coil (net `Signal Processing`), pin 1 is ground.
- Eleven capacitors can be switched across the coil: C1–C8 (0.47, 1, 2.2, 3.3, 4.7, 10, 22, 47 nF) by SW2 switches 8 down to 1, and C9–C11 (82, 100, 150 nF) by SW1 switches 3 down to 1, 422.67 nF in total. [`docs/simulation/README.md`](simulation/README.md) lists the switch settings for target frequencies.
- Damping: R1 (220 Ω) and trimmer RV1 (1 kΩ) in series with two TN0606 NMOS transistors source to source, which switch the coil to ground. GPIO15 drives both gates through R2 (100 Ω); R3 (10 kΩ) holds them off.

Signal Processing sheet: J5 ("Amplifier Input") carries the coil out to the amplifier and J6 ("Amplifier Output") brings it back. A note on the sheet reserves it for the amplifier and filter if they move onto the board.

MCU sheet:

- J2 ("Power") feeds U1, an LMR36510 buck converter with L1 (22 µH) and feedback R4/R5 (100 kΩ/24.9 kΩ), so the 5 V rail is 1.0 V × (1 + 100/24.9) ≈ 5.02 V. It powers the Pico (VSYS), the ADS1256 module (J3 pin 1), and J7. The Pico's VBUS pin is unconnected.
- R6/R7 (10 kΩ each) halve the 5 V rail and U2, an OPA320 (symbol MCP6001-OT), buffers it as `2.5VBias` (TP5).
- J6 pin 2 → C21 (1 µF) → R9 (510 Ω) → `FinalSignal` → J4 pin 1. R8 (10 kΩ) biases `FinalSignal` to 2.5 V, and D1/D2 (1N4148W) clamp it to within a diode drop of the bias. J4 pin 3 carries `2.5VBias`; pins 2 and 4 are ground.
- J3 matches the HiLetgo ADS1256 module's digital header: 5 V, GND, SCLK (GP18), DIN (GP19), DOUT (GP16), DRDY (GP20), CS (GP17), and PDWN (not connected).
- SW3 and SW4 pull GPIO27 and GPIO28 to ground (use internal pull-ups). J7 ("UART") brings out GND, GPIO1, GPIO0, and 5 V.

## Off-board amplifier

`ltspice/AmplificationSim.asc` models the coil as a 10 µV, 2268 Hz FID source (τ = 0.95 s) in series with 39 Ω and 28.11 mH, the tank as C1 = 180 nF ± 5 %, and two non-inverting stages between J5 and J6:

- C4 (1 µF) couples the tank into U1's +IN, which R8 (1 MΩ) biases at 2.5 V. R3/R4 (50 kΩ/1 kΩ) set a gain of 51 about 2.5 V.
- C5 (4.6 nF) and R9 (33 kΩ, to 2.5 V) high-pass the first stage at 1.05 kHz into U2, another gain-of-51 stage (R10/R11).
- C6 (18 nF) and R12 (33 kΩ, to ground) high-pass the output at 268 Hz to J6.
- C2 (1 µF) and R2 (10 kΩ to 2.5 V) are the board's C21 and R8. R1/C3 and R13/C7 model the ADS1256 inputs; R14/C8 and R15/C9 model op-amp input impedance. V6, a 60 Hz source, is drawn but not connected.

Both op amps are LTspice `UniversalOpAmp2` models (Avol 316k, GBW 3 MHz, slew 2.4 V/µs, 2.7 nV/√Hz with a 240 Hz 1/f corner, 0.6 fA/√Hz, 0.5 mV offset, outputs within 0.1 V of the 0 and 5 V rails). No part number is given. [`docs/breadboard/`](breadboard/README.md) lays the stages out on a breadboard powered from TP4 (5 V) and TP5 (2.5 V); [`docs/simulation/`](simulation/README.md) has the simulated response.

## Firmware

`firmware/` is [hjvania10-rgb/PicoProgramECE455](https://github.com/hjvania10-rgb/PicoProgramECE455) at commit `e9b393a` (2026-09-30), built with Pico SDK 2.3.1 for `PICO_BOARD pico2`.

- SPI0 at 1 MHz, mode 1. The ADS1256 runs with its input buffer on, auto-calibration off, MUX AIN1 − AIN0, PGA 64, and DRATE 15 kSPS, and self-calibrates at start-up. A comment notes that the board delivers about 20 kSPS in practice; the fit uses the rate measured from the Pico's clock.
- Each capture stops after 4 s, or when the AC RMS of a 100 ms window falls to 10 % of the first window's.
- Frequency comes from positive zero crossings with hysteresis (1 % of the initial peak-to-peak), interpolated at the record mean and fitted by least squares against cycle number. Gaps between crossings are converted to whole cycles using a 2 kHz center frequency. Results outside 1.425–2.625 kHz are rejected.
- The field is f / 42.57747892 MHz/T.
- The results and the first 10 ms of samples go over USB serial to `firmware/adc_plots.py`, which plots them. Its serial port is hard-coded as `COM5`.
- The firmware does not yet drive the damping switch (GPIO15), the polarization board, or the buttons.

## Coils and mechanics

`spreadsheets/TuningCapacitors.xlsx` gives the two sensing coils as 13.45 mH and 13.13 mH (26.58 mH in series, mutual inductance neglected) and tabulates LC resonance from 0 to 400 nF. `3d_models/` holds the SolidWorks parts and sliced print files for sensing coil V1 and polarizing coil V2.

## Open issues

`make test` checks what the files can establish: each board against its schematic, the BOM export, the firmware's SPI pins against J3, the LTspice parts that sit on the board, the breadboard against the LTspice netlist, and the firmware estimator on synthetic FIDs. These issues remain:

1. **ADC range.** With PGA 64 and VREF 2.05 V the ADS1256 full scale is ±64 mV. The drawing's 10 µV FID reaches about 200 mV at the ADC, three times full scale. Clipping leaves the zero-crossing frequency intact, but it saturates Vpp and the 10 % decay stop. PGA 16 or less, or less gain, would fit. The real FID amplitude has not been measured.
2. **ADC channels.** The firmware measures AIN1 − AIN0. The drawing calls the signal AIN1 and the 2.5 V bias AIN3, and the board puts them on J4 pins 1 and 3. Which ADS1256 inputs those pins reach depends on the module's header, which has not been checked against the part.
3. **Coil inductance and bank total.** The workbook's coils sum to 26.58 mH, while the drawing uses 28.11 mH, about a 3 % frequency difference. The workbook's reference bank total is 392.67 nF; the board's bank is 422.67 nF. Measure the series pair as installed.
4. **Gyromagnetic ratio.** The firmware and the workbook convert with the free-proton ratio. Protons in water are shielded, and their ratio is 25.7 ppm lower, so the reported field reads about 1.4 nT low at 53 µT. Anomalies are unaffected.
5. **Estimator at low SNR.** When noise approaches the decayed FID amplitude, missed crossings are counted with the fixed 2 kHz center frequency. Near 1.5 kHz two periods then count as three, and the fit is biased by tens of hertz. `util/tests/test_firmware.py` records this as an expected failure.
6. **Simulation step.** The drawing's `.tran` limits the step to 34 µs, about 13 points per cycle. That detunes the tank in the integration and understates the FID by about 13 %. Use about 4 µs.
7. **Parts not chosen.** No op-amp part is named. R3/R10 (50 kΩ) and C5 (4.6 nF) are not standard values; 51 kΩ and 4.7 nF are the nearest.
8. **Control lines.** No connector routes a Pico GPIO to the polarization board's J3, and the firmware does not sequence polarization, damping, and capture.
9. **Schematic hygiene.** Twenty-two unused Pico pins have no no-connect flags, so KiCad ERC will report them.
