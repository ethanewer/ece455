# Proton magnetometer

- One receiver, one coil pair, one frequency estimator
- USB-powered bench instrument
- Target: proton free-induction decay, about 35–59 µT
- Figures below are ngspice results, not bench measurements

---

# Signal chain

- Series-opposed coil, 14 Ω and 22 mH, untuned
- Analog front end on an OPA4197, about 2000 V/V
- HiLetgo ADS1256 module, PGA 64, 30 kSPS
- Seeed XIAO RP2350 estimates frequency and reports field over USB
- Acquisition firmware is not on the XIAO yet

---

# Field scale

- Shielded proton: 42.576 Hz/µT
- 1 nT is 0.0426 Hz
- 50 µT is 2128.8 Hz, the nominal design point
- Passband 1.5–2.5 kHz covers about 35–59 µT
- 1.8 kHz is a valid proton signal near 42 µT; no notch there

---

# Coil and blanking

- No tuning capacitor, so 1.7 kHz and 2.1 kHz both pass
- Input high-pass near 480 Hz, before any gain
- BAS116 clamps and a 1 kΩ series resistor limit input current
- TMUX1101 shorts the input to the 1.50 V bias while blanking
- Blanking is the power-up default; drive it off after 200 ms

---

# Analog path

- U1A: non-inverting gain 55.9
- U1B: 1.516 kHz high-pass, gain −56.19
- U1C: unity-gain Sallen–Key low-pass, natural frequency 3.03 kHz
- R12/C9: 7.23 kHz pole into ADS1256 AIN0
- Resistor-set gain is 3141 V/V; the filters bring the band to about 2000 V/V
- PGA 64 is extra and is not in these gain numbers

---

# Transient response

- Nominal FID: about 1 µV peak at the coil, 2128.8 Hz
- T2* in the model is 0.95 s, so 20 ms shows little decay
- Differential ADC input settles near ±2.0 mV
- PGA 64 full scale is ±78.1 mV, so this tone uses about 2.6% of range

![Nominal receiver transient, coil source and AIN0−AIN1](../receiver_design/analysis/receiver-waveforms.png)

---

# Frequency response

- Shaded band is the 1.5–2.5 kHz measurement window
- Dashed line is 2128.8 Hz
- In-band gain is flat: 1924–2032 V/V
- Gain at 2128.8 Hz is 2020 V/V (66.1 dB)
- Gain at 30 kHz is 7.3 V/V, 49 dB below the passband
- ADS1256 digital filter is already −3 dB at 6.1 kHz

![Nominal receiver frequency response](../receiver_design/analysis/receiver-frequency-response.png)

---

# ADC operating point

- Differential AIN0 − AIN1, input buffer on, PGA 64, 30 kSPS
- Conversion reference is the module ADR03, 2.5 V
- Analog bias is a separate 1.50 V, not that reference
- 1.50 V is below (V+)−3 V on the 5 V op-amp rail, where 5.5 nV/√Hz is specified
- Buffer inputs must stay between 0 V and AVDD−2 V (3.0 V)
- AIN2–AIN7 sit on the 1.50 V bias

---

# Input clamp

- D3 cathode is held at 1.80 V, so the diode is off at the 1.50 V bias
- A 5 V saturated output can raise AIN0 only by one diode drop above 1.80 V
- BAS116 forward drop is 0.9 V maximum at 1 mA
- Fault current through 10 kΩ is below 1 mA, so AIN0 stays under 3.0 V
- With the datasheet maximum drop, that fault point is 2.76 V

---

# Digital interface

- XIAO 3.3 V SPI through AHCT buffers to the 5 V ADC
- DOUT and DRDY return through LVC buffers
- CS and SYNC/PDWN idle high; both are active-low
- SCLK and MOSI idle low
- Hold SYNC/PDWN high while converting
- Calibrate with SELFCAL, buffer off, then SELFOCAL after the buffer is on
- Confirm the purchased module’s header order before laying out an adapter

---

# Power

- USB only: XIAO VBUS feeds the ADC module and the 5 V level shifters
- OPA4197 minimum supply is 4.5 V, so it uses filtered USB 5 V
- XIAO 3.3 V, filtered, powers the blanking switch and the input clamps
- No battery connector: the ADC module needs a 5 V rail

---

# Estimator

- Portable C99 core in `frequency_estimator_firmware/core`
- Same source for host tests and the RP2350
- Float32 path for the XIAO; Q31 path for a no-FPU check
- Input is one ADC record, up to 45 000 samples (1.5 s at 30 kSPS)
- Output is frequency in hertz, or an error if the peak is not interior
- SPI, blanking, and USB code are not in this directory

---

# Estimator pipeline

- Remove the mean
- Coarse Goertzel seed on the first 8192 samples, then a log-parabolic refine
- Mix to baseband with a digital oscillator at that seed
- 33-tap Hamming low-pass, decimate by 10
- Estimate decay time from the decimated envelope
- Scan ±20 Hz at 0.02 Hz steps with an exponential weight
- Refine the peak; an endpoint peak is rejected

---

# Estimator resources

- Full-rate samples are not stored
- Retained state is the decimated complex envelope
- That fits in the RP2350’s 520 KB SRAM with USB and SPI still to add
- Comparison estimators use a short Goertzel and streaming zero-crossings
- Host tests: 36 records, 1064 / 2129 / 2767 Hz, three decay times, SNR 0–30 dB
- Noise in those records covers 500–3500 Hz, so every carrier is inside the noise

---

# What is ready for the bench

- Simulated coil-to-ADC gain near 2000 V/V at 1.7 kHz and 2.1 kHz
- Estimator agrees with an independent NumPy mirror to 0.01 Hz on the host vectors
- Operating-SNR host error is inside 0.0426 Hz (1 nT) on those vectors
- Those vectors are not a hardware sensitivity claim

---

# Still required before a field result

- Build from `receiver_design/bom.csv` and measure gain, noise, and recovery
- Check ADS1256 clock error; 20 ppm is about 1 nT at 50 µT
- Write ADS1256 SPI, DRDY, blanking, and USB firmware
- There is no PCB yet, and no DRC result
