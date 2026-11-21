#!/usr/bin/env python3
"""Mark where the supplied Sierrathon package breaks, on the official files themselves.

    python3 tools/annotate_breaks.py <Schematic.pdf> <Stack-Up.png> <BOM.xlsx> <out_dir>

Outputs break_schematic.png, break_stackup.png, break_bom.png. Nothing is redrawn: the
schematic and stack-up are the organisers' own pages with callouts on top, and the BOM table
is the spreadsheet's rows verbatim. Each callout names the Lean theorem that proves it.
"""
import os
import subprocess
import sys
import tempfile

import openpyxl
from PIL import Image, ImageDraw, ImageFont

RED, YEL, LAV, INK, BG = (208, 59, 59), (214, 158, 46), (98, 80, 214), (11, 11, 11), (255, 255, 255)


def font(size, bold=False):
    for p in ["/root/.fonts/SpaceGrotesk[wght].ttf", "/usr/share/fonts/opentype/inter/Inter-Bold.otf" if bold else
              "/usr/share/fonts/opentype/inter/Inter-Regular.otf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if os.path.exists(p):
            f = ImageFont.truetype(p, size)
            if "SpaceGrotesk" in p:
                try:
                    f.set_variation_by_axes([700 if bold else 500])
                except Exception:
                    pass
            return f
    return ImageFont.load_default()


def box(d, xy, color, n=None, width=5):
    d.rounded_rectangle(xy, radius=14, outline=color, width=width)
    if n is not None:
        x, y = xy[0], xy[1]
        d.ellipse((x - 26, y - 26, x + 26, y + 26), fill=color)
        d.text((x, y), str(n), fill=BG, font=font(30, True), anchor="mm")


def legend(img, items, title):
    """Append a legend strip under the image."""
    pad, lh = 30, 46
    h = pad * 2 + 54 + lh * len(items)
    out = Image.new("RGB", (img.width, img.height + h), BG)
    out.paste(img, (0, 0))
    d = ImageDraw.Draw(out)
    d.line((0, img.height, img.width, img.height), fill=(200, 200, 200), width=2)
    d.text((pad, img.height + pad), title, fill=INK, font=font(34, True))
    y = img.height + pad + 60
    for n, color, text in items:
        d.ellipse((pad, y, pad + 36, y + 36), fill=color)
        d.text((pad + 18, y + 18), str(n), fill=BG, font=font(22, True), anchor="mm")
        d.text((pad + 52, y + 2), text, fill=INK, font=font(25))
        y += lh
    return out


def schematic(pdf, out):
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["pdftoppm", "-r", "200", "-png", pdf, os.path.join(td, "p")], check=True)
        img = Image.open(os.path.join(td, sorted(os.listdir(td))[0])).convert("RGB")
    assert img.size == (2200, 1700), img.size
    img = img.crop((0, 0, 2200, 1410))               # the drawing frame; the rest of the page is blank
    d = ImageDraw.Draw(img)
    box(d, (1790, 455, 2135, 1175), RED, 1)          # the seven LEDs D3..D9 with R12..R18
    box(d, (1895, 235, 2125, 440), RED, None, 3)     # the "LED Placement" box (7 positions)
    box(d, (1870, 480, 1945, 1150), YEL, 3, 4)       # R12..R18, 330 ohm
    box(d, (535, 760, 800, 830), LAV, 4)             # USB_N/USB_P -> R5/R6 -> USBR_N/USBR_P
    box(d, (655, 120, 965, 210), LAV, None, 4)       # D_P/D_N -> U4 -> USB_P/USB_N
    box(d, (210, 210, 335, 270), LAV, None, 4)       # D_P/D_N at the connector
    img = legend(img, [
        (1, RED, "Schematic draws 7 LEDs (D3–D9). BOM row 5 says Qty 8.   Lean: break1_only_row5, break1_schematic_has_7_leds"),
        (3, YEL, "R12–R18 = 330 Ω gives up to 4.945 mA, above the RP2040's 4 mA default pad drive.   Lean: break3_default_drive_fails"),
        (4, LAV, "USB_P/N, USBR_P/N, D_P/D_N must be 5 / 4 mil (90 Ω). A global 6 mil DFM rule flags them.   Lean: break4_*"),
    ], "Where the supplied schematic breaks (official Sierrathon_Schematic.pdf, callouts added)")
    img.save(out)


