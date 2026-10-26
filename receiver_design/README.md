# Active receiver design

The receiver is a purchased AD8421 instrumentation-amplifier module followed by a two-section RC anti-aliasing filter. It sits between the external sensor (J1) and the already purchased HiLetgo ADS1256 module, which is controlled by the already purchased Seeed XIAO RP2350. Everything to buy is listed, with Amazon links and prices, in [`amazon_purchases.json`](../amazon_purchases.json) at the repository root: $48.95 of a $50 budget for the required items, or $86.62 with the recommended spare module and clip-on ferrites.

## Requirements

`requirements.py` defines the requirements, and **`make verify` fails if any of them is missed**. `verify.py` simulates the deck at ten corners and exits with an error listing each failure:

- nominal;
- 0 °C and 50 °C;
- 4.75 V USB;
- batteries at 6.0 V (end of life) and 9.6 V (fresh);
- filter capacitors −10% with R1 −5%, and +10% with R1 +5%;
- two stacked corners. The first is 50 °C, 4.75 V USB, 6.0 V batteries, BIAS trimmed to 2.75 V, capacitors −10%, and R1 −5%. The second is 50 °C, BIAS 2.25 V, capacitors +10%, and R1 +5%.

| Requirement | Limit | How it is checked |
|---|---|---|
| Input impedance at J1 | \|Z_in\| ≥ 1 MΩ everywhere in 1.5–2.5 kHz | ngspice AC, V(J1)/I(source) |
| Noise | ≤ 5 nV/√Hz everywhere in 1.6–2.2 kHz | ngspice `.noise` with the untuned coil pair at J1, referred to the coil EMF, plus the ADS1256's 10.3 µV RMS referred through the minimum in-band gain |
| Interference | No clipping for a **10 mV peak tone at 50–400 Hz** or a **2 mV peak tone at 8–50 kHz** at J1 | DC headroom divided by gain from J1 at the AD8421 input range, the AD8421 output swing, and the ADS1256 AIN0 range |
| Anti-aliasing | Gain from J1 to AIN0 within 2.2 kHz of 1.92 MHz at least **90 dB** below the minimum in-band gain | ngspice AC across 1.9178–1.9222 MHz |

The noise limit comes from the frequency Cramér–Rao bound. At 5 nV/√Hz it is about 0.24 nT for the pessimistic 0.41 µV FID, a 4× margin under the 1 nT target. The interference limits cover mains and its harmonics, plus switching and audio-band pickup.

The ADS1256 is a delta-sigma converter. Its modulator samples at 1.92 MHz, and its digital filter rejects anything that would fold into 1.6–2.2 kHz by at least 110 dB at 30 kSPS. The exception is the band around 1.92 MHz itself, where the filter's response repeats. Only an analog filter can reject that band, which is why the anti-aliasing requirement exists.

There is no minimum gain requirement. The gain only has to make the ADC's own noise small, and the noise requirement already includes it.

## Simulated performance

These are ngspice values from `spice/receiver.cir` with a datasheet-based AD8421 model (see `analysis/README.md` and the `make verify` table), not measurements.

| Quantity | Nominal | Worst of ten corners |
|---|---|---|
| Gain J1 → AIN0, 1.6–2.2 kHz | 83.4–87.0 V/V | ≥ 77.9 V/V |
| \|Z_in\|, 1.5–2.5 kHz | 4.25–7.08 MΩ | ≥ 4.21 MΩ |
| Input noise with the untuned coil, including the ADC | 3.89 nV/√Hz | ≤ 4.06 nV/√Hz |
| Largest tone without clipping, 50–400 Hz | 27.2 mV (AIN0 range) | 15.7 mV |
| Largest tone without clipping, 8–50 kHz | 49.0 mV (AD8421 output) | 15.7 mV |
| Alias rejection near 1.92 MHz | 98.2 dB | ≥ 96.5 dB |
| Frequency CRB, untuned coil | 0.021 nT (3.59 µV FID), 0.188 nT (0.41 µV FID) | — |
| Input noise, 30 kΩ tuned-sensor fixture | 23.4 nV/√Hz, 0.4 dB noise figure | — |
| Low-pass −3 dB corner | 4.57 kHz | — |
| DC at AD8421 OUT / AIN0 | 2.50 V / 2.39 V | — |

