"""D4/D11/D12: regenerate every headline number and check the tree.

One command:
    python3 tools/reproduce.py             # regenerate + diff fixtures + docs
    python3 tools/reproduce.py --save      # (re)commit the fixtures

What it does (TODO.md D4, D11, D12; post-REDESIGN there is exactly ONE
J-producing path -- poc/evaluate.py -- so there is exactly ONE fixture):
  * D4  one-command reproduction: runs poc/circuit_spec.py --json, which
        evaluates the reference candidates through the E2E evaluator
        (SPICE -> candidate-shaped records -> the C estimator core);
  * D11 determinism: the E2E card set is byte-compared against the
        committed fixture (tests/fixtures/score_cards/reference_cards.json).
        No wall-clock in the output -- the ngspice timestamp lines are
        consumed by the parser (asserted in tests/test_ngspice_layer.py);
  * D12 docs-vs-code: every headline number in README.md and
        docs/architecture.md tables is extracted and checked against the
        regenerated output within the stated MC CI.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
POC = ROOT / "poc"
FIXTURE = ROOT / "tests" / "fixtures" / "score_cards" / "reference_cards.json"

GAMMA_NT = 0.04257638474          # Hz/nT, shielded proton (fid.py)

# Reference operating point for the unit-vector ablations (the same point
# the pre-redesign tables used; NOT a design -- these are C-core unit
# regressions on synthetic vectors, the docs quote them as such).
ABLATION_BASE = dict(b_tesla=50e-6, v0=2e-6, tau=1.5, fs=20_000.0,
                     blanking_s=0.2, record_s=1.5, r_coil=120.0, l_coil=2e-3,
                     e_amp=7e-9, i_amp=0.05e-12, gain=5000.0, adc_bits=16,
                     adc_fs=2.048)
N_ABLATION = 200


def _run(cmd, cwd):
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                          timeout=1800)


def regenerate_cards():
    """Run the E2E CLI; returns (banner, cards)."""
    r = _run([sys.executable, "circuit_spec.py", "--json"], POC)
    if r.returncode != 0:
        raise RuntimeError(r.stdout[-2000:] + r.stderr[-2000:])
    payload = r.stdout[r.stdout.index("[\n"):]
    return r.stdout[:r.stdout.index("[\n")], json.loads(payload)


# ---------------------------------------------------------------------------
# Unit-vector ablations through the C core (the docs' systematic findings;
# NOT design scores -- no candidate is involved)
# --------------------------------------------------------------------------- #
def _rms_nt(est, n, **rec_kwargs):
    import fe_binding
    import fid
    errs = []
    for i in range(n):
        phase = np.random.default_rng(10_000 + i).uniform(-np.pi, np.pi)
        rec = fid.generate_record(rng=i, phase=phase, **rec_kwargs)
        f_hat = fe_binding.estimate(est, rec["v_adc"], rec["fs"],
                                    rec["blanking_s"])
        errs.append(f_hat - rec["f_larmor"])
    errs = np.asarray(errs)
    errs = errs[np.isfinite(errs)]
    return float(np.sqrt(np.mean(errs**2))) / fid.GAMMA_HZ_PER_NT


def regenerate_ablations():
    """The systematic findings the docs quote, regenerated through the
    single (C) estimator implementation."""
    sys.path.insert(0, str(POC))
    import crb
    import fid

    out = {}
    base = dict(ABLATION_BASE)
    sigma_in = fid.input_noise_rms(base["r_coil"], base["l_coil"],
                                   base["e_amp"], base["i_amp"])

    # Blanking curve (deterministic -- colored CRB vs blanking time).
    out["blanking_crb_nt"] = {}
    for tb in (0.05, 0.1, 0.2, 0.3, 0.5):
        n = int(round(base["record_s"] * base["fs"]))
        t = tb + np.arange(n) / base["fs"]
        out["blanking_crb_nt"][f"{tb*1e3:.0f}ms"] = crb.freq_crb_colored(
            t, base["v0"], fid.larmor_hz(base["b_tesla"]), base["tau"], 0.0,
            base["fs"], *fid.NOISE_BAND, sigma_in) / fid.GAMMA_HZ_PER_NT

    # Baseline (no systematic).
    out["baseline_nt"] = _rms_nt("zoom", N_ABLATION, **base)
    # Rail ripple through PSRR (B3): 50 mV buck at 2 kHz.
    out["ripple_destroy_nt"] = _rms_nt(
        "zoom", N_ABLATION, rail_ripple=(2000.0, 0.05, 60.0), **base)
    out["ripple_survive_nt"] = _rms_nt(
        "zoom", N_ABLATION, rail_ripple=(2000.0, 0.05, 100.0), **base)
    # Comparator time-walk (B2): the zero-crossing front end's systematic.
    out["timewalk_nt"] = _rms_nt(
        "zoom", N_ABLATION, comparator_walk_vn=sigma_in, **base)
    return out


# ---------------------------------------------------------------------------
# D11: fixture byte-compare
# --------------------------------------------------------------------------- #
def check_fixtures(cards_new=None):
    """Fresh E2E cards byte-compared against the committed fixture."""
    if not FIXTURE.exists():
        return ["fixture missing at %s (run tools/reproduce.py --save)"
                % FIXTURE]
    if cards_new is None:
        _, cards_new = regenerate_cards()
    cards_old = json.loads(FIXTURE.read_text())
    if json.dumps(cards_new, indent=1) != json.dumps(cards_old, indent=1):
        return ["E2E score cards are not byte-identical to the committed "
                "fixture (D11)"]
    return []


def save_fixtures():
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    _, cards = regenerate_cards()
    FIXTURE.write_text(json.dumps(cards, indent=1))


# ---------------------------------------------------------------------------
# D12: docs-vs-code number extraction
# --------------------------------------------------------------------------- #
def check_docs(banner=None, cards=None, ablations=None):
    """Extract headline numbers from the docs and compare with regenerated
    output. Returns a list of drift descriptions (empty = consistent)."""
    errors = []
    text = ((ROOT / "README.md").read_text() + "\n"
            + (ROOT / "docs" / "architecture.md").read_text())
    if banner is None or cards is None:
        banner, cards = regenerate_cards()
    if ablations is None:
        ablations = regenerate_ablations()

    sys.path.insert(0, str(POC))
    import fid

    # --- gamma constant (both docs) ---------------------------------------
    if "0.0425764 Hz/nT" not in text:
        errors.append("docs: gamma'p 0.0425764 Hz/nT not found")
    if "42.57638474" not in text:
        errors.append("docs: CODATA 2018 gamma 42.57638474 not found")

    # --- physics V0 x T2* grid (architecture section 0, deterministic) ----
    coils = [("N=300, r=1.0 cm, 10 mT", 0.01, 300, 0.010),
             ("N=530, r=1.5 cm, 20 mT", 0.02, 530, 0.015),
             ("N=1500, r=3.0 cm, 50 mT", 0.05, 1500, 0.030)]
    for label, b_pol, n_turns, radius in coils:
        v0 = fid.estimate_v0(b_pol=b_pol, n_turns=n_turns, coil_radius_m=radius)
        m = re.search(rf"\| {re.escape(label)} \| ([\d.]+) µV \|", text)
        if m is None or abs(float(m.group(1)) - v0 * 1e6) \
                > max(0.01 * v0 * 1e6, 0.006):
            errors.append("docs V0 for %s: %s vs %.3f uV"
                          % (label, m and m.group(1), v0 * 1e6))

    # --- E2E reference candidate cards (README table) ---------------------
    for card in cards:
        fam = card["spec"].split("(")[0].strip()
        m = re.search(rf"\|\s*{re.escape(fam)}[^|]*\|\s*([\d.]+) µV \| "
                      rf"([\d.]+) nV \| ([\d.]+) ms \| ([^|]+)\|", text)
        if m is None:
            errors.append("docs: analog table row for %s not parsed" % fam)
            continue
        band50 = next(c for c in card["bands"]
                      if abs(c["b_earth_uT"] - 50.0) < 0.1)
        j_raw = re.sub(r"\s*\([^)]*\)\s*$", "", m.group(4).strip())
        j_raw = j_raw.strip().strip("*").strip()      # bold markers
        j_raw = j_raw.removesuffix(" nT").strip()
        if "fails" in j_raw or "gate" in j_raw:
            if card["J_nt"] != float("inf"):
                errors.append("docs says %s fails a gate but code J = %.4f"
                              % (fam, card["J_nt"]))
            if not any(v is False for c in card["bands"]
                       for v in c["gates"].values()):
                errors.append("docs says %s fails a gate but no gate failed"
                              % fam)
            continue
        if not re.match(r"^[\d.]+$", j_raw):
            errors.append("docs: analog J cell for %s unparsable: %r"
                          % (fam, j_raw))
            continue
        v0_doc, sigma_doc, tau_doc = (float(m.group(1)), float(m.group(2)),
                                      float(m.group(3)))
        j_doc = float(j_raw)
        if abs(v0_doc - band50["v0_uV"]) > 0.02 * band50["v0_uV"]:
            errors.append("docs V0 %s vs code %.2f"
                          % (v0_doc, band50["v0_uV"]))
        sigma_ref = band50["sigma_in_band_uV"] * 1e3
        if abs(sigma_doc - sigma_ref) > 0.03 * sigma_ref:
            errors.append("docs sigma_in(band) %s vs %.0f nV"
                          % (sigma_doc, sigma_ref))
        if abs(tau_doc - band50["tau_ring_ms"]) > 0.2 * band50["tau_ring_ms"]:
            errors.append("docs tau_ring %s vs %.1f ms"
                          % (tau_doc, band50["tau_ring_ms"]))
        if card["J_nt"] != float("inf"):
            if abs(j_doc - card["J_nt"]) > 0.15 * card["J_nt"]:
                errors.append("docs J %s vs %.4f nT" % (j_doc, card["J_nt"]))

    # --- unit-vector ablations (README findings) --------------------------
    b = ablations["blanking_crb_nt"]
    for tb in ("0.0435", "0.0587"):
        if tb not in text:
            errors.append("docs: blanking CRB value %s missing" % tb)
    if abs(b["50ms"] - 0.0435) > 0.001 or abs(b["500ms"] - 0.0587) > 0.001:
        errors.append("blanking CRB drifted: 50ms=%.4f 500ms=%.4f"
                      % (b["50ms"], b["500ms"]))
    if ablations["ripple_destroy_nt"] < 100.0:
        errors.append("ripple-destroy ablation no longer destroys: %.2f nT"
                      % ablations["ripple_destroy_nt"])
    if abs(ablations["ripple_survive_nt"] / ablations["baseline_nt"] - 1.0) \
            > 0.3:
        errors.append("ripple-survive ablation drifted: %.4f vs baseline "
                      "%.4f nT" % (ablations["ripple_survive_nt"],
                                   ablations["baseline_nt"]))
    if ablations["timewalk_nt"] < 10 * ablations["baseline_nt"]:
        errors.append("time-walk ablation no longer binds: %.4f vs baseline "
                      "%.4f nT" % (ablations["timewalk_nt"],
                                   ablations["baseline_nt"]))

    # --- clock ppm table (analytic; deterministic) ------------------------
    for ppm, bias50 in (("20", "1.0 nT"), ("2", "0.1 nT"),
                        ("0.5", "0.025 nT")):
        if bias50 not in text:
            errors.append("docs: %s ppm clock bias %s missing"
                          % (ppm, bias50))
    return errors


def main():
    if "--save" in sys.argv:
        print("Regenerating the committed fixture (D4/D11)...")
        save_fixtures()
        print("Saved. Re-run without --save to verify byte-identity.")
        return 0
    print("Reproducing headline numbers from a fresh run (D4)...")
    banner, cards = regenerate_cards()
    print("E2E cards regenerated for:", [c["spec"] for c in cards])
    print("Regenerating unit-vector ablations through the C core...")
    ablations = regenerate_ablations()
    errors = check_fixtures(cards) + check_docs(banner, cards, ablations)
    if errors:
        print("\nDRIFT FOUND (D11/D12):")
        for e in errors:
            print("  -", e)
        return 1
    print("\nFixture byte-identical; all docs numbers consistent "
          "(D4/D11/D12 PASS)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
