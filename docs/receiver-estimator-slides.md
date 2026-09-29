# Receiver

```mermaid
flowchart LR
  ext["External sensor assembly<br/>coil, tuning, damping"] --> amp["Minimal discrete band-pass amplifier<br/>≥ 2000 V/V at 1.6–2.2 kHz, |Z_in| ≥ 1 MΩ"]
  amp --> adc["Purchased ADS1256<br/>buffer on, PGA 1<br/>30 kSPS"]
  adc -->|direct SPI| xiao["Purchased XIAO RP2350<br/>filter and frequency estimator"]
```

- The receiver starts at J1; coil tuning and damping remain external.
- 30 Thomson kit parts: five gain and filter transistors, two transistor clamps, 13 resistors, and 9 capacitors.
- `make verify` fails if gain, input impedance, or noise requirements are missed at any of nine corners.

---

# Lab parts

- Stage 1 ×35 with a 32 µA 2N3904 input; stage 2 is one common-emitter stage, ×95
- Band-pass: Sallen-Key high-pass (1.1 kHz) with a follower, and a 5.3 kHz pole
- A single DC loop sets every bias point; its filtered node doubles as ADS1256 AIN1
- R11/C6 filter USB 5 V into the 4.8 V analog rail; total draw is 0.36 mA
- No level translators: the XIAO drives the ADS1256 SPI directly

![Analog construction schematic](receiver-construction-schematic.png)

---

# Sensitivity and blanking

- Simulated input noise: 3.5 nV/√Hz with the untuned coil, 25.7 nV/√Hz with a 30 kΩ source
- Frequency CRB with the untuned coil: 0.02 nT for the 3.59 µV FID, 0.17 nT for 0.41 µV; target 1 nT
- XIAO discards the blank, then briefly pulses SYNC/PDWN to restart the digital filter
- Simulated recovery from a ±10 V input pulse reaches 1 mV within about 95 ms

---

# Simulated analog transfer

- Example 10 µV source through provisional 30 kΩ external source impedance
- 2665–2701 V/V across 1.6–2.2 kHz; −3 dB at 1.0 and 6.4 kHz; |Z_in| 1.8–2.3 MΩ
- The model excludes ADC noise, digital filtering, and external coil resonance

![External test source and AIN0−AIN1](../receiver_design/analysis/receiver-waveforms.png)

![Receiver input-to-ADC gain and phase](../receiver_design/analysis/receiver-frequency-response.png)

---

# Frequency estimator

```mermaid
flowchart LR
  mean["Remove mean"] --> seed["Goertzel seed<br/>8192 samples"]
  seed --> mix["Mix to<br/>baseband"]
  mix --> fir["33-tap FIR<br/>decimate ÷10"]
  fir --> tau["Decay time"]
  tau --> zoom["Weighted zoom<br/>±20 Hz"]
  zoom --> hz["Frequency"]
```

- One record of up to 1.5 s at 30 kSPS
- The estimator core exists; ADS1256 SPI acquisition and USB reporting remain to be written
- The 1 nT repeatability target is not established for this lower-sensitivity analog path