The ADC's converter noise referred to J1 is 1.0 nV/√Hz. The amplifier alone (input shorted) is 3.6 nV/√Hz: the AD8421's 3.2 nV/√Hz maximum, R1's 1.3 nV/√Hz, and its 60 nV/√Hz output noise divided by the gain.

With the external tuning capacitor fitted, the receiver adds little: the 30 kΩ fixture result is 0.4 dB above the source's own thermal noise. Referred to the coil EMF that is about 1.35 nV/√Hz, against 3.89 nV/√Hz untuned, so tuning the coil is the largest remaining noise improvement.

A more expensive amplifier would not help. The AD8429 (1 nV/√Hz, but 1.5 pA/√Hz current noise) simulates at 3.86 nV/√Hz with the untuned coil and 50 nV/√Hz with the 30 kΩ fixture. The coil's roughly 2 kΩ reactance, and the tuned tank's 30 kΩ, turn its current noise into voltage noise. The ADC already contributes only 1.0 nV/√Hz, so a better converter would not help either.

The worst interference corner has 6.0 V batteries, BIAS at 2.75 V, and the highest gain. There the AD8421 output reaches its +VS − 1.6 V swing limit first.

## Circuit

Reference designators match `spice/receiver.cir`, `bom.csv`, and the construction schematic.

1. **Input clamps.** Q1 and Q2 are 2N3904s connected as diodes, collector tied to base. They clamp J1 to about ±0.65 V with negligible leakage. The AD8421 also tolerates 40 V from the opposite rail, but the clamps limit what reaches it during the polarizer turnoff.
2. **AD8421 module (MOD2), gain 100.**
   - The module's input jumper ties −IN to GND, so J1 drives +IN single-ended.
   - R1 (100 Ω) fits the module's GAIN footprint: G = 1 + 9.9 kΩ/R1 = 100.
   - The module's BIAS trimmer and on-board buffer drive REF. With J1 shorted, trim OUT to 2.50 V, the middle of AIN0's range.
   - The module's input RFI network must be removed (see `assembly.md`). The datasheet example (1 nF common mode, 10 nF differential) would load J1 to a few kilohms and detune the coil. A test in `tests/test_eda.py` shows that it fails the |Z_in| requirement.
   - Two 9 V batteries (BT1, BT2) through snap leads (W2, W3) give ±9 V. Their midpoint is the system ground.
3. **Cable.** W1, an SMA-to-Dupont lead, carries OUT from the module's SMA jack to the breadboard.
4. **Anti-aliasing filter.** R2 (1 kΩ) with C1 (22 nF), then R3 (10 kΩ) with C2 (2.2 nF), both poles near 7.2 kHz.
   - The second section has ten times the impedance of the first, so the sections barely load each other.
   - Response: −0.8 dB at 2.2 kHz, −14 dB at the 15 kHz Nyquist frequency, and about −96 dB at 1.92 MHz.
   - The 11 kΩ in series also limits fault current into AIN0 to under 1 mA, well inside the ADS1256's 10 mA input-current rating. External clamp diodes are therefore not fitted.
5. **ADC.** AIN0 takes the filter output and AIN1 is wired to GND.

## ADC configuration and SPI

Configure the ADS1256 for AIN0 − AIN1, input buffer **off**, **PGA 1** (±5 V full scale), and 30 kSPS. With the buffer off, AIN0 may span AGND − 0.1 V to AVDD + 0.1 V, so AIN1 can sit at GND and AIN0 at 2.4 V. The converter noise at this setting is 10.3 µV RMS (TI Table 4), the same as with the buffer on. The model includes the unbuffered input's effective impedance (TI Table 10, 260 kΩ and 220 kΩ at PGA 1), which costs about 8% of the gain. Leave AIN2–AIN7 unconnected.

The SPI connects **directly** to the XIAO. The ADS1256 datasheet specifies SCLK, DIN, CS, and SYNC/PDWN as inputs accepting up to 5.25 V. DOUT and DRDY swing only to DVDD, which is at most 3.6 V. Before connecting, measure the powered module's DRDY high level; expect about 3.3 V.

