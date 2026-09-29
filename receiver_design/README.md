# Active receiver design

The receiver is a discrete, low-noise band-pass amplifier between the external sensor (J1) and the already purchased HiLetgo ADS1256 module. It is controlled by the already purchased Seeed XIAO RP2350.

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
| Interference | No stage clips for a **10 mV peak tone at 50–400 Hz** or a **2 mV peak tone at 8–50 kHz** at J1 | Each stage's DC headroom (from the operating point) divided by its gain from J1; the stages are Q3, Q7, Q8, and Q4/AIN0 |

The noise limit comes from the frequency Cramér–Rao bound. At 5 nV/√Hz it is about 0.24 nT for the pessimistic 0.41 µV FID, a 4× margin under the 1 nT target. The interference limits cover mains and its harmonics, plus switching and audio-band pickup that the digital filter could otherwise only see after the analog chain had clipped.

The design uses **36 fitted parts**: 17 resistors, 11 capacitors, six 2N3904s, and two 2N3906s. All come from `new_allowed_components.json`, the Thomson kit plus three Plexus resistors (R4, R9, R17), alongside the two modules. There is no op-amp and no SPI level translator. J1–J3 are logical wire interfaces; TP1–TP8 are optional test points. There is no accepted physical board yet.

## Simulated performance

These are ngspice values from `spice/receiver.cir` with vendor transistor models (see `analysis/README.md` and the `make verify` table), not measurements.

| Quantity | Nominal | Worst of nine corners |
|---|---|---|
| Gain, 1.6–2.2 kHz | 3034–3155 V/V (peak at 1.74 kHz) | ≥ 2515 V/V |
| \|Z_in\|, 1.5–2.5 kHz | 1.82–2.50 MΩ | ≥ 1.17 MΩ |
| Input noise, untuned coil, 1.6–2.2 kHz | ≤ 4.15 nV/√Hz | ≤ 4.57 nV/√Hz |
| Largest tone without clipping, 50–400 Hz | 15.1 mV | 12.9 mV |
| Largest tone without clipping, 8–50 kHz | 4.7 mV | 4.3 mV |
| Frequency CRB, untuned coil | 0.023 nT (3.59 µV FID), 0.200 nT (0.41 µV FID) | — |
| Input noise, 30 kΩ tuned-sensor fixture | 25.4 nV/√Hz, 1.1 dB noise figure | — |
| −3 dB band | 1.15–3.09 kHz | — |
| DC at AIN0 / AIN1 (BIAS) | 2.13 V / 1.59 V | — |
| Supply | 0.60 mA from USB 5 V; VA ≈ 4.72 V | — |

Gain from J1 to AIN0 at frequencies outside the band, with stage-1 gain in parentheses:

| Frequency | Gain to AIN0 (stage 1) |
|---|---|
| 60 Hz | 1.3 (2.3) |
| 180 Hz | 3.5 (5.9) |
| 300 Hz | 19 (9.5) |
| 5 kHz | 698 (33) |
| 10 kHz | 83 (33) |
| 20 kHz | 6 (34) |
| 1.92 MHz (ADS1256 modulator) | 0.03 (14) |

The ADS1256's converter noise at PGA 1 is about 4 nV RMS referred to J1.

Other checks from the same deck:
- **Stability:** stage 1 settles from a step with under 1% overshoot. Both filter followers work at Q ≈ 1.3, where their 0.98 gain has little effect on Q.
- **Power-up** settles in about 1 s.
- **Overload recovery:** after a ±10 V, 2 ms pulse through the 30 kΩ fixture, AIN0−AIN1 returns within 10 mV in 57–75 ms and within 1 mV in 215–230 ms. The residual is a slow baseline that the estimator's mean removal rejects.
- **Overload stress:** during the pulse AIN0 stays between 1.1 and 4.65 V, never below ground and under the ADC's AVDD + 0.3 V absolute maximum.
- **Capacitor tolerance:** ±10% kit tolerance is not in the corner set. The filter corners move with it, so measure the built response.

## Circuit

Reference designators match `spice/receiver.cir`, `bom.csv`, and the construction schematic.

