#!/usr/bin/env python3
"""Generate the Sierrathon Altium library (.PcbLib + .SchLib + .LibPkg)
through the altium-designer-mcp server (stdio JSON-RPC).

Footprint geometry is converted from KiCad's official footprint library
(IPC-7351B generator output). KiCad is Y-down, Altium is Y-up, so Y is negated.
Symbols are drawn to match the Sierrathon schematic pin names and numbers.
"""
import json, re, sys, os
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get("MCPCLIENT_DIR", str(HERE)))
from mcpclient import MCP  # noqa: E402

KICAD = Path(os.environ["KICAD_FP_DIR"])
OUT = HERE
PCBLIB = str(OUT / "Sierrathon.PcbLib")
SCHLIB = str(OUT / "Sierrathon.SchLib")

LAYER = {"F.SilkS": "Top Overlay", "F.Fab": "Top Assembly", "F.CrtYd": "Top Courtyard"}


def r3(v):
    return round(v + 0.0, 4)


def kicad_to_footprint(path, name, desc, ep_override=None):
    s = re.sub(r"\s+", " ", Path(path).read_text())
    pads, tracks, xs, ys = [], [], [], []
    for m in re.finditer(r"\(pad \"?([^\" ]*)\"? (\w+) (\w+) \(at ([-\d. ]+)\) \(size ([-\d. ]+)\)(.*?)(?=\(pad |\(fp_|\(model|$)", s):
        des, kind, shape, at, size, rest = m.groups()
        at = [float(v) for v in at.split()]
        w, h = [float(v) for v in size.split()]
        rot = at[2] if len(at) > 2 else 0.0
        if des == "":  # KiCad paste-only subdivisions of the EP -> skip
            continue
        if ep_override and des == ep_override[0]:
            w = h = ep_override[1]
        pad = {"designator": des, "x": r3(at[0]), "y": r3(-at[1]), "width": r3(w), "height": r3(h)}
        if rot:
            pad["rotation"] = rot
        if kind == "smd":
            pad["layer"] = "Top Layer"
            pad["shape"] = "rectangle" if des == "1" else "rounded_rectangle"
            if des != "1":
                pad["corner_radius_percent"] = 25
        else:
            d = re.search(r"\(drill ([-\d.]+)", rest)
            pad["layer"] = "Multi-Layer"
            pad["hole_size"] = float(d.group(1))
            pad["shape"] = "round"
            pad["is_plated"] = kind == "thru_hole"
        pads.append(pad)
    for m in re.finditer(r"\(fp_line \(start ([-\d. ]+)\) \(end ([-\d. ]+)\) \(layer \"?([\w.]+)\"?\) \(width ([\d.]+)\)", s):
        a, b, layer, wd = m.groups()
        (x1, y1), (x2, y2) = [float(v) for v in a.split()], [float(v) for v in b.split()]
        if layer == "F.CrtYd":
            xs += [x1, x2]; ys += [-y1, -y2]
            continue
        if layer in LAYER:
            tracks.append({"layer": LAYER[layer], "width": float(wd), "x1": r3(x1), "y1": r3(-y1), "x2": r3(x2), "y2": r3(-y2)})
    fp = {"name": name, "description": desc, "pads": pads, "tracks": tracks}
    if xs:
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        fp["regions"] = [{"layer": "Top Courtyard", "vertices": [
            {"x": x0, "y": y0}, {"x": x1, "y": y0}, {"x": x1, "y": y1}, {"x": x0, "y": y1}]}]
    return fp


FOOTPRINTS = [
    # (kicad file, altium name, description, ep_override)
    ("Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", "CAPC1005X55N", "Chip capacitor 0402 (1005 metric), IPC-7351B nominal", None),
    ("Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod", "RESC1005X40N", "Chip resistor 0402 (1005 metric), IPC-7351B nominal", None),
    ("Capacitor_SMD.pretty/C_0603_1608Metric.kicad_mod", "CAPC1608X87N", "Chip capacitor 0603 (1608 metric), IPC-7351B nominal", None),
    ("Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod", "RESC1608X55N", "Chip resistor 0603 (1608 metric), IPC-7351B nominal", None),
    ("Capacitor_SMD.pretty/C_0805_2012Metric.kicad_mod", "CAPC2012X125N", "Chip capacitor 0805 (2012 metric), IPC-7351B nominal", None),
    ("LED_SMD.pretty/LED_0603_1608Metric.kicad_mod", "LEDC1608X80N", "Chip LED 0603 (1608 metric). Pad 1 = cathode", None),
    ("Package_TO_SOT_SMD.pretty/SOT-23-5.kicad_mod", "SOT95P280X145-5N", "SOT-23-5 (SOT-25), 0.95 mm pitch", None),
    ("Package_TO_SOT_SMD.pretty/SOT-23-6.kicad_mod", "SOT95P280X145-6N", "SOT-23-6, 0.95 mm pitch", None),
    ("Package_SO.pretty/SOIC-8_5.23x5.23mm_P1.27mm.kicad_mod", "SOIC127P790X216-8N", "SOIC-8 208 mil (5.23 x 5.23 mm body), 1.27 mm pitch", None),
    ("Crystal.pretty/Crystal_SMD_3225-4Pin_3.2x2.5mm.kicad_mod", "XTAL_3225-4", "SMD crystal 3.2 x 2.5 mm, 4 pad (ABM8)", None),
    ("Package_DFN_QFN.pretty/QFN-56-1EP_7x7mm_P0.4mm_EP5.6x5.6mm.kicad_mod", "QFN40P700X700X90-57N", "QFN-56 7x7 mm 0.4 mm pitch, EP 3.2 x 3.2 mm (RP2040)", ("57", 3.2)),
    ("MountingHole.pretty/MountingHole_4.3mm_M4.kicad_mod", "MH_M4_NPTH", "M4 mounting hole, 4.3 mm NPTH", None),
]

