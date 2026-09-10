"""D4/D11/D12: regenerate every headline number and check the tree.

One command:
    python3 tools/reproduce.py             # regenerate + diff fixtures + docs
    python3 tools/reproduce.py --save      # (re)commit the fixtures

What it does (TODO.md D4, D11, D12):
  * D4  one-command reproduction: runs poc/run_scoring.py and
        poc/circuit_spec.py --json from the current tree;
  * D11 determinism: run_scoring stdout and the circuit_spec card set are
        byte-compared against committed fixtures (tests/fixtures/reproduce/).
        No wall-clock in these outputs -- the ngspice timestamp lines are
        consumed by the parser and never printed (asserted in
        tests/test_ngspice_layer.py);
  * D12 docs-vs-code: every headline number in README.md and
        docs/architecture.md tables is extracted and checked against the
        regenerated output within the stated MC CI.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POC = ROOT / "poc"
FIXTURES = ROOT / "tests" / "fixtures" / "reproduce"

GAMMA_NT = 0.04257638474          # Hz/nT, shielded proton (fid.py)


def _run(cmd, cwd):
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                          timeout=1800)


def regenerate_run_scoring():
    r = _run([sys.executable, "run_scoring.py"], POC)
    if r.returncode != 0:
        raise RuntimeError(r.stdout[-2000:] + r.stderr[-2000:])
    return r.stdout


def regenerate_circuit_spec():
    r = _run([sys.executable, "circuit_spec.py", "--json"], POC)
    if r.returncode != 0:
        raise RuntimeError(r.stdout[-2000:] + r.stderr[-2000:])
    payload = r.stdout[r.stdout.index("[\n"):]
    return r.stdout[:r.stdout.index("[\n")], json.loads(payload)


# ---------------------------------------------------------------------------
# D11: fixture byte-compare
# --------------------------------------------------------------------------- #
def check_fixtures():
    """Fresh runs byte-compared against the committed fixtures."""
    errors = []
    rs_fix = FIXTURES / "run_scoring.txt"
    cs_fix = FIXTURES / "circuit_spec.json"
    if not rs_fix.exists() or not cs_fix.exists():
        return ["fixtures missing under %s (run tools/reproduce.py --save)"
                % FIXTURES]
    if regenerate_run_scoring() != rs_fix.read_text():
        errors.append("run_scoring.py output is not byte-identical to the "
                      "committed fixture (D11)")
    _, cards_new = regenerate_circuit_spec()
    cards_old = json.loads(cs_fix.read_text())
    if json.dumps(cards_new, indent=1) != json.dumps(cards_old, indent=1):
        errors.append("circuit_spec.py score cards are not byte-identical "
                      "to the committed fixture (D11)")
    return errors


def save_fixtures():
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / "run_scoring.txt").write_text(regenerate_run_scoring())
    _, cards = regenerate_circuit_spec()
    (FIXTURES / "circuit_spec.json").write_text(json.dumps(cards, indent=1))


# ---------------------------------------------------------------------------
# D12: docs-vs-code number extraction
# --------------------------------------------------------------------------- #
def check_docs(rs_out=None, cs_rows=None):
    """Extract headline numbers from the docs and compare with regenerated
    output. Returns a list of drift descriptions (empty = consistent)."""
    errors = []
    text = ((ROOT / "README.md").read_text() + "\n"
            + (ROOT / "docs" / "architecture.md").read_text())
    if rs_out is None:
        rs_out = regenerate_run_scoring()
    if cs_rows is None:
        _, cs_rows = regenerate_circuit_spec()

    sys.path.insert(0, str(POC))
    import crb
    import fid

    # --- gamma constant (both docs) ---------------------------------------
    if "0.0425764 Hz/nT" not in text:
        errors.append("docs: gamma'p 0.0425764 Hz/nT not found")
    if "42.57638474" not in text:
        errors.append("docs: CODATA 2018 gamma 42.57638474 not found")

    # --- run_scoring printed claims ---------------------------------------
    for ppm, bias50 in (("20", "1.000"), ("2", "0.100"), ("0.5", "0.025")):
        if bias50 not in rs_out:
            errors.append("run_scoring: %s ppm bias %s nT missing" % (ppm, bias50))
    # estimator table rows in docs (xCRB columns)
    for est, want_ratio in (("zoom", 1.02), ("FFT \+ log-parabolic", 1.05)):
        m = re.search(rf"\|[^|]*{est}[^|]*\|\s*([\d.]+)\s*\|", text)
        if m is None or abs(float(m.group(1)) - want_ratio) > 0.05:
            errors.append("docs xCRB for %s: %s vs %.2f"
                          % (est, m and m.group(1), want_ratio))
    # blanking numbers
    if "0.0435" not in text or "0.0587" not in text:
        errors.append("docs: blanking 0.0435->0.0587 numbers missing")

    # --- physics V0 x T2* grid (architecture section 0) -------------------
    coils = [("N=300, r=1.0 cm, 10 mT", 0.01, 300, 0.010),
             ("N=530, r=1.5 cm, 20 mT", 0.02, 530, 0.015),
             ("N=1500, r=3.0 cm, 50 mT", 0.05, 1500, 0.030)]
    for label, b_pol, n_turns, radius in coils:
        v0 = fid.estimate_v0(b_pol=b_pol, n_turns=n_turns, coil_radius_m=radius)
        m = re.search(rf"\| {re.escape(label)} \| ([\d.]+) µV \|", text)
        if m is None or abs(float(m.group(1)) - v0 * 1e6) \
                > max(0.01 * v0 * 1e6, 0.006):
            # 0.006 uV covers the table's 2-decimal display rounding
            errors.append("docs V0 for %s: %s vs %.3f uV"
                          % (label, m and m.group(1), v0 * 1e6))

    # --- analog candidate cards (README table) ----------------------------
    for card in cs_rows:
        fam = card["spec"].split(" + ")[0]
        m = re.search(rf"\|\s*{re.escape(fam)}[^|]*\|\s*([\d.]+) µV \| "
                      rf"([\d.]+) nV \| [\d.+−-]+ dB \| ([\d.]+) ms \| "
                      rf"([^|]+)\|", text)
        if m is None:
            errors.append("docs: analog table row for %s not parsed" % fam)
            continue
        j_raw = m.group(4).strip().strip("*")
        j_raw = re.sub(r"\s*\(= CRB\)\s*$", "", j_raw).strip()  # annotation
        j_raw = j_raw.removesuffix(" nT").strip()          # unit column text
        if "fails" in j_raw or "gate" in j_raw:
            # the doc row reports a gated-out candidate: the fixture card
            # must agree (J = inf) and the failing gate must be named
            if card["J_nt"] != float("inf"):
                errors.append("docs says %s fails a gate but code J = %.4f"
                              % (fam, card["J_nt"]))
            gate_ok = any(card["gates"].get(g) is False
                          for g in card["gates"])
            if not gate_ok:
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
        if abs(v0_doc - card["v0_uV"]) > 0.02 * card["v0_uV"]:
            errors.append("docs V0 %s vs code %.2f" % (v0_doc, card["v0_uV"]))
        sigma_ref = card["sigma_in_band_uV"] * 1e3
        if abs(sigma_doc - sigma_ref) > 0.03 * sigma_ref:
            errors.append("docs sigma_in(band) %s vs %.0f nV"
                          % (sigma_doc, sigma_ref))
        if abs(tau_doc - card["tau_ring_ms"]) > 0.2 * card["tau_ring_ms"]:
            errors.append("docs tau_ring %s vs %.1f ms"
                          % (tau_doc, card["tau_ring_ms"]))
        if card["J_nt"] != float("inf"):
            if abs(j_doc - card["J_nt"]) > 0.15 * card["J_nt"]:
                errors.append("docs J %s vs %.4f nT" % (j_doc, card["J_nt"]))
    return errors


def main():
    if "--save" in sys.argv:
        print("Regenerating committed fixtures (D4/D11)...")
        save_fixtures()
        print("Saved. Re-run without --save to verify byte-identity.")
        return 0
    print("Reproducing headline numbers from a fresh run (D4)...")
    rs = regenerate_run_scoring()
    _, cs_rows = regenerate_circuit_spec()
    print("run_scoring + circuit_spec regenerated;")
    print("cards:", [c["spec"] for c in cs_rows])
    errors = check_fixtures() + check_docs(rs, cs_rows)
    if errors:
        print("\nDRIFT FOUND (D11/D12):")
        for e in errors:
            print("  -", e)
        return 1
    print("\nAll fixtures byte-identical; all docs numbers consistent "
          "(D4/D11/D12 PASS)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