def stackup(png, out):
    img = Image.open(png).convert("RGB")
    s = 2200 / img.width
    img = img.resize((2200, int(img.height * s)), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    k = img.width / 1898.0                           # coordinates below were read at 1898 px width
    r = lambda a, b, c, e: (a * k, b * k, c * k, e * k)
    box(d, r(62, 176, 505, 232), RED, 2)             # L2 / L3 rows: 0.5oz
    box(d, r(780, 640, 1335, 790), LAV, 4)           # rows c, d: LW 5.00, spacing 4.00
    box(d, r(1462, 640, 1612, 790), LAV, None, 4)    # 89.7 ohm
    img = legend(img, [
        (2, RED, "Inner layers L2/L3 are drawn as 0.5 oz. The instructions say \"Internal copper thickness: 1 oz\".   Lean: break2_conflict"),
        (2, RED, "Both readings still meet 62 mil ± 10 % (59.5 and 61.0 mil), so it needs a question to the fab.   Lean: break2_both_readings_buildable"),
        (4, LAV, "90 Ω pairs are 5.00 / 4.00 mil (simulated 89.7 Ω), below the 6 mil rule for other nets.   Lean: break4_impedance_in_tolerance"),
    ], "Where the supplied stack-up breaks (official Sierrathon Stack-Up.png, callouts added)")
    img.save(out)


def bom(xlsx, out):
    ws = openpyxl.load_workbook(xlsx, data_only=True).active
    rows = [r for r in ws.iter_rows(values_only=True) if any(c is not None for c in r)]
    cols, widths = [0, 1, 2, 3, 4, 5], [90, 560, 80, 200, 400, 420]
    W, rh, pad = sum(widths) + 60, 46, 30
    img = Image.new("RGB", (W, rh * len(rows) + pad * 2), BG)
    d = ImageDraw.Draw(img)
    for i, r in enumerate(rows):
        y = pad + i * rh
        bad = i > 0 and r[0] == 5
        if i == 0:
            d.rectangle((pad, y, W - pad, y + rh), fill=(235, 235, 240))
        if bad:
            d.rectangle((pad, y, W - pad, y + rh), fill=(253, 232, 232))
        x = pad
        for c, w in zip(cols, widths):
            txt = "" if r[c] is None else str(r[c])
            d.text((x + 10, y + rh / 2), txt[:44], fill=RED if (bad and c == 2) else INK, font=font(22, i == 0 or (bad and c == 2)), anchor="lm")
            x += w
        d.line((pad, y + rh, W - pad, y + rh), fill=(215, 215, 220), width=1)
        if bad:
            box(d, (pad + 650 - 6, y + 3, pad + 650 + 86, y + rh - 3), RED, None, 4)
    img = legend(img, [
        (1, RED, "Row 5 says Qty 8 but lists 7 designators (D3–D9); every other row is consistent.   Lean: break1_only_row5, break1_row5"),
        (1, RED, "Fix: set the quantity to the designator count. Only row 5 changes (8 → 7).   Lean: break1_fix_changes_only_row5"),
    ], "Where the supplied BOM breaks (Sierrathon_BOM.xlsx, rows verbatim)")
    img.save(out)


if __name__ == "__main__":
    pdf, png, xlsx, outdir = sys.argv[1:5]
    os.makedirs(outdir, exist_ok=True)
    schematic(pdf, os.path.join(outdir, "break_schematic.png"))
    stackup(png, os.path.join(outdir, "break_stackup.png"))
    bom(xlsx, os.path.join(outdir, "break_bom.png"))
    print("wrote 3 images to", outdir)