# ---------- symbols ----------
def two_pin(name, prefix, desc, params, fp, n1="1", n2="2", body="rect", t1="passive", t2="passive"):
    sym = {"name": name, "designator_prefix": prefix, "description": desc, "parameters": params,
           "pins": [
               {"designator": "1", "name": n1, "electrical_type": t1, "length": 10, "orientation": "left", "x": -20, "y": 0},
               {"designator": "2", "name": n2, "electrical_type": t2, "length": 10, "orientation": "right", "x": 20, "y": 0}],
           "rectangles": [{"x1": -20, "y1": -5, "x2": 20, "y2": 5}]}
    if fp:
        sym["footprints"] = [{"name": fp, "library_path": "Sierrathon.PcbLib"}]
    return sym


def box(name, prefix, desc, params, fp, left, right, bottom=(), width=None, top=()):
    """left/right/bottom/top: list of (designator, name, type) — None = spacer."""
    rows = max(len(left), len(right))
    h = (rows + 1) * 10
    y_top = (h // 2 // 10) * 10
    wdt = width or 80
    pins = []
    for i, p in enumerate(left):
        if p: pins.append({"designator": p[0], "name": p[1], "electrical_type": p[2], "length": 20, "orientation": "left", "x": -wdt // 2, "y": y_top - 10 * (i + 1)})
    for i, p in enumerate(right):
        if p: pins.append({"designator": p[0], "name": p[1], "electrical_type": p[2], "length": 20, "orientation": "right", "x": wdt // 2, "y": y_top - 10 * (i + 1)})
    y_bot = y_top - h
    for i, p in enumerate(bottom):
        if p: pins.append({"designator": p[0], "name": p[1], "electrical_type": p[2], "length": 20, "orientation": "down", "x": -10 * (len(bottom) - 1) // 2 * 1 + 10 * i, "y": y_bot})
    for i, p in enumerate(top):
        if p: pins.append({"designator": p[0], "name": p[1], "electrical_type": p[2], "length": 20, "orientation": "up", "x": -10 * (len(top) - 1) // 2 + 10 * i, "y": y_top})
    sym = {"name": name, "designator_prefix": prefix, "description": desc, "parameters": params, "pins": pins,
           "rectangles": [{"x1": -wdt // 2, "y1": y_bot, "x2": wdt // 2, "y2": y_top, "filled": True}]}
    if fp:
        sym["footprints"] = [{"name": fp, "library_path": "Sierrathon.PcbLib"}]
    return sym


def P(value, mpn, mfr, desc, extra=None):
    ps = [{"name": "Value", "value": str(value)}, {"name": "Manufacturer", "value": mfr},
          {"name": "Manufacturer Part Number", "value": mpn}, {"name": "Description", "value": desc}]
    return ps + (extra or [])


NEEDS_FP = [{"name": "Footprint Status", "value": "PENDING - manufacturer land pattern required"}]

PW, IN, OUT_, IO, PS = "power", "input", "output", "bidirectional", "passive"

rp_left = [("1", "IOVDD", PW), ("10", "IOVDD", PW), ("22", "IOVDD", PW), ("33", "IOVDD", PW), ("42", "IOVDD", PW),
           ("49", "IOVDD", PW), ("48", "USB_VDD", PW), ("44", "VREG_VIN", PW), ("45", "VREG_VOUT", PW),
           ("23", "DVDD", PW), ("50", "DVDD", PW), ("43", "ADC_AVDD", PW), None, ("26", "RUN", IN),
           ("20", "XIN", IN), ("21", "XOUT", OUT_), ("24", "SWCLK", IN), ("25", "SWDIO", IO), None,
           ("46", "USB_DM", IO), ("47", "USB_DP", IO), None,
           ("56", "QSPI_SS_N", IO), ("52", "QSPI_SCLK", OUT_), ("53", "QSPI_SD0", IO), ("55", "QSPI_SD1", IO),
           ("54", "QSPI_SD2", IO), ("51", "QSPI_SD3", IO)]
gpio_pins = list(range(2, 10)) + list(range(11, 19)) + [27, 28, 29, 30, 31, 32, 34, 35, 36, 37, 38, 39, 40, 41]
rp_right = [(str(p), f"GPIO{i}" + (f"_ADC{i-26}" if i >= 26 else ""), IO) for i, p in enumerate(gpio_pins)]

SYMBOLS = [
    two_pin("CAP_1uF_0603", "C", "CAP CER 1UF 16V X7R 0603", P("1uF", "GCM188R71C105KA64D", "Murata Electronics", "CAP CER 1UF 16V X7R 0603"), "CAPC1608X87N"),
    two_pin("CAP_2.2uF_0805", "C", "CAP CER 2.2UF 16V X7R 0805", P("2.2uF", "GCM21BR71C225KA64L", "Murata Electronics", "CAP CER 2.2UF 16V X7R 0805"), "CAPC2012X125N"),
    two_pin("CAP_0.1uF_0402", "C", "CAP CER 0.1UF 16V X7R 0402", P("0.1uF", "GCM155R71C104KA55D", "Murata Electronics", "CAP CER 0.1UF 16V X7R 0402"), "CAPC1005X55N"),
    two_pin("CAP_15pF_0402", "C", "CAP CER 15PF 50V C0G/NP0 0402", P("15pF", "GCM1555C1H150JA16D", "Murata Electronics", "CAP CER 15PF 50V C0G/NP0 0402"), "CAPC1005X55N"),
    two_pin("LED_RED_0603", "D", "LED RED CLEAR 625NM 0603 SMD", P("LED", "QBLP601-R5", "QT Brightek (QTB)", "LED RED CLEAR 625NM 0603 SMD"), "LEDC1608X80N", n1="K", n2="A"),
    two_pin("RES_5.1K_0402", "R", "RES 5.1K OHM 5% 1/16W 0402", P("5.1K", "RC0402JR-075K1L", "YAGEO", "RES 5.1K OHM 5% 1/16W 0402"), "RESC1005X40N"),
    two_pin("RES_200_0603", "R", "RES 200 OHM 5% 1/10W 0603", P("200", "RC0603JR-07200RL", "YAGEO", "RES 200 OHM 5% 1/10W 0603"), "RESC1608X55N"),
    two_pin("RES_27_0402", "R", "RES 27 OHM 1% 1/16W 0402", P("27", "RC0402FR-0727RL", "YAGEO", "RES 27 OHM 1% 1/16W 0402"), "RESC1005X40N"),
    two_pin("RES_1K_0402", "R", "RES 1K OHM 1% 1/16W 0402", P("1K", "RC0402FR-071KL", "YAGEO", "RES 1K OHM 1% 1/16W 0402"), "RESC1005X40N"),
    two_pin("RES_10K_0402", "R", "RES 10K OHM 5% 1/16W 0402", P("10K", "RC0402JR-0710KL", "YAGEO", "RES 10K OHM 5% 1/16W 0402"), "RESC1005X40N"),
    two_pin("RES_330_0402", "R", "RES SMD 330 OHM 5% 1/16W 0402", P("330", "AF0402JR-07330RL", "YAGEO", "RES SMD 330 OHM 5% 1/16W 0402"), "RESC1005X40N"),
    box("RP2040", "U", "IC MCU 32BIT EXT MEM 56QFN", P("RP2040", "SC0914(13)", "Raspberry Pi", "IC MCU 32BIT EXT MEM 56QFN"),
        "QFN40P700X700X90-57N", rp_left, rp_right, bottom=[("19", "TESTEN", IN), ("57", "GND", PW)], width=140),
    box("AP2112K-3.3", "U", "IC REG LINEAR 3.3V 600MA SOT-25", P("AP2112", "AP2112K-3.3TRG1", "Diodes Incorporated", "IC REG LINEAR 3.3V 600MA SOT-25"),
        "SOT95P280X145-5N", [("1", "VIN", PW), ("3", "EN", IN), ("2", "GND", PW)], [("5", "VOUT", PW), None, ("4", "NC", PS)], width=60),
    box("W25Q128JVSIQ", "U", "IC FLASH 128MBIT SPI/QUAD 8SOIC", P("W25Q128JVSIQ", "W25Q128JVSIQ TR", "Winbond Electronics", "IC FLASH 128MBIT SPI/QUAD 8SOIC"),
        "SOIC127P790X216-8N", [("8", "VCC", PW), None, None, None, None, ("4", "GND", PW)],
        [("1", "C\\S\\", IN), ("6", "CLK", IN), ("5", "DI/D0", IO), ("2", "DO/D1", IO), ("3", "W\\P\\/D2", IO), ("7", "R\\E\\S\\E\\T\\/D3", IO)], width=100),
    box("USBLC6-2SC6", "U", "TVS DIODE 5.25VWM 17VC SOT23-6", P("USBLC6-2SC6", "USBLC6-2SC6", "STMicroelectronics", "TVS DIODE 5.25VWM 17VC SOT23-6"),
        "SOT95P280X145-6N", [("1", "I/O1A", PS), ("2", "GND", PW), ("3", "I/O2A", PS)], [("6", "I/O1B", PS), ("5", "VBUS", PW), ("4", "I/O2B", PS)], width=60),
    box("XTAL_12MHz_ABM8", "Y", "CRYSTAL 12.0000MHZ 10PF SMD", P("12MHz", "ABM8-272-T3", "Abracon LLC", "CRYSTAL 12.0000MHZ 10PF SMD"),
        "XTAL_3225-4", [("1", "1", PS), ("3", "3", PS)], [("2", "GND", PS), ("4", "GND", PS)], width=40),
    box("USB-C_UJ20-C-H-G-SMT", "J", "CONN RCPT USB 2.0 TYPE C PCB RA", P("USB-C", "UJ20-C-H-G-SMT-TR", "Same Sky (Formerly CUI Devices)", "CONN RCPT USB 2.0 TYPE C PCB RA", NEEDS_FP), None,
        [("A4", "VBUS", PW), ("B4", "VBUS1", PW), ("A9", "VBUS2", PW), ("B9", "VBUS3", PW), None, ("A5", "CC1", IO), ("B5", "CC2", IO), None,
         ("A6", "DP1", IO), ("B6", "DP2", IO), ("A7", "DN1", IO), ("B7", "DN2", IO)],
        [("A1", "GND", PW), ("B1", "GND1", PW), ("A12", "GND2", PW), ("B12", "GND3", PW), ("S1", "SHELL1", PS), ("S2", "SHELL2", PS),
         ("S3", "SHELL3", PS), ("S4", "SHELL4", PS), None, ("B8", "SBU2", IO), ("A8", "SBU1", IO)], width=100),
    box("SW_TACT_PTS526", "SW", "SWITCH TACTILE SPST-NO 0.05A 12V", P("PTS526", "PTS526SM15SMTR2 LFS", "C&K", "SWITCH TACTILE SPST-NO 0.05A 12V", NEEDS_FP), None,
        [("1", "1", PS), ("2", "2", PS)], [("4", "4", PS), ("3", "3", PS)], width=40),
    box("SW_PUSH_D6R90", "SW", "SWITCH PUSH SPST-NO 0.1A 32V", P("SWITCH", "D6R90 F2 LFS", "C&K", "SWITCH PUSH SPST-NO 0.1A 32V", NEEDS_FP), None,
        [("1", "1", PS), ("2", "2", PS)], [("4", "4", PS), ("3", "3", PS)], width=40),
    {"name": "MOUNTING_HOLE_M4", "designator_prefix": "MH", "description": "Mounting Hole M4 (DNI)",
     "parameters": [{"name": "Value", "value": "Mounting Hole"}, {"name": "DNI", "value": "DNI"}],
     "pins": [],
     "rectangles": [{"x1": -10, "y1": -10, "x2": 10, "y2": 10}],
     "footprints": [{"name": "MH_M4_NPTH", "library_path": "Sierrathon.PcbLib"}]},
]


def main():
    m = MCP(str(OUT))
    fps = [kicad_to_footprint(KICAD / f, n, d, ep) for f, n, d, ep in FOOTPRINTS]
    r = m.call("write_pcblib", {"filepath": PCBLIB, "footprints": fps, "append": False})
    print("write_pcblib:", json.dumps(r)[:1500])
    r = m.call("write_schlib", {"filepath": SCHLIB, "symbols": SYMBOLS, "append": False})
    print("write_schlib:", json.dumps(r)[:1500] if isinstance(r, dict) and "ERROR" in r else "ok")
    print("libpkg:", m.call("write_libpkg", {"filepath": str(OUT / "Sierrathon.LibPkg"), "documents": ["Sierrathon.SchLib", "Sierrathon.PcbLib"]}))
    for lib in (PCBLIB, SCHLIB):
        print("validate", Path(lib).name, json.dumps(m.call("validate_library", {"filepath": lib}))[:1500])


if __name__ == "__main__":
    main()
