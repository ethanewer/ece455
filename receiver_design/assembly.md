# Receiver prototype wiring

This guide describes the **logical** wiring for a perfboard prototype using the two purchased modules and the Thomson kit. It does not identify the purchased ADS1256 board's physical header positions. Read each signal name from that board's silkscreen and verify its SPI voltage before making a permanent connection. The coil, tuning capacitor, and damping resistor are external to this receiver.

## Identify parts

- Use the counted values in [bom.csv](bom.csv). Check each resistor with a meter. Check the ceramic capacitor markings and C5's voltage rating before use.
- For each 1N4148, the painted band marks the **cathode**. For each 2N3904, verify the actual kit part's emitter, base, and collector against its marking and datasheet; the nominal KiCad symbol maps pins 1/2/3 to E/B/C. Do not infer lead order solely from the drawing.
- C6 and C14 are polarized: their positive terminals go to VBIAS and USB 5 V respectively, and their negative terminals go to GND.
- All grounds are one net. Power the XIAO through USB; connect its VBUS to the ADC module's labelled 5 V input. Do not feed a second external 5 V source into VBUS while USB is connected.

## Analog wiring

| Net | Connections |
|---|---|
| `RECEIVER_IN` | External sensor signal J1, C5 one side |
| `COUPLED_INPUT` | C5 other side, R1 one side |
| `ADS1256_AIN0_SIGNAL` | R1 other side, R2 one side, C9 one side, D1 cathode, D2 anode, ADC AIN0 |
| `BIAS_RETURN_MID` | R2 other side, R3 one side |
| `VBIAS_1V60` | R3 other side, C9 other side, D1 anode, D2 cathode, R4 other side, R5 one side, C6 positive, C7 one side, ADC AIN1 and unused AIN2–AIN7 |
| `USB_VBUS_5V` | XIAO VBUS, ADC 5 V, R4 one side, C14 positive, optional module SPI pull-up selection |
| `GND` | External sensor return J1, XIAO GND, ADC GND, R5 other side, C6/C14 negative, C7/C10 other side, Q1–Q6 emitters |
| `XIAO_3V3_OUT` | XIAO 3V3, C10 one side, R18/R19 one side, optional module SPI pull-up selection |

R1 is 10 kΩ; R2/R3 are 1 MΩ each; R4 is 1 kΩ; R5 is 470 Ω. C5 is 22 nF; C9 is 100 pF; C6 is 47 µF; C7/C10 are 100 nF; C14 is 1 µF. D1/D2 are 1N4148.

## SPI transistor wiring

Every Q1–Q6 uses the same four-terminal pattern: emitter to GND; source signal through its listed 10 kΩ base resistor to the base; collector to its output signal; a 2.2 kΩ pull-up from that output to the listed rail; and a 1N4148 Baker diode with **anode at base and cathode at collector**. The XIAO firmware must invert each signal at its GPIO pad.

| Stage | Source through base resistor | Collector output | 2.2 kΩ pull-up | Baker diode |
|---|---|---|---|---|
| Q1 / R6 | XIAO D8 / GPIO2 SCLK | ADC SCLK | R12 to module SPI rail | D3 |
| Q2 / R7 | XIAO D10 / GPIO3 MOSI | ADC DIN | R13 to module SPI rail | D4 |
| Q3 / R8 | XIAO D3 / GPIO5 CS | ADC CS | R14 to module SPI rail | D5 |
| Q4 / R9 | XIAO D4 / GPIO6 SYNC/PDWN | ADC PDWN | R15 to module SPI rail | D6 |
| Q5 / R10 | ADC DOUT | XIAO D9 / GPIO4 MISO | R16 to XIAO 3V3 | D7 |
| Q6 / R11 | ADC DRDY | XIAO D2 / GPIO28 DRDY | R17 to XIAO 3V3 | D8 |

R18/R19 (10 kΩ) connect XIAO 3V3 to the MCU SCLK/MOSI nets so module SCLK/DIN idle low while the XIAO pins are high impedance. R20/R21 (100 kΩ) connect the MCU SYNC/PDWN and CS nets to GND so the module pins idle high. R22/R23 (10 kΩ) pull module DOUT/DRDY to the **measured module SPI rail** while those outputs are high impedance.

JP1 is a single selectable connection: join its centre rail to **either** XIAO 3V3 **or** USB 5 V, matching the actual module SPI header. On perfboard use one wire link. Never connect both rails together. The ADS1256 chip itself permits at most 3.6 V on DVDD; the module's 5 V power input does not establish its SPI pin level. Measure the powered board's DRDY high voltage or inspect its actual schematic first.

## First power and input checks

1. Leave J1 and the ADC module disconnected. Inspect all diode directions, transistor leads, electrolytic polarity, and shorts between 5 V, 3V3, and GND.
2. Power the XIAO from USB and measure VBUS, 3V3, and VBIAS. VBIAS should be near 1.60 V. Disconnect power if it is outside the ADS1256 buffered input range of 0–3 V.
3. Power and inspect the ADC module separately. Record its actual header labels and measure its SPI output high level. Select one JP1 rail; confirm the selected rail with a meter before connecting Q1–Q6 to the module.
4. Connect the digital wires by **signal labels**, then scope SCLK, DIN, DOUT, CS, DRDY, and SYNC/PDWN on both sides of their translators. Confirm polarity and timing at the intended SPI clock before relying on 30 kSPS capture.
5. With J1 still disconnected from the coil, inject a small calibrated sine through a known source resistance. Measure AIN0 − AIN1, noise, and the ADC samples. The analog path is near unity gain; the ADS1256 PGA provides the active gain.
6. Measure the polarizer turnoff pulse at the external sensor output without this receiver attached. Confirm C5 voltage rating, R1/diode pulse current, AIN0 range, and 200 ms recovery before connecting the actual sensor.

This guide does not replace a checked graphical schematic or board layout. The SPI acquisition and USB reporting firmware are still required for a functioning instrument.
