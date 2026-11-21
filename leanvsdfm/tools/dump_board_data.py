#!/usr/bin/env python3
"""Print `leancheck.board_data(<board.kicad_pcb>)` as JSON.

This is the reference the browser's KiCad reader (site/kicad_parse.js) has to match:
KiCad's own pcbnew reads the board, and this prints exactly what Lean is then given.

    python3 tools/dump_board_data.py pcb/sierrathon.kicad_pcb
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import leancheck  # noqa: E402


def main():
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    print(json.dumps(leancheck.board_data(sys.argv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
