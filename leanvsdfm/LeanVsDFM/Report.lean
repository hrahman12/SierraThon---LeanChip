import LeanVsDFM.PartsVerifier
import LeanVsDFM.Breaks
import LeanVsDFM.Specs
import LeanVsDFM.Fit3D
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
  /-- One entry per finding: the components it is about (none = the bare board) and the message.
  Green rows have none. This is what colours each component. -/
  items : List (List String × String) := []
  deriving Repr

def refOf : Issue → String
  | .missing r | .notOnBom r | .wrongPackage r _ _ | .noPad r _ | .wrongNet r _ _ _
  | .strayNet r _ _ | .polarity r | .landPattern r _ | .variantFootprint r _ => r

def describe : Issue → String
  | .missing r => s!"{r} missing from the board"
  | .notOnBom r => s!"{r} is not on the BOM"
  | .wrongPackage r f w => s!"{r}: footprint {f}, part needs {w}"
  | .noPad r p => s!"{r}: schematic pin {p} has no pad"
  | .wrongNet r p f w => s!"{r} pad {p}: net {f}, schematic says {w}"
  | .strayNet r p n => s!"{r} pad {p}: connected to {n}, not on the schematic"
  | .polarity r => s!"{r}: cathode (pad 1) not on GND"
  | .landPattern r p => s!"{r} pad {p}: differs from the manufacturer land pattern"
  | .variantFootprint r l => s!"{r}: {l} is a buildable variant, not the preferred land pattern"

def summary (msgs : List String) : String :=
  String.intercalate "; " (msgs.take 6) ++ (if msgs.length > 6 then s!"; … (+{msgs.length - 6})" else "")

/-- One row from its findings: green when there are none. -/
def rowI (sec check : String) (color : Color) (items : List (List String × String)) : Row :=
  if items.isEmpty then ⟨sec, check, .green, "proved", []⟩
  else ⟨sec, check, color, summary (items.map (·.2)), items⟩

/-- One row from the issues of one category. -/
def row (sec check : String) (color : Color) (is : List Issue) : Row :=
  rowI sec check color (is.map fun i => ([refOf i], describe i))

/-- Rows about the board file. -/
def boardRows (b : List Footprint) : List Row :=
  let is := verify b
  [ row "Board" "Every schematic part is placed and on the BOM" .red
      (is.filter fun | .missing _ | .notOnBom _ => true | _ => false),
    row "Board" "Footprint package matches the BOM part number" .red
      (is.filter fun i => match i with | .wrongPackage .. => !isStandIn i | _ => false),
    row "Board" "Manufacturer footprint used (not a library stand-in)" .yellow (is.filter isStandIn),
    row "Board" "Every schematic pin is on the right net (schematic ↔ PCB)" .red
      (is.filter fun | .wrongNet .. | .noPad .. => true | _ => false),
    row "Board" "No connections that are not on the schematic" .red
      (is.filter fun | .strayNet .. => true | _ => false),
    row "Board" "LED polarity (cathode to GND)" .red (is.filter fun | .polarity _ => true | _ => false),
    row "Board" "U3 land pattern = manufacturer (UltraLibrarian)" .yellow
      (is.filter fun | .landPattern .. => true | _ => false),
    row "Board" "Preferred land pattern (IPC nominal / manufacturer), not a variant" .yellow
      (is.filter fun | .variantFootprint .. => true | _ => false) ]

def describe3 : Fit3D.Issue → String
  | .bodyOutsideCourtyard r => s!"{r}: 3D body sticks out of its courtyard"
  | .courtyardsOverlap a b => s!"{a} and {b}: courtyards overlap"
  | .padsOffBoard r => s!"{r}: pads outside the board outline"
  | .bodyOffBoard r => s!"{r}: 3D body hangs over the board edge"
  | .unsupportedRotation r => s!"{r}: rotation is not a right angle"
  | .drillTooSmall r => s!"{r}: drill below 8 mil"
  | .outlineNotConvex => "board outline missing or not convex"

/-- The components a 3D finding is about. -/
def refs3 : Fit3D.Issue → List String
  | .bodyOutsideCourtyard r | .padsOffBoard r | .bodyOffBoard r | .unsupportedRotation r | .drillTooSmall r => [r]
  | .courtyardsOverlap a b => [a, b]
  | .outlineNotConvex => []

