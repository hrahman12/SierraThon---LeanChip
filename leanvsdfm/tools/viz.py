#!/usr/bin/env python3
"""Figures for Lean vs DFM on the Sierrathon PCB (2-D and 3-D).

Data sources (nothing is invented):
  * explore/results.json      design-space exploration, every verdict certified by the Lean kernel
  * pcb/sierrathon.kicad_pcb  our board, read with KiCad's pcbnew API
  * the spec functions        evaluated with exactly the definitions proved in LeanVsDFM/Specs.lean
                              and Fixers.lean (ledMax_uA, ldoTj, crystalLoad, ADC corner, stack-up)

    python3 tools/viz.py explore/results.json ../assets/viz
"""
import json
import math
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- palette (dark mode): surface, ink, status (reserved), categorical slots ----
BG, INK, INK2, GRID, AXIS = "#1a1a19", "#f0efec", "#c3c2b7", "#2c2c2a", "#383835"
GOOD, WARN, CRIT = "#0ca30c", "#fab219", "#d03b3b"
STATUS = {"GREEN": (GOOD, "o", "✓ green: proved"), "YELLOW": (WARN, "^", "▲ yellow: action needed"),
          "RED": (CRIT, "X", "✕ red: not the intended design")}
BLUE, ORANGE, AQUA, YEL, MAG, GRN, VIO, RED = ("#3987e5", "#d95926", "#199e70", "#c98500",
                                               "#d55181", "#0ca30c", "#9085e9", "#e66767")
plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG, "text.color": INK,
    "axes.labelcolor": INK2, "axes.edgecolor": AXIS, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "font.family": ["Inter", "DejaVu Sans"],
    "font.size": 11, "axes.titlesize": 14, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "legend.frameon": False, "lines.linewidth": 2, "axes.spines.top": False, "axes.spines.right": False})


def save(fig, out, name):
    fig.savefig(os.path.join(out, name), dpi=170, bbox_inches="tight")
    plt.close(fig)
    print("  ", name)


def style3d(ax):
    for a in (ax.xaxis, ax.yaxis, ax.zaxis):
        a.set_pane_color((0.10, 0.10, 0.10, 1.0))
        a._axinfo["grid"]["color"] = GRID
        a.label.set_color(INK2)
    ax.tick_params(colors=INK2)


def status_legend(ax, keys=("GREEN", "YELLOW", "RED"), loc="upper left", **kw):
    h = [Line2D([], [], marker=STATUS[k][1], ls="", color=STATUS[k][0], markersize=9, label=STATUS[k][2]) for k in keys]
    ax.legend(handles=h, loc=loc, **kw)


# ---- the Lean definitions, mirrored exactly (see the .lean files named) ----
def ledMax_uA(r):                 # Fixers.ledMax_uA
    return (1550 * 1000000 + 950 * r - 1) // (950 * r)


def ldoTj(i_mA, vin_mV=5250):     # Fixers.ldoTj generalised over VBUS (θJA 250, ambient 50, Vout min 3.25 V)
    return 50 + 250 * (vin_mV - 3250) * i_mA / 1e6


def ldoTj_lean(i_mA):             # exactly Fixers.ldoTj (integer, rounded up), at VBUS 5.25 V
    return 50 + (250 * 2000 * i_mA + 999999) // 1000000


def crystalLoad(c_pF, stray_pF):  # Specs: series(C6, C7) + stray
    return c_pF / 2 + stray_pF


def adc_fc(r, c_uF, pi=math.pi):  # Specs.adc_filter_corner
    return 1 / (2 * pi * r * c_uF * 1e-6)


E24 = [100, 110, 120, 130, 150, 160, 180, 200, 220, 240, 270, 300, 330, 360, 390, 430, 470, 510, 560, 620, 680, 750, 820, 910]


def board_verdict(r):
    worst = "GREEN"
    for row in r["rows"]:
        if row["section"] in ("Board", "3D fit"):
            if row["color"] == "RED":
                return "RED"
            if row["color"] == "YELLOW":
                worst = "YELLOW"
    return worst


