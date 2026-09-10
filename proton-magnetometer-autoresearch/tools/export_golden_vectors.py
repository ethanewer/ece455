"""Export golden FID vectors for the firmware host tests (C2).

Generates records with fid.generate_record at FIXED seeds over the C3
sensitivity matrix, saves each record's ADC samples (.npy float32) plus a
manifest with sha256 hashes -- the hash is pinned in git so the C core is
always validated against the same vectors (D2's "golden-vector hash
pinned"; TODO C2).

Usage:
    python3 tools/export_golden_vectors.py            # regenerate + hash
    python3 tools/export_golden_vectors.py --check    # verify hashes only
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
VEC = ROOT / "firmware" / "host" / "vectors"

# The C3 sensitivity matrix (research-frequency-estimation.md + mcu doc):
# fields 1064/2128.8/2767 Hz x T2* {0.3, 1.5, 3.0} s x SNR {0, 10, 20, 30} dB
FREQS = [1064.409619, 2128.819237, 2767.465008]      # 25 / 50 / 65 uT
TAUS = [0.3, 1.5, 3.0]
SNRS_DB = [0.0, 10.0, 20.0, 30.0]

BASE = dict(v0=2e-6, fs=20_000.0, blanking_s=0.2, record_s=1.5,
            r_coil=120.0, l_coil=2e-3, e_amp=7e-9, i_amp=0.05e-12,
            gain=5000.0, adc_bits=16, adc_fs=2.048)


def vectors():
    """[(name, samples_f32, meta)] with deterministic seeds."""
    sys.path.insert(0, str(ROOT / "poc"))
    import fid

    out = []
    for i_f, f_l in enumerate(FREQS):
        b = f_l / (fid.GAMMA_HZ_PER_T)        # b_tesla giving this f_L
        for i_t, tau in enumerate(TAUS):
            for i_s, snr_db in enumerate(SNRS_DB):
                # sigma from eta_ps = v0/sigma = 10^(snr/20)
                sigma = BASE["v0"] / (10.0 ** (snr_db / 20.0))
                name = f"fid_{f_l:.0f}Hz_T{tau:.1f}s_SNR{snr_db:.0f}dB"
                seed = 1000 * (100 * i_f + 10 * i_t + i_s)
                rec = fid.generate_record(
                    b_tesla=b, tau=tau, rng=seed, phase=0.7,
                    sigma_in=sigma, **BASE)
                out.append((name, rec))
    return out


def save():
    VEC.mkdir(parents=True, exist_ok=True)
    manifest = {"convention": "v_adc float32 samples; meta per vector",
                "vectors": []}
    for name, rec in vectors():
        v = rec["v_adc"].astype(np.float32)
        np.save(VEC / f"{name}.npy", v)
        h = hashlib.sha256(v.tobytes()).hexdigest()
        manifest["vectors"].append(dict(
            name=name, file=f"{name}.npy", sha256=h,
            n=len(v), fs=rec["fs"], t0=rec["blanking_s"],
            f_larmor=rec["f_larmor"], tau=rec["tau"], lsb=rec["lsb"]))
    (VEC / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"saved {len(manifest['vectors'])} vectors -> {VEC}")


def check() -> int:
    manifest = json.loads((VEC / "manifest.json").read_text())
    bad = 0
    for entry in manifest["vectors"]:
        v = np.load(VEC / entry["file"]).astype(np.float32)
        h = hashlib.sha256(v.tobytes()).hexdigest()
        if h != entry["sha256"]:
            print("HASH MISMATCH:", entry["name"])
            bad += 1
    print("checked", len(manifest["vectors"]), "vectors;",
          "OK" if bad == 0 else f"{bad} BAD")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(check())
    save()
