# Active receiver design

The receiver is a minimal discrete, low-noise band-pass amplifier between the external sensor (J1) and the already purchased HiLetgo ADS1256 module. It is controlled by the already purchased Seeed XIAO RP2350.

## Requirements

`requirements.py` defines the requirements, and **`make verify` fails if any of them is missed**. `verify.py` simulates the deck at nine corners and exits with an error listing each failure:

- nominal;
- every transistor's beta halved or doubled;
- 0 °C and 50 °C;
- 4.75 V and 5.25 V USB;
- two stacked corners: beta halved at 4.75 V, at 0 °C and at 50 °C.

| Requirement | Limit | How it is checked |
|---|---|---|
| Gain, J1 to AIN0−AIN1 | ≥ 2000 V/V everywhere in **1.6–2.2 kHz** | ngspice AC, minimum over the band |
| Input impedance at J1 | \|Z_in\| ≥ 1 MΩ everywhere in 1.5–2.5 kHz | ngspice AC, V(J1)/I(source) |
| Noise | ≤ 5 nV/√Hz everywhere in 1.6–2.2 kHz | ngspice `.noise` with the untuned coil pair at J1, referred to the coil EMF, plus the ADS1256's 10.7 µV RMS referred through the gain |

The noise limit comes from the frequency Cramér–Rao bound. At 5 nV/√Hz the bound is about 0.24 nT for the pessimistic 0.41 µV FID, with a 1.5 s record at 30 kSPS after a 200 ms blank. That is a 4× margin under the 1 nT target.

The design meets the requirements with **30 fitted parts**: 13 resistors, 9 capacitors, six 2N3904s, and one 2N3906, all from the Thomson kit in `new_allowed_components.json`, plus the two modules. There is no op-amp and no SPI level translator. J1–J3 are logical wire interfaces; TP1–TP8 are optional test points. There is no accepted physical board yet.

## Simulated performance

These are ngspice values from `spice/receiver.cir` with vendor transistor models (see `analysis/README.md` and the `make verify` table), not measurements.

| Quantity | Nominal | Worst of nine corners |
|---|---|---|
| Gain, 1.6–2.2 kHz | 2665–2701 V/V (peak 2701 at 1.88 kHz) | ≥ 2137 V/V (beta ×0.5, 0 °C, 4.75 V) |
| \|Z_in\|, 1.5–2.5 kHz | 1.81–2.32 MΩ | ≥ 1.12 MΩ (same corner) |
| Input noise, untuned coil, 1.6–2.2 kHz | ≤ 3.49 nV/√Hz | ≤ 3.81 nV/√Hz (50 °C) |
| Frequency CRB, untuned coil | 0.019 nT (3.59 µV FID), 0.168 nT (0.41 µV FID) | — |
| Input noise, 30 kΩ tuned-sensor fixture | 25.7 nV/√Hz, 1.2 dB noise figure | — |
| −3 dB band | 1.02–6.41 kHz | — |
| Gain at 60 Hz / 20 kHz | 0.46 / 796 V/V | — |
| DC at AIN0 / AIN1 (BIAS) | 1.11 V / 1.70 V | — |
| Supply | 0.36 mA from USB 5 V; VA ≈ 4.83 V | — |

With PGA 1, the ADS1256's converter noise is about 4.5 nV RMS referred to J1. It is negligible.

Other checks from the same deck:
- **Stability:** a stage-1 step overshoots 8%. The Q7 follower's gain peaks at 0.977, and the response falls monotonically from 10 kHz to 100 MHz.
- **Power-up** settles in 0.3 s.
- **Overload recovery:** after a ±10 V, 2 ms pulse through the 30 kΩ fixture, AIN0−AIN1 returns within 10 mV of baseline in 8–14 ms and within 1 mV in 90–95 ms. That is inside the 200 ms blank.
- **Overload stress:** during the pulse, the filter capacitors push AIN0 to about −2 V through at least 68 kΩ. That limits the ADS1256 input protection current to about 25 µA against its 10 mA rating. Q7's base-emitter reverse voltage stays at or below 2.0 V.
- **Mains:** Q4's collector sits ahead of the filter and clips first. At 60 Hz it tolerates about 22 mV peak at J1, and about 4 mV at 180 Hz.

## Circuit

Reference designators match `spice/receiver.cir`, `bom.csv`, and the construction schematic.

1. **Input clamps.** Q5 and Q6 are 2N3904s connected as diodes, collector tied to base. They clamp J1 to about ±0.65 V. Their femtoamp saturation current keeps leakage from loading the megohm input.
2. **Stage 1 (Q1–Q3), gain 1 + R7/R8 = 35.**
   - C1 (100 nF) couples J1 to Q1's base.
   - Q1 runs near 32 µA, set by Q2's V_BE across R4. It is the only noise-critical device.
   - Q2 is the second gain stage, and Q3 is a follower that drives R7.
   - The stage's loop gain raises Q1's base impedance to megohms.
   - C4 sets unity DC gain and a 480 Hz high-pass corner.