/-- Rows about the 2D → 3D fit: bodies, courtyards, outline, drills. -/
def fitRows (outline : List (Int × Int)) (ps : List Fit3D.Part) : List Row :=
  let is := Fit3D.fit3d outline ps
  let sel (f : Fit3D.Issue → Bool) : List (List String × String) := (is.filter f).map fun i => (refs3 i, describe3 i)
  [ rowI "3D fit" "Every 3D body sits inside its own courtyard" .red
      (sel fun | .bodyOutsideCourtyard _ | .unsupportedRotation _ => true | _ => false),
    rowI "3D fit" "No two courtyards overlap, so no two bodies can collide" .red
      (sel fun | .courtyardsOverlap .. => true | _ => false),
    rowI "3D fit" "Pads and bodies are on the board (inside the outline)" .red
      (sel fun | .padsOffBoard _ | .bodyOffBoard _ | .outlineNotConvex => true | _ => false),
    rowI "3D fit" "Every drilled hole is at least 8 mil" .red
      (sel fun | .drillTooSmall _ => true | _ => false),
    rowI "3D fit" "Every part has a 3D body model" .yellow
      ((Fit3D.noBody ps).map fun r => ([r], s!"{r}: no 3D model in the library")) ]

/-! ## The design package, with the knobs the tool lets you turn

Every default is the value in the supplied Sierrathon files, so `packageRowsK {}` is the verdict on
the package as supplied. Turning a knob re-runs the same Lean functions the theorems are about. -/

structure Knobs where
  /-- BOM row 5 quantity, as written in `Sierrathon_BOM.xlsx`. -/
  ledQty : Nat := ((Package.bom.find? (·.line == 5)).map (·.qty)).getD 0
  /-- Inner copper on the stack-up drawing, tenths of an ounce. -/
  cuStackup : Nat := Breaks.innerCopper_stackup
  /-- Inner copper in the written instructions, tenths of an ounce. -/
  cuInstructions : Nat := Breaks.innerCopper_instructions
  /-- 90 Ω pair trace width and gap, hundredths of a mil. -/
  pairW : Nat := Breaks.pairWidth
  pairGap : Nat := Breaks.pairGap
  /-- LED series resistor (BOM row 13), Ω. -/
  ledOhm : Nat := 330
  /-- RP2040 pad drive setting assumed for GPIO17–23, µA. -/
  driveUA : Nat := 4000
  /-- Worst-case load on the 3.3 V regulator, mA. -/
  loadmA : Nat := Specs.loadMax
  /-- Crystal load capacitors C6, C7 (BOM row 4), tenths of a pF. -/
  crystalC : Nat := Specs.c6
  /-- USB-C Rd pull-downs R1, R2 (BOM row 8), Ω. -/
  rdOhm : Nat := Specs.rdNom
  /-- Capacitors left unpopulated at assembly. -/
  dni : List String := []
  deriving Repr

def pad3 (n : Nat) : String := if n < 10 then s!"00{n}" else if n < 100 then s!"0{n}" else s!"{n}"
/-- µA as mA with three decimals. -/
def mA (uA : Nat) : String := s!"{uA / 1000}.{pad3 (uA % 1000)}"
/-- µin as mil with one decimal, rounded. -/
def mil1 (uin : Nat) : String := s!"{(uin + 50) / 1000}.{(uin + 50) % 1000 / 100}"
/-- Tenths as a decimal. -/
def d1 (tenths : Nat) : String := s!"{tenths / 10}.{tenths % 10}"

/-- RP2040 pad drive settings, µA. -/
def drives : List Nat := [2000, 4000, 8000, 12000]

def ledRefs : List String := (Package.bom.filter fun l => l.line == 5 || l.line == 13).flatMap (·.refdes)

