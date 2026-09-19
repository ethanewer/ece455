#!/usr/bin/env python3
"""Generate the fixed receiver connectivity netlist.

This is a reproducible serializer for one design. It does not search, mutate,
or rank circuit candidates.
"""

from pathlib import Path
import os

HERE = Path(__file__).resolve().parent
PIPELINE_DIR = HERE.parents[1] / "local" / "skidl"
PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
# SKiDL creates runtime logs and library caches in the process directory.
# Keep those uncommitted outputs out of the repository root.
os.chdir(PIPELINE_DIR)

KICAD = Path("/Applications/KiCad.app/Contents/SharedSupport")
for version in ("", "6", "7", "8", "9", "10"):
    os.environ.setdefault(f"KICAD{version}_SYMBOL_DIR", str(KICAD / "symbols"))
    os.environ.setdefault(f"KICAD{version}_FOOTPRINT_DIR", str(KICAD / "footprints"))

from skidl import KICAD10, Net, Part, generate_netlist, set_default_tool
from skidl import lib_search_paths

set_default_tool(KICAD10)
lib_search_paths[KICAD10].insert(0, str(HERE / "lib"))


def part(lib, name, ref, value=None, footprint=None):
    return Part(lib, name, ref=ref, tag=ref, value=value or name,
                footprint=footprint)


def resistor(ref, value):
    return part("Device", "R", ref, value, "Resistor_SMD:R_0603_1608Metric")


def capacitor(ref, value, footprint="Capacitor_SMD:C_0603_1608Metric"):
    return part("Device", "C", ref, value, footprint)


def testpoint(ref, net):
    tp = part("Connector", "TestPoint", ref, net.name,
              "TestPoint:TestPoint_Plated_Hole_D2.0mm")
    tp[1] += net


def level_buffer(ref, family, signal_in, signal_out, supply):
    """Add one always-enabled SOT-23-5 logic-level buffer."""
    u = part("74xGxx", family, ref, family,
             "Package_TO_SOT_SMD:SOT-23-5")
    u[1] += gnd       # active-low output enable
    u[2] += signal_in
    u[3] += gnd
    u[4] += signal_out
    u[5] += supply
    return u


# Rails and analog nodes.
gnd = Net("GND")
vbus5 = Net("USB_VBUS_5V")
raw_3v3 = Net("XIAO_3V3_OUT")
avdd = Net("AVDD_3V3")
opamp5 = Net("OPA_AVDD_5V")
vref_raw = Net("VREF_RAW")
vref = Net("VREF_2V5")
coil_hi = Net("COIL_HI")
protected = Net("PROTECTED")
pre_in = Net("PRE_IN")
stage1_n = Net("STAGE1_N")
stage1 = Net("STAGE1")
stage2_n = Net("STAGE2_N")
stage2 = Net("STAGE2")
stage3_n = Net("STAGE3_N")
stage3 = Net("STAGE3")
ads_ain0 = Net("ADS1256_AIN0_SIGNAL")
ads_ain1 = vref
blank = Net("BLANK_D1_GPIO27")

# MCU-side and 5 V ADS1256-side digital nets.
mcu_sclk = Net("MCU_SPI0_SCLK_D8_GPIO2")
mcu_mosi = Net("MCU_SPI0_MOSI_D10_GPIO3")
mcu_cs = Net("MCU_ADS_CS_D3_GPIO5")
mcu_pdwn = Net("MCU_ADS_PDWN_D4_GPIO6")
mcu_miso = Net("MCU_SPI0_MISO_D9_GPIO4")
mcu_drdy = Net("MCU_ADS_DRDY_D2_GPIO28")
ads_sclk = Net("ADS1256_SCLK_5V")
ads_din = Net("ADS1256_DIN_5V")
ads_cs = Net("ADS1256_CS_5V")
ads_pdwn = Net("ADS1256_PDWN_5V")
ads_dout = Net("ADS1256_DOUT_5V")
ads_drdy = Net("ADS1256_DRDY_5V")

# External sensing pair and 254.068 nF C0G tuning bank.
j1 = part("Connector_Generic", "Conn_01x02", "J1", "FID SENSING COIL",
          "TerminalBlock_Altech:Altech_AK100_1x02_P5.00mm")
j1[1] += coil_hi
j1[2] += gnd
for ref, value, fp in (
    ("C1", "220n C0G 2%", "Capacitor_SMD:C_1206_3216Metric"),
    ("C2", "33n C0G 2%", "Capacitor_SMD:C_0805_2012Metric"),
    ("C3", "1n C0G 1%", "Capacitor_SMD:C_0603_1608Metric"),
    ("C4", "68p C0G 1%", "Capacitor_SMD:C_0603_1608Metric"),
):
    c = capacitor(ref, value, fp)
    c[1] += coil_hi
    c[2] += gnd

