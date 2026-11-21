#!/usr/bin/env python3
"""Data for the web tool: every way the tool can realise each BOM line, as the exact text the
`leanchip` binary reads.

Each option is a real KiCad footprint placed on our reference layout (same position, same
rotation) and read back with the same code `leancheck` uses. The page only glues these lines
together and sends them to the Lean checker; it holds no verdict logic.

    python3 tools/tool_data.py ../site/data/tool.json
"""
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import build_pcb  # noqa: E402
import explore  # noqa: E402
import layout_pcb  # noqa: E402
import leancheck  # noqa: E402

REFERENCE = explore.REFERENCE
BIN = os.path.join(ROOT, ".lake", "build", "bin", "leanchip")
FAULTS = {
    "led_reversed": "LED D5 mounted backwards",
    "flash_pins_swapped": "Flash U3: two data pins swapped",
    "wrong_cap_size": "C4 fitted as 0603 instead of 0402",
    "narrow_flash": "Flash U3 on the narrow 150 mil SOIC",
}
# The knobs, each tied to the supplied file it comes from. Values are what the Lean `Knobs` take.
KNOBS = [
    {"key": "ledQty", "group": "BOM", "source": "Sierrathon_BOM.xlsx, row 5", "label": "LED quantity on BOM row 5",
     "options": [[8, "8 (as supplied)"], [7, "7 (one per designator D3–D9)"]]},
    {"key": "ledOhm", "group": "BOM", "source": "Sierrathon_BOM.xlsx, row 13", "label": "LED resistors R12–R18",
     "options": [[68, "68 Ω"], [220, "220 Ω"], [240, "240 Ω"], [330, "330 Ω (as supplied)"], [430, "430 Ω"]]},
    {"key": "crystalC", "group": "BOM", "source": "Sierrathon_BOM.xlsx, row 4", "label": "Crystal load capacitors C6, C7",
     "options": [[100, "10 pF"], [150, "15 pF (as supplied)"], [220, "22 pF"], [330, "33 pF"]]},
    {"key": "rdOhm", "group": "BOM", "source": "Sierrathon_BOM.xlsx, row 8", "label": "USB-C pull-downs R1, R2",
     "options": [[1000, "1 kΩ"], [5100, "5.1 kΩ (as supplied)"], [10000, "10 kΩ"]]},
    {"key": "driveUA", "group": "Schematic", "source": "Sierrathon_Schematic.pdf, GPIO17–23", "label": "RP2040 pad drive on the LED pins",
     "options": [[2000, "2 mA"], [4000, "4 mA (chip default)"], [8000, "8 mA"], [12000, "12 mA"]]},
    {"key": "loadmA", "group": "Schematic", "source": "Sierrathon_Schematic.pdf, +3.3V rail", "label": "Load on the 3.3 V regulator",
     "options": [[112, "112 mA (this design)"], [150, "150 mA"], [245, "245 mA"], [400, "400 mA"]]},
    {"key": "cuStackup", "group": "Stack-up", "source": "Sierrathon Stack-Up.png, L2 and L3", "label": "Inner copper on the stack-up drawing",
     "options": [[5, "0.5 oz (as supplied)"], [10, "1 oz"], [20, "2 oz"], [60, "6 oz"]]},
    {"key": "cuInstructions", "group": "Stack-up", "source": "Sierrathon_Instructions.docx", "label": "Inner copper in the instructions",
     "options": [[10, "1 oz (as supplied)"], [5, "0.5 oz (same as the drawing)"]]},
    {"key": "pair", "group": "Stack-up", "source": "Sierrathon Stack-Up.png, impedance table", "label": "90 Ω pair width / gap",
     "sets": ["pairW", "pairGap"],
     "options": [["500/400", "5 / 4 mil (stack-up table)"], ["600/600", "6 / 6 mil (what one global 6 mil rule forces)"], ["400/400", "4 / 4 mil"]]},
]
DEFAULTS = {"ledQty": 8, "ledOhm": 330, "crystalC": 150, "rdOhm": 5100, "driveUA": 4000, "loadmA": 112, "cuStackup": 5,
            "cuInstructions": 10, "pair": "500/400"}


def per_ref(d):
    f = {x["ref"]: leancheck.fp_lines(x) for x in d["fps"]}
    t = {x["ref"]: leancheck.part_line(x) for x in d["parts"]}
    return {r: {"f": f[r], "t": t[r]} for r in f}


