# Active receiver design

The receiver is a minimal discrete, low-noise amplifier between the external sensor (J1) and the already purchased HiLetgo ADS1256 module. It is controlled by the already purchased Seeed XIAO RP2350. Requirements:

1. Gain from J1 to AIN0−AIN1 of **at least 2000 V/V everywhere in 1.5–2.5 kHz**.
2. **|Z_in| ≥ 1 MΩ** at J1 in that band.
3. Noise low enough for accurate frequency estimates with the ADC and RP2350.

The design meets these with **24 fitted parts**: 11 resistors, 7 capacitors, five 2N3904s, and one 2N3906, all from the Thomson kit in `new_allowed_components.json`, plus the two modules. There is no op-amp, bandpass filter, or SPI level translator. J1–J3 are logical wire interfaces; TP1–TP7 are optional copper test points. There is no accepted physical board yet.

## Simulated performance

These are ngspice values from `spice/receiver.cir` with vendor transistor models (see `analysis/README.md`), not measurements. The "worst corner" combines every transistor's beta halved, 50 °C, and 4.75 V USB.

| Quantity | Nominal | Worst corner |
|---|---|---|
| Gain, J1 to AIN0−AIN1, 1.5–2.5 kHz | 2425–2514 V/V | ≥ 2122 V/V |
| \|Z_in\| at J1, 1.5–2.5 kHz | 2.10–2.19 MΩ | ≥ 1.51 MΩ |
| Input noise, untuned coil pair (EMF-referred) | 3.59 nV/√Hz | — |
| Input noise, 30 kΩ tuned-sensor fixture | 25.8 nV/√Hz, 1.3 dB noise figure | — |
| Amplifier noise, shorted input | 3.35 nV/√Hz | — |
| −3 dB bandwidth | 0.58–18.4 kHz | — |
| Gain at 60 Hz | 97 V/V (−28 dB) | — |
| Output DC (AIN0) / BIAS (AIN1) | 2.07 V / 1.72 V | 1.89–2.32 V / 1.59–1.88 V |
| Supply | 0.37 mA from USB 5 V; VA ≈ 4.83 V | — |

Separate corners give these minimum in-band gains:
- beta ×0.5: 2317 V/V
- 50 °C: 2383 V/V
- 4.75 V USB: 2236 V/V

**Noise is sufficient for the estimator.** For the untuned coil, the frequency Cramér–Rao bound is 0.020 nT with the active coil's 3.59 µV FID. For the older pessimistic 0.41 µV FID it is 0.174 nT. Both use a 1.5 s record at 30 kSPS after a 200 ms blank; the target is 1 nT. A tuned external capacitor steps up the FID and the coil noise together, so the receiver's share of the noise drops further. With PGA 1, the ADS1256's 10.7 µV RMS converter noise (TI Table 1, buffer on, 30 kSPS) is about 4.5 nV referred to J1. It is negligible.

There is no analog bandpass because the ADS1256 and firmware do the band limiting. The ADS1256 sinc filter strongly rejects noise that would alias into 1.5–2.5 kHz: about −115 dB near 28–32 kHz. Firmware filtering then removes everything outside the FID band. The analog response needs only two things:

- **Mains rejection**, so pickup does not saturate the ADC. The 60 Hz gain of 97 leaves room for about 9 mV peak of 60 Hz at J1 before AIN0 leaves the buffered 0–3 V range.
- **A 17 kHz roll-off**, from C7 with R10, which limits wideband noise at the ADC. Integrated from 10 Hz to 5 MHz, AIN0 noise is 10.5 mV RMS with the 30 kΩ fixture. It is 36 mV RMS for an ideal untuned inductor; a real coil's winding capacitance lowers that.

Other checks from the same deck:
- **Stage-1 loop:** a step overshoots 3.8%.
- **DC loop:** the low-frequency response rises monotonically, and power-up settles in 0.5 s.
- **Overload:** a ±10 V, 2 ms pulse through the 30 kΩ fixture keeps AIN0 between 0.04 and 4.76 V. That stays below AVDD + 0.3 V, so the ADC is safe, but it is outside the linear range during the pulse. AIN0−AIN1 returns within 10 mV of baseline 200–210 ms after the pulse and within 1 mV by 290–300 ms. The residual is a slow baseline, far below 1.5 kHz, which the estimator's mean removal and filtering reject. Extend the blank to 300 ms if bench captures show otherwise.

## Circuit

Reference designators match `spice/receiver.cir`, `bom.csv`, and the construction schematic.

1. **Input clamps.** Q5 and Q6 are 2N3904s connected as diodes, collector tied to base. They clamp J1 to about ±0.65 V. Their femtoamp saturation current makes their leakage negligible at 0 V bias. A pair of 1N4148s would load the input by several megohms, falling below 1 MΩ when warm.
2. **Stage 1 (Q1–Q3), gain 1 + R7/R8 = 26.5.**
   - C1 (100 nF) couples J1 to Q1's base.
   - Q1 (2N3904) runs near 32 µA, set by Q2's V_BE across R4. It is the only noise-critical device.
   - Q2 (2N3906) is the second gain stage, and Q3 is a follower that drives R7.
   - R8 contributes 1.8 nV/√Hz.
   - The stage's loop gain of about 40 raises Q1's base impedance to several megohms, which gives the high |Z_in|.
   - C4 sets unity DC gain and a 360 Hz high-pass corner.
