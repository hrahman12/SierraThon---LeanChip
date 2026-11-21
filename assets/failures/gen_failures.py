#!/usr/bin/env python3
"""Draw the six failure modes as schematics: BROKEN (top) vs FIXED BY LEAN (bottom).

Every number on these drawings is a theorem in leanvsdfm/LeanVsDFM/Fixers.lean.
    python3 assets/failures/gen_failures.py      (needs: pip install schemdraw)
"""
import os

import schemdraw
import schemdraw.elements as elm
from schemdraw import flow

BG, FG, DIM = "#0B1A33", "#C9D3DC", "#5B6B86"
RED, GREEN, LAV = "#FF6B5E", "#2DD4BF", "#B9A7FF"
OUT = os.path.dirname(os.path.abspath(__file__))
W = 13.0          # canvas width (drawing units)
DY = -6.6         # vertical offset of the FIXED half


def drawing():
    schemdraw.config(bgcolor=BG, color=FG, font="JetBrains Mono", fontsize=12, lw=1.6)
    d = schemdraw.Drawing(show=False)
    return d


def text(d, x, y, s, color=FG, size=12, halign="left"):
    d.add(elm.Label().at((x, y)).label(s, color=color, fontsize=size, halign=halign))


def frame(d, broken_title, broken_lines, fixed_title, fixed_lines, theorems, top=1.6):
    """Titles, notes, divider, and invisible corners so nothing is clipped."""
    text(d, 0, top, broken_title, RED, 15)
    for i, s in enumerate(broken_lines):
        text(d, 0, -2.9 - 0.55 * i, s, RED, 11)
    d.add(elm.Line(color=DIM, ls=":").at((0, -4.25)).to((W, -4.25)))
    text(d, 0, top + DY + 0.2, fixed_title, GREEN, 15)
    for i, s in enumerate(fixed_lines):
        text(d, 0, -2.9 + DY - 0.55 * i, s, GREEN, 11)
    text(d, 0, -2.9 + DY - 0.55 * len(fixed_lines), theorems, LAV, 10)
    d.add(elm.Line(color=BG).at((-0.3, top + 0.6)).to((W + 0.3, top + 0.6)))
    d.add(elm.Line(color=BG).at((-0.3, -4.6 + DY)).to((W + 0.3, -4.6 + DY)))


# ---------------------------------------------------------------- 1 crystal
def crystal(d, y, cap, col):
    x0 = 1.2
    d.add(elm.Line().at((x0, y)).right(1.4))
    text(d, x0 - 0.2, y, "XIN", LAV, 12, "right")
    a = d.here
    d.add(elm.Crystal().right(2.6))
    text(d, a[0] + 1.3, y + 0.9, "Y1  12 MHz · ABM8 · C_L = 10 pF", FG, 11, "center")
    b = d.here
    d.add(elm.Line().right(1.4))
    text(d, b[0] + 1.6, y, "XOUT", LAV, 12, "left")
    d.add(elm.Capacitor().at(a).down(1.6).color(col))
    d.add(elm.Ground())
    text(d, a[0] - 0.3, y - 0.8, f"C6 = {cap} pF", col, 12, "right")
    d.add(elm.Capacitor().at(b).down(1.6).color(col))
    d.add(elm.Ground())
    text(d, b[0] + 0.3, y - 0.8, f"C7 = {cap} pF", col, 12, "left")


def fig_crystal():
    d = drawing()
    crystal(d, 0, 22, RED)
    crystal(d, DY, 15, GREEN)
    frame(d, "BROKEN: 22 pF caps copied from a 20 pF-crystal reference design",
          ["C_L = 22·22/(22+22) + 2.5 pF stray = 13.5 pF ≠ 10 pF",
           "crystal pulled off frequency → clock error, USB timing margin lost"],
          "FIXED BY LEAN: fixCrystalCaps (10 pF) = 15 pF",
          ["C_L = 15·15/(15+15) + 2.5 = 10.0 pF ✓   (smallest E12 value that works)"],
          "crystal_fails · crystal_found · crystal_sound · crystal_minimal · crystal_design_ok")
    d.save(os.path.join(OUT, "f1_crystal.svg"))


