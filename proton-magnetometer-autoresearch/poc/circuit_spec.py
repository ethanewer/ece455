"""Machine-first circuit representation demo: JSON spec -> ngspice -> nT score.

The auto-research loop needs a circuit format that is (a) trivially emitted
and diffed by code, (b) simulatable end-to-end, and (c) compilable to
buildable KiCad artifacts (that leg is SKiDL's job in the real pipeline --
same component/net graph, different backend). This demo implements (a)+(b):

  declarative spec --emit--> ngspice netlist --batch--> .ac/.noise results
        --sigma_in, gain--> synthetic FID records --MC--> RMS nT error

Amplifier voltage noise is modeled the ngspice-native way: a physical
resistor of value R = e_n^2/(4kT) in series with the input of a noiseless
behavioral gain block produces exactly the datasheet noise density.
(Behavioral sources themselves are noiseless, and vendor PSpice macromodels
often lose their noise sections when translated to ngspice -- the physical
resistor is bulletproof.)

Two candidates are scored head-to-head -- an INA828-class in-amp
(7 nV/rtHz) vs a TL072-class op-amp (18 nV/rtHz), the exact mistake the
week-2 report said the Larmor Lads team made -- to show the loop
discriminates designs the way a bench would.

Run:  python3 circuit_spec.py     (requires ngspice on PATH)
"""
import re
import subprocess
from pathlib import Path

import numpy as np

import fid
from estimators import nlls_fit

K_B = 1.380649e-23
T0 = 300.0
N_MC = 200
WORKDIR = Path("/tmp/poc_circuits")


def noise_resistance(e_n: float) -> float:
    """Resistor whose Johnson noise equals an amplifier noise density e_n."""
    return e_n**2 / (4.0 * K_B * T0)


def afe_spec(e_amp: float) -> dict:
    """FID source -> coil (R+L) -> amp-noise resistor -> ideal in-amp (x100)
    -> anti-alias RC -> ideal x10 stage -> adc.

    The tuned-input variant (parallel C across the coil, resonant step-up)
    is deliberately left out: choosing between untuned and tuned inputs --
    and their ring-down dead-time cost -- is exactly the kind of experiment
    the auto-research loop should run, not something hard-coded here.
    """
    en_r = noise_resistance(e_amp)
    return {
        "title": f"PPM AFE untuned (e_amp={e_amp*1e9:.0f} nV/rtHz)",
        "params": {"RCOIL": "120", "LCOIL": "2m", "ENR": f"{en_r:.1f}"},
        "components": [
            {"name": "V1", "type": "V", "nodes": ["fid", "0"],
             "value": "DC 0 AC 1"},
            {"name": "Rcoil", "type": "R", "nodes": ["fid", "nc"],
             "value": "{RCOIL}"},
            {"name": "Lcoil", "type": "L", "nodes": ["nc", "nin"],
             "value": "{LCOIL}"},
            {"name": "Rnoise", "type": "R", "nodes": ["nin", "nq"],
             "value": "{ENR}"},
            {"name": "E1", "type": "E", "nodes": ["st1", "0"],
             "value": "nq 0 100"},
            {"name": "Raa", "type": "R", "nodes": ["st1", "naa"],
             "value": "1k"},
            {"name": "Caa", "type": "C", "nodes": ["naa", "0"],
             "value": "22n"},
            {"name": "E2", "type": "E", "nodes": ["adc", "0"],
             "value": "naa 0 10"},
        ],
        "control": [
            "ac dec 100 100 10k",
            "print vm(adc)",
            "noise v(adc) V1 dec 100 500 3500 1",
            "print inoise_total onoise_total",
        ],
    }


def emit_netlist(spec: dict) -> str:
    lines = [spec["title"]]
    for name, val in spec["params"].items():
        lines.append(f".param {name}={val}")
    for c in spec["components"]:
        lines.append(f"{c['name']} {' '.join(c['nodes'])} {c['value']}")
    lines.append(".control")
    lines += spec["control"]
    lines.append("endc")
    lines.append(".end")
    return "\n".join(lines) + "\n"


def run_ngspice(netlist: str) -> str:
    WORKDIR.mkdir(exist_ok=True)
    nl = WORKDIR / "afe.cir"
    nl.write_text(netlist)
    proc = subprocess.run(["ngspice", "-b", str(nl)],
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"ngspice failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
    return proc.stdout


def parse_results(stdout: str, f_target: float = 2128.9) -> dict:
    inoise = re.search(r"inoise_total\s*=\s*([0-9.eE+-]+)", stdout)
    onoise = re.search(r"onoise_total\s*=\s*([0-9.eE+-]+)", stdout)
    gain, f_best = float("nan"), float("inf")
    for line in stdout.splitlines():
        cols = line.split()
        # .control `print vm(adc)` tables are rows of (index, freq, mag)
        if len(cols) == 3:
            try:
                f, mag = float(cols[1]), float(cols[2])
            except ValueError:
                continue
            if abs(f - f_target) < abs(f_best - f_target):
                f_best, gain = f, mag
    return {"inoise_total": float(inoise.group(1)) if inoise else None,
            "onoise_total": float(onoise.group(1)) if onoise else None,
            "gain_at_fl": gain}


def score(spec: dict, v0: float = 2e-6, tau: float = 1.5,
          blanking_s: float = 0.2, record_s: float = 1.5) -> dict:
    """End-to-end: netlist -> ngspice -> MC estimator -> RMS nT error."""
    res = parse_results(run_ngspice(emit_netlist(spec)))
    sigma_in = res["inoise_total"]
    errs = []
    for i in range(N_MC):
        rec = fid.generate_record(v0=v0, tau=tau, sigma_in=sigma_in,
                                  gain=res["gain_at_fl"],
                                  blanking_s=blanking_s, record_s=record_s,
                                  rng=i)
        errs.append(nlls_fit(rec) - rec["f_larmor"])
    rms_nt = float(np.sqrt(np.mean(np.square(errs)))) / 42.577478e-3
    snr_db = 20 * np.log10((v0 / np.sqrt(2)) / sigma_in)
    return {"spec": spec["title"], "sigma_in_uV": sigma_in * 1e6,
            "gain": res["gain_at_fl"], "snr_db": snr_db, "rms_nt": rms_nt}


def main():
    candidates = [
        ("INA828-class in-amp (7 nV/rtHz)", 7e-9),
        ("TL072-class op-amp  (18 nV/rtHz)", 18e-9),
    ]
    print(f"Scoring AFE candidates from SPICE (N_MC={N_MC}, V0=2 uV, "
          f"T2*=1.5 s, blanking 200 ms, 1.5 s record)\n")
    print(f"{'candidate':<34} {'sigma_in':>10} {'SNR':>8} {'RMS err':>10}")
    for label, e_amp in candidates:
        spec = afe_spec(e_amp)
        r = score(spec)
        print(f"{r['spec']:<36} {r['sigma_in_uV']:>8.3f}uV"
              f" {r['snr_db']:>7.1f}dB {r['rms_nt']:>9.4f}nT")


if __name__ == "__main__":
    main()