def classify_choice(ln, fpname, lines):
    refs, pref, var, wrong, naive = lines[int(ln)]
    return "pref" if fpname == pref else ("var" if fpname in var else "wrong")


# ===================================================================== figures
def fig_design_space_3d(res, out):
    fig = plt.figure(figsize=(9, 7))
    ax = fig.add_subplot(projection="3d")
    style3d(ax)
    for r in res:
        v = board_verdict(r)
        nvar = sum(1 for i in r["issues"] if "variantFootprint" in i)
        nred = sum(1 for i in r["issues"] if any(k in i for k in ("wrongNet", "strayNet", "polarity", "noPad")) or
                   ("wrongPackage" in i and "MFR:" not in i)) + len(r.get("fit_issues", []))
        c, m, _ = STATUS[v]
        ax.scatter(r["pad_area_mm2"], nvar, nred, color=c, marker=m, s=70, edgecolors=BG, linewidths=1.5, depthshade=False)
    ax.set_xlabel("total pad copper (mm²)", labelpad=10)
    ax.set_ylabel("variant footprints", labelpad=10)
    ax.set_zlabel("red findings (wrong part + 3D fit)", labelpad=8)
    ax.view_init(elev=22, azim=-58)
    ax.set_title("Design space: every proposed build, certified by Lean", pad=14)
    status_legend(ax, loc="upper left", bbox_to_anchor=(0.0, 0.95))
    save(fig, out, "01_design_space_3d.png")


def fig_pareto(res, out):
    fig, ax = plt.subplots(figsize=(9, 5.6))
    pts = []
    for r in res:
        v = board_verdict(r)
        y = sum(1 for i in r["issues"] if "variantFootprint" in i or "landPattern" in i)
        c, m, _ = STATUS[v]
        ax.scatter(r["pad_area_mm2"], y, color=c, marker=m, s=80, edgecolors=BG, linewidths=1.8, zorder=3)
        if v != "RED":
            pts.append((r["pad_area_mm2"], y, r))
    pts.sort(key=lambda t: (t[0], t[1]))
    front, best = [], math.inf
    for x, y, r in pts:
        if y < best:
            front.append((x, y, r))
            best = y
    if front:
        ax.plot([p[0] for p in front], [p[1] for p in front], color=INK2, lw=1.2, ls="--", zorder=2)
        x, y, r = front[0]
        ax.annotate(f"best certified build\n(strategy: {r['strategy']})", (x, y), xytext=(x + 1.2, y + 3),
                    color=INK, fontsize=10, arrowprops=dict(arrowstyle="-", color=INK2, lw=1))
    ax.set_xlabel("total pad copper on the board (mm²)")
    ax.set_ylabel("yellow findings (variant / non-manufacturer land patterns)")
    ax.set_title("Pareto view: fewer yellow findings vs pad copper")
    status_legend(ax, loc="upper right")
    save(fig, out, "02_pareto.png")


def fig_heatmap(res, lines, out):
    order = {"GREEN": 0, "YELLOW": 1, "RED": 2}
    res = sorted(res, key=lambda r: (order[board_verdict(r)], r["pad_area_mm2"]))
    cols = sorted(lines)
    colmap = {"pref": GOOD, "var": WARN, "wrong": CRIT}
    fig, ax = plt.subplots(figsize=(11, max(4, 0.22 * len(res) + 1.6)))
    ax.grid(False)
    for yi, r in enumerate(res):
        for xi, ln in enumerate(cols):
            k = classify_choice(ln, r["lines"][str(ln)], lines)
            ax.add_patch(Rectangle((xi + 0.06, yi + 0.08), 0.88, 0.84, color=colmap[k], lw=0))
        v = board_verdict(r)
        ax.text(len(cols) + 0.25, yi + 0.5, {"GREEN": "✓", "YELLOW": "▲", "RED": "✕"}[v], color=STATUS[v][0],
                va="center", fontsize=11, fontweight="bold")
    ax.set_xlim(0, len(cols) + 0.8)
    ax.set_ylim(len(res), 0)
    labels = [lines[ln][0].split()[0] + ("…" if len(lines[ln][0].split()) > 1 else "") for ln in cols]
    ax.set_xticks([i + 0.5 for i in range(len(cols))], labels, rotation=45, ha="right", fontsize=9)
    ax.set_yticks([i + 0.5 for i in range(len(res))], [f"#{r['id']:02d} {r['strategy']}" for r in res], fontsize=8)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.legend(handles=[Patch(color=GOOD, label="✓ preferred land pattern"), Patch(color=WARN, label="▲ variant"),
                       Patch(color=CRIT, label="✕ wrong package")], loc="upper left", bbox_to_anchor=(0, -0.12), ncol=3)
    ax.set_title("Every build × every BOM line (right: Lean board verdict)")
    save(fig, out, "03_choice_heatmap.png")


