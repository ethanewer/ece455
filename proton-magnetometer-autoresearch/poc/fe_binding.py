"""ctypes binding to the C estimator core (firmware/core/).

REDESIGN.md step 1: the C core is the SINGLE estimator implementation in
every scoring path -- byte-identical to what ships to the MCU. Python
modules import `estimate()` from here; nothing in the repository may
re-implement an estimator in Python for scoring.

Estimator variants (all float32 ADC-domain samples in, Hz out):

    "zoom"       freq_est_f32    exp-weighted zoom/matched filter (baseline)
    "fft"        fft_est_f32     zero-padded FFT peak + log-parabolic refine
    "zc"         zc_est_f32      interpolated crossings + WLS mean period
                                 (ruled out at FID SNRs; kept so the
                                 ruling-out is an E2E result)
    "zoom_fixed" freq_est_fixed  Q31 fixed-point zoom (M0+ target build)

A non-zero return code from the core maps to NaN (gross-error semantics:
the estimator failed to produce an estimate on that record).
"""
import ctypes
import hashlib
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "firmware" / "core"

ESTIMATORS = ("zoom", "fft", "zc")           # legal candidate variants
F_LO, F_HI = 500.0, 3500.0                   # the AFE band

_libs = {}


def _build():
    subprocess.run(["make", "-C", str(CORE)], check=True,
                   capture_output=True)


def _lib(mode: str):
    """mode: "float" -> libfreq_est.so, "fixed" -> libfreq_est_fixed.so."""
    if mode not in _libs:
        so = CORE / ("libfreq_est.so" if mode == "float"
                     else "libfreq_est_fixed.so")
        if not so.exists():
            _build()
        _libs[mode] = ctypes.CDLL(str(so))
    return _libs[mode]


def firmware_sha256() -> str:
    """Hash of the estimator sources -- joins every score card's provenance
    (REDESIGN.md: the card proves which estimator build produced J)."""
    h = hashlib.sha256()
    for name in ("freq_est.h", "freq_est.c", "fft_est.c", "zc_est.c"):
        h.update((CORE / name).read_bytes())
    return h.hexdigest()[:16]


def _f32_fn(lib, name):
    fn = getattr(lib, name)
    fn.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.c_int,
                   ctypes.c_double, ctypes.c_double, ctypes.c_double,
                   ctypes.c_double, ctypes.POINTER(ctypes.c_double)]
    return fn


def _fixed_fn(lib):
    fn = lib.freq_est_fixed
    fn.argtypes = [ctypes.POINTER(ctypes.c_int32), ctypes.c_int,
                   ctypes.c_double, ctypes.c_double, ctypes.c_double,
                   ctypes.c_double, ctypes.POINTER(ctypes.c_double)]
    return fn


def estimate(name: str, v: np.ndarray, fs: float, t0: float,
             f_lo: float = F_LO, f_hi: float = F_HI) -> float:
    """Run one ADC-domain record through the named C estimator variant.

    v: ADC-domain samples (float; front-end gain and quantization already
    included). t0: time of v[0] since FID start [s] (the blanking time).
    Returns the frequency estimate [Hz], or NaN when the core returns an
    error (gross-error semantics).
    """
    out = ctypes.c_double(0.0)
    if name == "zoom_fixed":
        fn = _fixed_fn(_lib("fixed"))
        peak = float(np.max(np.abs(v)))
        q = np.round(v / peak * (2.0**31 - 1)).astype(np.int32)
        x = np.ascontiguousarray(q)
        rc = fn(x.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
                len(x), fs, t0, f_lo, f_hi, ctypes.byref(out))
    else:
        c_name = {"zoom": "freq_est_f32",
                  "fft": "fft_est_f32",
                  "zc": "zc_est_f32"}[name]
        fn = _f32_fn(_lib("float"), c_name)
        x = np.ascontiguousarray(v, dtype=np.float32)
        rc = fn(x.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                len(x), fs, t0, f_lo, f_hi, ctypes.byref(out))
    return out.value if rc == 0 else float("nan")
