# Proton magnetometer

- One receiver, one external coil assembly, one frequency estimator
- USB-powered bench instrument
- Target: proton free-induction decay around 35–59 µT
- The figures below are ngspice calculations, not bench measurements

---

# Circuit boundary

- The external assembly contains the sensing coil, tuning capacitor, and damping switch
- J1 is the receiver boundary; the receiver contains no LC tank
- A purchased AD8421 module and an RC anti-aliasing filter drive the already purchased HiLetgo ADS1256 module
- The already purchased XIAO RP2350 connects directly to the ADC's SPI and estimates frequency
- `amazon_purchases.json` lists the $48.95 of Amazon parts; seven lab parts come from `new_allowed_components.json`

---

# Requirements, enforced by `make verify`

- |Z_in| ≥ 1 MΩ everywhere in 1.5–2.5 kHz
- Input noise ≤ 5 nV/√Hz with the coil, including ADC noise: frequency CRB about 0.24 nT for a 0.41 µV FID
- Nothing clips for 10 mV tones at 50–400 Hz or 2 mV tones at 8–50 kHz
- At least 90 dB of alias rejection within 2.2 kHz of the ADS1256's 1.92 MHz modulator rate
- Checked at ten temperature, supply, battery, trim, and tolerance corners; any miss fails the build

---

# Analog chain

- Diode-connected 2N3904 clamps at J1 (femtoamp leakage)
- AD8421 module, G = 1 + 9.9 kΩ/R1 = 100 with R1 = 100 Ω; its input RFI parts are removed
- ±9 V from two batteries; the module's BIAS trimmer sets OUT to 2.5 V
- Two RC sections (1 kΩ/22 nF, 10 kΩ/2.2 nF) at AIN0; AIN1 is GND
- ADS1256 buffer off, PGA 1, 30 kSPS

![Analog construction schematic](receiver-construction-schematic.png)

---

# Simulated performance

- 83–87 V/V from J1 to AIN0 across 1.6–2.2 kHz; −3 dB at 4.6 kHz
- |Z_in| 4.25–7.08 MΩ; at least 4.21 MΩ at the worst corner
- 3.9 nV/√Hz with the untuned coil, including ADC noise: frequency CRB 0.02 nT (3.59 µV FID) or 0.19 nT (0.41 µV)
- 98 dB alias rejection at 1.92 MHz; tolerates 15.7 mV tones at the worst corner

---

# Simulated transfer

- Example source: 10 µV peak through a provisional 30 kΩ external source impedance
- The nominal 3.59 µV FID becomes about 0.3 mV peak at the ADC
- These plots exclude converter noise, digital filtering, and coil resonance

![Receiver transient](../receiver_design/analysis/receiver-waveforms.png)

![Receiver J1-to-ADC transfer](../receiver_design/analysis/receiver-frequency-response.png)

---

# Digital interface and blanking

- SPI wires run directly from the XIAO to the module; ADS1256 inputs accept 5.25 V and its outputs stay at or below DVDD
- Measure the module's DRDY high level (about 3.3 V) before connecting
- Firmware drives CS and SYNC/PDWN high, then waits for DRDY
- Discard the blank, then pulse SYNC/PDWN briefly and wait for valid DRDY
- Verify the purchased module's physical header order before wiring

---

# Estimator

- Portable C99 core in `frequency_estimator_firmware/core`
- Goertzel seed, baseband mixing, FIR decimation, decay weighting, and zoom frequency fit
- Up to 45,000 samples in 1.5 s at 30 kSPS
- SPI acquisition, blanking control, and USB reporting firmware remain to be written

---

# Bench gates

- Measure the actual polarizer turnoff voltage before connecting the sensor; verify Q1/Q2 clamp current
- Remove the module's input RFI parts; measure OUT and AIN0 levels, gain, low-pass corner, input noise, loading, and overload recovery
- Check the module DRDY level and scope SPI at the selected clock
- Verify frequency repeatability and gross error rate with a wet FID
- There is no accepted PCB or fabrication DRC result
