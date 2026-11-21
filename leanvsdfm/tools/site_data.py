#!/usr/bin/env python3
"""Build the website's data from real runs (nothing is typed in by hand).

    python3 leanvsdfm/tools/site_data.py site/data

  runs.json         leancheck --json on our board and the four fault boards
  explore.json      the design-space exploration, trimmed
  transcripts.json  commands run by Claude Code while building this project, with their real output
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = dict(os.environ, PATH=os.path.expanduser("~/.elan/bin") + os.pathsep + os.environ["PATH"])
ANSI = re.compile(r"\x1b\[[0-9;]*m")

BOARDS = [
    ("sierrathon", "Our board", "The placed 52 × 45 mm hexagon, every part from the Sierrathon BOM."),
    ("fault_led_reversed", "LED D5 reversed", "Same board, D5 placed with anode and cathode swapped."),
    ("fault_narrow_flash", "Narrow flash footprint", "U3 on the 150 mil SOIC-8 instead of the 208 mil package the W25Q128JVSIQ comes in."),
    ("fault_wrong_cap_size", "0603 footprint on an 0402 line", "C4 given an 0603 footprint; the BOM part is 0402."),
    ("fault_flash_pins_swapped", "Flash data pins swapped", "U3 DO/D1 and DI/D0 exchanged on the footprint."),
]


def sh(cmd, cwd=ROOT):
    p = subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True, shell=isinstance(cmd, str))
    return ANSI.sub("", (p.stdout + p.stderr)).strip(), p.returncode


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    runs = []
    for name, title, about in BOARDS:
        txt, _ = sh([sys.executable, "tools/leancheck.py", f"pcb/{name}.kicad_pcb", "--json"])
        rep = json.loads(txt.splitlines()[-1])
        runs.append({"id": name, "title": title, "about": about, "file": f"leanvsdfm/pcb/{name}.kicad_pcb", **rep})
        print(name, rep["overall"], "certified" if rep["certified"] else "NOT certified")
    json.dump(runs, open(os.path.join(out, "runs.json"), "w"), indent=1)

    ex = json.load(open(os.path.join(ROOT, "explore", "results.json")))
    slim = []
    for r in ex["results"]:
        board = "RED" if any(x["section"] in ("Board", "3D fit") and x["color"] == "RED" for x in r["rows"]) else (
            "YELLOW" if any(x["section"] in ("Board", "3D fit") and x["color"] == "YELLOW" for x in r["rows"]) else "GREEN")
        reasons = [x["check"] + ": " + x["detail"] for x in r["rows"] if x["section"] in ("Board", "3D fit") and x["color"] == "RED"]
        slim.append({"id": r["id"], "strategy": r["strategy"], "changed_line": r.get("changed_line"), "verdict": r["verdict"],
                     "name": r.get("name"), "rationale": r.get("rationale"),
                     "board_verdict": board, "certified": r["certified"], "collisions": sum("courtyardsOverlap" in i for i in r["fit_issues"]),
                     "reasons": reasons[:3], "pad_area_mm2": r["pad_area_mm2"],
                     "changed": sorted({v for k, v in r["lines"].items()} - {"x"})[:0]})
    json.dump({"builds": slim, "llm": ex.get("llm")}, open(os.path.join(out, "explore.json"), "w"), indent=1)

    T = []

    def rec(prompt, cmd, cwd="leanvsdfm", keep=None, note=""):
        txt, code = sh(cmd, cwd=os.path.join(os.path.dirname(ROOT), cwd) if cwd != "leanvsdfm" else ROOT)
        lines = txt.splitlines()
        if keep:
            lines = [l for l in lines if keep(l)]
        T.append({"prompt": prompt, "command": cmd, "output": "\n".join(lines[-40:]), "exit_code": code, "note": note})

    rec("Check our board with Lean. Give me green, yellow or red.",
        "python3 tools/leancheck.py pcb/sierrathon.kicad_pcb", note="Certified YELLOW is accepted with warnings.")
    rec("I swapped D5 around by mistake. Does the checker catch it?",
        "python3 tools/leancheck.py pcb/fault_led_reversed.kicad_pcb",
        keep=lambda l: "RED" in l or "OVERALL" in l or l.strip().startswith("D5") or "leancheck" in l, note="Exit code 3 means RED.")
    rec("Re-prove everything.", "lake build 2>&1 | tail -1 && grep -c '^theorem' LeanVsDFM/*.lean | grep -v ':0'")
    rec("Does Lean's idea of where the parts are in 3D match KiCad's STEP export?",
        "python3 tools/check_step_agreement.py out3d/sierrathon_parts.json", note="A test, not a proof.")
    rec("Is there any sorry, admit or native_decide in the proofs?",
        "grep -rn 'sorry\\|admit\\|native_decide' LeanVsDFM/*.lean | grep -v 'no `native_decide`' || echo 'none found'")
    json.dump(T, open(os.path.join(out, "transcripts.json"), "w"), indent=1)
    print("transcripts:", len(T))


if __name__ == "__main__":
    main()
