# Proton magnetometer

- One receiver, one external coil assembly, one frequency estimator
- USB-powered bench instrument
- Target: proton free-induction decay, about 35–59 µT
- Figures below are ngspice results, not bench measurements

---

# Signal chain and boundary

- The external assembly contains the sensing coil, any tuning capacitor, and any damping switch
- J1 is the receiver input boundary
- OPA4197 low-noise first stage, followed by fixed analog signal processing
- HiLetgo ADS1256 module, PGA 64, 30 kSPS
- Seeed XIAO RP2350 estimates frequency and reports field over USB

---

# Field scale

- Shielded proton: 42.576 Hz/µT
- 1 nT is 0.0426 Hz
- Receiver input examples: 1765 Hz and 2129 Hz
- The receiver contains no LC tuning bank or resonant shunt

---

# Input and blanking

- J1 accepts signal and return from the external sensor assembly
- Ten 510 kΩ resistors in series provide a 5.1 MΩ input bias return
- U1A is a unity-gain low-noise buffer
- BAS116 clamps and a 1 kΩ series resistor limit input current
- TMUX1101 shorts the input to the 1.36 V bias while blanking
- Blanking is the power-up default; drive it off after 200 ms

---

# Analog path

- U1B: 1.516 kHz high-pass, high-frequency gain −53.33
- U1C: unity-gain Sallen–Key low-pass, natural frequency 3.10 kHz
- R12/C9: 7.09 kHz pole into ADS1256 AIN0
- Simulated receiver input-to-ADC gain is about 37 V/V at both test frequencies
- External coil resonance and voltage step-up are measured separately

---

# Transient response

- Example source at J1: 10 µV peak with 30 kΩ external source impedance
- T2* in the example is 0.95 s; the plotted 200–220 ms window follows blanking
- Differential ADC input peak in that window is about 0.30 mV
- PGA 64 full scale is ±78.1 mV

![Receiver transient, external test source and AIN0−AIN1](../receiver_design/analysis/receiver-waveforms.png)

---

# Frequency response

- Shaded band is the fixed 1.5–2.5 kHz receiver filter
- Dashed line is the 1765 Hz example input frequency
- Gain is 37.3 V/V at 1765 Hz and 37.6 V/V at 2129 Hz
- External coil resonance is absent from this response
- ADS1256 digital filter is already −3 dB at 6.1 kHz

![Receiver input-to-ADC gain and phase](../receiver_design/analysis/receiver-frequency-response.png)

---

# ADC operating point

- Differential AIN0 − AIN1, input buffer on, PGA 64, 30 kSPS
- Conversion reference is the module ADR03, 2.5 V
- Analog bias is a separate 1.36 V
- Buffer inputs must stay between 0 V and AVDD−2 V (3.0 V)
- AIN2–AIN7 sit on the 1.36 V bias

---

# Input clamp

- D3 cathode is held near 1.58 V, reverse biased at the 1.36 V signal bias
- BAS116 forward drop is 0.9 V maximum at 1 mA
- A 5.25 V saturated output is estimated to leave AIN0 near 2.74 V
- Fault current through R12 is below 1 mA

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

- Simulated receiver input-to-ADC gain is about 37 V/V at both example frequencies
- Estimator agrees with an independent NumPy mirror to 0.01 Hz on the host vectors
- Operating-SNR host error is inside 0.0426 Hz (1 nT) on those vectors
- Those vectors are not a hardware sensitivity claim

---

# Still required before a field result

- Build the receiver from `receiver_design/bom.csv` and measure gain, noise, and recovery
- Check ADS1256 clock error; 20 ppm is about 1 nT at 50 µT
- Write ADS1256 SPI, DRDY, blanking, and USB firmware
- There is no PCB yet, and no DRC result
