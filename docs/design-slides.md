# Proton magnetometer

- One receiver, one external coil assembly, one frequency estimator
- USB-powered bench instrument
- Target: proton free-induction decay around 35–59 µT
- The figures below are ngspice calculations, not bench measurements

---

# Circuit boundary

- The external assembly contains the sensing coil, tuning capacitor, and damping switch
- J1 is the receiver boundary; the receiver contains no LC tank
- A discrete band-pass amplifier drives the already purchased HiLetgo ADS1256 module
- The already purchased XIAO RP2350 connects directly to the ADC's SPI and estimates frequency
- Every other fitted part is one of 36 lab parts in `new_allowed_components.json`

---

# Requirements, enforced by `make verify`

- Gain ≥ 2000 V/V from J1 to AIN0 − AIN1 everywhere in 1.6–2.2 kHz
- |Z_in| ≥ 1 MΩ everywhere in 1.5–2.5 kHz
- Input noise ≤ 5 nV/√Hz with the coil: frequency CRB about 0.24 nT for a 0.41 µV FID
- No stage clips for 10 mV tones at 50–400 Hz or 2 mV tones at 8–50 kHz
- Checked at nine beta, temperature, and USB-voltage corners; any miss fails the build

---

# Analog chain

- Diode-connected 2N3904 clamps at J1 (femtoamp leakage), 100 nF coupling
- Stage 1, ×35: low-noise 2N3904 input, 2N3906 gain stage, 2N3904 follower
- Fourth-order band-pass between the stages: Sallen-Key high-pass (1.31 kHz) and low-pass (3.05 kHz), each with a follower
- Stage 2, ×100: one common-emitter 2N3904 driving AIN0
- One DC loop (R3) sets every bias point; its filtered node is also AIN1

![Analog construction schematic](receiver-construction-schematic.png)

---

# Simulated performance

- 3034–3155 V/V across 1.6–2.2 kHz; at least 2515 V/V at the worst corner
- |Z_in| 1.82–2.50 MΩ; at least 1.17 MΩ at the worst corner
- 4.1 nV/√Hz with the untuned coil: frequency CRB 0.02 nT (3.59 µV FID) or 0.20 nT (0.41 µV)
- Gain 1.3 V/V at 60 Hz and 83 V/V at 10 kHz; tolerates 12.9 mV and 4.3 mV tones at the worst corner

---

# Simulated transfer

- Example source: 10 µV peak through a provisional 30 kΩ external source impedance
- The nominal 3.59 µV FID becomes about 11 mV peak at the ADC
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

- Measure the actual polarizer turnoff voltage before connecting the sensor; verify Q5/Q6 clamp current
- Measure stage bias points, gain, passband, input noise, loading, and recovery
- Check the module DRDY level and scope SPI at the selected clock
- Verify frequency repeatability and gross error rate with a wet FID
- There is no accepted PCB or fabrication DRC result
