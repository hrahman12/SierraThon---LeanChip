#!/usr/bin/env python3
"""leancheck: feed it the Sierrathon PCB, get GREEN / YELLOW / RED, certified by the Lean kernel.

Scope: this board and these exact parts only, i.e. the 21 lines / 54 designators of the official
Sierrathon BOM, with their manufacturer part numbers and specifications. Any extra part, missing
part, or footprint that is not the package of its exact MPN is RED.

    python3 tools/leancheck.py <board.kicad_pcb> [--html report.html]

Steps
  1. KiCad's pcbnew API reads the board (every footprint, every pad, its net, nm geometry).
  2. Lean evaluates `report` on it (rules in LeanVsDFM/PartsVerifier.lean and Report.lean).
  3. Lean certifies: it compiles `theorem certified : verify board = [findings]` with
     `decide +kernel`, so the findings are a kernel-checked theorem, not just program output.
"""
import html
import json
import os
import subprocess
import sys
import tempfile

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANSI = {"GREEN": "\033[42;30m GREEN  \033[0m", "YELLOW": "\033[43;30m YELLOW \033[0m", "RED": "\033[41;97m  RED   \033[0m"}


def _nm_box(x0, y0, x1, y1):
    return f"⟨{int(x0)}, {int(y0)}, {int(x1)}, {int(y1)}⟩"


def _courtyard(fp):
    """Courtyard rectangle from the graphic's real geometry (no line-width inflation)."""
    xs, ys = [], []
    for g in fp.GraphicalItems():
        if g.GetLayer() not in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            continue
        if g.GetShape() == pcbnew.SHAPE_T_CIRCLE:
            c, r = g.GetCenter(), g.GetRadius()
            xs += [c.x - r, c.x + r]
            ys += [c.y - r, c.y + r]
        elif g.GetShape() in (pcbnew.SHAPE_T_SEGMENT, pcbnew.SHAPE_T_RECT):
            xs += [g.GetStart().x, g.GetEnd().x]
            ys += [g.GetStart().y, g.GetEnd().y]
        else:
            bb, w = g.GetBoundingBox(), g.GetWidth() // 2
            xs += [bb.GetLeft() + w, bb.GetRight() - w]
            ys += [bb.GetTop() + w, bb.GetBottom() - w]
    if not xs:
        bb = fp.GetBoundingBox(False, False)
        xs, ys = [bb.GetLeft(), bb.GetRight()], [bb.GetTop(), bb.GetBottom()]
    return min(xs), min(ys), max(xs), max(ys)


def _outline(board):
    segs = [((d.GetStart().x, d.GetStart().y), (d.GetEnd().x, d.GetEnd().y)) for d in board.GetDrawings()
            if d.GetLayer() == pcbnew.Edge_Cuts and d.GetShape() == pcbnew.SHAPE_T_SEGMENT]
    if not segs:
        return []
    loop, cur = [segs[0][0]], segs[0][1]
    rest = segs[1:]
    while rest and cur != loop[0]:
        loop.append(cur)
        for i, (a, b) in enumerate(rest):
            if a == cur or b == cur:
                cur = b if a == cur else a
                rest.pop(i)
                break
        else:
            return []
    return loop


