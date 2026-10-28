# KiCad projects

Two KiCad 10 projects. Open the `.kicad_pro` file in KiCad.

| Folder | Board | Files |
|---|---|---|
| `polarization_board/` | Battery, fuse, 12 V regulator, TC4420 gate driver, and the NMOS switch and TVS for the polarizing coil | `PolarizationBoard.kicad_{pro,sch,pcb}`, `gerbers/` |
| `signal_control_board/` | Coil input, switched tuning bank, damping switch, amplifier connectors J5/J6, 5 V buck converter, 2.5 V bias, ADC input network, sockets for the ADS1256 module, and the Pico 2 | `SignalProcessing&ControlBoard.kicad_{pro,sch,pcb}`, sub-sheets `SignalProcessing.kicad_sch` and `MCU.kicad_sch`, `gerbers/`, and the BOM export `SignalProcessing&ControlBoard.csv` |

Keep the file names: the root schematic refers to its sub-sheets by name. After changing a board, re-export its Gerbers into `gerbers/` (and the signal board's BOM CSV), then run `make test`. The tests read these files directly with `util/kicad.py`. They check each board's nets against its schematic and compare the boards with the firmware, the LTspice drawing, and the breadboard layout. They do not replace KiCad ERC and DRC, which need KiCad itself. `.kicad_prl` files and `.history/` folders are local editor state and are not committed.

[`../docs/design.md`](../docs/design.md) describes both boards.