def fig_strategy(res, llm, out):
    strategies = ["preferred", "ai", "one-variant", "one-wrong", "hand", "naive", "random"]
    counts = {s: {k: 0 for k in ("GREEN", "YELLOW", "RED")} for s in strategies}
    for r in res:
        counts[r["strategy"]][board_verdict(r)] += 1
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.grid(axis="y", visible=False)
    for yi, s in enumerate(strategies):
        left = 0
        tot = sum(counts[s].values())
        for k in ("GREEN", "YELLOW", "RED"):
            w = counts[s][k]
            if w:
                ax.barh(yi, w - 0.06, left=left + 0.03, color=STATUS[k][0], height=0.6)
                ax.text(left + w / 2, yi, str(w), ha="center", va="center", color="#0b0b0b" if k == "YELLOW" else "#ffffff",
                        fontsize=10, fontweight="bold")
            left += w
        ax.text(left + 0.3, yi, f"{tot} builds", va="center", color=INK2, fontsize=9)
    ax.set_yticks(range(len(strategies)), strategies)
    ax.invert_yaxis()
    ax.set_xlabel("builds proposed (ai = proposals written by Claude, explore/ai_proposals.json)")
    ax.set_title("Who proposes good builds? (verdicts certified by Lean)")
    status_legend(ax, loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=3)
    save(fig, out, "04_proposer_strategies.png")


def fig_led(out):
    rs = np.arange(100, 1001)
    fig, ax = plt.subplots(figsize=(9, 5.4))
    ax.plot(rs, [ledMax_uA(int(r)) / 1000 for r in rs], color=BLUE, label="worst-case LED current  I(R)  [ledMax_uA]")
    for lim, lab in [(8.0, "8 mA pad drive"), (4.0, "4 mA default drive"), (50 / 7, "50 mA ÷ 7 LEDs")]:
        ax.axhline(lim, color=INK2, lw=1, ls="--")
        ax.text(1005, lim, lab, va="center", color=INK2, fontsize=9)
    for r in E24 + [1000]:
        if r > 1000:
            continue
        ok8 = ledMax_uA(r) <= 8000 and 7 * ledMax_uA(r) <= 50000
        ok4 = ledMax_uA(r) <= 4000 and 7 * ledMax_uA(r) <= 50000
        k = "GREEN" if ok4 else ("YELLOW" if ok8 else "RED")
        ax.scatter(r, ledMax_uA(r) / 1000, color=STATUS[k][0], marker=STATUS[k][1], s=60, edgecolors=BG, linewidths=1.5, zorder=4)
    for r, txt in [(330, "BOM: 330 Ω → 4.945 mA"), (240, "fixer @ 8 mA: 240 Ω"), (430, "fixer @ 4 mA: 430 Ω")]:
        ax.annotate(txt, (r, ledMax_uA(r) / 1000), xytext=(r + 60, ledMax_uA(r) / 1000 + 2.2), color=INK, fontsize=9,
                    arrowprops=dict(arrowstyle="-", color=INK2, lw=1))
    ax.set_xlim(100, 1000)
    ax.set_ylim(0, 17)
    ax.set_xlabel("series resistor R (Ω), E24 values marked")
    ax.set_ylabel("worst-case current per LED (mA)")
    ax.set_title("LED current vs resistor: what Lean proves (Fixers.lean)")
    h = [Line2D([], [], color=BLUE, label="I(R) = (3.35 − 1.8) V / (0.95 R)"),
         Line2D([], [], marker="o", ls="", color=GOOD, label="✓ ok at 4 mA and 8 mA"),
         Line2D([], [], marker="^", ls="", color=WARN, label="▲ ok only at 8 mA drive"),
         Line2D([], [], marker="X", ls="", color=CRIT, label="✕ over limits")]
    ax.legend(handles=h, loc="upper right")
    save(fig, out, "05_led_current.png")


