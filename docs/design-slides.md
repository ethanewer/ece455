# Proton magnetometer

- One receiver, one external coil assembly, one frequency estimator
- USB-powered bench instrument
- Target: proton free-induction decay around 35–59 µT
- The figures below are ngspice calculations, not bench measurements

---

# Circuit boundary

- The external assembly contains the sensing coil, tuning capacitor, and damping switch
- J1 is the receiver boundary; the receiver contains no LC tank
- The already purchased HiLetgo ADS1256 module supplies the first active input buffer and PGA
- The already purchased XIAO RP2350 controls conversion and estimates frequency
- Every other fitted part in the active BOM is in the Thomson lab kit

---

# Analog input

- C5 22 nF AC coupling; R1 10 kΩ current limit
- R2/R3 total 2 MΩ bias return; C9 100 pF to common-mode bias
- D1/D2 kit 1N4148 clamps from AIN0 to the 1.60 V bias
- ADS1256 AIN0 − AIN1, input buffer enabled, PGA 64, 30 kSPS
- Nominal input impedance near 1.8 kHz is about 0.8 MΩ
- No external analog gain or narrow bandpass is fitted

![Analog construction overview](receiver-construction-schematic.png)

---

# Noise tradeoff

- ADS1256 datasheet input noise: 1.742 µV RMS at 30 kSPS with buffer on and PGA 64
- Coil model nominal FID: 3.59 µV peak, about 6 dB peak-amplitude per-sample SNR before other noise
- The older 0.41 µV estimate falls below converter noise per sample
- Frequency fitting may recover a periodic FID; the 1 nT target needs a hardware test

---

# Simulated transfer

- Example source: 10 µV peak through a provisional 30 kΩ external source impedance
- The analog path is near unity gain over the example FID frequencies
- These plots exclude converter noise, digital filtering, and coil resonance

![Receiver transient](../receiver_design/analysis/receiver-waveforms.png)

![Receiver source-to-ADC transfer](../receiver_design/analysis/receiver-frequency-response.png)

---

# Digital interface and blanking

- Six kit 2N3904 stages translate SPI signals; RP2350 GPIO inversion restores polarity
- JP1 selects the module's measured SPI logic voltage, 3.3 V or 5 V
- SCLK and DIN idle low; CS and SYNC/PDWN idle high
- Discard the first 200 ms of data, then pulse SYNC/PDWN briefly and wait for valid DRDY
- Verify the purchased module's physical header order, voltage, and translator edge timing before wiring

---

# Estimator

- Portable C99 core in `frequency_estimator_firmware/core`
- Goertzel seed, baseband mixing, FIR decimation, decay weighting, and zoom frequency fit
- Up to 45,000 samples in 1.5 s at 30 kSPS
- SPI acquisition, blanking control, and USB reporting firmware remain to be written

---

# Bench gates

- Measure the actual polarizer turnoff voltage before connecting the sensor; verify C5 rating and clamp current
- Measure ADC input noise, receiver loading, bias, and recovery
- Check module SPI levels, select one JP1 bridge, and scope translated SPI at the selected clock
- Verify frequency repeatability and gross error rate with a wet FID
- There is no accepted PCB or fabrication DRC result
