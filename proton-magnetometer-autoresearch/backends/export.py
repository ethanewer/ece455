"""A5 + A6: fab/BOM export and docs (candidate-card) leg.

A5: from a generated KiCad project, export the manufacturing artifacts
via kicad-cli:
    pcb export gerbers --output <dir>
    pcb export drill   --output <dir>
    pcb export step    --output <file>.step
    sch export bom     --output <file>.xml
and price the BOM from the parts DB (parts/parts_db.json, hand-entered).

A6: one directory per candidate containing the score table + an SVG
schematic (kicad-cli sch export svg), so a human can review every
surviving candidate.
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOOTPRINT_DIR = "/Applications/KiCad.app/Contents/SharedSupport/footprints"


def _cli():
    p = subprocess.run(["which", "kicad-cli"], capture_output=True,
                       text=True).stdout.strip()
    return p or "/Applications/KiCad.app/Contents/MacOS/kicad-cli"


def export_fab(pcb_path: str, outdir: str) -> dict:
    """Gerbers + drill + STEP for a generated board. Returns paths."""
    cli = _cli()
    out = Path(outdir)
    gerbers = out / "gerbers"
    gerbers.mkdir(parents=True, exist_ok=True)
    procs = {}
    for args in (
        ["pcb", "export", "gerbers", "--output", str(gerbers), pcb_path],
        ["pcb", "export", "drill", "--output", str(gerbers), pcb_path],
        ["pcb", "export", "step", "--output", str(out / "board.step"),
         pcb_path],
    ):
        procs[args[2]] = subprocess.run([_cli()] + args, capture_output=True,
                                        text=True)
    ok = all(p.returncode == 0 for p in procs.values())
    return {"ok": ok, "gerbers": str(gerbers), "step": str(out / "board.step"),
            "detail": {k: v.returncode for k, v in procs.items()}}


def export_bom(sch_path: str, outdir: str) -> dict:
    """KiCad BOM XML for the schematic."""
    cli = _cli()
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    bom = out / "board-bom.xml"
    proc = subprocess.run(
        [cli, "sch", "export", "bom", "--output", str(bom), sch_path],
        capture_output=True, text=True)
    return {"ok": proc.returncode == 0, "bom": str(bom)}


# Footprint prefix -> parts-DB class (for costing; the demo AFE uses
# generic Device symbols, so costing keys off the reference designators).
_REF_CLASS = {"R": "resistor", "C": "capacitor", "L": "inductor",
              "U": "ic", "Q": "jfet", "SW": "switch"}


def cost_bom(bom_xml_path: str, parts_db_path: str = None) -> dict:
    """Price a KiCad BOM XML against the hand-entered parts DB.

    The demo candidates use generic symbols, so per-line costing maps the
    component class to the DB's representative part; amplifier lines cost
    the INA828-class entry. Prices are indicative 1ku approximations.
    """
    db = json.loads(Path(parts_db_path or
                         ROOT / "parts" / "parts_db.json").read_text())
    price_by_class = {}
    for part in db["parts"]:
        cls = (part.get("mpn_class") or part.get("mpn", "")).lower()
        price_by_class[cls] = part.get("price_usd", 0.0)

    text = Path(bom_xml_path).read_text()
    # KiCad 10's default BOM output is CSV: "Refs","Value","Footprint",...
    lines = []
    total = 0.0
    import csv as _csv
    import io
    rows = list(_csv.reader(io.StringIO(text)))
    for row in rows[1:]:
        if len(row) < 2:
            continue
        ref, val = row[0], row[1]
        prefix = re.match(r"[A-Za-z]+", ref)
        cls = _REF_CLASS.get(prefix.group(0) if prefix else "", "other")
        if cls == "ic":
            price = price_by_class.get("ina828aidr", 0.0)
        elif cls == "jfet":
            price = price_by_class.get("2n6550-class jfet", 0.0)
        else:
            price = 0.05 if cls in ("resistor", "capacitor") else 0.10
        total += price
        lines.append({"ref": ref, "value": val, "class": cls,
                      "price_usd": price})
    return {"total_usd_1ku": round(total, 2), "lines": lines,
            "note": "indicative hand-entered 1ku prices; verify at order"}


def candidate_card(spec: dict, score_card: dict, outdir: str) -> Path:
    """A6: one directory per candidate: score table + SVG schematic."""
    from backends.kicad import build_circuit
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    # score table
    rows = {k: v for k, v in score_card.items()
            if isinstance(v, (int, float, str, bool))}
    (out / "score.json").write_text(json.dumps(rows, indent=1))
    with (out / "score.md").open("w") as f:
        f.write("# %s\n\n" % spec["title"])
        f.write("| metric | value |\n|---|---|\n")
        for k, v in sorted(rows.items()):
            if k in ("gates",):
                continue
            if isinstance(v, float):
                v = f"{v:.4g}"
            f.write("| %s | %s |\n" % (k, v))
        f.write("\ngates: %s\n" % ", ".join(
            "%s:%s" % (k, "ok" if v else "FAIL")
            for k, v in score_card.get("gates", {}).items()))
    # SVG schematic via kicad-cli from the generated .kicad_sch
    try:
        from backends.kicad import write_schematic
        sch = write_schematic(spec, str(out))
        cli = _cli()
        subprocess.run([cli, "sch", "export", "svg", "--output", str(out),
                        str(sch)], capture_output=True, text=True)
    except Exception as e:
        (out / "svg_error.txt").write_text(str(e))
    return out
