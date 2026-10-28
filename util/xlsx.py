"""Read cell values from an .xlsx workbook with the standard library.

Formulas are not evaluated; each cell returns the value Excel cached when the
workbook was last saved.
"""
from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def read_workbook(path: Path | str) -> dict[str, dict[str, str | float]]:
    """Sheet name -> {cell reference such as "B5": number or text}."""
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("m:si", _NS):
                shared.append("".join(t.text or "" for t in item.iter(f"{{{_NS['m']}}}t")))
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {rel.get("Id"): rel.get("Target") for rel in relations}
        sheets = {}
        for sheet in workbook.find("m:sheets", _NS):
            target = targets[sheet.get(f"{{{_NS['r']}}}id")].lstrip("/")
            target = target if target.startswith("xl/") else "xl/" + target
            cells: dict[str, str | float] = {}
            for cell in ET.fromstring(archive.read(target)).iter(f"{{{_NS['m']}}}c"):
                kind, value = cell.get("t"), cell.find("m:v", _NS)
                if kind == "inlineStr":
                    cells[cell.get("r")] = "".join(t.text or "" for t in cell.iter(f"{{{_NS['m']}}}t"))
                elif value is None or value.text is None:
                    continue
                elif kind == "s":
                    cells[cell.get("r")] = shared[int(value.text)]
                elif kind in ("str", "e", "b"):
                    cells[cell.get("r")] = value.text
                else:
                    cells[cell.get("r")] = float(value.text)
            sheets[sheet.get("name")] = cells
    return sheets


def _split(ref: str) -> tuple[int, int]:
    """Cell reference -> (column number from 1, row number)."""
    letters, row = re.fullmatch(r"([A-Z]+)(\d+)", ref).groups()
    column = 0
    for letter in letters:
        column = column * 26 + ord(letter) - ord("A") + 1
    return column, int(row)


def row_beside(cells: dict[str, str | float], label: str) -> list[str | float]:
    """Values to the right of the only cell whose text is label, left to right."""
    found = [ref for ref, value in cells.items() if value == label]
    if len(found) != 1:
        raise KeyError(f"{len(found)} cells are labelled {label!r}")
    column, row = _split(found[0])
    beside = sorted((_split(ref)[0], value) for ref, value in cells.items()
                    if _split(ref)[1] == row and _split(ref)[0] > column)
    return [value for _, value in beside]


def value_beside(cells: dict[str, str | float], label: str) -> str | float:
    """The value to the right of the only cell whose text is label."""
    values = row_beside(cells, label)
    if not values:
        raise KeyError(f"nothing beside {label!r}")
    return values[0]
