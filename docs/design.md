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

`firmware/` is [hjvania10-rgb/PicoProgramECE455](https://github.com/hjvania10-rgb/PicoProgramECE455) at commit `3450aba` (2026-10-28), built with Pico SDK 2.3.1 for `PICO_BOARD pico2` (`make pico`, `make flash`).

- SPI0 at 1 MHz, mode 1. The ADS1256 runs with its input buffer on, auto-calibration off, MUX AIN1 − AIN0, PGA 64, VREF taken as 2.08 V, and DRATE 15 kSPS, and self-calibrates at start-up. The fit uses the sample rate measured from the Pico's clock.
- The start button (SW3, GP27) runs one measurement: GP0 high for 8 s to drive the polarization board, a 50 ms wait, then a capture that stops after 3 s or when the AC RMS of a 100 ms window falls to 10 % of the first window's. Presses are accepted at most every 10 s. GP0 reaches the board only on J7 pin 3, so a cable from J7 to the polarization board's J3 carries it.
- Frequency comes from positive zero crossings with hysteresis (1 % of the initial peak-to-peak), interpolated at the record mean and fitted by least squares against cycle number. Gaps between crossings are converted to whole cycles using a 2 kHz center frequency. Results outside 1.425–2.625 kHz are rejected, and valid results get an empirical +0.05 Hz correction (about 1.2 nT).
- The field is f / 42.57747892 MHz/T.
- The results and the whole record go over USB serial, the samples in binary, to `firmware/adc_plots.py`, which plots the capture and its 100–150 ms window.
- The firmware does not drive the damping switch (GPIO15).

## Coils and FID

`spreadsheets/CoilDesign.xlsx` plans both coils and `3d_models/` holds their printed forms. `util/printfile.py` measures the forms from the sliced G-code, and `make test` checks them against the workbook.

- Polarizing coil (form V2): 331 turns of 0.714 mm wire on a 146 × 76 mm core, 100 mm long, with a 71 × 141 mm opening. At 3 A it should give 8.6 mT at the center, with 9.8 mH and 7.9 Ω. It needs about 24 V for 3 A, and its current falls to zero in about 0.37 ms through the TVS.
- Sensing coils (form V1): each a closed-bottom cup with a 60 × 60 mm core, a 56 × 56 mm opening for the water, and a 100 mm winding between 70 × 70 mm flanges. The plan is 1477 turns of 0.462 mm wire, about 76 mH and 50 Ω each.
- The two sensing cups fit side by side in the polarizing form's opening with about 1 mm to spare, and when seated their windings line up with the polarizer's. The forms appear made to nest, with the sensing coils sharing the polarizing coil's axis.
- As built, the coils look smaller than planned. `TuningCapacitors.xlsx` gives 13.45 and 13.13 mH, and the LTspice drawing uses 39 Ω for the pair. Inverting the workbook's formulas, both imply about 600–630 turns per coil, not 1477.

The FID amplitude follows from Curie's law. [`simulation/README.md`](simulation/README.md#fid-amplitude) works it out for the pair in series, with water filling each opening, full polarization at 8.6 mT, and the polarizing axis perpendicular to Earth's field: about 4.7 µV with the planned windings and about 2.0 µV as built. These are best cases; partial filling, incomplete polarization (water's T1 is 2–3 s), the field direction, and the coils' finite length all reduce them. The LTspice drawing assumes 10 µV.

## Open issues

`make test` checks what the files can establish: each board against its schematic, the BOM export, the firmware's SPI pins against J3, the LTspice parts that sit on the board, the breadboard against the LTspice netlist, the printed coil forms against the coil workbook, and the firmware estimator on synthetic FIDs. These issues remain:

1. **Polarizer turn-off pickup.** If the sensing coils sit inside the polarizing coil as the forms suggest, its turn-off induces roughly 120 V in the as-built pair, open circuit, for about 0.4 ms (300 V with the planned windings). That is a center-field estimate, so the real figure is lower but of the same order. The damping MOSFETs (TN0606) are 60 V parts. The coil net also reaches the tuning capacitors (C1 is rated 50 V) and, through J5 and C4, an op-amp input with no protection. The input coupling (C4 1 µF, R8 1 MΩ) would then take seconds to recover. Measure the pickup with the sensing circuit disconnected before connecting the amplifier, and plan clamping or switching to match.
2. **FID amplitude and the estimator.** The best-case FID as built is about 2 µV, which puts 30–40 mV at the ADC, about 40 times the simulated wideband noise of 1 mV. With that noise, `util/tests/test_firmware.py` shows the firmware's estimator within 0.1 nT at 2.27 kHz. At 1.5 kHz the same FID comes out 0.5–1.5 Hz high (10–35 nT), which the tests record as an expected failure. In a wider amplitude sweep, below about 1 µV at the coils the estimate was wrong across the whole band while still reported as valid. The real FID will be smaller than the best case, so this margin matters.
3. **ADC range.** With PGA 64 and VREF 2.05 V the ADS1256 full scale is ±64 mV. The as-built estimate fits. The drawing's 10 µV FID would reach about 200 mV and clip, which leaves the zero-crossing frequency intact but saturates Vpp and the 10 % decay stop. Choose the PGA from a measured FID.
4. **ADC channels.** The firmware measures AIN1 − AIN0. The drawing calls the signal AIN1 and the 2.5 V bias AIN3, and the board puts them on J4 pins 1 and 3. Which ADS1256 inputs those pins reach depends on the module's header, which has not been checked against the part.
5. **Coil inductance and bank total.** The workbook's coils sum to 26.58 mH, while the drawing uses 28.11 mH, about a 3 % frequency difference. The workbook's reference bank total is 392.67 nF; the board's bank is 422.67 nF. Measure the series pair as installed.
6. **Gyromagnetic ratio.** The firmware and the workbook convert with the free-proton ratio. Protons in water are shielded, and their ratio is 25.7 ppm lower, so the reported field reads about 1.4 nT low at 53 µT. Anomalies are unaffected.
7. **Estimator cycle counting.** The failures in issue 2 come from converting missed crossings to cycles with the fixed 2 kHz center frequency: near 1.5 kHz two periods count as three. The record also runs into noise, because the amplifier passes about twice as much noise outside the 1.5–2.5 kHz band as inside it and the 10 % stop rule cannot trigger once noise exceeds a tenth of the initial amplitude. Band-pass filtering before the crossing detector, counting with the tuned frequency, and flagging low-SNR results would help.
8. **Simulation step.** The drawing's `.tran` limits the step to 34 µs, about 13 points per cycle. That detunes the tank in the integration and understates the FID by about 13 %. Use about 4 µs.
9. **Parts not chosen.** No op-amp part is named. R3/R10 (50 kΩ) and C5 (4.6 nF) are not standard values; 51 kΩ and 4.7 nF are the nearest.
10. **Control lines.** The firmware drives the polarizer from GP0, which leaves the board only on J7, so J7 needs a cable to the polarization board's J3. It waits a fixed 50 ms after switching the polarizer off and never drives the damping switch (GPIO15), so damping, blanking, and turn-off pickup are not yet sequenced.
11. **Schematic hygiene.** Twenty-two unused Pico pins have no no-connect flags, so KiCad ERC will report them.