def ledRow (k : Knobs) : Row :=
  let check := s!"LED current within the RP2040 pad drive ({k.driveUA / 1000} mA setting)"
  let i := Fixers.ledMax_uA k.ledOhm
  if Fixers.ledOk k.driveUA k.ledOhm then ⟨"Specs", check, .green, s!"{k.ledOhm} Ω gives up to {mA i} mA per LED", []⟩
  else match drives.find? (fun d => Fixers.ledOk d k.ledOhm) with
    | some d =>
      let alt := match Fixers.fixLedResistor k.driveUA with | some r => s!" (or {r} Ω)" | none => ""
      let msg := s!"{k.ledOhm} Ω gives up to {mA i} mA: GPIO17–23 must be set to {d / 1000} mA drive{alt}"
      ⟨"Specs", check, .yellow, msg, [(ledRefs, msg)]⟩
    | none =>
      let alt := match Fixers.fixLedResistor 8000 with | some r => s!" ({r} Ω works at 8 mA)" | none => ""
      let msg := s!"{k.ledOhm} Ω gives up to {mA i} mA per LED: over every RP2040 drive setting or the 50 mA total{alt}"
      ⟨"Specs", check, .red, msg, [(ledRefs, msg)]⟩

/-! ### Decoupling

ASSUMPTION (datasheets): the AP2112K needs at least 1 µF on its input and on its output. The RP2040
hardware design guide puts 1 µF on VREG_VIN and on VREG_VOUT, 100 nF on every IOVDD, DVDD and
USB_VDD pin, and at least 100 nF on ADC_AVDD. The supply pins are counted from the schematic
(`rp2040_supply_pins`). -/

structure Rail where
  net : String
  /-- Least total capacitance that must stay fitted, nF. -/
  minTotalNF : Nat
  /-- Least number of 100 nF capacitors that must stay fitted (one per supply pin). -/
  minSmall : Nat
  why : String

def rails : List Rail := [
  ⟨"VBUS", 1000, 0, "AP2112K input needs 1 µF"⟩,
  ⟨"+3.3V", 2700, 7, "AP2112K output 1 µF, RP2040 VREG_VIN 1 µF, and 100 nF on each of 6 IOVDD pins and USB_VDD"⟩,
  ⟨"+1.1V", 1200, 2, "RP2040 VREG_VOUT 1 µF and 100 nF on each of 2 DVDD pins"⟩,
  ⟨"ADC_AVDD", 100, 0, "RP2040 ADC_AVDD needs 100 nF"⟩]

/-- Capacitance of a BOM capacitor, nF (0 for anything that is not a decoupling value). -/
def capNF (ref : String) : Nat :=
  match (Package.bom.find? (·.refdes.contains ref)).map (·.value) with
  | some "1uF" => 1000 | some "2.2uF" => 2200 | some "0.1uF" => 100 | _ => 0

/-- Capacitors the schematic draws between this rail and GND. -/
def railCaps (net : String) : List String :=
  (Package.schematicPins.filter fun (r, _, n) => n == net && r.startsWith "C" &&
    Package.schematicPins.any (fun (r2, _, n2) => r2 == r && n2 == "GND")).map (·.1)

def railTotal (dni : List String) (net : String) : Nat :=
  (((railCaps net).filter (!dni.contains ·)).map capNF).foldl (· + ·) 0

def railSmall (dni : List String) (net : String) : Nat :=
  ((railCaps net).filter fun c => !dni.contains c && capNF c == 100).length

/-- Green: every schematic capacitor on the rail is fitted. Yellow: some are left off but the rail
still meets the datasheet minimum. Red: below the minimum. -/
def railColor (dni : List String) (r : Rail) : Color :=
  if ((railCaps r.net).all (!dni.contains ·)) then .green
  else if r.minTotalNF ≤ railTotal dni r.net && r.minSmall ≤ railSmall dni r.net then .yellow
  else .red

def railRow (dni : List String) (r : Rail) : Row :=
  let caps := railCaps r.net
  let off := caps.filter (dni.contains ·)
  let total := railTotal dni r.net
  let check := s!"Decoupling on {r.net} ({caps.length} on the schematic)"
  match railColor dni r with
  | .green => ⟨"Decoupling", check, .green, s!"all fitted, {total} nF", []⟩
  | .yellow =>
    ⟨"Decoupling", check, .yellow, s!"{", ".intercalate off} not fitted: {total} nF left, still above the datasheet minimum, but not the schematic",
      off.map fun c => ([c], s!"{c}: not fitted, {r.net} still meets the datasheet minimum ({total} nF left)")⟩
  | .red =>
    ⟨"Decoupling", check, .red, s!"{", ".intercalate off} not fitted: {total} nF and {railSmall dni r.net} × 100 nF left. {r.why}",
      off.map fun c => ([c], s!"{c}: not fitted, {r.net} falls below the datasheet minimum. {r.why}")⟩

