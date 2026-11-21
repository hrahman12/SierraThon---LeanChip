import LeanVsDFM.PackageData
import LeanVsDFM.Fixers
/-!
# Where the supplied Sierrathon package breaks, and how Lean catches it

Every fact here comes from the official files: `Sierrathon_Schematic.pdf` (via the golden
netlist), `Sierrathon_BOM.xlsx` (rows verbatim in `PackageData.lean`), `Sierrathon Stack-Up.png`
and `Sierrathon_Instructions.docx`. All proofs are kernel-checked (`decide`, `decide +kernel`).

A DFM tool reads fabrication data (Gerbers, drills, a rule deck). Breaks 1–3 are not in
fabrication data at all, so DFM cannot see them. Break 4 is in the rule deck, where a single
global rule gives the wrong answer.
-/
namespace LeanVsDFM.Breaks
open Package Fixers

/-! ## Break 1: BOM quantity contradicts the BOM's own reference list and the schematic -/

def qtyConsistent (l : BomLine) : Bool := l.qty == l.refdes.length

/-- **Lean catches it:** exactly one BOM row is inconsistent, row 5 (the LEDs). -/
theorem break1_only_row5 : (bom.filter (fun l => !qtyConsistent l)).map (·.line) = [5] := by decide

/-- Row 5 says 8 but lists 7 designators … -/
theorem break1_row5 : (bom.find? (·.line == 5)).map (fun l => (l.qty, l.refdes.length)) = some (8, 7) := by
  decide

/-- … and the schematic draws exactly 7 LEDs (D3–D9). -/
theorem break1_schematic_has_7_leds :
    (schematicRefdes.filter (fun r => r.startsWith "D")).length = 7 := by decide +kernel

/-- Every BOM designator is on the schematic and every schematic part is on the BOM. -/
theorem bom_schematic_sync :
    (bom.flatMap (·.refdes)).all (schematicRefdes.contains ·) = true ∧
    schematicRefdes.all ((bom.flatMap (·.refdes)).contains ·) = true := by decide +kernel

/-- **Fix:** set each row's quantity to its designator count; then every row is consistent. -/
def fixQty (l : BomLine) : BomLine := { l with qty := l.refdes.length }
theorem break1_fixed : (bom.map fixQty).all qtyConsistent = true := by decide
theorem break1_fix_changes_only_row5 :
    (bom.filter (fun l => l.qty != (fixQty l).qty)).map (fun l => (l.line, l.qty, (fixQty l).qty)) = [(5, 8, 7)] := by
  decide

/-! ## Break 2: inner copper weight, stack-up vs instructions -/

/-- Copper weight in tenths of an ounce. -/
def innerCopper_stackup : Nat := 5        -- Stack-Up.png: L2, L3 "0.5oz"
def innerCopper_instructions : Nat := 10  -- Instructions: "Internal copper thickness: 1 oz"

/-- **Lean catches it:** the two official sources disagree. -/
theorem break2_conflict : innerCopper_stackup ≠ innerCopper_instructions := by decide

/-- Thickness in µin. 0.5 oz = 600 µin, 1 oz = 1370 µin (1.37 mil). -/
def stack (inner : Nat) : Nat := 1500 + 4348 + inner + 45600 + inner + 4348 + 1500 + 500 + 500
def within62 (t : Nat) : Bool := 62000 * 90 ≤ t * 100 && t * 100 ≤ 62000 * 110

/-- Both readings meet 62 mil ± 10 %, so thickness cannot settle it: it needs a question to
the fab (RFI). Lean shows the conflict exists *and* that the board is buildable either way. -/
theorem break2_both_readings_buildable :
    stack 600 = 59496 ∧ within62 (stack 600) = true ∧ stack 1370 = 61036 ∧ within62 (stack 1370) = true := by
  decide

/-- The outer layers agree: 0.5 oz foil + 0.8 mil plating = 1.5 mil ≥ 1 oz finished (1.37 mil). -/
theorem external_copper_consistent : 600 + 800 + 100 ≥ 1370 := by decide

/-! ## Break 3: LED current vs the RP2040's default pad drive -/

/-- The LED resistor value straight from the BOM (row 13: R12–R18). -/
theorem led_resistor_from_bom : (bom.find? (·.line == 13)).map (·.value) = some "330" := by decide

/-- **Lean catches it:** with 330 Ω the worst-case current (4.945 mA) exceeds the RP2040's
default 4 mA pad drive. The schematic is fine only if firmware raises the drive to 8 mA. -/
theorem break3_default_drive_fails : ledMax_uA 330 = 4945 ∧ ledOk 4000 330 = false := by decide

/-- **Fix (BOM unchanged):** set the GPIO17–23 pad drive to 8 mA; then every limit holds. -/
theorem break3_fixed_by_8mA : ledOk 8000 330 = true := by decide

/-- Alternative fix if the BOM could change: the fixer's smallest E24 value for 4 mA. -/
theorem break3_alt_fix : fixLedResistor 4000 = some 430 := by decide

/-! ## Break 4: the 90 Ω pair geometry vs the 6 mil rule -/

/-- Widths and gaps in units of 0.01 mil. -/
def minNonImpedance : Nat := 600                -- Instructions: "Min. non-impedance trace width and spacing: 6 mil"
def pairWidth : Nat := 500                      -- Stack-Up.png impedance table, rows c/d: LW 5.00
def pairGap : Nat := 400                        --                                 spacing 4.00

/-- The impedance nets named in the instructions. -/
def impedanceNets : List String := ["USB_P", "USB_N", "USBR_P", "USBR_N", "D_P", "D_N"]

/-- They are all real nets on the schematic. -/
theorem impedance_nets_on_schematic : impedanceNets.all (schematicNets.contains ·) = true := by
  decide +kernel

/-- A DFM deck that applies the 6 mil rule to every net. -/
def dfmGlobal (w s : Nat) : Bool := minNonImpedance ≤ w && minNonImpedance ≤ s

/-- **DFM gets it wrong:** the mandated 5 / 4 mil pair geometry fails the global rule, on all six nets. -/
theorem break4_dfm_flags_mandated_geometry : dfmGlobal pairWidth pairGap = false := by decide

/-- …and the "DFM fix" (widen to 6 / 6 mil) is not the geometry the fab simulated at 89.7 Ω,
so it gives up the impedance guarantee. -/
theorem break4_dfm_fix_breaks_impedance : (600, 600) ≠ (pairWidth, pairGap) := by decide

/-- **Lean's rule:** impedance nets must use exactly the stack-up geometry; every other net
must meet 6 mil. -/
def leanRule (net : String) (w s : Nat) : Bool :=
  if impedanceNets.contains net then w == pairWidth && s == pairGap
  else minNonImpedance ≤ w && minNonImpedance ≤ s

theorem break4_lean_accepts_pairs : impedanceNets.all (fun n => leanRule n pairWidth pairGap) = true := by
  decide +kernel

/-- …while still forbidding 5 / 4 mil on every one of the other schematic nets. -/
theorem break4_lean_still_enforces_6mil :
    (schematicNets.filter (fun n => !impedanceNets.contains n)).all (fun n => !leanRule n pairWidth pairGap) = true := by
  decide +kernel

/-- And the geometry Lean requires is the one the fab simulated inside tolerance (89.7 Ω, 0.1 Ω units). -/
theorem break4_impedance_in_tolerance : 900 * 90 ≤ 897 * 100 ∧ 897 * 100 ≤ 900 * 110 := by decide

end LeanVsDFM.Breaks