def built(wd, name, fp, u3_pads="ul"):
    grid, path = os.path.join(wd, f"{name}_grid.kicad_pcb"), os.path.join(wd, f"{name}.kicad_pcb")
    build_pcb.build(grid, combo={"fp": fp, "u3_pads": u3_pads})
    layout_pcb.place_like(grid, REFERENCE, path)
    return per_ref(leancheck.board_data(path))


def bom_lines():
    src = open(os.path.join(ROOT, "LeanVsDFM", "PackageData.lean"), encoding="utf-8").read()
    rows = re.findall(r'⟨(\d+), \[([^\]]*)\], (\d+), "([^"]*)", "([^"]*)", (true|false)⟩', src)
    return {int(n): {"line": int(n), "refs": re.findall(r'"([^"]+)"', refs), "qty": int(q), "value": v, "mpn": m} for n, refs, q, v, m, _ in rows}


def main():
    out = sys.argv[1]
    ref_d = leancheck.board_data(REFERENCE)
    base = per_ref(ref_d)
    bom = bom_lines()
    opts = {ln: [pref] + var + wrong for ln, (_r, pref, var, wrong, _n) in explore.LINES.items()}
    kinds = {ln: ["preferred"] + ["variant"] * len(var) + ["wrong"] * len(wrong) for ln, (_r, _p, var, wrong, _n) in explore.LINES.items()}
    refs_of = {ln: v[0].split() for ln, v in explore.LINES.items()}
    lines = {ln: {**bom[ln], "options": [{"id": o, "kind": k, "per_ref": None} for o, k in zip(opts[ln], kinds[ln])]} for ln in opts}
    with tempfile.TemporaryDirectory() as wd:
        for j in range(max(len(o) for o in opts.values())):
            fp = {r: (opts[ln][j] if j < len(opts[ln]) else opts[ln][0]) for ln in opts for r in refs_of[ln]}
            data = built(wd, f"layer{j}", fp)
            if j == 0:      # the all-preferred build must be our reference board, character for character
                assert data == base, [r for r in base if data.get(r) != base[r]]
            for ln in opts:
                if j < len(opts[ln]):
                    lines[ln]["options"][j]["per_ref"] = {r: data[r] for r in refs_of[ln]}
        # the flash on the right package but with KiCad's library pads instead of the manufacturer's
        data = built(wd, "u3kicad", {r: opts[ln][0] for ln in opts for r in refs_of[ln]}, u3_pads="kicad")
        lines[19]["options"].insert(1, {"id": opts[19][0] + " (KiCad library pads)", "kind": "variant", "per_ref": {"U3": data["U3"]}})
    lines[19]["options"][0]["id"] += " (manufacturer pads)"
    faults = []
    for name, label in FAULTS.items():
        d = per_ref(leancheck.board_data(os.path.join(ROOT, "pcb", f"fault_{name}.kicad_pcb")))
        diff = {r: d[r] for r in d if d[r] != base[r]}
        assert diff, name
        faults.append({"id": name, "label": label, "per_ref": diff})
    fixed = {r: base[r] for r in base if not any(r in v for v in refs_of.values())}
    probe = json.loads(subprocess.run([BIN], input=leancheck.protocol(ref_d), capture_output=True, text=True, check=True).stdout)
    tool = {"about": "Generated by leanvsdfm/tools/tool_data.py from KiCad. Text lines are the input format of the leanchip binary.",
            "thickness_nm": ref_d["thickness_nm"], "outline": ref_d["outline"], "order": [x["ref"] for x in ref_d["fps"]],
            "fixed": fixed, "bom": [bom[k] for k in sorted(bom)], "lines": [lines[k] for k in sorted(lines)], "faults": faults,
            "knobs": KNOBS, "defaults": DEFAULTS, "rails": probe["rails"]}
    json.dump(tool, open(out, "w"), separators=(",", ":"))
    json.dump(json.load(open(os.path.join(ROOT, "models3d", "bbox.json")))["models"],
              open(os.path.join(os.path.dirname(out), "models.json"), "w"), separators=(",", ":"))
    print("wrote", out, os.path.getsize(out), "bytes;", sum(len(l["options"]) for l in tool["lines"]), "options on", len(tool["lines"]),
          "BOM lines;", len(faults), "faults;", len(fixed), "fixed parts")


if __name__ == "__main__":
    main()