/-- Unpopulated parts that are not decoupling capacitors: the schematic needs them. -/
def otherDni (dni : List String) : List String :=
  dni.filter fun c => !(rails.any fun r => (railCaps r.net).contains c)

/-- Rows about the design package (BOM, stack-up, specs, decoupling). Computed, not hard-coded. -/
def packageRowsK (k : Knobs) : List Row :=
  let bad := (Package.bom.map fun l => if l.line == 5 then { l with qty := k.ledQty } else l).filter
    (fun l => !Breaks.qtyConsistent l)
  let t := Breaks.stack (k.cuStackup * 120)
  let tj := Fixers.ldoTj k.loadmA
  let cl := Fixers.crystalLoad k.crystalC
  [ if bad.isEmpty then ⟨"Package", "BOM quantities match the designator lists", .green, "proved", []⟩
    else ⟨"Package", "BOM quantities match the designator lists", .yellow,
      String.intercalate "; " (bad.map fun l => s!"row {l.line}: qty {l.qty} but {l.refdes.length} designators"),
      bad.map fun l => (l.refdes, s!"BOM row {l.line}: quantity {l.qty} but {l.refdes.length} designators")⟩,
    if k.cuStackup == k.cuInstructions then
      ⟨"Package", "Inner copper: stack-up agrees with instructions", .green, "proved", []⟩
    else
      let msg := s!"stack-up {k.cuStackup}/10 oz vs instructions {k.cuInstructions}/10 oz; ask the fab" ++
        (if Breaks.within62 t && Breaks.within62 (Breaks.stack (k.cuInstructions * 120))
         then " (both readings meet 62 mil ± 10 %)" else "")
      ⟨"Package", "Inner copper: stack-up agrees with instructions", .yellow, msg, [([], msg)]⟩,
    if Breaks.within62 t then ⟨"Package", "Stack-up thickness within 62 mil ± 10 %", .green, s!"{mil1 t} mil", []⟩
    else ⟨"Package", "Stack-up thickness within 62 mil ± 10 %", .red, s!"{mil1 t} mil is out of tolerance",
      [([], s!"stack-up is {mil1 t} mil, outside 62 mil ± 10 %")]⟩,
    if (Breaks.impedanceNets.all fun n => Breaks.leanRule n k.pairW k.pairGap) then
      ⟨"Package", "90 Ω pairs use the stack-up geometry (5/4 mil), all other nets ≥ 6 mil", .green,
        "a single global 6 mil DFM rule would wrongly flag these 6 nets", []⟩
    else
      let msg := s!"pairs drawn {d1 (k.pairW / 10)}/{d1 (k.pairGap / 10)} mil, the stack-up table gives 5.0/4.0 mil for 90 Ω"
      ⟨"Package", "90 Ω pairs use the stack-up geometry (5/4 mil), all other nets ≥ 6 mil", .red, msg, [([], msg)]⟩,
    ledRow k,
    if Fixers.ldoOk k.loadmA then ⟨"Specs", "AP2112 junction temperature < 125 °C", .green, s!"{tj} °C worst case", []⟩
    else
      let msg := s!"{tj} °C at {k.loadmA} mA" ++
        (match Fixers.fixLdoLoad with | some i => s!" (largest safe load {i} mA)" | none => "")
      ⟨"Specs", "AP2112 junction temperature < 125 °C", .red, msg, [(["U2"], msg)]⟩,
    if Specs.pllUsb.valid && Specs.pllUsb.outKHz == 48000 then ⟨"Specs", "USB clock exactly 48 MHz", .green, "PLL 12 MHz × 100 ÷ 5 ÷ 5", []⟩
    else ⟨"Specs", "USB clock exactly 48 MHz", .red, "wrong PLL", [(["Y1"], "wrong PLL")]⟩,
    if Specs.pllSys.outKHz / 2 ≤ Specs.flashMaxQuadMHz * 1000 then ⟨"Specs", "QSPI clock within W25Q128 limit", .green, "62.5 ≤ 133 MHz", []⟩
    else ⟨"Specs", "QSPI clock within W25Q128 limit", .red, "overclocked", [(["U3"], "overclocked")]⟩,
    if Fixers.crystalOk Specs.crystalCL k.crystalC then
      ⟨"Specs", "Crystal load capacitors suit the crystal", .green, s!"{d1 k.crystalC} pF gives a {d1 cl} pF load", []⟩
    else
      let msg := s!"{d1 k.crystalC} pF gives a {d1 cl} pF load, the crystal needs {d1 Specs.crystalCL} pF" ++
        (match Fixers.fixCrystalCaps Specs.crystalCL with | some c => s!" (use {d1 c} pF)" | none => "")
      ⟨"Specs", "Crystal load capacitors suit the crystal", .red, msg, [(["C6", "C7", "Y1"], msg)]⟩,
    if Fixers.rdOk k.rdOhm then ⟨"Specs", "USB-C Rd pull-downs inside the Type-C window", .green, s!"{k.rdOhm} Ω", []⟩
    else
      let msg := s!"{k.rdOhm} Ω is outside the Type-C Rd window" ++
        (match Fixers.fixRd with | some r => s!" (use {r} Ω)" | none => "")
      ⟨"Specs", "USB-C Rd pull-downs inside the Type-C window", .red, msg, [(["R1", "R2"], msg)]⟩ ]
  ++ rails.map (railRow k.dni)
  ++ (if (otherDni k.dni).isEmpty then []
      else [⟨"Decoupling", "Every other part is populated", .red, s!"{", ".intercalate (otherDni k.dni)} not fitted",
        (otherDni k.dni).map fun c => ([c], s!"{c}: not fitted, the schematic needs it")⟩])