def board_data(path):
    """The board as plain data (nm): footprints with pads, parts with 3D data, and the outline.
    Everything Lean is given comes from here (the Lean terms, and the text the `leanchip` binary reads)."""
    bbox = json.load(open(os.path.join(ROOT, "models3d", "bbox.json")))["models"]
    b = pcbnew.LoadBoard(path)
    fps, parts = [], []
    for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
        pads, px, py, drills = [], [], [], []
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            px += [bb.GetLeft(), bb.GetRight()]
            py += [bb.GetTop(), bb.GetBottom()]
            dr = p.GetDrillSize()
            if dr.x > 0:
                drills.append(min(dr.x, dr.y) if dr.y > 0 else dr.x)
            if not p.GetNumber():
                continue
            d, s = p.GetPos0(), p.GetSize()  # footprint-local (rotation-invariant)
            pads.append({"number": p.GetNumber(), "net": p.GetNetname(), "x": int(d.x), "y": int(d.y), "w": int(s.x), "h": int(s.y)})
        ref = fp.GetReference()
        fps.append({"ref": ref, "lib": str(fp.GetFPID().GetLibItemName()), "rot": int(fp.GetOrientationDegrees()), "pads": pads})
        model, height = None, 0
        ms = list(fp.Models())
        if ms:
            m = ms[0]
            name = os.path.splitext(os.path.basename(str(m.m_Filename)))[0]
            plain = all(abs(v) < 1e-9 for v in (m.m_Offset.x, m.m_Offset.y, m.m_Offset.z, m.m_Rotation.x, m.m_Rotation.y,
                                                 m.m_Rotation.z)) and all(abs(v - 1) < 1e-9 for v in (m.m_Scale.x, m.m_Scale.y, m.m_Scale.z))
            if name in bbox and plain:
                mn, mx = bbox[name]["min"], bbox[name]["max"]
                model, height = [int(mn[0]), int(mn[1]), int(mx[0]), int(mx[1])], mx[2]
        o = fp.GetPosition()
        rot = fp.GetOrientationDegrees()
        rot = int(round(rot)) if abs(rot - round(rot)) < 1e-6 else 1
        parts.append({"ref": ref, "px": int(o.x), "py": int(o.y), "rot": rot, "court": [int(v) for v in _courtyard(fp)],
                      "pads": [int(min(px)), int(min(py)), int(max(px)), int(max(py))] if px else [int(o.x), int(o.y), int(o.x), int(o.y)],
                      "model": model, "height": height, "min_drill": min(drills) if drills else 0})
    return {"fps": fps, "parts": parts, "outline": [[int(x), int(y)] for x, y in _outline(b)], "n": len(fps),
            "thickness_nm": int(b.GetDesignSettings().GetBoardThickness())}


def fp_lines(f):
    """One footprint in the text form the `leanchip` binary reads (tab-separated)."""
    out = ["\t".join(["F", f["ref"], f["lib"], str(f["rot"])])]
    out += ["\t".join(["P", p["number"], p["net"], str(p["x"]), str(p["y"]), str(p["w"]), str(p["h"])]) for p in f["pads"]]
    return out


def part_line(t):
    m = t["model"]
    return "\t".join(["T", t["ref"], str(t["px"]), str(t["py"]), str(t["rot"]), *map(str, t["court"]), *map(str, t["pads"]),
                      "1" if m else "0", *map(str, m or [0, 0, 0, 0]), str(t["height"]), str(t["min_drill"])])


def protocol(d, knobs=None, dni=()):
    """A whole board (and optional design-package knobs) as input for the `leanchip` binary."""
    lines = [f"K\t{k}\t{v}" for k, v in (knobs or {}).items()] + [f"D\t{r}" for r in dni]
    lines += [f"B\tthickness\t{d['thickness_nm']}"] + [f"O\t{x}\t{y}" for x, y in d["outline"]]
    for f in d["fps"]:
        lines += fp_lines(f)
    lines += [part_line(t) for t in d["parts"]]
    return "\n".join(lines) + "\n"