# ---------------------------------------------------------------- 2 LED
def led(d, y, r, rcol, drive, dcol):
    d.add(elm.Dot().at((1.6, y)))
    text(d, 1.4, y, "GPIO17", LAV, 12, "right")
    d.add(elm.Line().right(0.6))
    p = d.here
    d.add(elm.Resistor().right(2.4).color(rcol))
    text(d, p[0] + 1.2, y + 0.75, f"R12 = {r} Ω", rcol, 12, "center")
    q = d.here
    d.add(elm.LED().right(2.2))
    text(d, q[0] + 1.1, y + 0.85, "D3 red 0603", FG, 11, "center")
    d.add(elm.Line().right(0.6))
    d.add(elm.Ground())
    text(d, 8.6, y, f"pad drive = {drive}", dcol, 12, "left")


def fig_led():
    d = drawing()
    led(d, 0, 68, RED, "4 mA (default)", RED)
    led(d, DY, 330, GREEN, "8 mA (firmware)", GREEN)
    frame(d, "BROKEN: 68 Ω chosen for a brighter LED",
          ["I = (3.35 − 1.8) V / (0.95 · 68 Ω) = 23.99 mA per pin  >  8 mA",
           "7 LEDs = 168 mA ≫ 50 mA GPIO budget → pads overloaded"],
          "FIXED BY LEAN: keep R = 330 Ω (BOM is fixed), set 8 mA pad drive",
          ["I ≤ 4.945 mA ≤ 8 mA and 7 · I = 34.6 mA ≤ 50 mA ✓",
           "fixer also proves: smallest safe E24 = 240 Ω at 8 mA, 430 Ω at 4 mA"],
          "led_fails · led_design · led_found_8mA · led_found_4mA · led_sound · led_minimal_8mA")
    d.save(os.path.join(OUT, "f2_led.svg"))


# ---------------------------------------------------------------- 3 Type-C Rd
def cc(d, y, r, col):
    d.add(elm.Dot().at((2.2, y)))
    text(d, 2.0, y, "J1 CC1 (A5)", LAV, 12, "right")
    d.add(elm.Line().right(2.0))
    p = d.here
    d.add(elm.Resistor().down(1.8).color(col))
    d.add(elm.Ground())
    text(d, p[0] + 0.5, y - 0.9, f"R1 = {r}", col, 12, "left")
    text(d, 7.2, y, "USB-C source  →  CC  →  Rd to GND", FG, 11, "left")


def fig_cc():
    d = drawing()
    cc(d, 0, "10 kΩ", RED)
    cc(d, DY, "5.1 kΩ", GREEN)
    frame(d, "BROKEN: 10 kΩ pasted where Rd belongs",
          ["10 kΩ ∉ Rd = 5.1 kΩ ± 10 %  (USB Type-C spec)",
           "a C-to-C charger never detects a sink → VBUS stays off"],
          "FIXED BY LEAN: fixRd = 5.1 kΩ",
          ["5.1 kΩ ± 5 % = 4.845–5.355 kΩ ⊂ 4.59–5.61 kΩ ✓   (the only E24 value that fits)"],
          "rd_fails · rd_found · rd_sound · rd_unique")
    d.save(os.path.join(OUT, "f3_typec_rd.svg"))


# ---------------------------------------------------------------- 4 LDO thermal
def ldo(d, y, load, col):
    d.add(elm.Dot().at((1.8, y)))
    text(d, 1.6, y, "VBUS ≤ 5.25 V", LAV, 12, "right")
    d.add(elm.Line().right(1.0))
    reg = d.add(elm.Ic(pins=[elm.IcPin(name="VIN", side="left"), elm.IcPin(name="VOUT", side="right"),
                             elm.IcPin(name="GND", side="bottom")], size=(3.0, 1.6), label="AP2112\n3.3 V",
                       pinspacing=1.0).anchor("VIN"))
    d.add(elm.Ground().at(reg.GND))
    d.add(elm.Line().at(reg.VOUT).right(1.6))
    p = d.here
    text(d, p[0] - 0.8, y + 0.45, "+3.3V", LAV, 12, "center")
    d.add(elm.SourceI().down(1.8).color(col))
    d.add(elm.Ground())
    text(d, p[0] + 0.7, y - 0.9, f"load = {load} mA", col, 12, "left")


