"""PCB worker: runs under KiCad's bundled Python (needs pcbnew).

Builds a placed .kicad_pcb from a KiCad netlist (kinet2pcb) and adds a
rectangular Edge.Cuts outline with a generous margin so the DRC design
rules (clearance, edge clearance, mask) can be checked on the placed
board. Routing is deliberately NOT attempted (a naive route created more
violations than it fixed); the DRC gate therefore runs with unrouted
pads expected -- the pre-layout stage -- and the gate classifies
violations: design-rule violations fail the gate, unconnected-items
(expected before layout) are reported separately.

Usage:
    kicad_python kicad_pcb_worker.py <netlist.net> <board.kicad_pcb>
"""
import pcbnew

FOOTPRINT_DIR = ("/Applications/KiCad.app/Contents/SharedSupport/"
                 "footprints")
MARGIN_NM = 30_000_000                      # 30 mm margin around parts


def build_board(netlist_path: str, board_path: str):
    import kinet2pcb
    kinet2pcb.kinet2pcb(netlist_path, board_path, fp_lib_dirs=[FOOTPRINT_DIR])
    brd = pcbnew.LoadBoard(board_path)

    # Board outline: rectangle around the placed parts.
    bb = brd.GetBoardEdgesBoundingBox()
    x0 = int(bb.GetX()) - MARGIN_NM
    x1 = int(bb.GetX()) + int(bb.GetWidth()) + MARGIN_NM
    y0 = int(bb.GetY()) - MARGIN_NM
    y1 = int(bb.GetY()) + int(bb.GetHeight()) + MARGIN_NM
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    for a, b in zip(pts[:-1], pts[1:]):
        seg = pcbnew.PCB_SHAPE(brd)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.VECTOR2I(a[0], a[1]))
        seg.SetEnd(pcbnew.VECTOR2I(b[0], b[1]))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(10_000)
        brd.Add(seg)

    pcbnew.SaveBoard(board_path, brd)
    return brd




def main(netlist_path: str, board_path: str) -> int:
    build_board(netlist_path, board_path)
    print("board saved:", board_path)
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
