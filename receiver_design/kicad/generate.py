#!/usr/bin/env python3
"""Generate fixed connectivity for the AD8421 module receiver.

This is one circuit, not a search or topology generator. It mirrors
spice/receiver.cir. The purchased modules' physical header order and the
ADS1256 SPI voltage must be checked before layout.
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


def part(lib, name, ref, value=None, footprint=None):
    return Part(lib, name, ref=ref, tag=ref, value=value or name,
                footprint=footprint)


def resistor(ref, value, left, right):
    r = part("Device", "R", ref, value, AXIAL)
    r[1] += left
    r[2] += right
    return r


def capacitor(ref, value, left, right):
    c = part("Device", "C", ref, value, DISC)
    c[1] += left
    c[2] += right
    return c


def bjt(ref, part_name, value, emitter, base, collector):
    """Kit TO-92 transistor; KiCad symbols number pins 1/2/3 as E/B/C."""
    q = part("Transistor_BJT", part_name, ref, value,
             "Package_TO_SOT_THT:TO-92_Inline")
    q[1] += emitter
    q[2] += base
    q[3] += collector
    return q


def battery(ref, positive, negative):
    b = part("Device", "Battery_Cell", ref, "9V ALKALINE")
    b[1] += positive
    b[2] += negative
    return b


def wires(ref, value, nets):
    """Logical wire interface to a purchased module or cable."""
    j = part("Connector_Generic", f"Conn_01x{len(nets):02d}", ref, value)
    for pin, net in enumerate(nets, start=1):
        j[pin] += net
    return j


def testpoint(ref, net):
    tp = part("Connector", "TestPoint", ref, net.name,
              "TestPoint:TestPoint_Plated_Hole_D2.0mm")
    tp[1] += net


gnd = Net("GND")
vbus5 = Net("USB_VBUS_5V")
bat_pos = Net("BAT_POS_9V")
bat_neg = Net("BAT_NEG_9V")
receiver_in = Net("RECEIVER_IN")
rg_a = Net("AD8421_RG_A")
rg_b = Net("AD8421_RG_B")
amp_out = Net("AD8421_OUT")
aaf_mid = Net("AAF_MID")
ain0 = Net("ADS1256_AIN0")

ads_sclk = Net("SPI0_SCLK_D8_GPIO2")
ads_din = Net("SPI0_MOSI_D10_GPIO3_ADS_DIN")
ads_dout = Net("SPI0_MISO_D9_GPIO4_ADS_DOUT")
ads_cs = Net("ADS_CS_D3_GPIO5")
ads_drdy = Net("ADS_DRDY_D2_GPIO28")
ads_pdwn = Net("ADS_PDWN_D4_GPIO6")

# Logical receiver boundary. The sensor LC tank and damping circuit stay
# outside J1. J1-J5 are wiring interfaces, not purchased connectors.
wires("J1", "EXTERNAL SENSOR WIRE INTERFACE", (receiver_in, gnd))

# Low-leakage input clamps: diode-connected 2N3904s, collector tied to base.
bjt("Q1", "2N3904", "2N3904", gnd, receiver_in, receiver_in)
bjt("Q2", "2N3904", "2N3904", receiver_in, gnd, gnd)

# AD8421 module (MOD2): IN+, IN- (jumpered to GND on the module), the RG
# pads, OUT (the SMA jack), and the screw-terminal supply. R1 fits the
# module's GAIN footprint: G = 1 + 9.9k/R1 = 100. The module's BIAS
# trimmer drives REF on the module itself.
wires("J4", "AD8421 MODULE LOGICAL WIRES",
      (receiver_in, gnd, rg_a, rg_b, amp_out, bat_pos, gnd, bat_neg))
resistor("R1", "100", rg_a, rg_b)

# Two 9 V batteries; their midpoint is the module and system ground.
battery("BT1", bat_pos, gnd)
battery("BT2", gnd, bat_neg)

# SMA-to-Dupont cable (W1) from the module's OUT jack to the filter.
wires("J5", "SMA TO DUPONT CABLE", (amp_out, gnd))

# Two-section RC anti-aliasing filter at ADS1256 AIN0.
resistor("R2", "1k", amp_out, aaf_mid)
capacitor("C1", "22n", aaf_mid, gnd)
resistor("R3", "10k", aaf_mid, ain0)
capacitor("C2", "2.2n", ain0, gnd)

# The ADS1256 SPI inputs tolerate 5.25 V and its outputs swing only to
# DVDD (at most 3.6 V), so the 3.3 V XIAO connects directly. Verify the
# module's DRDY high level before connecting.
u1 = part("Seeed_Studio_XIAO_Series", "XIAO-RP2350-SMD", "U1",
          "Seeed Studio XIAO RP2350",
          "Seeed_Studio_XIAO_Series:XIAO-RP2350-SMD")
u1[3] += ads_drdy    # D2 / GPIO28
u1[4] += ads_cs      # D3 / GPIO5
u1[5] += ads_pdwn    # D4 / GPIO6
u1[9] += ads_sclk    # D8 / GPIO2
u1[10] += ads_dout   # D9 / GPIO4
u1[11] += ads_din    # D10 / GPIO3
u1[14] += vbus5
for pin in (13, 26, 30):
    u1[pin] += gnd
# Other XIAO pads are intentionally unused in this logical netlist.

wires("J2", "HILETGO ADS1256 LOGICAL DIGITAL WIRES",
      (vbus5, gnd, ads_sclk, ads_din, ads_dout, ads_cs, ads_drdy, ads_pdwn))
wires("J3", "HILETGO ADS1256 LOGICAL ANALOG WIRES", (ain0, gnd))

for ref, net in (
    ("TP1", gnd), ("TP2", receiver_in), ("TP3", amp_out), ("TP4", ain0),
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
