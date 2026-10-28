# Receiver prototype wiring

This guide covers preparing the purchased AD8421 module, wiring it to the two already purchased modules, and bringing the receiver up. Buy the items in [`amazon_purchases.json`](../amazon_purchases.json), preferably with its recommended extras: a spare AD8421 module in case the RFI-part removal goes wrong, and clip-on ferrites. The lab parts are listed in [bom.csv](bom.csv). The coil, tuning capacitor, and damping resistor are external to this receiver. The construction schematic (`docs/receiver-construction-schematic.png`) shows the same circuit. The assembly drawing (`docs/receiver-breadboard.png`, with a hole-by-hole list in `docs/receiver-breadboard.md`; both also in `make export`) shows the AD8421 module, batteries, cable, ADS1256 module, XIAO, and breadboard together. It follows the board as built: clamps in columns 15–19, filter in columns 26–35, XIAO in columns 56–62, and GND on the outer top rail row beside the blue line.

Signal names below are **logical**. Read each one from the boards' silkscreens before making a permanent connection; this guide does not establish either module's physical header order.

## Prepare the AD8421 module

1. **Confirm the chip.** It should be marked AD8421 (SOIC-8: pin 1 −IN, 2 and 3 RG, 4 +IN, 5 −VS, 6 REF, 7 OUT, 8 +VS).
2. **Remove the input RFI network.** The listing photos show parts between the input SMA jacks and the AD8421's pins 1 and 4. They are silkscreened R3, R5, C4, C5, and C7, but trace them with a meter on the board in hand.
   - Remove every capacitor from +IN or −IN to ground or between them.
   - Measure the series input resistors. If either exceeds 50 Ω, bridge it with a short wire. A pair of 1 kΩ resistors would add 5.8 nV/√Hz.
   - With the module unpowered, the resistance from the +IN SMA center to the AD8421's pin 4 should be under 50 Ω. The capacitance from +IN to GND should be under 50 pF.
3. **Set the gain.** Fit R1 (100 Ω) across the GAIN footprint so that it connects pins 2 and 3; confirm with a meter. If R2 on the module is populated, measure it: the RG pads see R1 in parallel with it, and the gain is 1 + 9.9 kΩ/RG. Remove it if it lowers RG below about 95 Ω.
4. **Tie −IN to ground.** Leave the input header's jumper on −IN and GND. That jumper covers the header's GND pin, so the coil does not connect to the module directly. J1 lands on breadboard strip 17, and one jumper (a17) carries it to the header's +IN pin.
5. **Select BIAS for REF.** Fit the jumper that connects REF to the BIAS trimmer's buffer, not to GND. Confirm with a meter that REF follows the trimmer.

## Wiring

| Net | Connections |
|---|---|
| `BAT_POS_9V` | BT1 + (W2 red), module V+ terminal |
| `GND` | BT1 − and BT2 + (W2 black, W3 red), module GND terminal, module −IN jumper, W1 shield lead (T-28); on the breadboard's outer top rail row (T-): J1 return (T-17), Q1 emitter and Q2 collector and base (through a15, a16, a19), C1, C2, ADS1256 AIN1 (T-36), ADS1256 analog-header GND (T-37); XIAO GND (j61) to the ADS1256 digital-header GND |
| `BAT_NEG_9V` | BT2 − (W3 black), module V− terminal |
| `RECEIVER_IN` | breadboard strip 17: J1 signal (e17), Q1 collector, Q2 emitter, and the jumper (a17) to the module's +IN header pin; Q1 base on strip 18, joined by c17–c18 |
| `AD8421_RG_A` / `_B` | R1, on the module |
| `AD8421_OUT` | module OUT SMA jack, W1 signal lead (a26), R2 one side |
| `AAF_MID` | strip 31: R2 other side (1 kΩ), C1 (22 nF), R3 one side (10 kΩ) |
| `ADS1256_AIN0` | strip 35: R3 other side, C2 (2.2 nF), ADS1256 AIN0 (e35) |
| `USB_VBUS_5V` | XIAO 5V pin (j62), ADS1256 module 5V |

