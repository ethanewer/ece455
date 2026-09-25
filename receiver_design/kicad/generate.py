#!/usr/bin/env python3
"""Generate fixed connectivity for the lab-parts ADS1256 receiver.

This is one circuit, not a search or topology generator. The purchased
module's physical header order and SPI voltage must be checked before layout.
"""

from pathlib import Path
import os

HERE = Path(__file__).resolve().parent
PIPELINE_DIR = HERE.parents[1] / "local" / "skidl"
PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
os.chdir(PIPELINE_DIR)

KICAD = Path("/Applications/KiCad.app/Contents/SharedSupport")
for version in ("", "6", "7", "8", "9", "10"):
    os.environ.setdefault(f"KICAD{version}_SYMBOL_DIR", str(KICAD / "symbols"))
    os.environ.setdefault(f"KICAD{version}_FOOTPRINT_DIR", str(KICAD / "footprints"))

from skidl import KICAD10, Net, Part, generate_netlist, set_default_tool
from skidl import lib_search_paths

set_default_tool(KICAD10)
lib_search_paths[KICAD10].insert(0, str(HERE / "lib"))

AXIAL = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"
DISC = "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm"
RADIAL = "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm"
DIODE = "Diode_THT:D_DO-35_SOD27_P7.62mm_Horizontal"


def part(lib, name, ref, value=None, footprint=None):
    return Part(lib, name, ref=ref, tag=ref, value=value or name,
                footprint=footprint)


def resistor(ref, value, left, right):
    r = part("Device", "R", ref, value, AXIAL)
    r[1] += left
    r[2] += right
    return r


def capacitor(ref, value, left, right, electrolytic=False):
    c = part("Device", "C_Polarized" if electrolytic else "C", ref,
             value, RADIAL if electrolytic else DISC)
    c[1] += left
    c[2] += right
    return c


def diode(ref, anode, cathode):
    d = part("Device", "D", ref, "1N4148", DIODE)
    d[2] += anode
    d[1] += cathode
    return d


def testpoint(ref, net):
    tp = part("Connector", "TestPoint", ref, net.name,
              "TestPoint:TestPoint_Plated_Hole_D2.0mm")
    tp[1] += net


gnd = Net("GND")
vbus5 = Net("USB_VBUS_5V")
raw_3v3 = Net("XIAO_3V3_OUT")
logic_vdd = Net("MODULE_SPI_VDD_SELECT")
vref = Net("VBIAS_1V60")
receiver_in = Net("RECEIVER_IN")
coupled = Net("COUPLED_INPUT")
ads_ain0 = Net("ADS1256_AIN0_SIGNAL")
bias_mid = Net("BIAS_RETURN_MID")

mcu_sclk = Net("MCU_SPI0_SCLK_D8_GPIO2")
mcu_mosi = Net("MCU_SPI0_MOSI_D10_GPIO3")
mcu_cs = Net("MCU_ADS_CS_D3_GPIO5")
mcu_pdwn = Net("MCU_ADS_PDWN_D4_GPIO6")
mcu_miso = Net("MCU_SPI0_MISO_D9_GPIO4")
mcu_drdy = Net("MCU_ADS_DRDY_D2_GPIO28")
ads_sclk = Net("ADS1256_SCLK")
ads_din = Net("ADS1256_DIN")
ads_cs = Net("ADS1256_CS")
ads_pdwn = Net("ADS1256_PDWN")
ads_dout = Net("ADS1256_DOUT")
ads_drdy = Net("ADS1256_DRDY")

# Logical receiver boundary. The sensor LC tank and damping circuit stay
# outside J1. J1/J2/J3 are wiring interfaces, not purchased connectors.
j1 = part("Connector_Generic", "Conn_01x02", "J1",
          "EXTERNAL SENSOR WIRE INTERFACE")
j1[1] += receiver_in
j1[2] += gnd

# The converter's internal buffer is the first active high-impedance stage.
capacitor("C5", "22n", receiver_in, coupled)
resistor("R1", "10k", coupled, ads_ain0)
resistor("R2", "1Meg", ads_ain0, bias_mid)
resistor("R3", "1Meg", bias_mid, vref)
capacitor("C9", "100p", ads_ain0, vref)
diode("D1", vref, ads_ain0)
diode("D2", ads_ain0, vref)

