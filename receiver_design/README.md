# Active receiver design

This directory defines the receiver from the external FID sensing pair through a HiLetgo ADS1256 module and Seeed Studio XIAO RP2350. The selected ADC module is the Amazon item at https://www.amazon.com/dp/B09KGXC44Q.

## Receiver boundary and signal path

`J1` accepts signal and return from an external sensor assembly. The coil, any tuning capacitor, and any switched damping resistor are outside this receiver and its BOM. No receiver part is placed across the input to make an LC tank. The 99.94 ohm, 152.6 mH coil pair in `verification_modeling/coil.py` is an external sensor estimate, not circuitry fitted here.

1. `C5` AC couples the external signal into `U1A`, the unity-gain low-noise input buffer. `R1` limits clamp current, `D1` and `D2` protect the input, and ten available 510 kohm resistors (`R2`, `R6`, `R24`–`R31`) form a 5.1 megohm bias return. `U2` shorts the protected input to the buffered 1.36 V bias during blanking.
2. `U1B` uses `C7` 100 nF, `R8` 1.05 kohm, and `R9` 56 kohm for a 1.516 kHz high pass and 53.33 V/V high frequency gain. `U1C` uses `R10`+`R22` and `R11`+`R23` at 11 kohm per leg, `C8` and `C32` at 3.3 nF each in parallel, and `C23` at 3.3 nF for a 3.10 kHz natural low pass frequency.
3. `R12` 6.8 kohm and `C9` 3.3 nF provide a 7.09 kHz differential ADC input pole. `R14` 1.47 kohm and `R15` 680 ohm hold the `D3` clamp cathode near 1.58 V. Allowing for divider rise under a 5.25 V rail fault and a 0.9 V BAS116 drop, the estimated AIN0 fault level is about 2.74 V, below the 3.0 V buffer limit. `AIN1` and unused analog inputs receive the buffered bias.
4. The ADS1256 input buffer is enabled and its PGA is set to 64. With the module's nominal 2.5 V reference, differential full scale is plus or minus 78.125 mV. The ADS1256 sends 30 kSPS data to the XIAO RP2350 over SPI.

The SPICE deck applies a 10 µV FID test source through 30 kohm of representative external source impedance. Its plots show receiver input-to-ADC gain. They do not predict the signal gain, resonance, or damping of the external coil assembly. The supplied inventory lists passive values, but omits quantities, dielectrics, voltage ratings, and packages. The KiCad footprints are nominal until the supplied parts are identified.

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

This revision is USB-powered. The XIAO RP2350 receives 5 V through its onboard USB-C connector. Its exposed VBUS pad powers the ADS1256 module and the four AHCT level shifters. `C14` provides 1 uF bypass on the 5 V module rail; the purchased module retains its onboard local bypassing.

The XIAO's onboard regulator produces `3V3_OUT`. `FB1` and `C10` through `C13` filter that rail into `AVDD_3V3` for the TMUX1101 and input clamps. The two LVC level shifters use unfiltered XIAO 3.3 V so their switching currents do not flow through the analog ferrite.

The OPA4197 is not a 3.3 V part: its specified minimum supply is 4.5 V. `FB2`, `C21`, and `C22` therefore filter USB VBUS into `OPA_AVDD_5V` for U1. `U1D` buffers the 1.36 V bias made by `R4` (20 kΩ), `R5` (7.5 kΩ), and `C6`. On a 5 V rail that bias is below (V+)−3 V, the common-mode region where TI specifies the 5.5 nV/√Hz density. The module's ADR03 remains the 2.5 V conversion reference; it is not this bias.

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

Run `make figures` to regenerate plots, `make kicad` to regenerate and check KiCad artifacts, and `make eda` after any receiver change. Run `make export` to test the current receiver and create a timestamped review package under `local/`. The package shares the construction schematic, BOM, and connectivity, and writes separate `1.7kHz/` and `2.1kHz/` receiver-input simulations. PCB renders appear only after a strict-DRC-clean board exists. See `docs/circuit-tooling.md`.

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

This is a complete circuit definition, not hardware proof. The compact OPA4197 model does not include TI's full production behavior or the external sensor LC response. The SPICE model represents the selected PGA as an ideal internal block and does not include ADS1256 converter noise, digital-filter alias response, INL, reference noise, clock tolerance, or settling. Verify those properties on the purchased module at PGA 64 and 30 kSPS.

XIAO ADC acquisition is no longer used. ADS1256 SPI acquisition, DRDY handling, blanking control, estimator integration, and USB reporting firmware are not implemented yet. `frequency_estimator_firmware/` currently contains only the portable estimator core and host tests.

There is no graphical KiCad schematic or routed PCB yet. Do not fabricate from `receiver.net`. First verify the module header pinout, produce and audit a graphical schematic, pass ERC, place and route a board or module adapter, and obtain a DRC report with zero violations and zero unconnected pads. Follow `docs/verification-plan.md` for transfer, noise, clock, blanking, and wet-FID tests.
