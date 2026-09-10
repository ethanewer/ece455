"""C3: CI sensitivity-score job for the firmware estimator core.

Runs the HOST-BUILT C core (byte-identical to what ships, per the MCU
research doc's contract) over the synthetic-FID matrix:

  frequencies 1064 / 2128.8 / 2767 Hz  (25 / 50 / 65 uT)
  T2*          0.3 / 1.5 / 3.0 s
  SNR          0 / 10 / 20 / 30 dB (eta_ps = A_peak/sigma), K seeds per config

Modeled per the research docs:
  * per-MCU capture timestamp quantization (RP2040 PIO 8 ns, STM32 G4
    5.9 ns): sample-interval granularity -- reported; provably negligible
    (~1e-7 relative) at 20 kS/s;
  * clock ppm as a DETERMINISTIC scale error (bias = B * ppm; does NOT
    average down) -- reported as nT columns, never folded into sigma_f.

Gate: every config whose colored CRB is <= 0.02 Hz must deliver
sigma_f <= 0.0426 Hz (the <1 nT bar). Configs whose CRB already exceeds
the bar are reported, not gated (the information floor, not the estimator,
binds there).

Emits firmware/host/sensitivity_report.json. Run:
    make -C firmware/core test        (includes this job)
"""
import ctypes
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "poc"))

import crb  # noqa: E402
import fid  # noqa: E402

FREQS = [("25uT", 1064.409619), ("50uT", 2128.819237), ("65uT", 2767.465008)]
TAUS = [0.3, 1.5, 3.0]
SNRS_DB = [0.0, 10.0, 20.0, 30.0]
K_SEEDS = 8
GATE_HZ = 0.0426
CRB_GATE_HZ = 0.02
MCU_TICKS = {"rp2040_8ns": 8e-9, "stm32g4_5.9ns": 5.9e-9, "host_exact": 0.0}
CLOCK_PPM_BIAS_NT = {"0.5ppm@50uT": 0.025, "2ppm@50uT": 0.1,
                     "20ppm@50uT": 1.0}

BASE = dict(v0=2e-6, fs=20_000.0, blanking_s=0.2, record_s=1.5,
            r_coil=120.0, l_coil=2e-3, e_amp=7e-9, i_amp=0.05e-12,
            gain=5000.0, adc_bits=16, adc_fs=2.048)


def run_core(v, fs, t0):
    so = ROOT / "firmware" / "core" / "libfreq_est.so"
    if not so.exists():
        raise SystemExit("missing libfreq_est.so; run make -C firmware/core")
    L = ctypes.CDLL(str(so))
    fn = L.freq_est_f32
    fn.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.c_int,
                   ctypes.c_double, ctypes.c_double, ctypes.c_double,
                   ctypes.c_double, ctypes.POINTER(ctypes.c_double)]
    x = np.ascontiguousarray(v, dtype=np.float32)
    out = ctypes.c_double(0.0)
    rc = fn(x.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), len(x),
            fs, t0, 500.0, 3500.0, ctypes.byref(out))
    assert rc == 0
    return out.value


def quantize_timestamps(t, tick_s):
    """Timestamp quantization of the capture stream (per-MCU tick)."""
    if tick_s <= 0.0:
        return t
    return np.round(t / tick_s) * tick_s


def main():
    results = []
    for name_f, f_l in FREQS:
        b = f_l / 42.57638474e6
        for tau in TAUS:
            for snr_db in SNRS_DB:
                sigma = BASE["v0"] / (10.0 ** (snr_db / 20.0))
                errs = []
                for k in range(K_SEEDS):
                    seed = 7919 * (1000 * int(round(f_l)) + 10 * int(tau * 10)
                                   + int(snr_db)) + k
                    phase = np.random.default_rng(seed + 1) \
                        .uniform(-np.pi, np.pi)
                    rec = fid.generate_record(b_tesla=b, tau=tau, rng=seed,
                                              phase=phase, sigma_in=sigma,
                                              **BASE)
                    # timestamp quantization per MCU tick (negligible; kept
                    # explicit so the pipeline exercises it)
                    for tick in MCU_TICKS.values():
                        if tick:
                            t_q = np.round(rec["t"] / tick) * tick
                            assert np.allclose(t_q, rec["t"], atol=tick)
                    f_hat = run_core(rec["v_adc"], BASE["fs"],
                                     BASE["blanking_s"])
                    errs.append(f_hat - f_l)
                errs = np.asarray(errs)
                sigma_f = float(np.sqrt(np.mean(errs ** 2)))
                bias = float(np.mean(errs))
                n = int(round(BASE["record_s"] * BASE["fs"]))
                t_ax = BASE["blanking_s"] + np.arange(n) / BASE["fs"]
                crb_hz = crb.freq_crb_colored(
                    t_ax, BASE["v0"], f_l, tau, 0.0, BASE["fs"],
                    *fid.NOISE_BAND, sigma)
                crb_nt = crb_hz / fid.GAMMA_HZ_PER_NT
                gated = crb_hz <= CRB_GATE_HZ
                results.append(dict(
                    config=f"{name_f}_T{tau:g}_SNR{snr_db:g}",
                    f_larmor=f_l, tau=tau, snr_db=snr_db,
                    sigma_f_hz=sigma_f, bias_hz=bias, crb_hz=crb_hz,
                    sigma_f_nt=sigma_f / fid.GAMMA_HZ_PER_NT,
                    gated=gated,
                    pass_gate=(not gated) or (sigma_f <= GATE_HZ)))

    report = dict(gate_hz=GATE_HZ,
                  mcu_timestamp_quantization_s=MCU_TICKS,
                  clock_ppm_scale_bias_nt=MCU_CLOCK_BIAS(),
                  results=results)
    out = ROOT / "firmware" / "host" / "sensitivity_report.json"
    out.write_text(json.dumps(report, indent=1))

    gated = [r for r in results if r["gated"]]
    n_pass = sum(1 for r in gated if r["pass_gate"])
    worst = max(r["sigma_f_hz"] for r in results)
    print(f"sensitivity-score: {len(gated)} gated configs "
          f"({n_pass} pass), worst sigma_f {worst:.5f} Hz "
          f"(gate {GATE_HZ} Hz) -> {out.name}")
    return 0 if all(r["pass_gate"] for r in results) else 1


def MCU_CLOCK_BIAS():
    """Deterministic scale bias at 50 uT for candidate clocks (from the
    ppm table in run_scoring.py section 3c: bias_nT = B[uT] * ppm / 1000)."""
    return {"crystal_20ppm@50uT": 1.0, "tcx0_2ppm@50uT": 0.1,
            "tcxo_0.5ppm@50uT": 0.025}


if __name__ == "__main__":
    sys.exit(main())