# 1.60 V common-mode bias. C6 is the positive-to-ground electrolytic.
resistor("R4", "1k", vbus5, vref)
resistor("R5", "470", vref, gnd)
capacitor("C6", "47u", vref, gnd, electrolytic=True)
capacitor("C7", "100n", vref, gnd)
capacitor("C14", "1u", vbus5, gnd, electrolytic=True)
capacitor("C10", "100n", raw_3v3, gnd)

# Select the measured header logic voltage at assembly. Never bridge both
# sides. This solder bridge is PCB copper rather than a purchased component.
jp1 = part("Jumper", "SolderJumper_3_Open", "JP1", "SPI VDD SELECT",
           "Jumper:SolderJumper-3_P1.3mm_Open_Pad1.0x1.5mm")
jp1[1] += raw_3v3
jp1[2] += logic_vdd
jp1[3] += vbus5

# One 2N3904 per SPI wire translates in either 3.3 V or 5 V module mode.
# Each stage inverts; RP2350 GPIO INOVER/OUTOVER restores logical polarity.
# Baker clamp 1N4148 diodes limit saturation storage. SPI timing still
# requires a scope check with the actual module and wiring.
def translator(ref, base_ref, pull_ref, clamp_ref, source, output, pull_rail):
    q = part("Transistor_BJT", "2N3904", ref, "2N3904",
             "Package_TO_SOT_THT:TO-92_Inline")
    q[1] += gnd
    q[3] += output
    base = Net(f"{ref}_BASE")
    q[2] += base
    resistor(base_ref, "10k", source, base)
    resistor(pull_ref, "2.2k", pull_rail, output)
    diode(clamp_ref, base, output)


translator("Q1", "R6", "R12", "D3", mcu_sclk, ads_sclk, logic_vdd)
translator("Q2", "R7", "R13", "D4", mcu_mosi, ads_din, logic_vdd)
translator("Q3", "R8", "R14", "D5", mcu_cs, ads_cs, logic_vdd)
translator("Q4", "R9", "R15", "D6", mcu_pdwn, ads_pdwn, logic_vdd)
translator("Q5", "R10", "R16", "D7", ads_dout, mcu_miso, raw_3v3)
translator("Q6", "R11", "R17", "D8", ads_drdy, mcu_drdy, raw_3v3)

# During reset, SCLK and DIN idle low; CS and SYNC/PDWN idle high.
# Holding SYNC/PDWN low for the whole 200 ms blank would power down the ADC
# and impose an oscillator restart delay. Firmware discards the early data
# and issues only a short synchronization pulse when capture begins.
resistor("R18", "10k", raw_3v3, mcu_sclk)
resistor("R19", "10k", raw_3v3, mcu_mosi)
resistor("R20", "100k", mcu_pdwn, gnd)
resistor("R21", "100k", mcu_cs, gnd)
# ADS1256 DOUT/DRDY can float while powered down. Their pull-ups make
# the inverted MCU inputs idle high and avoid spurious DRDY assertions.
resistor("R22", "10k", logic_vdd, ads_dout)
resistor("R23", "10k", logic_vdd, ads_drdy)

u3 = part("Seeed_Studio_XIAO_Series", "XIAO-RP2350-SMD", "U3",
          "Seeed Studio XIAO RP2350",
          "Seeed_Studio_XIAO_Series:XIAO-RP2350-SMD")
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
# Other XIAO pads are intentionally unused in this logical netlist.

j2 = part("Connector_Generic", "Conn_01x08", "J2",
          "HILETGO ADS1256 LOGICAL DIGITAL WIRES")
for pin, net in enumerate((vbus5, gnd, ads_sclk, ads_din, ads_dout,
                           ads_cs, ads_drdy, ads_pdwn), start=1):
    j2[pin] += net
j3 = part("Connector_Generic", "Conn_01x08", "J3",
          "HILETGO ADS1256 LOGICAL ANALOG WIRES")
j3[1] += ads_ain0
j3[2] += vref
for pin in range(3, 9):
    j3[pin] += vref

for ref, net in (
    ("TP1", gnd), ("TP2", receiver_in), ("TP3", ads_ain0),
    ("TP4", vref), ("TP5", logic_vdd), ("TP6", vbus5),
    ("TP7", raw_3v3), ("TP8", ads_drdy),
):
    testpoint(ref, net)

netlist_path = HERE / "receiver.net"
generate_netlist(file_=str(netlist_path))
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
