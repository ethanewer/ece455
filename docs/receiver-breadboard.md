# Receiver breadboard placement

Standard 830-point board: columns 1–63, rows a–e above the centre channel and f–j below it. `T-` is the outer top rail row, beside the blue line, used as GND; the other three rails stay unused. `receiver-breadboard.png` draws the same holes with the AD8421 module, its batteries, the ADS1256 module, and the XIAO.

## Receiver parts

Ref | Part | Holes
--- | --- | ---
Q2 | 2N3904 | C d15, B d16, E d17
Q1 | 2N3904 | C b17, B b18, E b19
R2 | 1 kΩ | b26, b31
C1 | 22 nF | a31, T-31
R3 | 10 kΩ | c31, c35
C2 | 2.2 nF | a35, T-35
R1 | 100 Ω | module GAIN footprint

## Test input

A function generator stands in for the coil. Set it to High-Z load; the voltage at J1 is then its amplitude × RT2 / (RT1 + RT2), about 1/1001. Measure RT1 and RT2 for the exact ratio.

Ref | Part | Holes
--- | --- | ---
RT1 | 100 kΩ | b5, b11
RT2 | 100 Ω | a11, T-11

For the coil, remove the e11–e17 jumper and the generator leads, then connect the coil signal to e17 and the coil return to T-17.

## Jumpers

From | To
--- | ---
c17 | c18
a15 | T-15
a16 | T-16
a19 | T-19
e11 | e17 (test J1; remove for the coil)

## XIAO RP2350 (U1)

The XIAO straddles the channel with its pins in rows c and h, columns 56–62, and its USB-C connector past column 63. Its body covers rows c–h of columns 55–63.

Pin | Pin hole | Wire from | To
--- | --- | --- | ---
D2 | c60 | a60 | ADS1256 DRDY
D3 | c59 | a59 | ADS1256 CS
D4 | c58 | a58 | ADS1256 PDWN
D8 | h57 | j57 | ADS1256 SCLK
D9 | h58 | j58 | ADS1256 DOUT
D10 | h59 | j59 | ADS1256 DIN
GND | h61 | j61 | ADS1256 GND (digital header)
5V | h62 | j62 | ADS1256 5V

## Off-board wires

Hole | Connection
--- | ---
e5 | Function generator signal
T-40 | Function generator ground clip
a17 | jumper to module +IN pin
a26 | W1 signal lead
T-28 | W1 shield lead
e35 | ADS1256 AIN0
T-36 | ADS1256 AIN1
T-37 | ADS1256 GND (analog header)
a58 | ADS1256 PDWN
a59 | ADS1256 CS
a60 | ADS1256 DRDY
j57 | ADS1256 SCLK
j58 | ADS1256 DOUT
j59 | ADS1256 DIN
j61 | ADS1256 GND (digital header)
j62 | ADS1256 5V

## Modules and batteries

- BT1 + → AD8421 module V+; BT1 − and BT2 + → module GND; BT2 − → module V−.
- W1 SMA end → module OUT jack; its signal lead → a26, its shield lead → T-28.
- Keep the AD8421 module's input jumper on −IN/GND and its REF jumper on BIAS.
- The ADS1256 module's pin labels are on its underside. Use female Dupont ends on its pins, run the AIN0, AIN1, and GND leads together, and do not jumper AIN1 to the GND pin beside it.
- Clip the generator ground to T-40, right of every analog ground on the rail.

Check each transistor's pinout before inserting it; the holes name its C, B, and E leads.
