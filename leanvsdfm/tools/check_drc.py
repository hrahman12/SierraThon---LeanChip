#!/usr/bin/env python3
"""Check fabrication geometry and connectivity with KiCad 9's DRC."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", type=Path)
    parser.add_argument("--report", type=Path, help="save the full KiCad JSON report")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="leanchip-drc-") as tmp:
        report = Path(tmp) / "drc.json"
        try:
            subprocess.run(
                ["kicad-cli", "pcb", "drc", "--format", "json", "--output", str(report), str(args.board)],
                check=True,
            )
            data = json.loads(report.read_bytes())
            violations = data["violations"]
            unconnected = data["unconnected_items"]
            warnings = sum(item["severity"] == "warning" for item in violations)
            errors = len(violations) - warnings
            if args.report is not None:
                args.report.write_bytes(report.read_bytes())
        except (OSError, subprocess.CalledProcessError, ValueError, KeyError, TypeError) as exc:
            print(f"DRC could not run: {exc}", file=sys.stderr)
            return 2

    blocked = bool(errors or unconnected)
    status = "blocked" if blocked else "accepted with warnings" if warnings else "accepted"
    print(f"DRC {status} ({errors} errors, {len(unconnected)} unconnected items, {warnings} warnings).")
    return 3 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
