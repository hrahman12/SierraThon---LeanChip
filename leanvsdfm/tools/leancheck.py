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


def board_term(path):
    """The board as a Lean term (List Footprint), integer nanometres."""
    q = json.dumps
    b = pcbnew.LoadBoard(path)
    fps = []
    for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
        o = fp.GetPosition()
        pads = []
        for p in fp.Pads():
            if not p.GetNumber():
                continue
            d, s = p.GetPosition() - o, p.GetSize()
            pads.append(f"⟨{q(p.GetNumber())}, {q(p.GetNetname())}, {int(d.x)}, {int(d.y)}, {int(s.x)}, {int(s.y)}⟩")
        fps.append(f"⟨{q(fp.GetReference())}, {q(str(fp.GetFPID().GetLibItemName()))}, "
                   f"{int(fp.GetOrientationDegrees())}, [{', '.join(pads)}]⟩")
    return "[" + ",\n  ".join(fps) + "]", len(fps)


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
def board : List Footprint := {board}
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
</main></body></html>"""
    open(path, "w").write(doc)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = sys.argv[1]
    out_html = sys.argv[sys.argv.index("--html") + 1] if "--html" in sys.argv else None
    term, nfp = board_term(src)

    # 1. evaluate
    p = lean(HEADER.format(board=term) + "#eval IO.println (toJson (report board))\n#eval IO.println (repr (verify board))\n")
    if p.returncode != 0:
        print(p.stdout, p.stderr)
        return 2
    lines = p.stdout.strip().split("\n")
    data = json.loads(lines[0])
    findings = "\n".join(lines[1:])

    # 2. certify
    c = lean(HEADER.format(board=term) +
             f"theorem certified : verify board = {findings} := by decide +kernel\n"
             f"theorem certified_overall : (overall (report board)).name = \"{data['overall']}\" := by decide +kernel\n")
    certified = c.returncode == 0

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
    if out_html:
        write_html(out_html, data, src, certified, nfp)
        print(f"  report: {out_html}")
    return {"GREEN": 0, "YELLOW": 1, "RED": 3}[data["overall"]] if certified else 4


if __name__ == "__main__":
    sys.exit(main())
