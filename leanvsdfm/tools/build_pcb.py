#!/usr/bin/env python3
"""Build sierrathon.kicad_pcb (KiCad 7) with every part of the golden netlist placed and every
pad assigned to its schematic net. Footprints come from KiCad's official library, except U3,
whose pads are set to the UltraLibrarian land pattern for W25Q128JVSIQ-TR.

Placement here is a compact grid, not the final layout: the parts verifier only looks at each
footprint's own pads (relative to its origin), its nets and its library identity.

    python3 tools/build_pcb.py [out.kicad_pcb] [--fault NAME]
Faults (for demonstrating the verifier): narrow_flash, led_reversed, wrong_cap_size, flash_pins_swapped
"""
import json
import os
import sys

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FPLIB = "/usr/share/kicad/footprints"

# refdes prefix/explicit -> (library, footprint)
FOOTPRINT = {
    "C_0402": ("Capacitor_SMD", "C_0402_1005Metric"), "C_0603": ("Capacitor_SMD", "C_0603_1608Metric"),
    "C_0805": ("Capacitor_SMD", "C_0805_2012Metric"), "R_0402": ("Resistor_SMD", "R_0402_1005Metric"),
    "R_0603": ("Resistor_SMD", "R_0603_1608Metric"), "LED_0603": ("LED_SMD", "LED_0603_1608Metric"),
    "U1": ("Package_DFN_QFN", "QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm"),
    "U2": ("Package_TO_SOT_SMD", "SOT-23-5"), "U3": ("Package_SO", "SOIC-8_5.23x5.23mm_P1.27mm"),
    "U4": ("Package_TO_SOT_SMD", "SOT-23-6"), "Y1": ("Crystal", "Crystal_SMD_3225-4Pin_3.2x2.5mm"),
    # placeholders until the manufacturer footprints exist (the verifier flags these):
    "J1": ("Connector_USB", "USB_C_Receptacle_HRO_TYPE-C-31-M-12"),
    "SW1": ("Button_Switch_SMD", "SW_SPST_TL3342"), "SW2": ("Button_Switch_SMD", "SW_SPST_TL3342"),
    "SW3": ("Button_Switch_THT", "SW_PUSH_6mm"),
    "MH": ("MountingHole", "MountingHole_4.3mm_M4"),
}
SIZE = {}  # refdes -> package size for passives, from the BOM description
for refs, size in [("C1 C2", "0603"), ("C3 C5 C14 C17", "0805"), ("C4 C8 C9 C10 C11 C12 C13 C15 C16 C6 C7", "0402"),
                   ("R1 R2 R5 R6 R7 R8 R9 R10 R19 R12 R13 R14 R15 R16 R17 R18", "0402"), ("R4", "0603")]:
    for r in refs.split():
        SIZE[r] = size

# UltraLibrarian W25Q128JVSIQ-TR land pattern (mm), read from the supplied .PcbLib via altium-designer-mcp
UL_SOIC208 = {str(n): (x, y, 1.513, 0.533) for n, x, y in
              [(1, -3.645, -1.905), (2, -3.645, -0.635), (3, -3.645, 0.635), (4, -3.645, 1.905),
               (5, 3.645, 1.905), (6, 3.645, 0.635), (7, 3.645, -0.635), (8, 3.645, -1.905)]}

# How schematic pin numbers map to footprint pad numbers (identity unless listed).
PINMAP = {"J1": {"S2": "S1", "S3": "S1", "S4": "S1"},
          "SW1": {"1": "1", "2": "1", "3": "2", "4": "2"}, "SW2": {"1": "1", "2": "1", "3": "2", "4": "2"},
          "SW3": {"1": "1", "2": "1", "3": "2", "4": "2"}}


def fp_for(ref):
    if ref.startswith("MH"):
        return FOOTPRINT["MH"]
    if ref in FOOTPRINT:
        return FOOTPRINT[ref]
    if ref.startswith("D"):
        return FOOTPRINT["LED_0603"]
    return FOOTPRINT[f"{ref[0]}_{SIZE[ref]}"]


LIBDIR = [("C_", "Capacitor_SMD"), ("R_", "Resistor_SMD"), ("LED_", "LED_SMD"), ("QFN", "Package_DFN_QFN"),
          ("SOT-", "Package_TO_SOT_SMD"), ("SOIC", "Package_SO"), ("Crystal", "Crystal")]


def lib_of(name):
    return next(d for p, d in LIBDIR if name.startswith(p))


def build(out, fault=None, combo=None):
    """combo = {"fp": {ref: footprint_name}, "u3_pads": "ul" | "kicad"} overrides the defaults."""
    combo = combo or {}
    nl = json.load(open(os.path.join(ROOT, "..", "netlist", "Sierrathon.netlist.json")))
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(pcbnew.FromMM(1.5748))
    nets = {}
    for name in nl["nets"]:
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni
    comps = nl["components"]
    for k, ref in enumerate(sorted(comps, key=lambda r: (r.rstrip("0123456789"), int(r.lstrip("CDJMHRSUWY") or 0)))):
        lib, name = fp_for(ref)
        if ref in combo.get("fp", {}):
            name = combo["fp"][ref]
            lib = lib_of(name)
        if fault == "narrow_flash" and ref == "U3":
            name = "SOIC-8_3.9x4.9mm_P1.27mm"
        if fault == "wrong_cap_size" and ref == "C4":
            lib, name = FOOTPRINT["C_0603"]
        fp = pcbnew.FootprintLoad(f"{FPLIB}/{lib}.pretty", name)
        fp.SetReference(ref)
        fp.SetValue(comps[ref].get("value", ""))
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(10 + 12 * (k % 8)), pcbnew.FromMM(10 + 12 * (k // 8))))
        board.Add(fp)
        if ref == "U3" and name.startswith("SOIC-8_5.23") and combo.get("u3_pads", "ul") == "ul":
            for p in fp.Pads():
                x, y, w, h = UL_SOIC208[p.GetNumber()]
                p.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(w), pcbnew.FromMM(h)))
                rel = pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))
                p.SetPos0(rel)
                p.SetPosition(fp.GetPosition() + rel)
        pins = comps[ref]["pins"]
        pm = dict(PINMAP.get(ref, {}))
        if fault == "led_reversed" and ref == "D5":
            pm = {"1": "2", "2": "1"}
        if fault == "flash_pins_swapped" and ref == "U3":
            pm = {"2": "5", "5": "2"}
        for pin, entry in pins.items():
            net = entry["net"] if isinstance(entry, dict) else entry
            pad_no = pm.get(pin, pin)
            for p in fp.Pads():
                if p.GetNumber() == pad_no and net:
                    p.SetNet(nets[net])
    pcbnew.SaveBoard(out, board)
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fault = sys.argv[sys.argv.index("--fault") + 1] if "--fault" in sys.argv else None
    combo = json.load(open(sys.argv[sys.argv.index("--combo") + 1])) if "--combo" in sys.argv else None
    args = [a for a in args if a not in (fault,) and not a.endswith(".json")]
    out = args[0] if args else os.path.join(ROOT, "pcb", "sierrathon.kicad_pcb")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    print("wrote", build(out, fault, combo))