def board_term(path):
    """The board as Lean terms: footprints with pads, parts with 3D data, and the outline (nm)."""
    q = json.dumps
    d = board_data(path)
    box = lambda v: f"⟨{v[0]}, {v[1]}, {v[2]}, {v[3]}⟩"
    fps = [f"⟨{q(f['ref'])}, {q(f['lib'])}, {f['rot']}, [" +
           ", ".join(f"⟨{q(p['number'])}, {q(p['net'])}, {p['x']}, {p['y']}, {p['w']}, {p['h']}⟩" for p in f["pads"]) + "]⟩"
           for f in d["fps"]]
    parts = [f"⟨{q(t['ref'])}, {t['px']}, {t['py']}, {t['rot']}, {box(t['court'])}, {box(t['pads'])}, "
             f"{'(some ' + box(t['model']) + ')' if t['model'] else 'none'}, {t['height']}, {t['min_drill']}⟩" for t in d["parts"]]
    outline = "[" + ", ".join(f"({x}, {y})" for x, y in d["outline"]) + "]"
    return {"fps": "[" + ",\n  ".join(fps) + "]", "parts": "[" + ",\n  ".join(parts) + "]", "outline": outline,
            "n": d["n"], "thickness_nm": d["thickness_nm"], "data": d}


def lean(src):
    env = dict(os.environ)
    env["PATH"] = os.path.expanduser("~/.elan/bin") + os.pathsep + env.get("PATH", "")
    with tempfile.NamedTemporaryFile("w", suffix=".lean", delete=False, dir=tempfile.gettempdir()) as f:
        f.write(src)
        name = f.name
    try:
        return subprocess.run(["lake", "env", "lean", name], cwd=ROOT, env=env, capture_output=True, text=True)
    finally:
        os.unlink(name)


HEADER = """import LeanVsDFM
open LeanVsDFM.Pcb LeanVsDFM.Parts LeanVsDFM.Report
set_option maxRecDepth 100000
def board : List Footprint := {fps}
def parts : List LeanVsDFM.Fit3D.Part := {parts}
def outline : List (Int × Int) := {outline}
"""