def fig_ldo_3d(out):
    vin = np.linspace(4750, 5250, 40)
    cur = np.linspace(0, 300, 60)
    V, I = np.meshgrid(vin, cur)
    T = ldoTj(I, V)
    fig = plt.figure(figsize=(9.5, 7))
    ax = fig.add_subplot(projection="3d")
    style3d(ax)
    ax.plot_surface(V / 1000, I, T, cmap="Blues_r", alpha=0.85, linewidth=0, antialiased=True)
    ax.plot_surface(V / 1000, I, np.full_like(T, 125), color=CRIT, alpha=0.18, linewidth=0)
    i_lim = (125 - 50) * 1e6 / (250 * (V[0] - 3250))
    ax.plot(V[0] / 1000, i_lim, 125, color=CRIT, lw=2.5, label="Tj = 125 °C boundary")
    ax.scatter([5.25], [112], [ldoTj(112)], color=GOOD, marker="o", s=80, label=f"board budget 112 mA → {ldoTj_lean(112)} °C ✓")
    ax.scatter([5.25], [245], [ldoTj(245)], color=CRIT, marker="X", s=90, label=f"68 Ω LEDs 245 mA → {ldoTj_lean(245)} °C ✕")
    ax.set_xlabel("VBUS (V)", labelpad=8)
    ax.set_ylabel("load current (mA)", labelpad=8)
    ax.set_zlabel("AP2112 junction (°C)", labelpad=6)
    ax.view_init(elev=20, azim=-130)
    ax.set_title("AP2112 junction temperature surface (Specs/Fixers: ldoTj)", pad=12)
    ax.legend(loc="upper left", bbox_to_anchor=(0, 0.95))
    save(fig, out, "06_ldo_thermal_3d.png")


def fig_crystal(out):
    stray = np.linspace(0, 6, 200)
    fig, ax = plt.subplots(figsize=(9, 5.2))
    ax.axhspan(9, 11, color=GOOD, alpha=0.10, lw=0)
    ax.axvspan(2, 5, color=INK2, alpha=0.07, lw=0)
    ax.text(2.05, 21.3, "assumed board stray 2–5 pF", color=INK2, fontsize=9)
    ax.text(0.05, 11.15, "spec: 10 pF ± 1 pF", color=INK2, fontsize=9)
    for c, col in [(10, VIO), (12, AQUA), (15, BLUE), (18, ORANGE), (22, MAG)]:
        ax.plot(stray, crystalLoad(c, stray), color=col, label=f"C6 = C7 = {c} pF" + ("  (BOM)" if c == 15 else ""))
    ax.scatter([2.5], [crystalLoad(15, 2.5)], color=GOOD, marker="o", s=70, zorder=4, edgecolors=BG)
    ax.scatter([2.5], [crystalLoad(22, 2.5)], color=CRIT, marker="X", s=80, zorder=4, edgecolors=BG)
    ax.annotate("fixCrystalCaps 10 pF = 15 pF ✓", (2.5, 10), xytext=(3.4, 7.2), color=INK, fontsize=9,
                arrowprops=dict(arrowstyle="-", color=INK2, lw=1))
    ax.annotate("22 pF copy-paste: 13.5 pF ✕", (2.5, 13.5), xytext=(3.4, 16.5), color=INK, fontsize=9,
                arrowprops=dict(arrowstyle="-", color=INK2, lw=1))
    ax.set_xlabel("stray capacitance (pF)")
    ax.set_ylabel("load seen by Y1, C_L (pF)")
    ax.set_ylim(4, 22)
    ax.set_title("Crystal load vs stray for E12 caps (crystal_load_window, fixCrystalCaps)")
    ax.legend(loc="upper left", ncol=1, bbox_to_anchor=(0, 0.93))
    save(fig, out, "07_crystal_load.png")


