# Active receiver design

This directory defines the receiver from the external FID sensing pair through a HiLetgo ADS1256 module and Seeed Studio XIAO RP2350. The selected ADC module is the Amazon item at https://www.amazon.com/dp/B09KGXC44Q.

## Signal path

1. `J1` connects the series-aiding sensing pair from `CoilDesign.xlsx`: 99.936 ohm and 152.568 mH. `J4` selects the tank and is the only setup change between the two test bands. A shunt on pins 1-2 connects `C25` (47 nF) and `C26` (4.7 nF), resonant at 1792 Hz. A shunt on pins 2-3 connects `C27` (33 nF) and `C28` (4.7 nF), resonant at 2099 Hz. Each tank is about 104 Hz wide because that width is R/(2πL). With the shunt removed, an external capacitor from pin 4 to pin 2 uses C = 1/(4π²f²L) when the measured inductance differs. The amplifier, blanking, bias, and 1.5–2.5 kHz filter stay fitted for both bands.
2. `R2` is 8.2 megohm from the buffer input to the 1.50 V bias. With `R1` (1 kilohm) and `C5` (3.3 nF) the load on the tank is 8.20 megohm at 1792 Hz, inside the 5 to 10 megohm target. `C5` blocks the coil's DC ground from the bias. `D1` and `D2` clamp overvoltage. `U1B`'s 1.516 kHz high-pass is the first gain and is what attenuates 50/60 Hz. The series-aiding pair does not cancel uniform pickup.
3. `U2`, a TMUX1101, shorts the protected input to the 1.50 V bias while `BLANK_D1_GPIO27` is high. `R3` makes blanking the power-up default. While the switch is on, the tank is loaded by `C5` and `R1`.
4. `U1A`, one channel of an OPA4197, is a unity-gain buffer. The tank provides the voltage step-up, about 17 at resonance. A gain of 56 ahead of the 1.516 kHz pole would amplify residual mains and would drive the 3.64 µV Curie-law FID past the ADC full scale.
5. `U1B`, `C7`, `R8`, and `R9` form a 1.516 kHz high-pass stage with high-frequency gain minus 56.19 V/V. `C7` is 100 nF C0G in 1206; that value does not exist in 0603.
6. `U1C`, `R10`, `R11`, `C8`, and `C23` form a unity-gain Sallen-Key low-pass with a 3.03 kHz natural frequency. It passes both 1.7 kHz and 2.1 kHz. The ADS1256 digital filter's −3 dB bandwidth at 30 kSPS is 6.1 kHz; this analog pole adds rejection above that bandwidth. The selected tank rejects 30 kHz much more strongly than this stage alone.
7. `R12` and `C9` form a 7.23 kHz differential input pole. The signal goes to ADS1256 `AIN0`; the buffered 1.50 V bias goes to `AIN1`. `R14` and `R15` hold D3's cathode at 1.80 V. The signal bias reverse-biases D3. A `U1C` output stuck at 5 V can raise `AIN0` only by one BAS116 drop above 1.80 V, which remains below the buffer limit of AVDD−2 V (3.0 V). The BAS116 forward voltage is 0.9 V maximum at 1 mA, and the fault current through 10 kΩ is below that. `AIN2` through `AIN7` are tied to the same 1.50 V bias.
8. The ADS1256 input buffer is enabled and its PGA is set to 64. With the module's nominal 2.5 V ADR03 reference, differential full scale is plus or minus 78.125 mV.
9. The ADS1256 sends 30 kSPS data to the XIAO RP2350 over SPI. Target firmware must feed samples to the estimator and report frequency and field through USB CDC.

`U1B` still sets a high-frequency gain of 56.19. That high-pass and the 3.03 kHz low-pass pass both test bands, so they are not changed when `J4` moves. The simulated coil-source-to-ADC differential gain is 647 V/V (56.2 dB) with the 1792 Hz shunt and 751 V/V (57.5 dB) with the 2099 Hz shunt. This gain excludes the ADS1256 internal PGA. These are simulated nominal values.

## ADC module interface

The purchased HiLetgo module contains an ADS1256IDB, a nominal 2.5 V ADR03 reference, and a 7.68 MHz ADC clock source. It requires 5 V power and exposes `SCLK`, `DIN`, `DOUT`, `CS`, `DRDY`, `PDWN`, and `AIN0` through `AIN7`.

The XIAO uses:

| Function | XIAO pin | RP2350 GPIO |
|---|---|---:|
| Receiver blank | D1 | GPIO27 |
| ADS1256 DRDY | D2 | GPIO28 |
| ADS1256 CS | D3 | GPIO5 |
| ADS1256 PDWN/SYNC | D4 | GPIO6 |
| SPI0 SCLK | D8 | GPIO2 |
| SPI0 MISO | D9 | GPIO4 |
| SPI0 MOSI | D10 | GPIO3 |