def write_html(path, data, src, certified, nfp):
    color = {"GREEN": "#1f9d55", "YELLOW": "#d69e2e", "RED": "#e53e3e"}
    rows = "".join(
        f"<tr><td>{html.escape(r['section'])}</td><td>{html.escape(r['check'])}</td>"
        f"<td><span class='pill' style='background:{color[r['color']]}'>{r['color']}</span></td>"
        f"<td>{html.escape(r['detail'])}</td></tr>" for r in data["rows"])
    cert = ("Certified by the Lean kernel: <code>theorem certified : verify board = …</code> "
            "compiled with <code>decide +kernel</code>." if certified else
            "<b>Not certified</b>: the Lean kernel did not accept the findings theorem.")
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>leancheck report</title>
<style>
:root{{--bg:#0b1a33;--fg:#f3efe6;--dim:#9fb3c3;--card:#111d36;--line:#24324d}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,Segoe UI,Arial,sans-serif}}
main{{max-width:1040px;margin:0 auto;padding:28px 16px}}
h1{{margin:0 0 4px;font-size:26px}} .sub{{color:var(--dim);margin-bottom:18px}}
.big{{display:inline-block;padding:10px 18px;border-radius:10px;font-weight:700;font-size:20px;color:#fff;background:{color[data['overall']]}}}
table{{width:100%;border-collapse:collapse;margin-top:18px;background:var(--card);border-radius:12px;overflow:hidden}}
td,th{{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{color:var(--dim);font-weight:600;font-size:13px}} .pill{{color:#fff;font-weight:700;font-size:12px;padding:3px 9px;border-radius:999px}}
code{{color:#b9a7ff}} .cert{{margin-top:16px;color:var(--dim)}}
@media (max-width:640px){{td:nth-child(1),th:nth-child(1){{display:none}}}}
</style></head><body><main>
<h1>leancheck: Sierrathon PCB</h1>
<div class="sub">{html.escape(os.path.basename(src))} · {nfp} footprints · checked against the 21-line Sierrathon BOM and its manufacturer specs</div>
<div class="big">{data['overall']}</div>
<table><tr><th>Section</th><th>Check</th><th>Result</th><th>Detail</th></tr>{rows}</table>
<div class="cert">{cert}</div>
<div class="cert">3D envelope: board {data['envelope']['board_thickness_mm']} mm + tallest body {data['envelope']['tallest_body_mm']} mm = {data['envelope']['total_height_mm']} mm.{' Theorem proved for this board: no two part bodies overlap.' if data.get('no_collision_theorem') else ''}</div>
</main></body></html>"""
    open(path, "w").write(doc)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = sys.argv[1]
    out_html = sys.argv[sys.argv.index("--html") + 1] if "--html" in sys.argv else None
    t = board_term(src)
    nfp = t["n"]
    head = HEADER.format(fps=t["fps"], parts=t["parts"], outline=t["outline"])

    # 1. evaluate
    p = lean(head + "#eval IO.println (toJson (report board outline parts))\n"
                    "#eval IO.println (repr (LeanVsDFM.Fit3D.maxHeight parts))\n"
                    "#eval IO.println \"---\"\n#eval IO.println (repr (verify board))\n"
                    "#eval IO.println \"---\"\n#eval IO.println (repr (LeanVsDFM.Fit3D.fit3d outline parts))\n")
    if p.returncode != 0:
        print(p.stdout, p.stderr)
        return 2
    chunks = p.stdout.strip().split("\n---\n")
    first = chunks[0].split("\n")
    data = json.loads(first[0])
    max_h = int(first[1])
    findings, fit = chunks[1], chunks[2]
    fits = fit.strip() == "[]"
    data["envelope"] = {"board_thickness_mm": round(t["thickness_nm"] / 1e6, 4), "tallest_body_mm": round(max_h / 1e6, 3),
                        "total_height_mm": round((t["thickness_nm"] + max_h) / 1e6, 3)}

    # 2. certify: the findings are theorems, and (when the fit is clean) so is "no two bodies overlap"
    c = lean(head +
             f"theorem certified : verify board = {findings} := by decide +kernel\n"
             f"theorem certified_fit : LeanVsDFM.Fit3D.fit3d outline parts = {fit} := by decide +kernel\n"
             f"theorem certified_overall : (overall (report board outline parts)).name = \"{data['overall']}\" := by decide +kernel\n"
             + ("theorem certified_no_collision : parts.Pairwise LeanVsDFM.Fit3D.bodySep :=\n"
                "  LeanVsDFM.Fit3D.bodies_never_collide _ (by decide +kernel)\n" if fits else ""))
    certified = c.returncode == 0
    data["no_collision_theorem"] = bool(fits and certified)

    if "--json" in sys.argv:
        clean = lambda txt: [l.strip().strip(",[]") for l in txt.splitlines() if l.strip().strip(",[]")]
        print(json.dumps({"overall": data["overall"], "rows": data["rows"], "certified": certified,
                          "issues": clean(findings), "fit_issues": clean(fit), "envelope": data["envelope"],
                          "no_collision_theorem": data["no_collision_theorem"]}))
        return 0
    print(f"\nleancheck  {os.path.basename(src)}  ({nfp} footprints, Sierrathon BOM parts only)\n")
    sec = None
    for r in data["rows"]:
        if r["section"] != sec:
            sec = r["section"]
            print(f"  {sec}")
        print(f"    {ANSI[r['color']]}  {r['check']}")
        if r["color"] != "GREEN" or r["detail"] != "proved":
            print(f"              {r['detail']}")
    print(f"\n  OVERALL {ANSI[data['overall']]}   "
          + ("certified by the Lean kernel (decide +kernel)" if certified else "NOT certified: " + c.stdout[-300:]))
    e = data["envelope"]
    print(f"  3D envelope: board {e['board_thickness_mm']} mm + tallest body {e['tallest_body_mm']} mm = {e['total_height_mm']} mm"
          + ("   | theorem: no two bodies overlap" if data["no_collision_theorem"] else ""))
    if out_html:
        write_html(out_html, data, src, certified, nfp)
        print(f"  report: {out_html}")
    return {"GREEN": 0, "YELLOW": 1, "RED": 3}[data["overall"]] if certified else 4


if __name__ == "__main__":
    sys.exit(main())