def fig_crystal_3d(out):
    c = np.linspace(8, 24, 60)
    C6, C7 = np.meshgrid(c, c)
    CL = C6 * C7 / (C6 + C7) + 2.5
    fig = plt.figure(figsize=(9, 7))
    ax = fig.add_subplot(projection="3d")
    style3d(ax)
    ax.plot_surface(C6, C7, CL, cmap="Blues", alpha=0.85, linewidth=0)
    ax.contour(C6, C7, CL, levels=[9, 10, 11], colors=[WARN, GOOD, WARN], linewidths=2, offset=CL.min())
    ax.scatter([15], [15], [10], color=GOOD, s=80, marker="o", label="BOM 15/15 pF → 10.0 pF ✓")
    ax.scatter([22], [22], [13.5], color=CRIT, s=90, marker="X", label="22/22 pF → 13.5 pF ✕")
    ax.set_xlabel("C6 (pF)", labelpad=8)
    ax.set_ylabel("C7 (pF)", labelpad=8)
    ax.set_zlabel("C_L (pF)", labelpad=6)
    ax.view_init(elev=26, azim=-125)
    ax.set_title("Crystal load surface C_L(C6, C7) at 2.5 pF stray", pad=12)
    ax.legend(loc="upper left", bbox_to_anchor=(0, 0.95))
    save(fig, out, "08_crystal_surface_3d.png")


def fig_adc(out):
    r = np.linspace(170, 230, 240)
    c = np.linspace(1.8, 2.6, 240)
    R, C = np.meshgrid(r, c)
    F = adc_fc(R, C)
    fig, ax = plt.subplots(figsize=(9, 5.6))
    ax.grid(False)
    im = ax.pcolormesh(R, C, F, cmap="Blues", shading="auto")
    cs = ax.contour(R, C, F, levels=[313, 362, 424], colors=[INK, INK2, INK], linewidths=[1.6, 1, 1.6])
    ax.clabel(cs, fmt=lambda v: f"{v:.0f} Hz", colors=INK, fontsize=9)
    ax.add_patch(Rectangle((190, 1.98), 20, 0.44, fill=False, ec=GOOD, lw=2.2, ls="-"))
    ax.text(191, 2.44, "R4 ± 5 %  ×  C5 ± 10 %", color="#0b0b0b", fontsize=9, fontweight="bold")
    ax.scatter([200], [2.2], color=GOOD, marker="o", s=60, edgecolors=BG, zorder=4)
    cb = fig.colorbar(im, ax=ax, pad=0.02)
    cb.set_label("corner frequency f_c (Hz)", color=INK2)
    cb.ax.yaxis.set_tick_params(color=INK2)
    plt.setp(cb.ax.get_yticklabels(), color=INK2)
    ax.set_xlabel("R4 (Ω)")
    ax.set_ylabel("C5 (µF)")
    ax.set_title("ADC_AVDD filter: Lean proves 313 ≤ f_c ≤ 424 Hz on the whole box")
    save(fig, out, "09_adc_filter.png")


def fig_stackup(out):
    layers = [("mask", 500), ("L1 Cu", 1500), ("prepreg 1067×2", 4348), ("L2 Cu", None), ("core 0.047", 45600),
              ("L3 Cu", None), ("prepreg 1067×2", 4348), ("L4 Cu", 1500), ("mask", 500)]
    fig, axs = plt.subplots(2, 1, figsize=(10, 4.2), sharex=True)
    for ax, inner, title in [(axs[0], 600, "stack-up drawing: inner 0.5 oz"), (axs[1], 1370, "instructions: inner 1 oz")]:
        ax.grid(False)
        left = 0
        cols = {"mask": GRN, "Cu": ORANGE, "prepreg": AQUA, "core": BLUE}
        for name, t in layers:
            t = inner if t is None else t
            col = next(v for k, v in cols.items() if k in name)
            ax.barh(0, t / 1000 - 0.05, left=left / 1000 + 0.025, color=col, height=0.55)
            left += t
        ax.axvspan(55.8, 68.2, color=INK2, alpha=0.08)
        ax.axvline(62, color=INK2, lw=1, ls="--")
        ax.text(left / 1000 + 0.4, 0, f"{left / 1000:.1f} mil ✓", va="center", color=GOOD, fontsize=10, fontweight="bold")
        ax.set_yticks([0], [title])
        ax.set_ylim(-0.5, 0.5)
    axs[1].set_xlabel("cumulative thickness (mil); band = 62 mil ± 10 %")
    axs[0].set_title("Stack-up: both readings meet 62 mil ± 10 % (break2_both_readings_buildable)")
    axs[1].legend(handles=[Patch(color=GRN, label="mask"), Patch(color=ORANGE, label="copper"),
                           Patch(color=AQUA, label="prepreg"), Patch(color=BLUE, label="core")],
                  loc="upper left", bbox_to_anchor=(0, -0.45), ncol=4)
    save(fig, out, "10_stackup.png")