3. **Stage 2 (Q4).** A common-emitter stage with R9 bypassed by C5. Its gain is (VA − V_OUT)/V_T ≈ 95, which depends on the DC operating point and temperature, not on transistor beta. The collector drives AIN0 directly.
4. **Bias, DC loop, and AIN1.**
   - R3 (1 MΩ) returns the inverted output to the BIAS node, which C3 filters. BIAS feeds Q1's base through R2 and R1.
   - This single negative loop sets every operating point, placing the output near 2.1 V.
   - C2 bootstraps R1 from Q1's emitter, which follows the input, so R1 appears as tens of megohms in band.
   - BIAS is quiet and sits about 0.35 V below the output, so it doubles as the ADS1256 AIN1 reference. No separate reference divider is needed.
5. **Power.** R11 (470 Ω) and C6 (470 µF) filter the XIAO's USB 5 V into VA. Stage 1 rejects VA noise by design. Stage 2 passes VA noise to AIN0 unamplified, where it is negligible against the 2000× signal gain.

## Noise and input tradeoffs

Q1's bias current trades voltage noise against current noise. At 32 µA, the untuned-coil noise figure is 8.9 dB over the coil's own resistance. The input is also optimized for the documented tuned-sensor case (1.3 dB), and both cases stay well inside the 1 nT CRB target.

A lower R8 lowers the noise and raises gain, but it reduces the loop gain and therefore |Z_in|. Stage-1 gain was lowered to 26.5 for this reason, and stage 2 supplies the rest. The transistor models omit 1/f noise and use the vendor 10 Ω base resistance, so measure the floor. Take it with J1 shorted, with a 30 kΩ resistor at J1, and with the coil connected.

## ADC configuration and SPI

Configure the ADS1256 for AIN0 − AIN1, input buffer **on**, **PGA 1** (±5 V full scale), and 30 kSPS. AIN0 is the amplifier output and AIN1 is BIAS. Leave AIN2–AIN7 unconnected. The ~0.35 V DC difference between them is well within full scale.

The SPI connects **directly** to the XIAO; no level translation is needed. The ADS1256 datasheet specifies SCLK, DIN, CS, and SYNC/PDWN as inputs accepting up to 5.25 V (6 V absolute). DOUT and DRDY swing only to DVDD, which is at most 3.6 V. Before connecting, measure the powered module's DRDY high level (expect about 3.3 V). If it were below about 2.5 V, the RP2350 might not read it reliably.

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
2. Wait for DRDY; the ADC may have been powered down while the XIAO was in reset.
3. Configure the ADC.
4. For each measurement, ignore conversions during the blank.
5. Pulse SYNC/PDWN low briefly (under 20 DRDY periods) and wait for DRDY before recording. Holding SYNC/PDWN low for the whole blank would power down the oscillator.

At 30 kSPS the SPI needs at least 720 kbit/s for 24-bit data, plus command overhead.

J2/J3 give **logical signal names**, not the purchased board's physical header order. Verify that order before wiring. Check each kit transistor's lead order against its marking and datasheet before soldering. KiCad TO-92 symbols number pins 1/2/3 as E/B/C.

## Protection limits

Q5/Q6 take the polarizer turnoff current at J1, limited only by the external sensor's impedance. The 2N3904 is rated 200 mA collector current. C1 sees at most the clamped ±0.65 V plus Q1's base bias. The SPICE models do not prove surge survival. Measure the actual polarizer turnoff voltage and current at the sensor output before connecting it.

## Files and status

- `spice/receiver.cir` is the active ngspice model. It omits ADC converter noise, the digital filter, SPI timing, firmware blanking, and the external sensor's LC response.
- `analyze.py` generates the committed `analysis/` CSV, PNG, and Markdown artifacts, including the |Z_in| and noise/CRB tables.
- `schematic.py` draws the construction schematic used by `make export` and `docs/`.
- `bom.csv` lists every fitted part. `digikey_missing_components.csv` records that the only non-kit items, the ADC and XIAO, are already purchased; no order is required.
- `assembly.md` gives the perfboard wiring and bring-up sequence.
- `kicad/generate.py` emits the text connectivity netlist `kicad/receiver.net`. `verify.py` checks that it, the SPICE deck, and the BOM describe the same parts and pins. There is no graphical KiCad schematic or PCB, and `make pcb` intentionally fails.

Data sources: [TI ADS1256 datasheet](https://www.ti.com/lit/ds/symlink/ads1256.pdf) for absolute maximum ratings, digital I/O levels, buffered input range, PGA full scale, and Table 1 input-referred noise; [onsemi 2N3904 datasheet](https://www.onsemi.com/pdf/datasheet/2n3904-d.pdf) for pinout and limits. The exact HiLetgo module PCB remains to be identified physically.