3. **Stage 2 (Q4).** A common-emitter stage with R9 bypassed by C5. Its gain is (VA − V_Q4C)/V_T ≈ 95.
4. **Band-pass filter (C7, C8, C9, R12, R13, R14, Q7).**
   - **Low side of the band:** C8, C9, R12, and R13 form a Sallen-Key high-pass (f0 1.1 kHz, Q 1.05). The Q7 follower buffers it and drives AIN0 directly.
   - **Robust at Q ≈ 1:** Q7's 0.98 gain moves Q by only a few percent.
   - **Low DC error:** Q7 runs near 11 µA, so its base current barely shifts the DC loop.
   - **High side of the band:** C7 to ground, with R10, adds the 5.3 kHz low-pass pole.
   - **Result:** a band centered at 1.9 kHz, with 60 Hz attenuated to 0.46 V/V.
5. **Bias, DC loop, and AIN1.**
   - R3 (1 MΩ) returns Q4's inverted collector voltage to BIAS, which C3 filters. BIAS feeds Q1's base through R2 and R1. This single negative loop sets every operating point.
   - C2 bootstraps R1 from Q1's emitter, so R1 appears as tens of megohms in band.
   - BIAS is quiet, so it is ADS1256 AIN1. R13 references the filter to BIAS, so the filter's output and AIN1 share a reference.
6. **Power.** R11 (470 Ω) and C6 (470 µF) filter the XIAO's USB 5 V into VA.

## Noise and input tradeoffs

Q1's bias current trades voltage noise against current noise. It is set for the documented tuned-sensor case, with a 1.2 dB noise figure, and the untuned coil still meets the noise requirement.

Lowering R8 raises gain and lowers noise, but it reduces stage-1 loop gain and therefore |Z_in|. Stage 1 runs at a gain of 35 so that the filter's in-band loss still leaves at least 2000 V/V at every corner. The transistor models omit 1/f noise and use the vendor 10 Ω base resistance, so measure the noise floor on the bench.

Capacitor tolerance is not in the corner set. Kit ceramics (±10%) shift the filter's 1.1 kHz and 5.3 kHz corners by about 10%. In simulation, the worst ±10% combination on C7–C9 still gives at least 2588 V/V across 1.6–2.2 kHz at nominal conditions. Measure the built response.

## ADC configuration and SPI

Configure the ADS1256 for AIN0 − AIN1, input buffer **on**, **PGA 1** (±5 V full scale), and 30 kSPS. AIN0 is Q7's emitter and AIN1 is BIAS. Leave AIN2–AIN7 unconnected. The −0.6 V DC difference between them is well within full scale.

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

J2/J3 give **logical signal names**, not the purchased board's physical header order. Verify that order before wiring. Check each kit transistor's lead order against its marking and datasheet before soldering. KiCad TO-92 symbols number pins 1/2/3 as E/B/C.

## Protection limits

Q5/Q6 take the polarizer turnoff current at J1, limited only by the external sensor's impedance. The 2N3904 is rated 200 mA collector current. The SPICE models do not prove surge survival. Measure the actual polarizer turnoff voltage and current at the sensor output before connecting it.

## Files and status

- `requirements.py` defines the requirements, the corner set, and the checker used by `verify.py` and the tests.
- `spice/receiver.cir` is the active ngspice model. It omits ADC converter noise, the digital filter, SPI timing, firmware blanking, and the external sensor's LC response.
- `analyze.py` generates the committed `analysis/` CSV, PNG, and Markdown artifacts, including the |Z_in| and noise/CRB tables.
- `schematic.py` draws the construction schematic used by `make export` and `docs/`.
- `bom.csv` lists every fitted part. `digikey_missing_components.csv` records that the only non-kit items, the ADC and XIAO, are already purchased.
- `assembly.md` gives the perfboard wiring and bring-up sequence.
- `kicad/generate.py` emits the text connectivity netlist `kicad/receiver.net`. `verify.py` checks that it, the SPICE deck, and the BOM describe the same parts and pins. There is no graphical KiCad schematic or PCB, and `make pcb` intentionally fails.

Data sources: [TI ADS1256 datasheet](https://www.ti.com/lit/ds/symlink/ads1256.pdf) for absolute maximum ratings, digital I/O levels, buffered input range, PGA full scale, and Table 1 input-referred noise; [onsemi 2N3904 datasheet](https://www.onsemi.com/pdf/datasheet/2n3904-d.pdf) for pinout and limits.
