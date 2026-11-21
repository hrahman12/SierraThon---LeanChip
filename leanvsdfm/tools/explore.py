#!/usr/bin/env python3
"""Design-space explorer: proposers suggest ways to build the Sierrathon board from these exact
parts; Lean (leancheck) certifies GREEN / YELLOW / RED for each.

Proposers are untrusted. Their job is to suggest; only the Lean-certified verdict counts.
  preferred   : preferred land pattern for every part
  hand        : hand-assembly variants where KiCad has them
  one-variant : our build with ONE BOM line switched to its variant footprint (sensitivity)
  one-wrong   : our build with ONE BOM line switched to a wrong-size package
  random      : random allowed option per BOM line, with a 12 % chance of a wrong-size part
  naive       : first KiCad footprint whose name matches the BOM package text (a common AI/human slip)
  ai          : proposals written by an AI, read from explore/ai_proposals.json

    python3 tools/explore.py <N> <out.json>
"""
import concurrent.futures as cf
import json
import os
import random
import subprocess
import sys
import tempfile

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import build_pcb  # noqa: E402
import layout_pcb  # noqa: E402

REFERENCE = os.path.join(ROOT, "pcb", "sierrathon.kicad_pcb")   # our placed board: positions are kept

# BOM line -> (designators, preferred, variants, wrong-size distractors, naive keyword pick)
LINES = {
    1: ("C1 C2", "C_0603_1608Metric", ["C_0603_1608Metric_Pad1.08x0.95mm_HandSolder"], ["C_0402_1005Metric", "C_0805_2012Metric"], "C_0603_1608Metric"),
    2: ("C3 C5 C14 C17", "C_0805_2012Metric", ["C_0805_2012Metric_Pad1.18x1.45mm_HandSolder"], ["C_0603_1608Metric"], "C_0805_2012Metric"),
    3: ("C4 C8 C9 C10 C11 C12 C13 C15 C16", "C_0402_1005Metric", ["C_0402_1005Metric_Pad0.74x0.62mm_HandSolder"], ["C_0603_1608Metric"], "C_0402_1005Metric"),
    4: ("C6 C7", "C_0402_1005Metric", ["C_0402_1005Metric_Pad0.74x0.62mm_HandSolder"], ["C_0603_1608Metric"], "C_0402_1005Metric"),
    5: ("D3 D4 D5 D6 D7 D8 D9", "LED_0603_1608Metric", ["LED_0603_1608Metric_Pad1.05x0.95mm_HandSolder"], [], "LED_0603_1608Metric"),
    8: ("R1 R2", "R_0402_1005Metric", ["R_0402_1005Metric_Pad0.72x0.64mm_HandSolder"], ["R_0603_1608Metric"], "R_0402_1005Metric"),
    9: ("R4", "R_0603_1608Metric", ["R_0603_1608Metric_Pad0.98x0.95mm_HandSolder"], ["R_0402_1005Metric"], "R_0603_1608Metric"),
    10: ("R5 R6", "R_0402_1005Metric", ["R_0402_1005Metric_Pad0.72x0.64mm_HandSolder"], ["R_0603_1608Metric"], "R_0402_1005Metric"),
    11: ("R7 R8", "R_0402_1005Metric", ["R_0402_1005Metric_Pad0.72x0.64mm_HandSolder"], ["R_0603_1608Metric"], "R_0402_1005Metric"),
    12: ("R9 R10 R19", "R_0402_1005Metric", ["R_0402_1005Metric_Pad0.72x0.64mm_HandSolder"], ["R_0603_1608Metric"], "R_0402_1005Metric"),
    13: ("R12 R13 R14 R15 R16 R17 R18", "R_0402_1005Metric", ["R_0402_1005Metric_Pad0.72x0.64mm_HandSolder"], ["R_0603_1608Metric"], "R_0402_1005Metric"),
    17: ("U1", "QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm", ["QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm_ThermalVias"], ["QFN-56-1EP_7x7mm_P0.4mm_EP5.6x5.6mm"], "QFN-56-1EP_7x7mm_P0.4mm_EP5.6x5.6mm"),
    18: ("U2", "SOT-23-5", ["SOT-23-5_HandSoldering"], ["SOT-23-6"], "SOT-23-5"),
    19: ("U3", "SOIC-8_5.23x5.23mm_P1.27mm", ["SOIC-8_5.275x5.275mm_P1.27mm"], ["SOIC-8_3.9x4.9mm_P1.27mm", "SOIC-8_7.5x5.85mm_P1.27mm"], "SOIC-8_3.9x4.9mm_P1.27mm"),
    20: ("U4", "SOT-23-6", ["SOT-23-6_Handsoldering"], ["SOT-23-5"], "SOT-23-6"),
    21: ("Y1", "Crystal_SMD_3225-4Pin_3.2x2.5mm", ["Crystal_SMD_3225-4Pin_3.2x2.5mm_HandSoldering"], [], "Crystal_SMD_3225-4Pin_3.2x2.5mm"),
}