# Coupling, current limit, low-leakage clamps, bias, and default-on blanking.
c5 = capacitor("C5", "1u X7R 25V", "Capacitor_SMD:C_1210_3225Metric")
c5[1] += coil_hi
c5[2] += protected
r1 = resistor("R1", "1k 1%")
r1[1] += protected
r1[2] += pre_in
r2 = resistor("R2", "1Meg 1%")
r2[1] += pre_in
r2[2] += vref
d1 = part("Device", "D", "D1", "BAS116H low leakage",
          "Diode_SMD:D_SOD-323_HandSoldering")
d1[1] += pre_in  # cathode
d1[2] += gnd     # anode
d2 = part("Device", "D", "D2", "BAS116H low leakage",
          "Diode_SMD:D_SOD-323_HandSoldering")
d2[1] += avdd    # cathode
d2[2] += pre_in  # anode
u2 = part("Analog_Switch", "TMUX1101DBV", "U2", "TMUX1101DBVR")
u2[1] += pre_in
u2[2] += vref
u2[3] += gnd
u2[4] += blank
u2[5] += avdd
r3 = resistor("R3", "100k 1%")
r3[1] += avdd
r3[2] += blank

# OPA4197 quad on a filtered 5 V rail (its specified minimum is 4.5 V). U1D
# buffers 2.5 V VREF. The ADS1256 PGA supplies the final x64, so board-level
# gain is only 4.01 * 4.02 * 1 = 16.12 V/V at midband.
u1 = part("Amplifier_Operational", "OPA4197xPW", "U1", "OPA4197IPWR",
          "Package_SO:TSSOP-14_4.4x5mm_P0.65mm")
u1[4] += opamp5
u1[11] += gnd

r4 = resistor("R4", "10k 0.1%")
r5 = resistor("R5", "10k 0.1%")
r4[1] += opamp5
r4[2] += vref_raw
r5[1] += vref_raw
r5[2] += gnd
c6 = capacitor("C6", "10u 10V", "Capacitor_SMD:C_0805_2012Metric")
c6[1] += vref_raw
c6[2] += gnd
u1[12] += vref_raw
u1[13] += vref
u1[14] += vref

# U1A non-inverting gain 4.01.
u1[3] += pre_in
u1[2] += stage1_n
u1[1] += stage1
r6 = resistor("R6", "1k 0.1%")
r7 = resistor("R7", "3.01k 0.1%")
r6[1] += stage1_n
r6[2] += vref
r7[1] += stage1
r7[2] += stage1_n

# U1B high-pass, 723 Hz corner and inverting gain 4.02.
c7 = capacitor("C7", "22n C0G 2%")
r8 = resistor("R8", "10k 0.1%")
r9 = resistor("R9", "40.2k 0.1%")
c7[1] += stage1
c7[2] += r8[1]
r8[2] += stage2_n
r9[1] += stage2
r9[2] += stage2_n
u1[5] += vref
u1[6] += stage2_n
u1[7] += stage2

# U1C unity-gain inverting low pass, 4.82 kHz feedback pole.
r10 = resistor("R10", "10k 0.1%")
r11 = resistor("R11", "10k 0.1%")
c8 = capacitor("C8", "3.3n C0G 2%")
r10[1] += stage2
r10[2] += stage3_n
r11[1] += stage3_n
r11[2] += stage3
c8[1] += stage3_n
c8[2] += stage3
u1[10] += vref
u1[9] += stage3_n
u1[8] += stage3

# Differential ADS1256 input. AIN1 is the same buffered 2.5 V reference used
# by the amplifier chain. PGA=64 gives a nominal differential full scale of
# +/-2*2.5V/64 = +/-78.125 mV with the module's ADR03 reference.
r12 = resistor("R12", "1k 0.1%")
c9 = capacitor("C9", "22n C0G 2%")
r12[1] += stage3
r12[2] += ads_ain0
c9[1] += ads_ain0
c9[2] += ads_ain1

# Filtered 3.3 V switch/clamp rail and filtered 5 V OPA4197 rail.
fb1 = part("Device", "FerriteBead", "FB1", "600R@100MHz 500mA",
           "Inductor_SMD:L_0603_1608Metric")
fb1[1] += raw_3v3
fb1[2] += avdd
fb2 = part("Device", "FerriteBead", "FB2", "600R@100MHz 500mA",
           "Inductor_SMD:L_0603_1608Metric")
