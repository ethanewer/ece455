"""Make the flat poc/ modules importable from the tests directory."""
import sys
from pathlib import Path

POC = Path(__file__).resolve().parent.parent / "poc"
if str(POC) not in sys.path:
    sys.path.insert(0, str(POC))
