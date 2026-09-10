"""A4 machine-gate test: one INA828-class AFE passes ERC + DRC with exit
code 0 from a clean tree, and the gates are ABLE to fail.

Each gate runs in a fresh interpreter (subprocess) because skidl keeps
global state across generate calls.

Run:  python3 -m pytest tests/test_kicad_gate.py
      (requires KiCad 10 + kicad-cli + skidl; skips if unavailable)
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PY = sys.executable
HAVE_SKIDL = True
try:
    import skidl  # noqa: F401
except ImportError:
    HAVE_SKIDL = False

HAVE_KICAD = shutil.which("kicad-cli") is not None or \
    Path("/Applications/KiCad.app/Contents/MacOS/kicad-cli").exists()

pytestmark = pytest.mark.skipif(
    not (HAVE_KICAD and HAVE_SKIDL),
    reason="KiCad 10 / skidl not available on this tree")


def run_gate(mode: str, outdir: Path) -> int:
    proc = subprocess.run(
        [PY, "-m", "backends.gate_cli", mode, str(outdir)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    if proc.returncode not in (0, 5):
        raise RuntimeError("gate_cli failed:\n%s\n%s"
                           % (proc.stdout[-1500:], proc.stderr[-1500:]))
    return proc.returncode


def test_ina828_class_afe_passes_erc(tmp_path):
    assert run_gate("erc", tmp_path) == 0


def test_ina828_class_afe_passes_drc(tmp_path):
    assert run_gate("drc", tmp_path) == 0


def test_erc_gate_can_fail(tmp_path):
    """The gate must be ABLE to fail: a dangling element in an otherwise
    connected 3-part circuit must trip kicad-cli ERC (exit != 0)."""
    assert run_gate("erc_negative", tmp_path) != 0
