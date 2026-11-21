#!/usr/bin/env python3
"""Build Sierrathon.netlist.json (Universal Netlist schema v3) from the
Sierrathon schematic PDF + BOM, transcribed by hand.

Unnamed schematic nets get descriptive names (CC1, CC2, ADC_AVDD, XOUT_XTAL,
LED*_A). Everything else uses the schematic's own net names.
"""
import argparse
import datetime
import hashlib
import json
from collections import defaultdict
from pathlib import Path

SOURCE_FILES = {
    "Sierrathon_Schematic.pdf": "5ea766dbad13a9056ede6f61209510168a3f14011f0de9dbdb423a5a05102659",
    "Sierrathon_BOM.xlsx": "39ba15d28d5883e5c12c9deb57445fd459c35ad13e80c90ac27a29e955ae53a8",
}

# ---- components: refdes -> (value, mpn, manufacturer, description, {pin: name}) ----
BOM = {
    "C1": ("1uF", "GCM188R71C105KA64D", "Murata Electronics", "CAP CER 1UF 16V X7R 0603"),
    "C3": ("2.2uF", "GCM21BR71C225KA64L", "Murata Electronics", "CAP CER 2.2UF 16V X7R 0805"),
    "C4": ("0.1uF", "GCM155R71C104KA55D", "Murata Electronics", "CAP CER 0.1UF 16V X7R 0402"),
    "C6": ("15pF", "GCM1555C1H150JA16D", "Murata Electronics", "CAP CER 15PF 50V C0G/NP0 0402"),
    "D3": ("LED", "QBLP601-R5", "QT Brightek (QTB)", "LED RED CLEAR 625NM 0603 SMD"),
    "J1": ("USB-C", "UJ20-C-H-G-SMT-TR", "Same Sky (Formerly CUI Devices)", "CONN RCPT USB 2.0 TYPE C PCB RA"),
    "R1": ("5.1K", "RC0402JR-075K1L", "YAGEO", "RES 5.1K OHM 5% 1/16W 0402"),
    "R4": ("200", "RC0603JR-07200RL", "YAGEO", "RES 200 OHM 5% 1/10W 0603"),
    "R5": ("27", "RC0402FR-0727RL", "YAGEO", "RES 27 OHM 1% 1/16W 0402"),
    "R7": ("1K", "RC0402FR-071KL", "YAGEO", "RES 1K OHM 1% 1/16W 0402"),
    "R9": ("10K", "RC0402JR-0710KL", "YAGEO", "RES 10K OHM 5% 1/16W 0402"),
    "R12": ("330", "AF0402JR-07330RL", "YAGEO", "RES SMD 330 OHM 5% 1/16W 0402"),
    "SW1": ("BOOT", "PTS526SM15SMTR2 LFS", "C&K", "SWITCH TACTILE SPST-NO 0.05A 12V"),
    "SW3": ("SWITCH", "D6R90 F2 LFS", "C&K", "SWITCH PUSH SPST-NO 0.1A 32V"),
    "U1": ("RP2040", "SC0914(13)", "Raspberry Pi", "IC MCU 32BIT EXT MEM 56QFN"),
    "U2": ("AP2112", "AP2112K-3.3TRG1", "Diodes Incorporated", "IC REG LINEAR 3.3V 600MA SOT-25"),
    "U3": ("W25Q128JVSIQ", "W25Q128JVSIQ TR", "Winbond Electronics", "IC FLASH 128MBIT SPI/QUAD 8SOIC"),
    "U4": ("USBLC6-2SC6", "USBLC6-2SC6", "STMicroelectronics", "TVS DIODE 5.25VWM 17VC SOT23-6"),
    "Y1": ("CRYSTAL14", "ABM8-272-T3", "Abracon LLC", "CRYSTAL 12.0000MHZ 10PF SMD"),
}
SAME_AS = {"C2": "C1", "C5": "C3", "C14": "C3", "C17": "C3", "C7": "C6", "R2": "R1", "R6": "R5", "R8": "R7",
           "R10": "R9", "R19": "R9", "SW2": "SW1"}
for c in ["C8", "C9", "C10", "C11", "C12", "C13", "C15", "C16"]: SAME_AS[c] = "C4"
for i in range(4, 10): SAME_AS[f"D{i}"] = "D3"
for i in range(13, 19): SAME_AS[f"R{i}"] = "R12"
for k, v in SAME_AS.items(): BOM[k] = BOM[v]
BOM["SW2"] = ("RESET",) + BOM["SW1"][1:]