/-- The package as supplied. -/
def packageRows : List Row := packageRowsK {}

/-- Every placed footprint needs exactly one matching geometry record. -/
def geometryIssues (b : List Footprint) (ps : List Fit3D.Part) : List (List String × String) :=
  let footprints := b.map (·.ref)
  let parts := ps.map (·.ref)
  (footprints ++ parts).eraseDups.filterMap fun ref =>
    if footprints.count ref == 1 && parts.count ref == 1 then none
    else some ([ref], s!"{ref}: expected one footprint and one geometry record")

/-- The whole report for a board and a setting of the knobs. -/
def reportK (k : Knobs) (b : List Footprint) (outline : List (Int × Int)) (ps : List Fit3D.Part) : List Row :=
  boardRows b ++ [rowI "3D fit" "Each footprint has one geometry record" .red (geometryIssues b ps)] ++
    fitRows outline ps ++ packageRowsK k

/-- The report for a board with the package as supplied: this is what `leancheck` prints. -/
def report (b : List Footprint) (outline : List (Int × Int)) (ps : List Fit3D.Part) : List Row :=
  reportK {} b outline ps

def overall (rows : List Row) : Color := rows.foldl (fun c r => c.worst r.color) .green

/-- Green and yellow are accepted by the design checker. A red finding blocks acceptance. -/
def Color.accepted (c : Color) : Bool := c.rank < Color.red.rank

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

theorem accepted_has_no_red (rows : List Row) (h : (overall rows).accepted = true)
    (r : Row) (hr : r ∈ rows) : r.color ≠ .red := by
  intro hc
  have hle := overall_is_worst rows r hr
  rw [hc] at hle
  exact (Nat.not_lt_of_ge hle) (of_decide_eq_true h)

/-- JSON for the CLI and the HTML report. -/
def esc (s : String) : String := (s.replace "\\" "\\\\").replace "\"" "\\\""

def toJson (rows : List Row) : String :=
  "{\"overall\":\"" ++ (overall rows).name ++ "\",\"accepted\":" ++
    toString (overall rows).accepted ++ ",\"rows\":[" ++
    String.intercalate "," (rows.map fun r =>
      "{\"section\":\"" ++ esc r.section_ ++ "\",\"check\":\"" ++ esc r.check ++ "\",\"color\":\"" ++
        r.color.name ++ "\",\"detail\":\"" ++ esc r.detail ++ "\"}") ++ "]}"

end LeanVsDFM.Report