- **Q1 and Q2 are clamp diodes made from 2N3904s** on the breadboard. Q1's collector and base go to J1 signal (the yellow c17–c18 jumper joins them) and its emitter to GND. Q2's collector and base both go to GND and its emitter to J1 signal. Fit the c17–c18 jumper before the transistors, which sit over it.
- **W1:** before wiring, use a meter to find which Dupont lead reaches the SMA center pin. That lead is the signal; the other is GND.
- **Placement:** fit the parts at the holes in `docs/receiver-breadboard.md`. Take C1 and C2 from the kit's ceramic capacitors. Their rail legs, RT2's, and the black jumpers go to the outer rail row, past the + row. Keep the AIN0, AIN1, and GND wires to the ADS1256 module short and run them together.
- **+IN jumper:** a male-to-female Dupont jumper from a17 to the module's +IN header pin. Keep it short.
- **ADS1256 module:** its pin labels are on its underside. Wire it with male-to-female Dupont leads: AIN0 from e35, AIN1 from T-36, and one analog-header GND from T-37. Do not jumper AIN1 to the GND pin beside it on the module: AIN1 must sense the breadboard ground next to C2.
- **XIAO:** solder its pin headers if they are not fitted, then plug it across the channel with its pins in rows c and h, columns 56–62, and USB-C past column 63. Its GND pin connects only to the ADS1256 digital-header GND, so its ground reaches the breadboard only through the ADS1256 module.
- **Ferrites (recommended extra):** snap a 5 mm clip-on ferrite onto the J1 pair next to the module input and another onto W1 next to the breadboard. They suppress common-mode RF from tens of MHz up (phones, FM, Wi-Fi), which the AD8421 could otherwise rectify into a DC shift now that its RFI network is removed. The RC filter, not the ferrites, handles the 1.92 MHz alias band.
- **Ground:** all grounds are one net. The batteries' midpoint lands on the AD8421 module's GND terminal, and W1's shield lead is the only ground link from that module to the breadboard. No 9 V supply touches the breadboard. Every ground on the T- rail between columns 11 and 37 is an analog ground; supply and ground-loop currents enter at T-37 or to its right. Twist the J1 pair.
- **Power:** power the XIAO and ADS1256 through USB. Do not feed a second 5 V source into VBUS while USB is connected.

SPI and control lines are direct Dupont wires from the XIAO's strips to the ADS1256 module:

| XIAO pin | Wire from | ADS1256 module |
|---|---|---|
| D8 / GPIO2 | j57 | SCLK |
| D10 / GPIO3 | j59 | DIN |
| D9 / GPIO4 | j58 | DOUT |
| D3 / GPIO5 | a59 | CS |
| D2 / GPIO28 | a60 | DRDY |
| D4 / GPIO6 | a58 | SYNC/PDWN |
| GND | j61 | GND (digital header) |
| 5V | j62 | 5V |

## Test input from a function generator

RT1 and RT2 form a 1000:1 divider so that a function generator can stand in for the coil. The full chain under test is generator → divider → clamps → AD8421 → RC filter → ADS1256 → XIAO.