| Function | XIAO pin | RP2350 GPIO | Module pin |
|---|---|---:|---|
| ADS1256 DRDY | D2 | GPIO28 | DRDY (input to XIAO) |
| ADS1256 CS | D3 | GPIO5 | CS |
| ADS1256 SYNC/PDWN | D4 | GPIO6 | PDWN |
| SPI0 SCLK | D8 | GPIO2 | SCLK |
| SPI0 MISO | D9 | GPIO4 | DOUT |
| SPI0 MOSI | D10 | GPIO3 | DIN |
| 5 V / GND | VBUS / GND | — | 5V / GND |

Firmware must do the following:

1. Drive CS and SYNC/PDWN high.
2. Wait for DRDY.
3. Configure the ADC.
4. For each measurement, ignore conversions during the blank.
5. Pulse SYNC/PDWN low briefly (under 20 DRDY periods) and wait for DRDY before recording.

At 30 kSPS the SPI needs at least 720 kbit/s for 24-bit data, plus command overhead.

J2–J5 give **logical signal names**, not the purchased boards' physical header order. Verify the ADS1256 module's header order and the AD8421 module's jumpers against the boards in hand before wiring. Check each kit transistor's lead order against its marking and datasheet before soldering. KiCad TO-92 symbols number pins 1/2/3 as E/B/C.

## Protection limits

Q1/Q2 take the polarizer turnoff current at J1, limited only by the external sensor's impedance. The 2N3904 is rated 200 mA collector current. The SPICE models do not prove surge survival, and the AD8421 model does not clip or recover from overload. Measure the actual polarizer turnoff voltage and current at the sensor output before connecting it, then measure the AD8421's recovery after the blank.

## Files and status

- `../amazon_purchases.json` lists everything to buy, with links, prices, and the budget. `verify.py` checks that the BOM uses every required item, that the required total fits the budget, and that the recommended extras (spare module, ferrites) have valid links and totals.
- `requirements.py` defines the requirements, the corner set, and the checker used by `verify.py`, the tests, and the analysis report.
- `spice/receiver.cir` is the active ngspice model. It contains the AD8421 behavioral model, which uses datasheet values (Rev. 0) for input impedance, noise, gain, and bandwidth. It omits the module's BIAS/REF path noise, ADC converter noise, the digital filter, SPI timing, firmware blanking, and the external sensor's LC response.
- `analyze.py` generates the committed `analysis/` CSV, PNG, and Markdown artifacts, including |Z_in|, interference tolerance, alias rejection, and the noise/CRB table.
- `schematic.py` draws the construction schematic used by `make export` and `docs/`.
- `breadboard.py` holds the fixed placement on a standard 830-point breadboard, laid out as the board was built, and draws it with the AD8421 module, batteries, cable, ADS1256 module, and XIAO (`docs/receiver-breadboard.png`). It includes a 1000:1 divider so a function generator can stand in for the coil. `make export` checks the receiver against `spice/receiver.cir` and the XIAO-to-ADS1256 wires against `kicad/receiver.net`, then draws the board and lists every hole.
- `bom.csv` lists every fitted and purchased part. Lab parts come from `new_allowed_components.json`.
- `assembly.md` covers module preparation, wiring, and the bring-up sequence.
- `kicad/generate.py` emits the text connectivity netlist `kicad/receiver.net`. `verify.py` checks that it, the SPICE deck, and the BOM describe the same parts and pins. There is no graphical KiCad schematic or PCB, and `make pcb` intentionally fails.

Data sources:

- [Analog Devices AD8421 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ad8421.pdf): noise, input impedance, input and output ranges, gain equation, bandwidth, and the RFI filter example.
- [TI ADS1256 datasheet](https://www.ti.com/lit/ds/symlink/ads1256.pdf): absolute maximum ratings, unbuffered input range and impedance, digital-filter response, digital I/O levels, and Table 4 input-referred noise.
- [onsemi 2N3904 datasheet](https://www.onsemi.com/pdf/datasheet/2n3904-d.pdf): pinout and limits.