PIN_NAMES = {
    "U1": {"1": "IOVDD", "10": "IOVDD", "22": "IOVDD", "33": "IOVDD", "42": "IOVDD", "49": "IOVDD",
           "19": "TESTEN", "20": "XIN", "21": "XOUT", "23": "DVDD", "50": "DVDD", "24": "SWCLK", "25": "SWDIO",
           "26": "RUN", "43": "ADC_AVDD", "44": "VREG_VIN", "45": "VREG_VOUT", "46": "USB_DM", "47": "USB_DP",
           "48": "USB_VDD", "51": "QSPI_SD3", "52": "QSPI_SCLK", "53": "QSPI_SD0", "54": "QSPI_SD2",
           "55": "QSPI_SD1", "56": "QSPI_SS_N", "57": "GND"},
    "U2": {"1": "VIN", "2": "GND", "3": "EN", "4": "NC", "5": "VOUT"},
    "U3": {"1": "/CS", "2": "DO/D1", "3": "/WP/D2", "4": "GND", "5": "DI/D0", "6": "CLK", "7": "/RESET/D3", "8": "VCC"},
    "U4": {"1": "I/O1A", "2": "GND", "3": "I/O2A", "4": "I/O2B", "5": "VBUS", "6": "I/O1B"},
    "J1": {"A4": "VBUS", "B4": "VBUS1", "A9": "VBUS2", "B9": "VBUS3", "A1": "GND", "B1": "GND1", "A12": "GND2",
           "B12": "GND3", "S1": "SHELL1", "S2": "SHELL2", "S3": "SHELL3", "S4": "SHELL4", "A5": "CC1", "B5": "CC2",
           "A6": "DP1", "B6": "DP2", "A7": "DN1", "B7": "DN2", "A8": "SBU1", "B8": "SBU2"},
}
gpio_pin = list(range(2, 10)) + list(range(11, 19)) + [27, 28, 29, 30, 31, 32, 34, 35, 36, 37, 38, 39, 40, 41]
for g, p in enumerate(gpio_pin):
    PIN_NAMES["U1"][str(p)] = f"GPIO{g}" + (f"/ADC{g-26}" if g >= 26 else "")
for d in range(3, 10):
    PIN_NAMES[f"D{d}"] = {"1": "K", "2": "A"}

# ---- nets: name -> list of "REF.PIN" ----
NETS = {
    "VBUS": "J1.A4 J1.B4 J1.A9 J1.B9 U4.5 U2.1 U2.3 C1.1",
    "+3.3V": "U2.5 C2.1 R4.1 U1.1 U1.10 U1.22 U1.33 U1.42 U1.49 U1.48 U1.44 U3.8 C3.1 C4.1 R9.1 R10.1 R19.1 "
             "C8.1 C9.1 C10.1 C11.1 C12.1 C13.1 C14.1",
    "+1.1V": "U1.45 U1.23 U1.50 C15.1 C16.1 C17.1",
    "GND": "J1.A1 J1.B1 J1.A12 J1.B12 J1.S1 J1.S2 J1.S3 J1.S4 R1.2 R2.2 U4.2 U2.2 C1.2 C2.2 C3.2 C4.2 U3.4 "
           "C5.2 Y1.2 Y1.4 C6.1 C7.1 SW1.3 SW1.4 SW2.3 SW2.4 SW3.3 SW3.4 U1.19 U1.57 "
           "D3.1 D4.1 D5.1 D6.1 D7.1 D8.1 D9.1 C8.2 C9.2 C10.2 C11.2 C12.2 C13.2 C14.2 C15.2 C16.2 C17.2",
    "CC1": "J1.A5 R1.1",
    "CC2": "J1.B5 R2.1",
    "D_P": "J1.A6 J1.B6 U4.1",
    "D_N": "J1.A7 J1.B7 U4.3",
    "USB_P": "U4.6 R6.1",
    "USB_N": "U4.4 R5.1",
    "USBR_P": "R6.2 U1.47",
    "USBR_N": "R5.2 U1.46",
    "ADC_AVDD": "R4.2 C5.1 U1.43",
    "XIN": "U1.20 Y1.1 C6.2",
    "XOUT": "U1.21 R7.2",
    "XOUT_XTAL": "Y1.3 C7.2 R7.1",
    "RESET": "R10.2 SW2.1 SW2.2 U1.26",
    "BOOT": "SW1.1 SW1.2 R8.1",
    "QSPI_CS": "R8.2 R9.2 U3.1 U1.56",
    "QSPI_CLK": "U3.6 U1.52",
    "QSPI_D0": "U3.5 U1.53",
    "QSPI_D1": "U3.2 U1.55",
    "QSPI_D2": "U3.3 U1.54",
    "QSPI_D3": "U3.7 U1.51",
    "SW": "U1.36 R19.2 SW3.1 SW3.2",
}
for i, (pin, r, d) in enumerate(zip([28, 29, 30, 31, 32, 34, 35], range(12, 19), range(3, 10)), start=1):
    NETS[f"Led{i}"] = f"U1.{pin} R{r}.1"
    NETS[f"LED{i}_A"] = f"R{r}.2 D{d}.2"