def propose(strategy, rng):
    choice = {}
    for ln, (refs, pref, var, wrong, naive) in LINES.items():
        if strategy == "preferred":
            c = pref
        elif strategy == "hand":
            c = var[0] if var else pref
        elif strategy == "naive":
            c = naive
        else:
            r = rng.random()
            c = rng.choice(wrong) if (wrong and r < 0.12) else (rng.choice(var) if (var and r < 0.5) else pref)
        choice[ln] = c
    u3_pads = "ul" if strategy in ("preferred", "hand") else rng.choice(["ul", "ul", "kicad"])
    if strategy == "naive":
        u3_pads = "kicad"
    fp = {ref: choice[ln] for ln, (refs, *_rest) in LINES.items() for ref in refs.split()}
    return {"strategy": strategy, "lines": choice, "fp": fp, "u3_pads": u3_pads}


def propose_single(ln, kind):
    """Our preferred build with exactly one BOM line changed (a sensitivity test)."""
    refs, pref, var, wrong, naive = LINES[ln]
    choice = {k: v[1] for k, v in LINES.items()}
    choice[ln] = var[0] if kind == "variant" else wrong[0]
    fp = {ref: choice[k] for k, (rs, *_r) in LINES.items() for ref in rs.split()}
    return {"strategy": f"one-{kind}", "changed_line": ln, "lines": choice, "fp": fp, "u3_pads": "ul"}


def propose_ai():
    """Proposals written by an AI (explore/ai_proposals.json). Untrusted, like every proposer."""
    path = os.path.join(ROOT, "explore", "ai_proposals.json")
    out = []
    if not os.path.exists(path):
        return out
    for p in json.load(open(path))["proposals"]:
        choice = {k: v[1] for k, v in LINES.items()}
        for ln, fpname in p["changes"].items():
            choice[int(ln)] = fpname
        fp = {ref: choice[k] for k, (rs, *_r) in LINES.items() for ref in rs.split()}
        out.append({"strategy": "ai", "name": p["name"], "rationale": p["rationale"], "lines": choice, "fp": fp, "u3_pads": "ul"})
    return out


def pad_area_mm2(path):
    b = pcbnew.LoadBoard(path)
    a = 0.0
    for fp in b.GetFootprints():
        for p in fp.Pads():
            s = p.GetSize()
            a += pcbnew.ToMM(s.x) * pcbnew.ToMM(s.y)
    return a


def judge(i, combo, workdir):
    grid = os.path.join(workdir, f"grid_{i:03d}.kicad_pcb")
    path = os.path.join(workdir, f"combo_{i:03d}.kicad_pcb")
    build_pcb.build(grid, combo=combo)
    layout_pcb.place_like(grid, REFERENCE, path)      # same placement as our board, footprints swapped in place
    p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "leancheck.py"), path, "--json"],
                       capture_output=True, text=True, cwd=ROOT)
    rep = json.loads(p.stdout.strip().splitlines()[-1])
    return {**combo, "id": i, "verdict": rep["overall"], "certified": rep["certified"], "rows": rep["rows"],
            "issues": rep["issues"], "fit_issues": rep["fit_issues"], "envelope": rep["envelope"],
            "no_collision_theorem": rep["no_collision_theorem"], "pad_area_mm2": round(pad_area_mm2(path), 3)}


def main():
    n, out = int(sys.argv[1]), sys.argv[2]
    rng = random.Random(20261121)
    combos = [propose("preferred", rng), propose("hand", rng), propose("naive", rng)] + propose_ai()
    for ln, (refs, pref, var, wrong, naive) in LINES.items():      # one change at a time
        if var:
            combos.append(propose_single(ln, "variant"))
        if wrong:
            combos.append(propose_single(ln, "wrong"))
    while len(combos) < n:
        combos.append(propose("random", rng))
    seen, uniq = set(), []
    for c in combos:
        k = json.dumps([c["fp"], c["u3_pads"]], sort_keys=True)
        if k not in seen or c["strategy"] == "ai":
            seen.add(k)
            uniq.append(c)
    with tempfile.TemporaryDirectory() as wd:
        results = [None] * len(uniq)
        # pcbnew is not thread-safe: build the boards one by one, then let Lean judge 4 at a time
        paths = []
        for i, c in enumerate(uniq):
            grid, path = os.path.join(wd, f"grid_{i:03d}.kicad_pcb"), os.path.join(wd, f"combo_{i:03d}.kicad_pcb")
            build_pcb.build(grid, combo=c)
            layout_pcb.place_like(grid, REFERENCE, path)
            paths.append((path, round(pad_area_mm2(path), 3)))

        def run(i):
            p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "leancheck.py"), paths[i][0], "--json"],
                               capture_output=True, text=True, cwd=ROOT)
            rep = json.loads(p.stdout.strip().splitlines()[-1])
            return {**uniq[i], "id": i, "verdict": rep["overall"], "certified": rep["certified"], "rows": rep["rows"],
                    "issues": rep["issues"], "fit_issues": rep["fit_issues"], "envelope": rep["envelope"],
                    "no_collision_theorem": rep["no_collision_theorem"], "pad_area_mm2": paths[i][1]}

        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            results = list(ex.map(run, range(len(uniq))))
    llm = None
    json.dump({"results": results, "llm": llm}, open(out, "w"), indent=1)
    hist = {}
    for r in results:
        hist[(r["strategy"], r["verdict"])] = hist.get((r["strategy"], r["verdict"]), 0) + 1
    print(f"{len(results)} combos judged; all certified: {all(r['certified'] for r in results)}")
    print(hist)


if __name__ == "__main__":
    main()