def _lean_bodies():
    """Every part's body box exactly as Lean computes it (Fit3D.bodyBox), in mm."""
    import subprocess
    import tempfile
    src = ('import LeanVsDFM\nopen LeanVsDFM\n#eval IO.println (String.intercalate "\\n" (PcbData.parts.map fun p =>\n'
           '  match Fit3D.bodyBox p with\n'
           '  | some b => s!"{p.ref} {b.x0} {b.y0} {b.x1} {b.y1} {p.height} {p.court.x0} {p.court.y0} {p.court.x1} {p.court.y1}"\n'
           '  | none => s!"{p.ref} - - - - 0 {p.court.x0} {p.court.y0} {p.court.x1} {p.court.y1}"))\n'
           '#eval IO.println ("OUTLINE " ++ String.intercalate ";" (PcbData.outline.map fun (x, y) => s!"{x},{y}"))\n')
    env = dict(os.environ, PATH=os.path.expanduser("~/.elan/bin") + os.pathsep + os.environ["PATH"])
    with tempfile.NamedTemporaryFile("w", suffix=".lean", delete=False) as f:
        f.write(src)
    out = subprocess.run(["lake", "env", "lean", f.name], cwd=ROOT, env=env, capture_output=True, text=True).stdout
    os.unlink(f.name)
    lines = out.strip().splitlines()
    outline = [tuple(int(v) / 1e6 for v in pt.split(",")) for pt in lines[-1].split(" ", 1)[1].split(";")]
    parts = []
    for l in lines[:-1]:
        t = l.split()
        body = None if t[1] == "-" else tuple(int(v) / 1e6 for v in t[1:5])
        parts.append((t[0], body, int(t[5]) / 1e6, tuple(int(v) / 1e6 for v in t[6:10])))
    return parts, outline


def _box3d(ax, x0, y0, x1, y1, z0, z1, color, alpha=0.95):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    faces = [[v[i] for i in f] for f in ((4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))]
    ax.add_collection3d(Poly3DCollection(faces, facecolor=color, edgecolor=BG, linewidths=0.4, alpha=alpha))


def fig_pcb_3d(out):
    parts, outline = _lean_bodies()
    standin = {"J1", "SW1", "SW2", "SW3"}
    fig = plt.figure(figsize=(11, 8))
    ax = fig.add_subplot(projection="3d")
    style3d(ax)
    ol = [(x, -y) for x, y in outline]
    ax.add_collection3d(Poly3DCollection([[(x, y, 0) for x, y in ol]], facecolor="#1f7a55", edgecolor=AQUA, alpha=0.35))
    for ref, body, h, court in parts:
        col = WARN if ref in standin else GOOD
        cx0, cy0, cx1, cy1 = court
        ax.plot([cx0, cx1, cx1, cx0, cx0], [-cy0, -cy0, -cy1, -cy1, -cy0], [0.01] * 5, color=INK2, lw=0.5, alpha=0.7)
        if body:
            x0, y0, x1, y1 = body
            _box3d(ax, x0, -y1, x1, -y0, 0, h, col)
    ax.set_xlim(-27, 27)
    ax.set_ylim(-24, 24)
    ax.set_zlim(0, 6)
    ax.set_zticks([0, 2, 4, 6])
    ax.set_box_aspect((54, 48, 14))
    ax.set_xlabel("x (mm)", labelpad=10)
    ax.set_ylabel("y (mm)", labelpad=10)
    ax.set_zlabel("height (mm)", labelpad=4)
    ax.view_init(elev=36, azim=-62)
    ax.set_title("What Lean checks: 49 measured bodies inside 54 courtyards on the hexagon outline", pad=10)
    h = [Line2D([], [], marker="s", ls="", color=GOOD, markersize=9, label="✓ body of the exact part"),
         Line2D([], [], marker="s", ls="", color=WARN, markersize=9, label="▲ library stand-in (J1 has no model)"),
         Line2D([], [], color=INK2, lw=0.8, label="courtyard (2D keep-out)")]
    ax.legend(handles=h, loc="upper left", bbox_to_anchor=(0, 0.93))
    save(fig, out, "11_pcb_3d_verdicts.png")