def fig_ldo():
    d = drawing()
    ldo(d, 0, 245, RED)
    ldo(d, DY, 112, GREEN)
    frame(d, "BROKEN: 68 Ω LEDs push the regulator load to 245 mA",
          ["Tj = 50 °C + 250 °C/W · 2.0 V · 0.245 A = 173 °C  >  125 °C",
           "thermal shutdown → brown-out / reset loop"],
          "FIXED BY LEAN: load ≤ fixLdoLoad = 150 mA; real budget 112 mA",
          ["Tj = 50 + 250 · 2.0 · 0.112 = 106 °C < 125 °C ✓"],
          "ldo_fails · ldo_found · ldo_sound · ldo_design_ok")
    d.save(os.path.join(OUT, "f4_ldo_thermal.svg"))


# ---------------------------------------------------------------- 5/6 block chains
def chain(d, y, blocks):
    x = 0.4
    prev = None
    for label, w, col, arrow_label in blocks:
        if prev is not None:
            a = d.add(flow.Arrow().at(prev.E).right(0.8))
            if arrow_label:
                text(d, prev.E[0] + 0.4, y + 0.45, arrow_label[0], arrow_label[1], 11, "center")
        b = d.add(flow.Box(w=w, h=1.1).at((x, y) if prev is None else d.here).anchor("W").label(label).color(col))
        prev = b
        x = b.E[0] + 0.8


def fig_pll():
    d = drawing()
    chain(d, 0, [("XOSC\n12 MHz", 2.2, FG, None), ("× FBDIV\n100", 2.2, RED, None),
                 ("÷ 6 ÷ 4", 2.2, RED, None), ("clk_usb\n50 MHz", 2.4, RED, None)])
    chain(d, DY, [("XOSC\n12 MHz", 2.2, FG, None), ("× FBDIV\n64", 2.2, GREEN, None),
                  ("÷ 4 ÷ 4", 2.2, GREEN, None), ("clk_usb\n48.000 MHz", 2.4, GREEN, None)])
    frame(d, "BROKEN: POSTDIV 6 × 4",
          ["12 MHz · 100 / (6 · 4) = 50 MHz ≠ 48 MHz → USB will not enumerate"],
          "FIXED BY LEAN: fixPLL (48 MHz) = (64, 4, 4)",
          ["12 · 64 / 16 = 48 MHz exactly; VCO 768 MHz ∈ [750, 1600] ✓  (SDK's 100/5/5 also proved)"],
          "pll_fails · pll_found · pll_sound · pll_design_ok")
    d.save(os.path.join(OUT, "f5_usb_pll.svg"))


def fig_qspi():
    d = drawing()
    chain(d, 0, [("clk_sys\n300 MHz", 2.4, FG, None), ("÷ 2", 1.6, RED, None),
                 ("U3 W25Q128JV\nmax 133 MHz", 3.4, RED, ("150 MHz", RED))])
    chain(d, DY, [("clk_sys\n300 MHz", 2.4, FG, None), ("÷ 4", 1.6, GREEN, None),
                  ("U3 W25Q128JV\nmax 133 MHz", 3.4, GREEN, ("75 MHz", GREEN))])
    frame(d, "BROKEN: clk_sys overclocked to 300 MHz, QSPI divider left at 2",
          ["150 MHz > 133 MHz → corrupted execute-in-place reads, random crashes"],
          "FIXED BY LEAN: fixQspiDiv (300 MHz) = 4",
          ["75 MHz ≤ 133 MHz, divider even ✓   (shipping: 125 MHz ÷ 2 = 62.5 MHz ✓)"],
          "qspi_fails · qspi_found · qspi_sound · qspi_design_ok")
    d.save(os.path.join(OUT, "f6_qspi.svg"))


if __name__ == "__main__":
    fig_crystal(); fig_led(); fig_cc(); fig_ldo(); fig_pll(); fig_qspi()
    print("wrote", sorted(f for f in os.listdir(OUT) if f.endswith(".svg")))
