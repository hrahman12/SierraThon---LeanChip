---
description: Check the Sierrathon PCB with Lean and report GREEN / YELLOW / RED
argument-hint: "[board.kicad_pcb]"
allowed-tools: Bash(python3 leanvsdfm/tools/leancheck.py:*), Read
---
Run the Lean checker on a KiCad board and explain the result.

Board: `$ARGUMENTS` (if empty, use `leanvsdfm/pcb/sierrathon.kicad_pcb`).

1. Run `python3 leanvsdfm/tools/leancheck.py <board> --html leanvsdfm/reports/last.html`.
2. Report the overall colour first, then every row that is not green, grouped by section
   (Board, 3D fit, Package, Specs). Quote the detail text exactly.
3. Say whether the result was certified by the Lean kernel. If it says "NOT certified", say so
   plainly and show the Lean error.
4. For each red row, name the footprint or net to change. Do not edit the board unless asked.

Exit codes: 0 green, 1 yellow, 3 red, 4 not certified.
