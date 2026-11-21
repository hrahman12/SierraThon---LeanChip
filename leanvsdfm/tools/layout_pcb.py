#!/usr/bin/env python3
"""Compact layout of the Sierrathon board: a flat-top hexagon with every part placed.

Anchors are placed by hand where the schematic dictates (USB-C at the edge, RP2040 central,
flash beside its QSPI pins, crystal under XIN/XOUT, LED cluster in the schematic's "LED
Placement" pattern, M4 holes at hexagon vertices). Every other part is auto-placed at the
nearest free spot to the pads it connects to, with courtyards kept apart by GAP and inside the
outline by MARGIN. Nets and footprints are untouched, so the Lean verdict is unchanged.

    python3 tools/layout_pcb.py <in.kicad_pcb> <out.kicad_pcb>
"""
import math
import sys

import pcbnew

R = 26.0                     # hexagon circumradius (mm): 52 mm across corners, 45 mm across flats
H = R * math.sqrt(3) / 2     # half the flat-to-flat height
GAP, MARGIN = 0.25, 0.4      # courtyard-to-courtyard and courtyard-to-edge clearance (mm)

ANCHORS = {   # ref: (x, y, rotation°), KiCad coordinates (y down), board centre at (0, 0)
    "J1": (0.0, -H + 3.6, 180), "U4": (0.0, -11.6, 0), "U1": (0.0, -2.2, 0), "U3": (-9.6, -5.9, 90),
    "Y1": (0.0, 5.4, 0),
    "D3": (-5.2, 10.6, 0), "D8": (5.2, 10.6, 0), "D4": (-5.2, 13.2, 0), "D9": (0.0, 13.2, 0),
    "D7": (5.2, 13.2, 0), "D5": (-5.2, 15.8, 0), "D6": (5.2, 15.8, 0),
    "MH1": (-20.2, 0.0, 0), "MH2": (20.2, 0.0, 0), "MH3": (-11.0, -15.5, 0), "MH4": (11.0, -15.5, 0),
}


def courtyard(fp):
    """Axis-aligned courtyard rectangle (mm) in board coordinates."""
    xs, ys = [], []
    for g in fp.GraphicalItems():
        if g.GetLayer() in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            bb = g.GetBoundingBox()
            xs += [bb.GetLeft(), bb.GetRight()]
            ys += [bb.GetTop(), bb.GetBottom()]
    if not xs:
        bb = fp.GetBoundingBox(False, False)
        xs, ys = [bb.GetLeft(), bb.GetRight()], [bb.GetTop(), bb.GetBottom()]
    return (pcbnew.ToMM(min(xs)), pcbnew.ToMM(min(ys)), pcbnew.ToMM(max(xs)), pcbnew.ToMM(max(ys)))


def inside_hex(rect, m=MARGIN):
    for x in (rect[0], rect[2]):
        for y in (rect[1], rect[3]):
            if abs(y) > H - m or math.sqrt(3) * abs(x) + abs(y) > math.sqrt(3) * R - 2 * m:
                return False
    return True


def overlaps(a, b, g=GAP):
    return not (a[2] + g <= b[0] or b[2] + g <= a[0] or a[3] + g <= b[1] or b[3] + g <= a[1])


def place(fp, x, y, rot):
    fp.SetOrientationDegrees(rot)
    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))


def finalize(b, dst):
    """3D models, outline and stack-up; then save."""
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    # Point every footprint at the STEP version of its KiCad library model (same file name).
    for f in b.GetFootprints():
        names = [str(mm.m_Filename) for mm in f.Models()]
        ms = f.Models()
        while len(ms):
            ms.pop()
        for n in names:
            mod = pcbnew.FP_3DMODEL()
            mod.m_Filename = n[:-4] + ".step" if n.endswith(".wrl") else n
            ms.push_back(mod)
    # U3: KiCad has no 3D model for the 208 mil SOIC; use the manufacturer model from the
    # supplied UltraLibrarian package (same origin and orientation as the footprint).
    if str(fps["U3"].GetFPID().GetLibItemName()) == "SOIC-8_5.23x5.23mm_P1.27mm":
        m = fps["U3"].Models()
        while len(m):
            m.pop()
        mod = pcbnew.FP_3DMODEL()
        mod.m_Filename = "${KICAD7_3DMODEL_DIR}/Package_SO.3dshapes/UL_W25Q128JVSIQ_SOIC_208MIL.step"
        m.push_back(mod)
    # hexagon outline on Edge.Cuts
    pts = [(R * math.cos(math.radians(a)), R * math.sin(math.radians(a))) for a in range(0, 360, 60)]
    for i in range(6):
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(pts[i][0]), pcbnew.FromMM(pts[i][1])))
        s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(pts[(i + 1) % 6][0]), pcbnew.FromMM(pts[(i + 1) % 6][1])))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(pcbnew.FromMM(0.1))
        b.Add(s)
    pcbnew.SaveBoard(dst, b)
    inject_stackup(dst)


def place_like(src, ref_path, dst):
    """Keep every part exactly where the reference layout has it (same position and rotation)."""
    b = pcbnew.LoadBoard(src)
    ref = pcbnew.LoadBoard(ref_path)
    pos = {f.GetReference(): (f.GetPosition(), f.GetOrientationDegrees()) for f in ref.GetFootprints()}
    for f in b.GetFootprints():
        p, r = pos[f.GetReference()]
        f.SetOrientationDegrees(r)
        f.SetPosition(pcbnew.VECTOR2I(p.x, p.y))
    finalize(b, dst)


