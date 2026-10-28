"""One-off: which R1 values keep every requirement at every corner."""
import sys, tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from receiver_design import requirements as r

BASE = Path("receiver_design/spice/receiver.cir").read_text()

def run(rg):
    d = Path(tempfile.mkdtemp()) / "receiver.cir"
    d.write_text(BASE.replace("R1 rg_a rg_b 100", f"R1 rg_a rg_b {rg:g}"))
    res = r.check_requirements(d)
    return rg, dict(
        gain=1 + 9900 / rg,
        noise=max(x.noise_max_v_rt_hz for x in res) * 1e9,
        mains=min(x.interference[0][0] for x in res) * 1e3,
        hf=min(x.interference[1][0] for x in res) * 1e3,
        alias=min(x.alias_rejection_db for x in res),
        zin=min(x.zin_min_ohm for x in res) / 1e6,
        gain_ain0=min(x.gain_min for x in res),
        fails=sorted({f.split(" ")[0] for x in res for f in x.failures}),
    )

if __name__ == "__main__":
    values = [float(v) for v in sys.argv[1:]]
    with ProcessPoolExecutor(8) as pool:
        for rg, m in pool.map(run, values):
            print(f"R1 {rg:7g} G {m['gain']:7.1f} AIN0 min {m['gain_ain0']:6.1f}  noise {m['noise']:5.2f}  "
                  f"mains {m['mains']:6.1f} mV  hf {m['hf']:6.1f} mV  alias {m['alias']:5.1f} dB  "
                  f"zin {m['zin']:4.2f}  {'PASS' if not m['fails'] else 'FAIL ' + ','.join(m['fails'])}")