fb2[1] += vbus5
fb2[2] += opamp5
for ref, value, fp, rail in (
    ("C10", "10u 10V", "Capacitor_SMD:C_0805_2012Metric", avdd),
    ("C11", "100n X7R", "Capacitor_SMD:C_0603_1608Metric", avdd),
    ("C12", "100n X7R", "Capacitor_SMD:C_0603_1608Metric", avdd),
    ("C13", "1u X7R", "Capacitor_SMD:C_0603_1608Metric", avdd),
    ("C14", "10u 10V", "Capacitor_SMD:C_0805_2012Metric", vbus5),
    ("C15", "100n X7R", "Capacitor_SMD:C_0603_1608Metric", vbus5),
    ("C16", "100n X7R", "Capacitor_SMD:C_0603_1608Metric", vbus5),
    ("C17", "100n X7R", "Capacitor_SMD:C_0603_1608Metric", vbus5),
    ("C18", "100n X7R", "Capacitor_SMD:C_0603_1608Metric", vbus5),
    ("C19", "100n X7R", "Capacitor_SMD:C_0603_1608Metric", raw_3v3),
    ("C20", "100n X7R", "Capacitor_SMD:C_0603_1608Metric", raw_3v3),
    ("C21", "10u 10V", "Capacitor_SMD:C_0805_2012Metric", opamp5),
    ("C22", "100n X7R", "Capacitor_SMD:C_0603_1608Metric", opamp5),
):
    c = capacitor(ref, value, fp)
    c[1] += rail
    c[2] += gnd

# XIAO RP2350. SPI0 talks to the ADS1256 module through explicit 3.3V/5V
# buffers. USB VBUS powers the 5 V ADC module, so this revision is USB-only.
u3 = part("Seeed_Studio_XIAO_Series", "XIAO-RP2350-SMD", "U3",
          "Seeed Studio XIAO RP2350",
          "Seeed_Studio_XIAO_Series:XIAO-RP2350-SMD")
u3[2] += blank       # D1 / GPIO27
u3[3] += mcu_drdy    # D2 / GPIO28
u3[4] += mcu_cs      # D3 / GPIO5
u3[5] += mcu_pdwn    # D4 / GPIO6
u3[9] += mcu_sclk    # D8 / GPIO2
u3[10] += mcu_miso   # D9 / GPIO4
u3[11] += mcu_mosi   # D10 / GPIO3
u3[12] += raw_3v3
u3[28] += raw_3v3
u3[14] += vbus5
for pin in (13, 26, 30):
    u3[pin] += gnd
for pin in (1, 6, 7, 8, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25,
            27, 29):
    NC += u3[pin]

# 3.3 V -> 5 V: AHCT inputs recognize 3.3 V logic. 5 V -> 3.3 V: LVC inputs
# are 5.5 V tolerant. All six buffers have active-low OE tied to ground.
level_buffer("U4", "74AHCT1G125", mcu_sclk, ads_sclk, vbus5)
level_buffer("U5", "74AHCT1G125", mcu_mosi, ads_din, vbus5)
level_buffer("U6", "74AHCT1G125", mcu_cs, ads_cs, vbus5)
level_buffer("U7", "74AHCT1G125", mcu_pdwn, ads_pdwn, vbus5)
level_buffer("U8", "74LVC1G125", ads_dout, mcu_miso, raw_3v3)
level_buffer("U9", "74LVC1G125", ads_drdy, mcu_drdy, raw_3v3)

# HiLetgo ADS1256 module headers. Verify physical header order against the
# purchased board before layout; these are logical interface connectors.
j2 = part("Connector_Generic", "Conn_01x08", "J2",
          "HILETGO ADS1256 DIGITAL HEADER",
          "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical")
for pin, net in enumerate((vbus5, gnd, ads_sclk, ads_din, ads_dout,
                           ads_cs, ads_drdy, ads_pdwn), start=1):
    j2[pin] += net
j3 = part("Connector_Generic", "Conn_01x08", "J3",
          "HILETGO ADS1256 ANALOG HEADER",
          "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical")
j3[1] += ads_ain0
j3[2] += ads_ain1
for pin in range(3, 9):
    NC += j3[pin]

for ref, net in (
    ("TP1", gnd), ("TP2", coil_hi), ("TP3", pre_in), ("TP4", vref),
    ("TP5", stage1), ("TP6", stage2), ("TP7", stage3),
    ("TP8", ads_ain0), ("TP9", blank), ("TP10", avdd),
    ("TP11", vbus5), ("TP12", ads_drdy),
):
    testpoint(ref, net)

# SKiDL 2.3's KiCad 10 graphical auto-router can misjoin dense analog nets, so
# only the audited connectivity netlist is emitted here.
netlist_path = HERE / "receiver.net"
generate_netlist(file_=str(netlist_path))
# SKiDL emits trailing spaces in its legacy connectivity format. Normalize
# them so generated artifacts pass repository whitespace checks.
normalized_lines = []
for line in netlist_path.read_text().splitlines():
    stripped = line.strip()
    indentation = line[: len(line) - len(line.lstrip())]
    if stripped.startswith('(date "'):
        line = indentation + '(date "generated")'
    elif stripped.startswith("(source "):
        line = indentation + '(source "generate.py")'
    normalized_lines.append(line.rstrip())
netlist_path.write_text("\n".join(normalized_lines) + "\n")