# Every pin each part has (unlisted ones become NC "")
ALL_PINS = {r: list(PIN_NAMES[r]) for r in PIN_NAMES}
for r in BOM:
    ALL_PINS.setdefault(r, ["1", "2", "3", "4"] if r.startswith(("SW", "Y")) else ["1", "2"])


def build():
    nets, pin_net = {}, {}
    for name, members in NETS.items():
        m = defaultdict(list)
        for rp in members.split():
            ref, pin = rp.split(".")
            assert ref in BOM, rp
            assert pin in ALL_PINS[ref], rp
            assert (ref, pin) not in pin_net, f"{rp} on two nets"
            pin_net[(ref, pin)] = name
            m[ref].append(pin)
        nets[name] = dict(m)
    comps = {}
    for ref, (val, mpn, mfr, desc) in BOM.items():
        pins = {}
        for p in ALL_PINS[ref]:
            net = pin_net.get((ref, p), "")
            pins[p] = {"name": PIN_NAMES[ref][p], "net": net} if ref in PIN_NAMES else net
        comps[ref] = {"mpn": mpn, "manufacturer": mfr, "description": desc, "value": val, "pins": pins}
    for n in range(1, 5):
        comps[f"MH{n}"] = {"value": "Mounting Hole", "description": "Mounting Hole (DNI)", "dns": True, "pins": {}}
    return nets, comps


def _js_key_order(keys):
    """JS object key order after sorted insertion: array-index keys first
    (numeric ascending), then the remaining keys in sorted (UTF-16) order."""
    is_idx = lambda k: k.isdigit() and (k == "0" or not k.startswith("0")) and int(k) < 2**32 - 1
    return sorted((k for k in keys if is_idx(k)), key=int) + sorted(k for k in keys if not is_idx(k))


def canonical(o):
    if isinstance(o, dict):
        return {k: canonical(o[k]) for k in _js_key_order(o)}
    if isinstance(o, list):
        return [canonical(x) for x in o]
    return o


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify the supplied files and checked-in transcription")
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent
    for name, digest in SOURCE_FILES.items():
        source = directory.parent / "site" / "files" / name
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise SystemExit(f"{name} differs from the source used for the transcription")

    nets, comps = build()
    payload = json.dumps(canonical({"nets": nets, "components": comps}), separators=(",", ":"), ensure_ascii=False)
    doc = {
        "universalNetlistSchemaVersion": 3,
        "metadata": {
            "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "netlistHash": "sha256:" + hashlib.sha256(payload.encode()).hexdigest(),
            "origin": {"type": "native"},
            "sourceTranscription": {"method": "manual", "sha256": SOURCE_FILES},
        },
        "nets": nets,
        "components": comps,
    }
    out = directory / "Sierrathon.netlist.json"
    if args.check:
        checked_in = json.loads(out.read_text())
        del doc["metadata"]["generatedAt"]
        checked_in["metadata"].pop("generatedAt", None)
        if checked_in != doc:
            raise SystemExit(f"{out.name} differs from the transcription")
        print(f"Source hashes and transcription verified ({len(nets)} nets, {len(comps)} components).")
        return

    out.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"wrote {out}: {len(nets)} nets, {len(comps)} components")


if __name__ == "__main__":
    main()