# The Sierrathon stack-up (Stack-Up.png), written into the KiCad file. Thickness in mm
# (1 mil = 0.0254 mm): mask 0.5, L1 1.5, prepreg 4.348, L2 0.6, core 45.6, L3 0.6, prepreg 4.348,
# L4 1.5, mask 0.5 mil = 59.496 mil. KiCad 7's Python API does not expose the stack-up editor,
# so the block is inserted into the saved file and KiCad re-reads it.
STACKUP = """    (stackup
      (layer "F.SilkS" (type "Top Silk Screen") (color "White"))
      (layer "F.Paste" (type "Top Solder Paste"))
      (layer "F.Mask" (type "Top Solder Mask") (color "Green") (thickness 0.0127))
      (layer "F.Cu" (type "copper") (thickness 0.0381))
      (layer "dielectric 1" (type "prepreg") (thickness 0.1104392) (material "FR-370HR 1067 x2") (epsilon_r 3.65) (loss_tangent 0.02))
      (layer "In1.Cu" (type "copper") (thickness 0.01524))
      (layer "dielectric 2" (type "core") (thickness 1.15824) (material "FR-370HR 0.047") (epsilon_r 4.24) (loss_tangent 0.02))
      (layer "In2.Cu" (type "copper") (thickness 0.01524))
      (layer "dielectric 3" (type "prepreg") (thickness 0.1104392) (material "FR-370HR 1067 x2") (epsilon_r 3.65) (loss_tangent 0.02))
      (layer "B.Cu" (type "copper") (thickness 0.0381))
      (layer "B.Mask" (type "Bottom Solder Mask") (color "Green") (thickness 0.0127))
      (layer "B.Paste" (type "Bottom Solder Paste"))
      (layer "B.SilkS" (type "Bottom Silk Screen") (color "White"))
      (copper_finish "None")
      (dielectric_constraints yes)
    )
"""


def inject_stackup(path):
    s = open(path).read()
    if "(stackup" in s:
        a = s.index("(stackup")
        depth, i = 0, a
        while True:
            depth += s[i] == "("
            depth -= s[i] == ")"
            i += 1
            if depth == 0:
                break
        s = s[:a].rstrip(" ") + s[i:].lstrip("\n")
    k = s.index("(setup") + len("(setup")
    s = s[:k] + "\n" + STACKUP + s[k:].lstrip("\n")
    s = s.replace("(thickness 1.5748)", "(thickness 1.5111984)").replace("(thickness 1.6)", "(thickness 1.5111984)")
    open(path, "w").write(s)
    b = pcbnew.LoadBoard(path)          # KiCad validates and normalises the file
    pcbnew.SaveBoard(path, b)


def main(src, dst):
    b = pcbnew.LoadBoard(src)
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    placed = {}
    for ref, (x, y, r) in ANCHORS.items():
        place(fps[ref], x, y, r)
        placed[ref] = courtyard(fps[ref])
    def hole_ok(rect, m=MARGIN):
        cx, cy, r = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2, (rect[2] - rect[0]) / 2
        return abs(cy) <= H - r - m and (math.sqrt(3) * R - math.sqrt(3) * abs(cx) - abs(cy)) / 2 >= r + m

    for ref, rect in placed.items():
        ok = hole_ok(rect) if ref.startswith("MH") else inside_hex(rect)
        assert ref == "J1" or ok, f"anchor {ref} outside outline"
    for a in placed:
        for c in placed:
            assert a >= c or not overlaps(placed[a], placed[c]), f"anchors {a} and {c} overlap"

    def target(fp):
        nets = {p.GetNetname() for p in fp.Pads()} - {"", "GND"}
        pts = [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y))
               for r in placed for p in fps[r].Pads() if p.GetNetname() in nets]
        if not pts:
            return (0.0, 0.0)
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

    rest = [r for r in fps if r not in placed]
    rest.sort(key=lambda r: -(courtyard(fps[r])[2] - courtyard(fps[r])[0]) * (courtyard(fps[r])[3] - courtyard(fps[r])[1]))
    for ref in rest:
        fp = fps[ref]
        tx, ty = target(fp)
        best = None
        for k in range(0, 2400):                 # spiral search on a 0.2 mm grid
            ang = k * 0.5
            rad = 0.2 * math.sqrt(k) * 2.2
            x, y = tx + rad * math.cos(ang), ty + rad * math.sin(ang)
            for rot in (0, 90):
                place(fp, round(x, 2), round(y, 2), rot)
                rect = courtyard(fp)
                if inside_hex(rect) and all(not overlaps(rect, o) for o in placed.values()):
                    best = (round(x, 2), round(y, 2), rot, rect)
                    break
            if best:
                break
        if not best:
            raise SystemExit(f"could not place {ref}")
        place(fp, best[0], best[1], best[2])
        placed[ref] = best[3]

    finalize(b, dst)

    # report
    pairs = [(a, c) for a in placed for c in placed if a < c and overlaps(placed[a], placed[c], 0.0)]
    area = 3 * math.sqrt(3) / 2 * R * R
    used = sum((r[2] - r[0]) * (r[3] - r[1]) for r in placed.values())
    print(f"placed {len(placed)} parts in a {2 * R:.0f} × {2 * H:.1f} mm hexagon; courtyard overlaps: {len(pairs)}; "
          f"courtyard fill {100 * used / area:.0f} % of {area:.0f} mm²")


if __name__ == "__main__":
    if "--like" in sys.argv:
        place_like(sys.argv[1], sys.argv[sys.argv.index("--like") + 1], sys.argv[2])
    else:
        main(sys.argv[1], sys.argv[2])