def fig_fit_margins(out):
    parts, _ = _lean_bodies()
    best = {}
    for ref, body, h, court in parts:
        if not body:
            continue
        slack = min(body[0] - court[0], court[2] - body[2], body[1] - court[1], court[3] - body[3])
        key = (tuple(sorted((round(body[2] - body[0], 3), round(body[3] - body[1], 3)))), round(h, 3))
        if key not in best or slack < best[key][1]:
            best[key] = (ref, slack, h, key[0])
    rows = sorted(best.values(), key=lambda r: r[1])
    fig, ax = plt.subplots(figsize=(9, 5.0))
    ax.grid(axis="y", visible=False)
    y = np.arange(len(rows))
    ax.barh(y, [r[1] for r in rows], height=0.55, color=BLUE)
    for i, r in enumerate(rows):
        ax.text(r[1] + 0.012, i, f"{r[1]:.3f} mm", va="center", color=INK2, fontsize=9)
    ax.set_yticks(y, [f"{r[0]}  ·  {r[3][1]:.2f} × {r[3][0]:.2f} × {r[2]:.2f} mm" for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, max(r[1] for r in rows) * 1.18)
    ax.set_xlabel("smallest gap between the measured 3D body and its courtyard edge (mm); below 0 would be a red finding")
    ax.set_title("2D → 3D slack: every measured body fits inside its courtyard")
    save(fig, out, "13_fit_margins.png")


def fig_proofs(axfile, out):
    data = json.load(open(axfile))
    mods = list(data)
    none_ = [data[m]["none"] for m in mods]
    some = [data[m]["standard"] for m in mods]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    ax.grid(axis="x", visible=False)
    x = np.arange(len(mods))
    ax.bar(x, none_, color=BLUE, width=0.6, label="no axioms at all")
    ax.bar(x, some, bottom=none_, color=VIO, width=0.6, label="standard axioms only (propext / Quot.sound / choice)")
    for i, (a, b2) in enumerate(zip(none_, some)):
        ax.text(i, a + b2 + 0.4, str(a + b2), ha="center", color=INK, fontsize=10, fontweight="bold")
    ax.set_xticks(x, mods)
    ax.set_ylabel("theorems")
    ax.set_title(f"{sum(none_) + sum(some)} kernel-checked theorems · 0 sorry · 0 native_decide")
    ax.set_ylim(0, max(a + b2 for a, b2 in zip(none_, some)) + 4)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
    save(fig, out, "12_lean_proofs.png")


def main():
    res_file, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    data = json.load(open(res_file))
    res = data["results"]
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from explore import LINES
    fig_design_space_3d(res, out)
    fig_pareto(res, out)
    fig_heatmap(res, LINES, out)
    fig_strategy(res, data.get("llm"), out)
    fig_led(out)
    fig_ldo_3d(out)
    fig_crystal(out)
    fig_crystal_3d(out)
    fig_adc(out)
    fig_stackup(out)
    fig_pcb_3d(out)
    fig_fit_margins(out)
    ax = os.path.join(ROOT, "explore", "axioms.json")
    if os.path.exists(ax):
        fig_proofs(ax, out)


if __name__ == "__main__":
    main()
