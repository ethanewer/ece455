# Active receiver design

This directory defines the receiver from the external FID sensing pair through a HiLetgo ADS1256 module and Seeed Studio XIAO RP2350. The selected ADC module is the Amazon item at https://www.amazon.com/dp/B09KGXC44Q.

## Signal path

1. `J1` connects the nominal 14 ohm, 22 mH series-opposed sensing pair.
2. `C1` through `C4` form a 254.068 nF C0G tuning bank for 2128.8 Hz at the nominal 22 mH.
3. `C5`, `R1`, `D1`, and `D2` AC-couple, current-limit, bias, and clamp the receiver input.
4. `U2`, a TMUX1101, shorts the protected input to the 2.5 V reference while `BLANK_D1_GPIO27` is high. `R3` makes blanking the power-up default.
5. `U1A`, one channel of an OPA4197, is a non-inverting preamplifier. `R6` and `R7` set gain to 4.01 V/V.
6. `U1B`, `C7`, `R8`, and `R9` form a 723 Hz high-pass stage with gain minus 4.02 V/V.
7. `U1C`, `R10`, `R11`, and `C8` form a unity-gain inverting stage with a 4.82 kHz low-pass pole.
8. `R12` and `C9` form a 7.23 kHz differential input pole. The signal goes to ADS1256 `AIN0`; buffered `VREF_2V5` goes to `AIN1`.
9. The ADS1256 input buffer is enabled and its PGA is set to 64. With the module's nominal 2.5 V ADR03 reference, differential full scale is plus or minus 78.125 mV.
10. The ADS1256 sends 30 kSPS data to the XIAO RP2350 over SPI. Target firmware must feed samples to the estimator and report frequency and field through USB CDC.

Board-level resistor-set midband gain is 16.12 V/V, about 64 times lower than the previous 1026.6 V/V design. Filter attenuation reduces electronics gain to about 13.3 V/V at 2128.8 Hz. The active SPICE model predicts approximately 279.5 V/V from the induced series source to ADS1256 AIN0 minus AIN1 at nominal resonance. The ADC's internal PGA makes the modeled post-PGA gain approximately 17,888 V/V. These are simulated nominal values.

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

The ADC module uses 5 V digital I/O. Four SN74AHCT1G125 buffers translate XIAO SCLK, MOSI, CS, and PDWN from 3.3 V to 5 V. Two SN74LVC1G125 buffers translate DOUT and DRDY from 5 V to 3.3 V. Their active-low output-enable pins are tied to ground.

`J2` and `J3` describe the module's logical digital and analog headers. Verify the physical pin order against the exact purchased board before laying out an adapter. Do not assume that the logical connector numbering matches the module silkscreen. `C15` through `C20` provide one local 100 nF bypass capacitor for each level-shifter IC.

## Power

This revision is USB-powered. The XIAO RP2350 receives 5 V through its onboard USB-C connector. Its exposed VBUS pad powers the ADS1256 module and the four AHCT level shifters. `C14` provides bulk bypass on the 5 V module rail; the purchased module retains its onboard local bypassing.

The XIAO's onboard regulator produces `3V3_OUT`. `FB1` and `C10` through `C13` filter that rail into `AVDD_3V3` for the TMUX1101 and input clamps. The two LVC level shifters use unfiltered XIAO 3.3 V so their switching currents do not flow through the analog ferrite.

The OPA4197 is not a 3.3 V part: its specified minimum supply is 4.5 V. `FB2`, `C21`, and `C22` therefore filter USB VBUS into `OPA_AVDD_5V` for U1. `U1D` buffers the 2.5 V half-supply reference made by `R4`, `R5`, and `C6`. This also puts ADS1256 AIN1 at the module reference midpoint.

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

Run `make figures` to regenerate plots, `make kicad` to regenerate and check KiCad artifacts, and `make eda` after any receiver change. See `docs/circuit-tooling.md`.

## Required ADS1256 configuration

- Channel: differential `AIN0 - AIN1`
- Input buffer: enabled
- PGA: 64
- Data rate: 30 kSPS
- Data format: signed 24-bit two's complement
- DRDY: use falling edges to pace SPI reads
- Calibration: issue self-calibration after setting buffer, PGA, and data rate
- Receiver state: drive D1 low only after the 200 ms blanking interval

The ADS1256 does not offer a 20 kSPS data-rate setting. Estimator code must use the actual 30 kSPS rate or resample with a tested digital filter. Clock error changes the measured field scale, so calibrate or measure the ADS1256 module clock and keep that error separate from cycle-to-cycle noise.

## Limits and required work

This is a complete circuit definition, not hardware proof. The compact OPA4197 model does not include TI's full production behavior. The SPICE model represents the selected PGA as an ideal internal block and does not include ADS1256 converter noise, digital-filter alias response, INL, reference noise, clock tolerance, or settling. Verify those properties on the purchased module at PGA 64 and 30 kSPS.

XIAO ADC acquisition is no longer used. ADS1256 SPI acquisition, DRDY handling, blanking control, estimator integration, and USB reporting firmware are not implemented yet. `frequency_estimator_firmware/` currently contains only the portable estimator core and host tests.

There is no graphical KiCad schematic or routed PCB yet. Do not fabricate from `receiver.net`. First verify the module header pinout, produce and audit a graphical schematic, pass ERC, place and route a board or module adapter, and obtain a DRC report with zero violations and zero unconnected pads. Follow `docs/verification-plan.md` for transfer, noise, clock, blanking, and wet-FID tests.
