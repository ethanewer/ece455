# Receiver prototype wiring

This guide describes the **logical** wiring for a perfboard prototype using the two purchased modules and the 30 kit parts in [bom.csv](bom.csv). It does not identify the purchased ADS1256 board's physical header positions. Read each signal name from that board's silkscreen before making a permanent connection. The coil, tuning capacitor, and damping resistor are external to this receiver. The construction schematic (`docs/receiver-construction-schematic.png`, also in `make export`) shows the same circuit.

## Identify parts

- Check each resistor with a meter.
- Verify each transistor's emitter, base, and collector against its marking and datasheet. The tables below name terminals, not lead positions. Kit 2N3904 and 2N3906 parts are commonly E-B-C, but do not assume it.
- **Q5 and Q6 are clamp diodes made from 2N3904s:** join each one's collector and base leads. Q5's joined C/B goes to J1 signal and its emitter to GND. Q6's joined C/B goes to GND and its emitter to J1 signal.
- Electrolytics C4, C5, and C6 have their negative leads to GND.
- All grounds are one net. Keep J1, Q5/Q6, C1, Q1, R1, C2, R8, and C4 compact, and return C4 and the J1 ground to the same point. Run AIN1 to BIAS as its own wire alongside the AIN0 wire.
- Power the XIAO through USB. Do not feed a second external 5 V source into VBUS while USB is connected.

## Wiring

| Net | Connections |
|---|---|
| `USB_VBUS_5V` | XIAO VBUS, ADC module 5 V, R11 one side |
| `ANALOG_VA_4V8` | R11 other side, C6 positive, R4, R10, Q2 emitter, Q3 collector, Q7 collector |
| `GND` | J1 return, XIAO GND, ADC GND, Q5 emitter, Q6 collector and base, R5, R6, R9, R14, C3, C7, C4/C5/C6 negative |
| `RECEIVER_IN` | J1 signal, Q5 collector and base, Q6 emitter, C1 one side |
| `Q1_BASE` | C1 other side, R1 one side (470 kΩ), Q1 base |
| `BOOTSTRAP` | R1 other side, C2 one side (100 nF), R2 one side (100 kΩ) |
| `Q1_COLLECTOR` | Q1 collector, R4 other side (20 kΩ), Q2 base |
| `Q1_EMITTER_FEEDBACK` | Q1 emitter, C2 other side, R7 one side (5.1 kΩ), R8 one side (150 Ω) |
| `STAGE1_AC_RETURN` | R8 other side, C4 positive (2.2 µF) |
| `Q2_COLLECTOR` | Q2 collector, R5 (20 kΩ), Q3 base |
| `STAGE1_OUT` | Q3 emitter, R6 (4.7 kΩ), R7 other side, Q4 base |
| `Q4_EMITTER` | Q4 emitter, R9 (1 kΩ), C5 positive (2.2 µF) |
| `STAGE2_OUT` | Q4 collector, R10 other side (20 kΩ), R3 one side (1 MΩ), C7 (1.5 nF), C8 one side (1 nF) |
| `HP_A` | C8 other side, C9 one side (1 nF), R12 one side (68 kΩ) |
| `HP_B` | C9 other side, R13 one side (300 kΩ), Q7 base |
| `ADS1256_AIN0` | Q7 emitter, R12 other side, R14 (100 kΩ), ADC AIN0 |
| `BIAS_AIN1_1V7` | R3 other side, R13 other side, R2 other side, C3 (100 nF), ADC AIN1 |

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

1. Fit R11 and C6 only. Power from USB and confirm that VA is about 4.8 V.
2. Fit the rest of the analog circuit with J1 shorted and the ADC disconnected. After about 1 s, measure:

   | Point | Expected |
   |---|---|
   | AIN0 (TP3) | ≈1.1 V |
   | BIAS (TP4) | ≈1.7 V |
   | Q4 collector (TP8) | ≈2.3 V |
   | Q1 emitter (TP7) | ≈0.9 V |
   | Voltage across R4 | ≈0.64 V, so Q1 ≈ 32 µA |

   AIN0 and BIAS must both lie within 0–3 V. Scope AIN0 and TP8 for oscillation; there should be none.
3. Drive J1 from a signal generator through a 1000:1 divider (for example 100 kΩ over 100 Ω) at 10 µV to 1 mV peak. Sweep 1–7 kHz. Confirm at least 2000 V/V from J1 to AIN0−BIAS across 1.6–2.2 kHz (about 2700 expected, peaking near 1.9 kHz) and −3 dB near 1.0 and 6.4 kHz. Check the mains rejection at 60 Hz (about 0.5 V/V). Load J1 with a known 1 MΩ series resistor and compare amplitudes to confirm |Z_in| ≥ 1 MΩ.
4. With the generator off, measure AIN0−BIAS noise with J1 shorted and with 30 kΩ at J1. Simulation predicts about 0.21 mV and 1.7 mV RMS in the 1.6–2.2 kHz band.
5. Power the ADC module and measure its DRDY high level (expect about 3.3 V) before wiring the SPI directly to the XIAO.
6. Connect the ADC. Configure buffer on, PGA 1, and 30 kSPS, and repeat steps 3–4 from the ADC samples.
7. Measure the polarizer turnoff pulse at the external sensor output without this receiver attached. Confirm Q5/Q6 clamp current and recovery before connecting the actual sensor.

This guide does not replace a checked board layout. The SPI acquisition and USB reporting firmware are still required for a functioning instrument.