1. Fit RT1 (100 kΩ, b5–b11), RT2 (100 Ω, a11–T-11), and the green J1 jumper (e11–e17). Measure RT1 and RT2; the voltage at J1 is the generator voltage × RT2 / (RT1 + RT2), about 1/1001.
2. Set the generator's load to **High-Z**. In its 50 Ω mode it displays half the voltage it actually drives into 100 kΩ.
3. Clip the generator's signal lead to a short jumper in e5 and its ground lead to a short jumper in T-40. T-40 is right of every analog ground on the rail. If the generator and the laptop are both earthed, or the generator is powered from the same laptop, a ground-loop current flows from the ground clip to the XIAO's USB ground. Entering at T-40 keeps that current out of the rail between RT2 and the W1 shield, where it would add to the input.
4. Use a sine at 1.6–2.2 kHz:

   | Generator (High-Z) | At J1 | At AIN0 (≈85 V/V) |
   |---|---|---|
   | 200 mVpp | 100 µV peak | ≈8.5 mV peak |
   | 7.2 mVpp | 3.6 µV peak (nominal FID) | ≈0.31 mV peak |
   | 0.82 mVpp | 0.41 µV peak (pessimistic FID) | ≈35 µV peak |

   If the generator cannot go below about 1 mVpp, fit 1 MΩ as RT1 (about 10 000:1) for the smallest level. The generator's own noise is divided by the same ratio, but at its lowest settings it can still exceed the receiver's; compare against a record with the output off. A generator with burst or arbitrary-waveform mode can also play a decaying FID (time constant about 1.5 s).
5. Compare the estimated frequency with the generator's setting. A constant offset comes from the ADS1256 module's 7.68 MHz crystal: each 10 ppm of crystal error moves a 2 kHz estimate by 0.02 Hz, about 0.5 nT. Repeat records to measure the scatter, which is what the receiver noise sets.
6. To return to the coil, remove the green jumper and the generator leads, then connect the coil signal to e17 and the coil return to T-17.

## First power and bench checks

1. Short J1. Connect the batteries to the module only (W1 unplugged) and measure the supply current. The AD8421 draws at most 2.3 mA; the module's power LEDs and BIAS buffer add to that. Disconnect the batteries when idle.
2. Measure +9 V and −9 V at the module terminals. Trim the BIAS trimmer until OUT reads 2.50 V. The AD8421 output swings to 1.6 V below V+ and 1.2 V above V−; the requirements are checked down to 6.0 V per battery.
3. Connect W1 and the filter with the ADS1256 module powered from USB. Measure:

   | Point | Expected |
   |---|---|
   | OUT (TP3, strip 26) | 2.50 V |
   | AAF_MID (strip 31) | ≈2.49 V |
   | AIN0 (TP4, strip 35) | ≈2.39 V |
   | Module GND terminal to the T- rail | under 1 Ω (with the batteries disconnected) |
   | T-11 to T-40 | under 1 Ω (the rail is continuous) |

   Scope OUT and AIN0 for oscillation; there should be none.
4. Drive J1 from a function generator through the test divider (below) at 10 µV to 1 mV peak.
   - Sweep 100 Hz–50 kHz. Expect about 85 V/V from J1 to AIN0 across 1.6–2.2 kHz and a −3 dB corner near 4.6 kHz.
   - Put a known 1 MΩ resistor in series between e11 and e17 in place of the green jumper and compare amplitudes to confirm |Z_in| ≥ 1 MΩ.
   - Raise a 300 Hz tone at J1 to 10 mV peak and confirm neither OUT nor AIN0 clips.
5. With the generator connected but its output off, measure AIN0 noise; RT2 then stands in for the coil's resistance. For the 30 kΩ check, unclip the generator, remove RT1, and fit 30 kΩ in place of RT2. Simulation predicts about 7 µV RMS in the 1.6–2.2 kHz band with J1 shorted (slightly more with RT2) and 49 µV with 30 kΩ.
6. Measure the ADS1256 module's DRDY high level (expect about 3.3 V) before wiring the SPI directly to the XIAO.
7. Connect the ADC. Configure AIN0 − AIN1, buffer **off**, PGA 1, and 30 kSPS, and repeat steps 4–5 from the ADC samples.
8. Measure the polarizer turnoff pulse at the external sensor output without this receiver attached. Confirm Q1/Q2 clamp current and the AD8421's overload recovery before connecting the actual sensor.

This guide does not replace a checked board layout. The SPI acquisition and USB reporting firmware are still required for a functioning instrument.