The ADC module uses 5 V digital I/O. Four SN74AHCT1G125 buffers translate XIAO SCLK, MOSI, CS, and PDWN from 3.3 V to 5 V. Two SN74LVC1G125 buffers translate DOUT and DRDY from 5 V to 3.3 V. Their active-low output-enable pins are tied to ground. `R13` and `R16` pull CS and SYNC/PDWN high while the XIAO pins are high-Z, so the converter idles running and deselected. Both of those ADS1256 pins are active-low. `R19` and `R20` pull SCLK and MOSI low so those AHCT inputs are not floating; the ADS1256 clocks data with SCLK idle-low. `R17` and `R18` pull DOUT and DRDY high so the LVC inputs are not floating while the ADC output drivers are high-Z.

`J2` and `J3` describe the module's logical digital and analog headers. Verify the physical pin order against the exact purchased board before laying out an adapter. Do not assume that the logical connector numbering matches the module silkscreen. `C15` through `C20` provide one local 100 nF bypass capacitor for each level-shifter IC.

## Power

This revision is USB-powered. The XIAO RP2350 receives 5 V through its onboard USB-C connector. Its exposed VBUS pad powers the ADS1256 module and the four AHCT level shifters. `C14` provides bulk bypass on the 5 V module rail; the purchased module retains its onboard local bypassing.

The XIAO's onboard regulator produces `3V3_OUT`. `FB1` and `C10` through `C13` filter that rail into `AVDD_3V3` for the TMUX1101 and input clamps. The two LVC level shifters use unfiltered XIAO 3.3 V so their switching currents do not flow through the analog ferrite.

The OPA4197 is not a 3.3 V part: its specified minimum supply is 4.5 V. `FB2`, `C21`, and `C22` therefore filter USB VBUS into `OPA_AVDD_5V` for U1. `U1D` buffers the 1.50 V bias made by `R4` (23.2 kΩ), `R5` (10 kΩ), and `C6`. On a 5 V rail that bias is below (V+)−3 V, the common-mode region where TI specifies the 5.5 nV/√Hz density. The module's ADR03 remains the 2.5 V conversion reference; it is not this bias.

The former battery connector was removed because this ADS1256 module requires 5 V and the XIAO battery input does not provide a 5 V module rail. Do not inject an external 5 V source into VBUS while USB is connected.

## Design files

- `kicad/generate.py` is the fixed-topology KiCad circuit source.
- `kicad/receiver.net` is its committed connectivity netlist.
- `kicad/lib/` contains Seeed Studio's official XIAO RP2350 symbol and SMD footprint.
- `spice/receiver.cir` is the active ngspice-compatible circuit model.
- `analyze.py` generates transient and frequency-response data and figures.
- `analysis/` contains generated CSV, PNG, and Markdown results.
- `kicad/validate.py` regenerates connectivity and runs available KiCad CLI checks.
- `bom.csv` lists every fitted part, the ADS1256 module, and sensor assumptions.

Run `make figures` to regenerate plots, `make kicad` to regenerate and check KiCad artifacts, and `make eda` after any receiver change. Run `make export` to test the current receiver and create a timestamped review package under `local/`. The package shares the construction schematic, BOM, and connectivity, and writes separate `1.7kHz/` and `2.1kHz/` simulation results for the two J4 shunts. PCB renders appear only after a strict-DRC-clean board exists. See `docs/circuit-tooling.md`.

## Required ADS1256 configuration

- Channel: differential `AIN0 - AIN1`
- Input buffer: enabled
- PGA: 64
- Data rate: 30 kSPS
- Data format: signed 24-bit two's complement
- DRDY: use falling edges to pace SPI reads
- Calibration: run SELFCAL with the input buffer off, then enable the buffer and run SELFOCAL only. Self-gain calibration with the buffer on is not valid here, because VREFN is 0 V and that is the bottom of the buffer's input range
- SYNC/PDWN: hold D4 high while converting. The pin is active-low; `R16` already idles it high
- Receiver state: drive D1 low only after the 200 ms blanking interval

The ADS1256 does not offer a 20 kSPS data-rate setting. Estimator code must use the actual 30 kSPS rate or resample with a tested digital filter. Clock error changes the measured field scale, so calibrate or measure the ADS1256 module clock and keep that error separate from cycle-to-cycle noise.

## Limits and required work

This is a complete circuit definition, not hardware proof. The compact OPA4197 model does not include TI's full production behavior. The SPICE model represents the selected PGA as an ideal internal block and does not include ADS1256 converter noise, digital-filter alias response, INL, reference noise, clock tolerance, or settling. Verify those properties on the purchased module at PGA 64 and 30 kSPS.

XIAO ADC acquisition is no longer used. ADS1256 SPI acquisition, DRDY handling, blanking control, estimator integration, and USB reporting firmware are not implemented yet. `frequency_estimator_firmware/` currently contains only the portable estimator core and host tests.

There is no graphical KiCad schematic or routed PCB yet. Do not fabricate from `receiver.net`. First verify the module header pinout, produce and audit a graphical schematic, pass ERC, place and route a board or module adapter, and obtain a DRC report with zero violations and zero unconnected pads. Follow `docs/verification-plan.md` for transfer, noise, clock, blanking, and wet-FID tests.
