import LeanVsDFM.PartsVerifier
import LeanVsDFM.Breaks
import LeanVsDFM.Specs
/-!
# Traffic-light report for a PCB design

`report board` turns the verifier's findings into rows of 🟢 / 🟡 / 🔴:

* 🔴 **red**: the board is not the intended design (wrong package, wrong net, stray connection,
  reversed polarity, land pattern differs from the manufacturer's).
* 🟡 **yellow**: buildable, but needs an action (a library stand-in must be replaced by the
  manufacturer footprint; a spec conflict needs a question to the fab; a design rule that
  depends on a setting outside the PCB).
* 🟢 **green**: proved correct.

The overall verdict is the worst row (`overall_is_worst`).
-/
namespace LeanVsDFM.Report
open LeanVsDFM.Pcb LeanVsDFM.Parts

inductive Color where
  | green | yellow | red
  deriving Repr, DecidableEq

def Color.rank : Color → Nat
  | .green => 0 | .yellow => 1 | .red => 2

def Color.worst (a b : Color) : Color := if a.rank ≥ b.rank then a else b

def Color.name : Color → String
  | .green => "GREEN" | .yellow => "YELLOW" | .red => "RED"

structure Row where
  section_ : String
  check : String
  color : Color
  detail : String
  deriving Repr

def refOf : Issue → String
  | .missing r | .notOnBom r | .wrongPackage r _ _ | .noPad r _ | .wrongNet r _ _ _
  | .strayNet r _ _ | .polarity r | .landPattern r _ => r

def describe : Issue → String
  | .missing r => s!"{r} missing from the board"
  | .notOnBom r => s!"{r} is not on the BOM"
  | .wrongPackage r f w => s!"{r}: footprint {f}, part needs {w}"
  | .noPad r p => s!"{r}: schematic pin {p} has no pad"
  | .wrongNet r p f w => s!"{r} pad {p}: net {f}, schematic says {w}"
  | .strayNet r p n => s!"{r} pad {p}: connected to {n}, not on the schematic"
  | .polarity r => s!"{r}: cathode (pad 1) not on GND"
  | .landPattern r p => s!"{r} pad {p}: differs from the manufacturer land pattern"

def isMfr : Issue → Bool
  | .wrongPackage _ _ w => w.startsWith "MFR:"
  | _ => false

/-- One row from the issues of one category. -/
def row (sec check : String) (color : Color) (is : List Issue) : Row :=
  if is.isEmpty then ⟨sec, check, .green, "proved"⟩
  else ⟨sec, check, color, String.intercalate "; " ((is.map describe).take 6) ++
    (if is.length > 6 then s!"; … (+{is.length - 6})" else "")⟩

/-- Rows about the board file. -/
def boardRows (b : List Footprint) : List Row :=
  let is := verify b
  [ row "Board" "Every schematic part is placed and on the BOM" .red
      (is.filter fun | .missing _ | .notOnBom _ => true | _ => false),
    row "Board" "Footprint package matches the BOM part number" .red
      (is.filter fun i => match i with | .wrongPackage .. => !isMfr i | _ => false),
    row "Board" "Manufacturer footprint used (not a library stand-in)" .yellow (is.filter isMfr),
    row "Board" "Every schematic pin is on the right net (schematic ↔ PCB)" .red
      (is.filter fun | .wrongNet .. | .noPad .. => true | _ => false),
    row "Board" "No connections that are not on the schematic" .red
      (is.filter fun | .strayNet .. => true | _ => false),
    row "Board" "LED polarity (cathode to GND)" .red (is.filter fun | .polarity _ => true | _ => false),
    row "Board" "U3 land pattern = manufacturer (UltraLibrarian)" .red
      (is.filter fun | .landPattern .. => true | _ => false) ]

/-- Rows about the design package (BOM, stack-up, specs). Computed, not hard-coded. -/
def packageRows : List Row :=
  let bad := Package.bom.filter (fun l => !Breaks.qtyConsistent l)
  [ if bad.isEmpty then ⟨"Package", "BOM quantities match the designator lists", .green, "proved"⟩
    else ⟨"Package", "BOM quantities match the designator lists", .yellow,
      String.intercalate "; " (bad.map fun l => s!"row {l.line}: qty {l.qty} but {l.refdes.length} designators")⟩,
    if Breaks.innerCopper_stackup == Breaks.innerCopper_instructions then
      ⟨"Package", "Inner copper: stack-up agrees with instructions", .green, "proved"⟩
    else ⟨"Package", "Inner copper: stack-up agrees with instructions", .yellow,
      s!"stack-up {Breaks.innerCopper_stackup}/10 oz vs instructions {Breaks.innerCopper_instructions}/10 oz; ask the fab (both readings meet 62 mil ± 10 %)"⟩,
    if Breaks.within62 (Breaks.stack 600) then ⟨"Package", "Stack-up thickness within 62 mil ± 10 %", .green, "59.5 mil"⟩
    else ⟨"Package", "Stack-up thickness within 62 mil ± 10 %", .red, "out of tolerance"⟩,
    if (Breaks.impedanceNets.all fun n => Breaks.leanRule n Breaks.pairWidth Breaks.pairGap) then
      ⟨"Package", "90 Ω pairs use the stack-up geometry (5/4 mil), all other nets ≥ 6 mil", .green,
        "a single global 6 mil DFM rule would wrongly flag these 6 nets"⟩
    else ⟨"Package", "90 Ω pairs use the stack-up geometry", .red, "geometry mismatch"⟩,
    if Fixers.ledOk 4000 330 then ⟨"Specs", "LED current within the RP2040 default 4 mA drive", .green, "proved"⟩
    else ⟨"Specs", "LED current within the RP2040 default 4 mA drive", .yellow,
      "330 Ω gives up to 4.945 mA: GPIO17–23 must be set to 8 mA drive (or 430 Ω)"⟩,
    if Specs.tjWorst < Specs.tjMax then ⟨"Specs", "AP2112 junction temperature < 125 °C", .green, s!"{Specs.tjWorst} °C worst case"⟩
    else ⟨"Specs", "AP2112 junction temperature < 125 °C", .red, "too hot"⟩,
    if Specs.pllUsb.valid && Specs.pllUsb.outKHz == 48000 then ⟨"Specs", "USB clock exactly 48 MHz", .green, "PLL 12 MHz × 100 ÷ 5 ÷ 5"⟩
    else ⟨"Specs", "USB clock exactly 48 MHz", .red, "wrong PLL"⟩,
    if Specs.pllSys.outKHz / 2 ≤ Specs.flashMaxQuadMHz * 1000 then ⟨"Specs", "QSPI clock within W25Q128 limit", .green, "62.5 ≤ 133 MHz"⟩
    else ⟨"Specs", "QSPI clock within W25Q128 limit", .red, "overclocked"⟩ ]

def report (b : List Footprint) : List Row := boardRows b ++ packageRows

def overall (rows : List Row) : Color := rows.foldl (fun c r => c.worst r.color) .green

/-- The overall colour is at least as bad as every row. -/
theorem worst_ge_left (a b : Color) : a.rank ≤ (a.worst b).rank := by
  cases a <;> cases b <;> decide
theorem worst_ge_right (a b : Color) : b.rank ≤ (a.worst b).rank := by
  cases a <;> cases b <;> decide

theorem overall_is_worst_aux (rows : List Row) (c : Color) :
    c.rank ≤ (rows.foldl (fun c r => c.worst r.color) c).rank ∧
    ∀ r ∈ rows, r.color.rank ≤ (rows.foldl (fun c r => c.worst r.color) c).rank := by
  induction rows generalizing c with
  | nil => exact ⟨Nat.le_refl _, by simp⟩
  | cons r rs ih =>
    have ⟨h1, h2⟩ := ih (c.worst r.color)
    refine ⟨Nat.le_trans (worst_ge_left _ _) h1, ?_⟩
    intro x hx
    rcases List.mem_cons.mp hx with rfl | hx
    · exact Nat.le_trans (worst_ge_right _ _) h1
    · exact h2 x hx

theorem overall_is_worst (rows : List Row) : ∀ r ∈ rows, r.color.rank ≤ (overall rows).rank :=
  (overall_is_worst_aux rows .green).2

/-- JSON for the CLI and the HTML report. -/
def esc (s : String) : String := (s.replace "\\" "\\\\").replace "\"" "\\\""

def toJson (rows : List Row) : String :=
  "{\"overall\":\"" ++ (overall rows).name ++ "\",\"rows\":[" ++
    String.intercalate "," (rows.map fun r =>
      "{\"section\":\"" ++ esc r.section_ ++ "\",\"check\":\"" ++ esc r.check ++ "\",\"color\":\"" ++
        r.color.name ++ "\",\"detail\":\"" ++ esc r.detail ++ "\"}") ++ "]}"

end LeanVsDFM.Report
