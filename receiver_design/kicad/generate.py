#!/usr/bin/env python3
"""Generate fixed connectivity for the discrete band-pass receiver.

This is one circuit, not a search or topology generator. It mirrors
spice/receiver.cir. The purchased module's physical header order and SPI
voltage must be checked before layout.
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


def bjt(ref, part_name, value, emitter, base, collector):
    """Kit TO-92 transistor; KiCad symbols number pins 1/2/3 as E/B/C."""
    q = part("Transistor_BJT", part_name, ref, value,
             "Package_TO_SOT_THT:TO-92_Inline")
    q[1] += emitter
    q[2] += base
    q[3] += collector
    return q


def testpoint(ref, net):
    tp = part("Connector", "TestPoint", ref, net.name,
              "TestPoint:TestPoint_Plated_Hole_D2.0mm")
    tp[1] += net


gnd = Net("GND")
vbus5 = Net("USB_VBUS_5V")
va = Net("ANALOG_VA_4V8")
receiver_in = Net("RECEIVER_IN")
q1_base = Net("Q1_BASE")
q1_col = Net("Q1_COLLECTOR")
q1_emit = Net("Q1_EMITTER_FEEDBACK")
stage1_ac = Net("STAGE1_AC_RETURN")
q2_col = Net("Q2_COLLECTOR")
stage1_out = Net("STAGE1_OUT")
hp_a = Net("HP_A")
hp_b = Net("HP_B")
filt = Net("HP_OUT")
lp_a = Net("LP_A")
lp_b = Net("LP_B")
lpo = Net("LP_OUT")
q4_emit = Net("Q4_EMITTER")
out = Net("ADS1256_AIN0_OUT")
boot = Net("BOOTSTRAP")
bias = Net("BIAS_AIN1_1V6")

ads_sclk = Net("SPI0_SCLK_D8_GPIO2")
ads_din = Net("SPI0_MOSI_D10_GPIO3_ADS_DIN")
ads_dout = Net("SPI0_MISO_D9_GPIO4_ADS_DOUT")
ads_cs = Net("ADS_CS_D3_GPIO5")
ads_drdy = Net("ADS_DRDY_D2_GPIO28")
ads_pdwn = Net("ADS_PDWN_D4_GPIO6")

# Logical receiver boundary. The sensor LC tank and damping circuit stay
# outside J1. J1/J2/J3 are wiring interfaces, not purchased connectors.
j1 = part("Connector_Generic", "Conn_01x02", "J1",
          "EXTERNAL SENSOR WIRE INTERFACE")
j1[1] += receiver_in
j1[2] += gnd

# Low-leakage input clamps: diode-connected 2N3904s, collector tied to base.
bjt("Q5", "2N3904", "2N3904", gnd, receiver_in, receiver_in)
bjt("Q6", "2N3904", "2N3904", receiver_in, gnd, gnd)

# Stage 1: low-noise series-feedback triple, AC gain 1 + R7/R8.
capacitor("C1", "100n", receiver_in, q1_base)
bjt("Q1", "2N3904", "2N3904", q1_emit, q1_base, q1_col)
resistor("R4", "24.9k", va, q1_col)
bjt("Q2", "2N3906", "2N3906", va, q1_col, q2_col)
resistor("R5", "47k", q2_col, gnd)
bjt("Q3", "2N3904", "2N3904", stage1_out, q2_col, va)
resistor("R6", "2.2k", stage1_out, gnd)
resistor("R7", "5.1k", stage1_out, q1_emit)
resistor("R8", "150", q1_emit, stage1_ac)
capacitor("C4", "1u", stage1_ac, gnd, electrolytic=True)

# Fourth-order band-pass between the stages: Sallen-Key high-pass with the
# Q7 follower, then Sallen-Key low-pass with the Q8 PNP follower.
capacitor("C8", "6.8n", stage1_out, hp_a)
capacitor("C9", "6.8n", hp_a, hp_b)
resistor("R12", "6.8k", hp_a, filt)
resistor("R13", "47k", hp_b, bias)
bjt("Q7", "2N3904", "2N3904", filt, hp_b, va)
resistor("R14", "47k", filt, gnd)
resistor("R15", "20k", filt, lp_a)
resistor("R16", "20k", lp_a, lp_b)
capacitor("C10", "6.8n", lp_a, lpo)
capacitor("C11", "1n", lp_b, gnd)
bjt("Q8", "2N3906", "2N3906", lpo, lp_b, gnd)
resistor("R17", "33k", va, lpo)

# Stage 2: common emitter; its collector drives ADS1256 AIN0 directly.
bjt("Q4", "2N3904", "2N3904", q4_emit, lpo, out)
resistor("R9", "8.2k", q4_emit, gnd)
capacitor("C5", "1u", q4_emit, gnd, electrolytic=True)
resistor("R10", "20k", va, out)
capacitor("C7", "2.2n", out, gnd)

# Bootstrapped bias and DC loop. BIAS is also ADS1256 AIN1.
resistor("R1", "470k", q1_base, boot)
capacitor("C2", "100n", boot, q1_emit)
resistor("R2", "100k", boot, bias)
capacitor("C3", "100n", bias, gnd)
resistor("R3", "1Meg", out, bias)

# Analog rail filtered from USB 5 V.
resistor("R11", "470", vbus5, va)
capacitor("C6", "470u", va, gnd, electrolytic=True)

# The ADS1256 SPI inputs tolerate 5.25 V and its outputs swing only to
# DVDD (at most 3.6 V), so the 3.3 V XIAO connects directly. Verify the
# module's DRDY high level before connecting.
u3 = part("Seeed_Studio_XIAO_Series", "XIAO-RP2350-SMD", "U3",
          "Seeed Studio XIAO RP2350",
          "Seeed_Studio_XIAO_Series:XIAO-RP2350-SMD")
u3[3] += ads_drdy    # D2 / GPIO28
u3[4] += ads_cs      # D3 / GPIO5
u3[5] += ads_pdwn    # D4 / GPIO6
u3[9] += ads_sclk    # D8 / GPIO2
u3[10] += ads_dout   # D9 / GPIO4
u3[11] += ads_din    # D10 / GPIO3
u3[14] += vbus5
for pin in (13, 26, 30):
    u3[pin] += gnd
# Other XIAO pads are intentionally unused in this logical netlist.

j2 = part("Connector_Generic", "Conn_01x08", "J2",
          "HILETGO ADS1256 LOGICAL DIGITAL WIRES")
for pin, net in enumerate((vbus5, gnd, ads_sclk, ads_din, ads_dout,
                           ads_cs, ads_drdy, ads_pdwn), start=1):
    j2[pin] += net
j3 = part("Connector_Generic", "Conn_01x02", "J3",
          "HILETGO ADS1256 LOGICAL ANALOG WIRES")
j3[1] += out
j3[2] += bias

for ref, net in (
    ("TP1", gnd), ("TP2", receiver_in), ("TP3", out), ("TP4", bias),
    ("TP5", va), ("TP6", stage1_out), ("TP7", q1_emit), ("TP8", lpo),
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
