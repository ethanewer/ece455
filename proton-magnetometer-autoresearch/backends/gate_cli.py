"""Run one KiCad machine gate in a fresh interpreter (skidl keeps global
state, so tests invoke this per run).

Usage: python3 -m backends.gate_cli erc|drc|erc_negative <outdir>
Prints the gate exit code; non-zero = gate failed.
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "poc"))

from backends.kicad import (run_drc, run_erc, set_kicad_env,  # noqa: E402
                            write_pcb, write_schematic)


def afe_signal_path_spec():
    import circuit_spec as cs
    s = cs.afe_spec("INA828-class AFE (gate)",
                    e_amp=7e-9, i_amp=170e-15, tuned=False,
                    coil=dict(r_coil=120, l_coil="2m", n_turns=530,
                              radius_m=0.015, b_pol=0.02))
    # Standing gate circuit: the AFE signal path minus the AA cap Caa.
    # (The 13-part path routes, but including BOTH Raa and Caa trips a
    # non-deterministic junction bug in skidl 2.3.0's schematic router.)
    keep = {"Rcoil", "Lcoil", "Rnoise", "Rin", "E1", "R1", "R2", "C1", "C2",
            "R3", "Ebp", "Raa"}
    s["components"] = [c for c in s["components"] if c["name"] in keep]
    return s


def main():
    mode, outdir = sys.argv[1], Path(sys.argv[2])
    if mode == "erc":
        # skidl 2.3.0's schematic router has a non-deterministic junction
        # bug (coalesce KeyError) that strikes maybe 1 run in 3; retry a
        # couple of times before surfacing the failure.
        sch = None
        for _attempt in range(4):
            try:
                sch = write_schematic(afe_signal_path_spec(), str(outdir))
                break
            except RuntimeError:
                raise
            except Exception as e:            # router crash: retry
                if _attempt == 3:
                    raise
        rc, rep = run_erc(str(sch))
    elif mode == "drc":
        pcb = write_pcb(afe_signal_path_spec(), str(outdir))
        rc, rep = run_drc(str(pcb))
    elif mode == "erc_negative":
        set_kicad_env()
        from skidl import Circuit, Net, Part
        c = Circuit()
        r1 = Part("Device", "R", value="1k", circuit=c)
        r2 = Part("Device", "R", value="1k", circuit=c)
        bad = Part("Connector", "Conn_01x02_Pin", value="X", circuit=c)
        n1 = Net(name="a", circuit=c)
        n1 += r1.pins[0]
        n1 += r2.pins[0]
        outdir.mkdir(parents=True, exist_ok=True)
        c.generate_schematic(filepath=str(outdir), flatness=1.0)
        files = sorted(outdir.glob("*.kicad_sch"))
        if not files:
            print("no schematic for negative case")
            return 1
        rc, rep = run_erc(str(files[0]))
    else:
        raise SystemExit(f"unknown mode {mode}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
