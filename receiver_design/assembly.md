# Receiver prototype wiring

This guide covers preparing the purchased AD8421 module, wiring it to the two already purchased modules, and bringing the receiver up. Buy the items in [`amazon_purchases.json`](../amazon_purchases.json), preferably with its recommended extras: a spare AD8421 module in case the RFI-part removal goes wrong, and clip-on ferrites. The lab parts are listed in [bom.csv](bom.csv). The coil, tuning capacitor, and damping resistor are external to this receiver. The construction schematic (`docs/receiver-construction-schematic.png`, also in `make export`) shows the same circuit.

Signal names below are **logical**. Read each one from the boards' silkscreens before making a permanent connection; this guide does not establish either module's physical header order.

## Prepare the AD8421 module

1. **Confirm the chip.** It should be marked AD8421 (SOIC-8: pin 1 −IN, 2 and 3 RG, 4 +IN, 5 −VS, 6 REF, 7 OUT, 8 +VS).
2. **Remove the input RFI network.** The listing photos show parts between the input SMA jacks and the AD8421's pins 1 and 4. They are silkscreened R3, R5, C4, C5, and C7, but trace them with a meter on the board in hand.
   - Remove every capacitor from +IN or −IN to ground or between them.
   - Measure the series input resistors. If either exceeds 50 Ω, bridge it with a short wire. A pair of 1 kΩ resistors would add 5.8 nV/√Hz.
   - With the module unpowered, the resistance from the +IN SMA center to the AD8421's pin 4 should be under 50 Ω. The capacitance from +IN to GND should be under 50 pF.
3. **Set the gain.** Fit R1 (100 Ω) across the GAIN footprint so that it connects pins 2 and 3; confirm with a meter. If R2 on the module is populated, measure it: the RG pads see R1 in parallel with it, and the gain is 1 + 9.9 kΩ/RG. Remove it if it lowers RG below about 95 Ω.
4. **Tie −IN to ground.** Fit the input jumper between −IN and GND. Run J1 to the +IN pin of the same 3-pin header (or the +IN SMA jack) and J1 return to its GND pin.
5. **Select BIAS for REF.** Fit the jumper that connects REF to the BIAS trimmer's buffer, not to GND. Confirm with a meter that REF follows the trimmer.

## Wiring

| Net | Connections |
|---|---|
| `BAT_POS_9V` | BT1 + (W2 red), module V+ terminal |
| `GND` | BT1 − and BT2 + (W2 black, W3 red), module GND terminal, module −IN jumper, J1 return, Q1 emitter, Q2 collector and base, W1 shield lead, C1, C2, ADS1256 AIN1, ADS1256 GND, XIAO GND |
| `BAT_NEG_9V` | BT2 − (W3 black), module V− terminal |
| `RECEIVER_IN` | J1 signal, Q1 collector and base, Q2 emitter, module +IN |
| `AD8421_RG_A` / `_B` | R1, on the module |
| `AD8421_OUT` | module OUT SMA jack, W1 signal lead, R2 one side |
| `AAF_MID` | R2 other side (1 kΩ), C1 (22 nF), R3 one side (10 kΩ) |
| `ADS1256_AIN0` | R3 other side, C2 (2.2 nF), ADS1256 AIN0 |
| `USB_VBUS_5V` | XIAO VBUS, ADS1256 module 5 V |

- **Q1 and Q2 are clamp diodes made from 2N3904s:** join each one's collector and base leads. Q1's joined C/B goes to J1 signal and its emitter to GND. Q2's joined C/B goes to GND and its emitter to J1 signal. Fit them at the module's input header.
- **W1:** before wiring, use a meter to find which Dupont lead reaches the SMA center pin. That lead is the signal; the other is GND.
- **Placement:** fit R2, C1, R3, and C2 on a breadboard next to the ADS1256 module, with short leads from C1 and C2 to the ADS1256 GND. Take C1 and C2 from the kit's ceramic capacitors.
- **Ferrites (recommended extra):** snap a 5 mm clip-on ferrite onto the J1 pair next to the module input and another onto W1 next to the breadboard. They suppress common-mode RF from tens of MHz up (phones, FM, Wi-Fi), which the AD8421 could otherwise rectify into a DC shift now that its RFI network is removed. The RC filter, not the ferrites, handles the 1.92 MHz alias band.
- **Ground:** all grounds are one net. Join the battery midpoint to the ADS1256 GND with one wire (W1's shield is the second return path; keep it short). Twist the J1 pair.
- **Power:** power the XIAO and ADS1256 through USB. Do not feed a second 5 V source into VBUS while USB is connected.

SPI and control lines are direct wires:

| XIAO | ADS1256 module |
|---|---|
| D8 / GPIO2 | SCLK |
| D10 / GPIO3 | DIN |
| D9 / GPIO4 | DOUT |
| D3 / GPIO5 | CS |
| D2 / GPIO28 | DRDY |
| D4 / GPIO6 | SYNC/PDWN |

## First power and bench checks

1. Short J1. Connect the batteries to the module only (W1 unplugged) and measure the supply current. The AD8421 draws at most 2.3 mA; the module's power LEDs and BIAS buffer add to that. Disconnect the batteries when idle.
2. Measure +9 V and −9 V at the module terminals. Trim the BIAS trimmer until OUT reads 2.50 V. The AD8421 output swings to 1.6 V below V+ and 1.2 V above V−; the requirements are checked down to 6.0 V per battery.
3. Connect W1 and the filter with the ADS1256 module powered from USB. Measure:

   | Point | Expected |
   |---|---|
   | OUT (TP3) | 2.50 V |
   | AAF_MID | ≈2.49 V |
   | AIN0 (TP4) | ≈2.39 V |

   Scope OUT and AIN0 for oscillation; there should be none.
4. Drive J1 from a signal generator through a 1000:1 divider (for example 100 kΩ over 100 Ω) at 10 µV to 1 mV peak.
   - Sweep 100 Hz–50 kHz. Expect about 85 V/V from J1 to AIN0 across 1.6–2.2 kHz and a −3 dB corner near 4.6 kHz.
   - Load J1 with a known 1 MΩ series resistor and compare amplitudes to confirm |Z_in| ≥ 1 MΩ.
   - Raise a 300 Hz tone at J1 to 10 mV peak and confirm neither OUT nor AIN0 clips.
5. With the generator off, measure AIN0 noise with J1 shorted and with 30 kΩ at J1. Simulation predicts about 7 µV and 49 µV RMS in the 1.6–2.2 kHz band.
6. Measure the ADS1256 module's DRDY high level (expect about 3.3 V) before wiring the SPI directly to the XIAO.
7. Connect the ADC. Configure AIN0 − AIN1, buffer **off**, PGA 1, and 30 kSPS, and repeat steps 4–5 from the ADC samples.
8. Measure the polarizer turnoff pulse at the external sensor output without this receiver attached. Confirm Q1/Q2 clamp current and the AD8421's overload recovery before connecting the actual sensor.

This guide does not replace a checked board layout. The SPI acquisition and USB reporting firmware are still required for a functioning instrument.
