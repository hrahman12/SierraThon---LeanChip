import LeanVsDFM.PcbTypes
import LeanVsDFM.PackageData
/-!
# Parts verifier: is every part on the PCB the part it is meant to be?

Input: a KiCad `.kicad_pcb`, extracted by `tools/extract_pcb.py` with KiCad's own pcbnew API.
Reference: the official BOM (MPNs), the schematic pin list, and manufacturer specifications.

For every part the verifier checks:
1. **Package**: the footprint is the package that manufacturer part number comes in.
2. **Pins**: every schematic pin has a pad, on the same net (schematic ↔ PCB sync).
3. **No stray copper**: every pad with a net corresponds to a schematic pin on that net.
4. **Polarity**: LED pad 1 (cathode) is on GND.
5. **Land pattern**: U3's pads equal the manufacturer (UltraLibrarian) land pattern to the nm.

A DFM tool checks fabrication geometry; a footprint that is the wrong part but has clean
geometry passes it. This verifier compares the board against what the parts *are*.
-/
namespace LeanVsDFM.Parts
open LeanVsDFM.Pcb LeanVsDFM.Package

/-- How good a footprint is for a part: the preferred land pattern (IPC nominal or the
manufacturer's), or a legitimate variant (e.g. KiCad hand-solder pads) that is buildable but
not preferred for reflow assembly. -/
inductive Grade where
  | preferred | variant
  deriving Repr, DecidableEq

/-- Allowed footprints for each MPN. Anything not listed is the wrong package. Parts without a
footprint in KiCad's library need the manufacturer's (`MFR:` entries). -/
def footprintOptions : List (String × String × Grade) := [
  ("GCM188R71C105KA64D", "C_0603_1608Metric", .preferred), ("GCM188R71C105KA64D", "C_0603_1608Metric_Pad1.08x0.95mm_HandSolder", .variant),
  ("GCM21BR71C225KA64L", "C_0805_2012Metric", .preferred), ("GCM21BR71C225KA64L", "C_0805_2012Metric_Pad1.18x1.45mm_HandSolder", .variant),
  ("GCM155R71C104KA55D", "C_0402_1005Metric", .preferred), ("GCM155R71C104KA55D", "C_0402_1005Metric_Pad0.74x0.62mm_HandSolder", .variant),
  ("GCM1555C1H150JA16D", "C_0402_1005Metric", .preferred), ("GCM1555C1H150JA16D", "C_0402_1005Metric_Pad0.74x0.62mm_HandSolder", .variant),
  ("QBLP601-R5", "LED_0603_1608Metric", .preferred), ("QBLP601-R5", "LED_0603_1608Metric_Pad1.05x0.95mm_HandSolder", .variant),
  ("UJ20-C-H-G-SMT-TR", "MFR:UJ20-C-H-G-SMT-TR", .preferred),
  ("", "MountingHole_4.3mm_M4", .preferred),
  ("RC0402JR-075K1L", "R_0402_1005Metric", .preferred), ("RC0402JR-075K1L", "R_0402_1005Metric_Pad0.72x0.64mm_HandSolder", .variant),
  ("RC0603JR-07200RL", "R_0603_1608Metric", .preferred), ("RC0603JR-07200RL", "R_0603_1608Metric_Pad0.98x0.95mm_HandSolder", .variant),
  ("RC0402FR-0727RL", "R_0402_1005Metric", .preferred), ("RC0402FR-0727RL", "R_0402_1005Metric_Pad0.72x0.64mm_HandSolder", .variant),
  ("RC0402FR-071KL", "R_0402_1005Metric", .preferred), ("RC0402FR-071KL", "R_0402_1005Metric_Pad0.72x0.64mm_HandSolder", .variant),
  ("RC0402JR-0710KL", "R_0402_1005Metric", .preferred), ("RC0402JR-0710KL", "R_0402_1005Metric_Pad0.72x0.64mm_HandSolder", .variant),
  ("AF0402JR-07330RL", "R_0402_1005Metric", .preferred), ("AF0402JR-07330RL", "R_0402_1005Metric_Pad0.72x0.64mm_HandSolder", .variant),
  ("PTS526SM15SMTR2 LFS", "MFR:PTS526SM15SMTR2", .preferred), ("D6R90 F2 LFS", "MFR:D6R90F2LFS", .preferred),
  ("SC0914(13)", "QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm", .preferred),
  ("SC0914(13)", "QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm_ThermalVias", .preferred),
  ("AP2112K-3.3TRG1", "SOT-23-5", .preferred), ("AP2112K-3.3TRG1", "SOT-23-5_HandSoldering", .variant),
  ("W25Q128JVSIQ TR", "SOIC-8_5.23x5.23mm_P1.27mm", .preferred), ("W25Q128JVSIQ TR", "SOIC-8_5.275x5.275mm_P1.27mm", .variant),
  ("USBLC6-2SC6", "SOT-23-6", .preferred), ("USBLC6-2SC6", "SOT-23-6_Handsoldering", .variant),
  ("ABM8-272-T3", "Crystal_SMD_3225-4Pin_3.2x2.5mm", .preferred), ("ABM8-272-T3", "Crystal_SMD_3225-4Pin_3.2x2.5mm_HandSoldering", .variant)]

def mpnOf (ref : String) : Option String := (bom.find? (fun l => l.refdes.contains ref)).map (·.mpn)

/-- The preferred footprint for a part (first preferred option). -/
def expectedFootprint (ref : String) : Option String :=
  mpnOf ref >>= fun m => (footprintOptions.find? (fun (k, _, g) => k == m && g == .preferred)).map (·.2.1)

def gradeOf (ref lib : String) : Option Grade :=
  mpnOf ref >>= fun m => (footprintOptions.find? (fun (k, f, _) => k == m && f == lib)).map (·.2.2)

/-- Schematic pin → footprint pad number (identity except where a footprint merges pins). -/
def padFor (ref pin : String) : String :=
  if ref == "J1" && (pin == "S2" || pin == "S3" || pin == "S4") then "S1"
  else if (ref == "SW1" || ref == "SW2" || ref == "SW3") then (if pin == "1" || pin == "2" then "1" else "2")
  else pin

/-- W25Q128JVSIQ-TR land pattern from the supplied UltraLibrarian library, nm. -/
def ulSoic208 : List (String × Int × Int × Int × Int) :=
  [("1", -3645000, -1905000, 1513000, 533000), ("2", -3645000, -635000, 1513000, 533000),
   ("3", -3645000, 635000, 1513000, 533000), ("4", -3645000, 1905000, 1513000, 533000),
   ("5", 3645000, 1905000, 1513000, 533000), ("6", 3645000, 635000, 1513000, 533000),
   ("7", 3645000, -635000, 1513000, 533000), ("8", 3645000, -1905000, 1513000, 533000)]

inductive Issue where
  | missing (ref : String)
  | notOnBom (ref : String)
  | wrongPackage (ref found want : String)
  | noPad (ref pin : String)
  | wrongNet (ref pad found want : String)
  | strayNet (ref pad net : String)
  | polarity (ref : String)
  | landPattern (ref pad : String)
  | variantFootprint (ref lib : String)
  deriving Repr, DecidableEq

def find (b : List Footprint) (r : String) : Option Footprint := b.find? (·.ref == r)

def checkPackage (fp : Footprint) : List Issue :=
  match expectedFootprint fp.ref with
  | none => [.notOnBom fp.ref]
  | some want =>
    match gradeOf fp.ref fp.lib with
    | some .preferred => []
    | some .variant => [.variantFootprint fp.ref fp.lib]
    | none => [.wrongPackage fp.ref fp.lib want]

def checkPins (b : List Footprint) : List Issue :=
  schematicPins.flatMap fun (r, p, n) =>
    match find b r with
    | none => []
    | some fp =>
      let pads := fp.pads.filter (·.number == padFor r p)
      if pads.isEmpty then [.noPad r p]
      else (pads.filter (·.net != n)).map (fun pd => .wrongNet r pd.number pd.net n)

def checkStray (fp : Footprint) : List Issue :=
  (fp.pads.filter fun pd => pd.net != "" &&
      !(schematicPins.any fun (r, p, n) => r == fp.ref && padFor r p == pd.number && n == pd.net)).map
    (fun pd => .strayNet fp.ref pd.number pd.net)

def checkPolarity (fp : Footprint) : List Issue :=
  if fp.ref.startsWith "D" && !(fp.pads.any fun pd => pd.number == "1" && pd.net == "GND") then [.polarity fp.ref]
  else []

def checkLand (fp : Footprint) : List Issue :=
  if fp.ref == "U3" && fp.lib == "SOIC-8_5.23x5.23mm_P1.27mm" then
    ulSoic208.filterMap fun (n, x, y, w, h) =>
      if fp.pads.any (fun pd => pd.number == n && pd.x == x && pd.y == y && pd.w == w && pd.h == h) then none
      else some (.landPattern "U3" n)
  else []

/-- **The verifier.** Deterministic, total, and every rule above. -/
def verify (b : List Footprint) : List Issue :=
  (schematicRefdes.filter (fun r => (find b r).isNone)).map .missing ++
  b.flatMap checkPackage ++ checkPins b ++ b.flatMap checkStray ++ b.flatMap checkPolarity ++
  b.flatMap checkLand

/-- Issues other than "needs the manufacturer footprint" and "variant footprint". -/
def electrical (is : List Issue) : List Issue :=
  is.filter fun | .wrongPackage _ _ w => !w.startsWith "MFR:" | .variantFootprint _ _ => false | _ => true

end LeanVsDFM.Parts
