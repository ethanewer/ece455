# Active receiver design

The receiver uses the already purchased Seeed XIAO RP2350 and HiLetgo ADS1256 module. Every other fitted electrical part in `bom.csv` is listed in the Thomson section of `new_allowed_components.json`. J1–J3 are logical wire interfaces; JP1 and TP1–TP8 are PCB copper features, not purchased parts. There is no accepted physical board yet.

## Boundary and signal path

J1 accepts signal and return from the external sensor. The coil, tuning capacitor, and switched damping resistor are outside the receiver and its BOM. Nothing in this circuit is placed across J1 to create an LC tank.

1. C5 (22 nF) AC couples the sensor into R1 (10 kΩ). R1 limits current into the antiparallel kit 1N4148 clamps D1/D2. R2 and R3 (1 MΩ each) return the input to VBIAS. C9 (100 pF) limits very high frequency pickup without heavily loading the 1.7–2.1 kHz FID. The ADS1256's **internal input buffer** is the first active, high-impedance stage. There is no external op-amp.
2. R4 (1 kΩ), R5 (470 Ω), C6 (47 µF), and C7 (100 nF) make a nominal 1.60 V common-mode bias for ADS1256 AIN1 and the unused analog inputs. The ADC measures AIN0 − AIN1 with its buffer enabled, PGA 64, and 30 kSPS output rate. The module's own 2.5 V reference remains the conversion reference.
3. There is no analog gain or narrow bandpass before the ADC. The ADS1256 PGA and digital filter provide signal processing, followed by firmware filtering and frequency estimation. The XIAO ignores conversions during the 200 ms acquisition blank, then gives SYNC/PDWN a short pulse and waits for DRDY before recording. D1/D2 remain connected throughout and limit the differential input excursion. Holding SYNC/PDWN low for 200 ms would put the ADC into power-down and add an oscillator restart delay.

The 30 kΩ external source impedance in `spice/receiver.cir` is a provisional test fixture, not a fitted resistor. Its voltage source is 10 µV peak. The analog input impedance depends on frequency: the 2 MΩ bias return in parallel with the ADS1256's specified 10 MΩ buffered input is about 1.67 MΩ at low frequency, while C9 makes it about 0.8 MΩ magnitude near 1.8 kHz. These values are estimates for the chip and nominal kit parts; measure the purchased module and assembled receiver.

## Sensitivity tradeoff

This lab-parts revision has much less sensitivity than the previous external op-amp receiver. TI specifies 1.742 µV RMS input-referred ADC noise with the buffer on, PGA 64, and 30 kSPS. The project model's nominal 3.59 µV peak coil FID gives about 6 dB peak-amplitude per-sample SNR before filtering and other noise. The weaker 0.41 µV estimate is below the ADC's per-sample noise. Digital filtering and fitting can recover a periodic FID, but the 1 nT cycle-to-cycle target is **not established** for this circuit. Keep the external sensor resonance, if used, outside the receiver and measure its actual gain and source impedance.

The kit 1N4148 and 2N3904 parts are not precision low-leakage substitutes for the former BAS116H and TMUX1101. This circuit avoids a transistor across the high-impedance analog input. The 1.60 V bias and antiparallel clamps nominally keep AIN0 in the ADS1256 buffered input's 0–3 V operating range. The actual polarizer turnoff voltage, C5 voltage rating, diode current, module input protection, and recovery time must be measured before connecting the sensor. The SPICE diode and ADC models do not prove transient survival.

## SPI interface from kit transistors

Q1–Q6 are 2N3904 open-collector inverters. R6–R11 are 10 kΩ base resistors, R12–R17 are 2.2 kΩ collector pull-ups, and D3–D8 are 1N4148 Baker clamps from each base to its collector. Q1–Q4 drive SCLK, DIN, CS, and SYNC/PDWN to the module's logic rail; Q5/Q6 receive DOUT and DRDY with 3.3 V pull-ups. JP1 selects the module-side pull-up rail. Bridge pad 1–2 only for a measured 3.3 V SPI header, or pad 2–3 only for a verified 5 V SPI header. **Do not bridge both.** The board's 5 V power input alone does not identify its SPI voltage. Measure the powered module's DOUT/DRDY high level or obtain its actual schematic before setting JP1.

Each wire is inverted once. Configure RP2350 `gpio_set_outover(pin, GPIO_OVERRIDE_INVERT)` on GPIO2, GPIO3, GPIO5, and GPIO6; configure `gpio_set_inover(pin, GPIO_OVERRIDE_INVERT)` on GPIO4 and GPIO28. If DRDY uses a GPIO interrupt, also configure `gpio_set_irqover(28, GPIO_OVERRIDE_INVERT)` because the IRQ path has a separate override. R18/R19 hold module SCLK/DIN low during reset; R20/R21 keep SYNC/PDWN and CS high. R22/R23 hold DOUT/DRDY high when those module pins float. Initialize the GPIO overrides before enabling SPI. After discarding the first 200 ms, pulse SYNC/PDWN low for the datasheet's required minimum timing but less than 20 DRDY periods, then wait for a valid DRDY. The transistor delay and pull-up rise time must be checked at the chosen SPI clock with the actual module. 30 kSPS needs at least 720 kbit/s for 24-bit data alone, plus command and timing overhead.

| Function | XIAO pin | RP2350 GPIO | Translator |
|---|---|---:|---|
| ADS1256 DRDY | D2 | GPIO28 | Q6, input inverted |
| ADS1256 CS | D3 | GPIO5 | Q3, output inverted |
| ADS1256 SYNC/PDWN | D4 | GPIO6 | Q4, output inverted |
| SPI0 SCLK | D8 | GPIO2 | Q1, output inverted |
| SPI0 MISO | D9 | GPIO4 | Q5, input inverted |
| SPI0 MOSI | D10 | GPIO3 | Q2, output inverted |

J2/J3 give **logical signal names**, not the purchased board's physical header order. Verify that order and dimensions before wiring or laying out an adapter. The nominal KiCad through-hole footprints must also be checked against the actual kit parts.

## Files and status

- `spice/receiver.cir` is the active ngspice analog model. It does not include ADC converter noise, the true digital filter, transistor SPI timing, firmware blanking, or the external sensor LC response.
- `kicad/generate.py` defines fixed connectivity and generates `kicad/receiver.net`; the latter is not hand edited.
- `analyze.py` generates the committed `analysis/` CSV, PNG, and Markdown artifacts.
- `bom.csv` groups fitted parts by value and count. `digikey_missing_components.csv` records that the only non-lab items, the ADC and XIAO, are already purchased; no new order is required by this logical design.
- `assembly.md` gives the logical perfboard wiring and staged power-up sequence; its module connections still require the purchased board's physical labels and SPI voltage.

There is no graphical KiCad schematic, verified module footprint, routed PCB, or ADC acquisition firmware yet. Do not fabricate from the connectivity netlist. Bench acceptance steps are in `docs/verification-plan.md`. `make pcb` intentionally fails while the physical board is absent.

Data sources: [TI ADS1256 datasheet](https://www.ti.com/lit/ds/symlink/ads1256.pdf) for buffered input impedance, noise, range, and SYNC/PDWN timing; [Raspberry Pi Pico SDK GPIO interface](https://github.com/raspberrypi/pico-sdk/blob/master/src/rp2_common/hardware_gpio/include/hardware/gpio.h) for `GPIO_OVERRIDE_INVERT`; [onsemi 2N3904 datasheet](https://www.onsemi.com/pdf/datasheet/2n3904-d.pdf) for transistor pinout and limits. The exact HiLetgo module PCB remains to be identified physically.