1. **Input clamps.** Q5 and Q6 are 2N3904s connected as diodes, collector tied to base. They clamp J1 to about ±0.65 V with negligible leakage.
2. **Stage 1 (Q1–Q3), gain 1 + R7/R8 = 35.**
   - C1 (100 nF) couples J1 to Q1's base.
   - Q1 runs near 26 µA, set by Q2's V_BE across R4. It is the only noise-critical device.
   - Q2 is a second gain stage. Its 47 kΩ load raises the loop gain.
   - Q3 (about 300 µA) drives the feedback network and the filter.
   - The loop gain raises Q1's base impedance to megohms.
   - C4 sets unity DC gain and a 1.1 kHz high-pass shelf.
3. **Band-pass filter between the stages.** Only stage 1's gain (≤ 35) precedes it, so interference is attenuated before the high-gain stage.
   - C8, C9, R12, and R13 form a Sallen-Key high-pass (f0 1.31 kHz, Q 1.3) buffered by the Q7 follower.
   - R15, R16, C10, and C11 form a Sallen-Key low-pass (f0 3.05 kHz, Q 1.3) buffered by the PNP follower Q8. Q8's V_BE shift restores Q4's base bias.
   - R13 references the filter to BIAS.
4. **Stage 2 (Q4).** A common-emitter stage with R9 bypassed by C5 above about 800 Hz. Its gain is about (VA − V_OUT)/V_T. The collector drives ADS1256 AIN0 directly, and C7 adds a 3.6 kHz pole.
5. **Bias, DC loop, and AIN1.**
   - R3 (1 MΩ) returns Q4's inverted collector voltage to BIAS, which C3 filters.
   - BIAS drives Q1's base through R2 and R1, and Q4's base through R13, Q7, and Q8. This single negative loop sets every operating point.
   - C2 bootstraps R1 from Q1's emitter, so R1 appears as tens of megohms in band.
   - BIAS is quiet, so it is ADS1256 AIN1.
6. **Power.** R11 (470 Ω) and C6 (470 µF) filter the XIAO's USB 5 V into VA.

## Noise and input tradeoffs

Q1's bias is set for the documented tuned-sensor case (1.1 dB noise figure). The untuned coil still meets the noise requirement.

The filter now follows only stage 1's gain, so its resistors add some input-referred noise. Noise is 4.15 nV/√Hz nominal, with about 9% margin at the hot corner. Stage 1's gain of 35 is a compromise: a higher gain would lower filter noise and raise overall gain, but it reduces stage-1 loop gain and therefore |Z_in|.

The transistor models omit 1/f noise and use the vendor 10 Ω base resistance, so measure the noise floor on the bench.

## ADC configuration and SPI

Configure the ADS1256 for AIN0 − AIN1, input buffer **on**, **PGA 1** (±5 V full scale), and 30 kSPS. AIN0 is Q4's collector and AIN1 is BIAS. Leave AIN2–AIN7 unconnected. The ~0.55 V DC difference between them is well within full scale.

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

- `requirements.py` defines the requirements, the corner set, and the checker used by `verify.py`, the tests, and the analysis report.
- `spice/receiver.cir` is the active ngspice model. It omits ADC converter noise, the digital filter, SPI timing, firmware blanking, and the external sensor's LC response.
- `analyze.py` generates the committed `analysis/` CSV, PNG, and Markdown artifacts, including |Z_in|, interference tolerance, and the noise/CRB table.
- `schematic.py` draws the construction schematic used by `make export` and `docs/`.
- `bom.csv` lists every fitted part. `digikey_missing_components.csv` records that the only non-lab items, the ADC and XIAO, are already purchased.
- `assembly.md` gives the perfboard wiring and bring-up sequence.
- `kicad/generate.py` emits the text connectivity netlist `kicad/receiver.net`. `verify.py` checks that it, the SPICE deck, and the BOM describe the same parts and pins. There is no graphical KiCad schematic or PCB, and `make pcb` intentionally fails.

Data sources: [TI ADS1256 datasheet](https://www.ti.com/lit/ds/symlink/ads1256.pdf) for absolute maximum ratings, digital I/O levels, buffered input range, PGA full scale, and Table 1 input-referred noise; [onsemi 2N3904 datasheet](https://www.onsemi.com/pdf/datasheet/2n3904-d.pdf) for pinout and limits.
