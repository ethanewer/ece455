"""Make the flat poc/ modules importable from the tests directory."""
import os
import sys
from pathlib import Path

POC = Path(__file__).resolve().parent.parent / "poc"
if str(POC) not in sys.path:
    sys.path.insert(0, str(POC))
# skidl reads these at import time; set them before anything imports skidl
# (harmless on trees without KiCad).
_KICAD_SYMS = "/Applications/KiCad.app/Contents/SharedSupport/symbols"
for _v in ("KICAD_SYMBOL_DIR", "KICAD10_SYMBOL_DIR", "KICAD9_SYMBOL_DIR",
           "KICAD8_SYMBOL_DIR"):
    if Path(_KICAD_SYMS).exists():
        os.environ.setdefault(_v, _KICAD_SYMS)
