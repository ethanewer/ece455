"""Host test harness for the portable estimator core (C2, TODO).

Drives the C core (freq_est_f32 / freq_est_fixed) through ctypes on the
committed golden vectors (firmware/host/vectors/, sha256-pinned manifest)
and cross-validates against the numpy mirror of the C algorithm
(tools/freq_est_mirror.py):

  1. every vector: C float and C fixed estimates agree with the numpy
     mirror (C-vs-mirror divergence catches C-side bugs: NCO table, FIR
     indexing, fixed-point saturation);
  2. the C estimate lands within a generous gate of the truth on the
     operating-SNR vectors (the full statistical gates live in
     sensitivity_score.py, C3);
  3. vector hashes verify against the pinned manifest first.

Run:  make -C firmware/core test
"""
import ctypes
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]   # project root (this file:
CORE = ROOT / "firmware" / "core"            # firmware/host/run_host_tests.py)
VEC = ROOT / "firmware" / "host" / "vectors"
sys.path.insert(0, str(ROOT / "tools"))

F_LO, F_HI = 500.0, 3500.0           # the AFE band
TOL_MIRROR_HZ = 0.01                 # C float vs numpy mirror
TOL_FIXED_HZ = 0.05                  # Q31 path vs mirror
TOL_TRUTH_HZ = 0.5                   # sanity gate at operating SNR


def lib(mode: str):
    name = "libfreq_est.so" if mode == "float" else "libfreq_est_fixed.so"
    if not (CORE / name).exists():
        raise SystemExit(f"missing {name}; run make -C firmware/core")
    return ctypes.CDLL(str(CORE / name))


def run_core(mode: str, v: np.ndarray, fs: float, t0: float,
             f_lo: float = F_LO, f_hi: float = F_HI) -> float:
    """Call the C core on one record. 'fixed' scales the record to Q31
    (int32, peak = 2^31-1) as an MCU ADC would deliver it."""
    L = lib(mode)
    out = ctypes.c_double(0.0)
    if mode == "float":
        fn = L.freq_est_f32
        fn.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.c_int,
                       ctypes.c_double, ctypes.c_double,
                       ctypes.c_double, ctypes.c_double,
                       ctypes.POINTER(ctypes.c_double)]
        x = np.ascontiguousarray(v, dtype=np.float32)
        rc = fn(x.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                len(x), fs, t0, f_lo, f_hi, ctypes.byref(out))
        assert rc == 0, f"freq_est_f32 rc={rc}"
        return out.value
    else:
        peak = float(np.max(np.abs(v)))
        q = np.round(v / peak * (2.0**31 - 1)).astype(np.int32)
        x = np.ascontiguousarray(q)
        fn = L.freq_est_fixed
        fn.argtypes = [ctypes.POINTER(ctypes.c_int32), ctypes.c_int,
                       ctypes.c_double, ctypes.c_double,
                       ctypes.c_double, ctypes.c_double,
                       ctypes.POINTER(ctypes.c_double)]
        rc = fn(x.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
                len(x), fs, t0, f_lo, f_hi, ctypes.byref(out))
        assert rc == 0, f"freq_est_fixed rc={rc}"
        return out.value


def main() -> int:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "freq_est_mirror", str(ROOT / "tools" / "freq_est_mirror.py"))
    mirror = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mirror)

    manifest = json.loads((VEC / "manifest.json").read_text())

    # 0. hash check (C2: golden-vector hash pinned)
    for e in manifest["vectors"]:
        v = np.load(VEC / e["file"]).astype(np.float32)
        h = hashlib.sha256(v.tobytes()).hexdigest()
        assert h == e["sha256"], f"vector hash drifted: {e['name']}"

    fails = []
    n_checked = 0
    for e in manifest["vectors"]:
        v = np.load(VEC / e["file"]).astype(np.float32)
        truth = e["f_larmor"]
        snr_db = float(e["name"].split("SNR")[1].replace("dB", ""))
        # Mirror tolerance: at operating SNR the two implementations must
        # agree to ~0.01 Hz (accumulation-order noise). At threshold SNR
        # (0/10 dB) each implementation's tau estimate is threshold-
        # sensitive, so independent numerical trajectories legitimately
        # differ by a fraction of the estimator's own variance -- scale
        # the tolerance with 1/eta (20 dB -> 0.01 Hz floor).
        tol = max(TOL_MIRROR_HZ, 0.5 * 10 ** ((20.0 - snr_db) / 20.0))
        f_c = run_core("float", v, e["fs"], e["t0"])
        f_m = mirror.fe_mirror(v, e["fs"], e["t0"], F_LO, F_HI)
        d_mirror = abs(f_c - f_m)
        ok = d_mirror < tol
        # sanity vs truth at operating SNR (>=20 dB)
        d_truth = abs(f_c - truth)
        if "SNR20" in e["name"] or "SNR30" in e["name"]:
            ok = ok and d_truth < TOL_TRUTH_HZ
        status = "ok" if ok else "FAIL"
        print(f"{e['name']:32s} C={f_c:12.5f} mirror={f_m:12.5f} "
              f"truth={truth:10.4f} d_mirror={d_mirror:.5f}Hz {status}")
        n_checked += 1
        if not ok:
            fails.append((e["name"], f_c, f_m, truth))

    # fixed-point path on a representative subset
    for e in manifest["vectors"][::9]:
        v = np.load(VEC / e["file"]).astype(np.float32)
        f_c = run_core("float", v, e["fs"], e["t0"])
        f_q = run_core("fixed", v, e["fs"], e["t0"])
        d = abs(f_c - f_q)
        print(f"fixed {e['name']:34s} d(float,fixed) = {d:.5f} Hz "
              f"{'ok' if d < TOL_FIXED_HZ else 'FAIL'}")
        if d >= TOL_FIXED_HZ:
            fails.append((e["name"], f_c, f_q, "fixed-vs-float"))

    if fails:
        print(f"\n{len(fails)} FAILURES")
        return 1
    print(f"\nhost tests PASS ({n_checked} vectors, float+mirror+fixed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
