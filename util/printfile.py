"""Measure printed parts from Bambu Studio .gcode.3mf files.

The print files in 3d_models/ hold sliced G-code rather than a mesh. On each
layer the outer-wall toolpaths trace the part's outline and any holes, so
their extents, corrected by half the line width, give the printed
cross-section to a fraction of a millimetre.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from functools import cache
from pathlib import Path

_MOVE = re.compile(r"^G[0-3] ")
_X = re.compile(r"X(-?[\d.]+)")
_Y = re.compile(r"Y(-?[\d.]+)")
_E = re.compile(r" E[\d.]*[1-9]")


@dataclass(frozen=True)
class Section:
    """Consecutive layers with the same cross-section, in mm."""

    z_bottom: float
    z_top: float
    outline: tuple[float, float]
    holes: tuple[tuple[float, float], ...]

    @property
    def height(self) -> float:
        return self.z_top - self.z_bottom


@cache
def sections(path: Path | str) -> tuple[Section, ...]:
    """Cross-sections of the first object on the plate, bottom to top."""
    gcode = zipfile.ZipFile(path).read("Metadata/plate_1.gcode").decode(errors="replace")
    width = float(re.search(r"; outer_wall_line_width = ([\d.]+)", gcode).group(1))
    loops_by_layer: dict[float, list[list[tuple[float, float]]]] = {}
    z, feature, obj, first_obj = 0.0, "", None, None
    x = y = None
    loop: list[tuple[float, float]] = []

    def close() -> None:
        if len(loop) > 2:
            loops_by_layer.setdefault(z, []).append(list(loop))
        loop.clear()

    for line in gcode.splitlines():
        if line.startswith(";"):
            if line.startswith("; FEATURE:"):
                close()
                feature = line.split(":", 1)[1].strip()
            elif line.startswith("; Z_HEIGHT:"):
                close()
                z = float(line.split(":", 1)[1])
            elif line.startswith("; start printing object"):
                obj = line.rsplit(":", 1)[1].strip()
                first_obj = first_obj or obj
            elif line.startswith("; stop printing object"):
                close()
                obj = None
            continue
        if not _MOVE.match(line):
            continue
        match_x, match_y = _X.search(line), _Y.search(line)
        x = float(match_x.group(1)) if match_x else x
        y = float(match_y.group(1)) if match_y else y
        if feature != "Outer wall" or obj != first_obj:
            continue
        if _E.search(line):
            loop.append((x, y))
        else:
            close()
    close()

    result: list[Section] = []
    for layer_z in sorted(loops_by_layer):
        boxes = sorted(((max(p[0] for p in l) - min(p[0] for p in l),
                         max(p[1] for p in l) - min(p[1] for p in l)) for l in loops_by_layer[layer_z]),
                       key=lambda box: -box[0] * box[1])
        outline = tuple(round(v + width, 1) for v in boxes[0])
        # Slivers narrower than a millimetre are slots or lettering, not openings.
        holes = tuple(tuple(round(v - width, 1) for v in box) for box in boxes[1:]
                      if min(box) - width >= 1.0)
        if result and (result[-1].outline, result[-1].holes) == (outline, holes):
            previous = result[-1]
            result[-1] = Section(previous.z_bottom, layer_z, outline, holes)
        else:
            bottom = result[-1].z_top if result else 0.0
            result.append(Section(bottom, layer_z, outline, holes))
    return tuple(result)
