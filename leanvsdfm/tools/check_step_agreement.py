#!/usr/bin/env python3
"""Test (not a proof): Lean's 3D body placement agrees with KiCad's STEP exporter.

Lean computes where each part's body lands (Fit3D.bodyBox) from the placement, the rotation and
the model's measured bounding box. KiCad's STEP exporter places the same models independently.
This script compares the two for every part and prints the largest difference.

    python3 tools/check_step_agreement.py out3d/sierrathon_parts.json
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = """import LeanVsDFM
open LeanVsDFM
#eval IO.println (String.intercalate "\\n" (PcbData.parts.filterMap fun p =>
  (Fit3D.bodyBox p).map fun b => s!"{p.ref} {b.x0} {b.y0} {b.x1} {b.y1} {p.height}"))
"""


def main():
    step = json.load(open(sys.argv[1]))["parts"]
    env = dict(os.environ, PATH=os.path.expanduser("~/.elan/bin") + os.pathsep + os.environ["PATH"])
    with tempfile.NamedTemporaryFile("w", suffix=".lean", delete=False) as f:
        f.write(SRC)
    out = subprocess.run(["lake", "env", "lean", f.name], cwd=ROOT, env=env, capture_output=True, text=True).stdout
    os.unlink(f.name)
    lean = [l.split() for l in out.strip().splitlines()]
    bodies = [p for p in step if "PCB" not in p["name"]]
    board_top = max(p["max"][2] for p in step if "PCB" in p["name"])
    worst_xy, worst_z, used = 0.0, 0.0, set()
    for ref, x0, y0, x1, y1, h in lean:
        x0, y0, x1, y1, h = (int(v) / 1e6 for v in (x0, y0, x1, y1, h))
        best = None
        for i, p in enumerate(bodies):       # STEP is y-up; KiCad board coordinates are y-down
            if i in used:
                continue
            dxy = max(abs(p["min"][0] - x0), abs(p["max"][0] - x1), abs(-p["max"][1] - y0), abs(-p["min"][1] - y1))
            dz = abs((p["max"][2] - board_top) - h)
            if best is None or dxy < best[0]:
                best = (dxy, dz, i)
        used.add(best[2])
        worst_xy, worst_z = max(worst_xy, best[0]), max(worst_z, best[1])
        if best[0] > 0.005:
            print(f"  {ref}: outline differs by {best[0] * 1000:.1f} µm")
    ok = worst_xy <= 0.005 and worst_z <= 0.06 and len(lean) == len(bodies)
    print(f"{len(lean)} Lean bodies vs {len(bodies)} bodies in KiCad's STEP export: largest outline (x, y) difference "
          f"{worst_xy * 1000:.1f} µm, largest height difference {worst_z * 1000:.0f} µm -> {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
