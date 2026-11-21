import Sierrathon.Hardware
/-!
# Dice faces

Faces are defined abstractly on the 3×3 pip grid (the way a real die looks),
then compiled to an RP2040 GPIO bit mask *through the netlist*.
-/
namespace Sierrathon.Dice
open Hardware

abbrev Pos := Nat × Nat

def corners : List Pos := [(0, 0), (0, 2), (2, 0), (2, 2)]

/-- Pip layout of face `n` (1..6). -/
def pips : Nat → List Pos
  | 1 => [(1, 1)]
  | 2 => [(0, 0), (2, 2)]
  | 3 => [(0, 0), (1, 1), (2, 2)]
  | 4 => corners
  | 5 => corners ++ [(1, 1)]
  | 6 => corners ++ [(1, 0), (1, 2)]
  | _ => []

def faces : List Nat := [1, 2, 3, 4, 5, 6]

/-- 180° rotation of the grid. -/
def rot180 (p : Pos) : Pos := (2 - p.1, 2 - p.2)

/-- GPIO mask for face `n`, via placement box → LED refdes → netlist trace. -/
def mask (n : Nat) : Nat :=
  (pips n).foldl (fun m p =>
    match ledAt p >>= ledDriver with
    | some (g, _) => m ||| (1 <<< g)
    | none => m) 0

/-- All LED GPIOs (bit mask). -/
def ledMask : Nat := mask 6 ||| mask 1

def popcount (x : Nat) : Nat := (List.range 32).countP (fun i => x.testBit i)

/-! ## Pure die-geometry facts (kernel-checked with `decide`) -/

/-- Face n shows exactly n pips. -/
theorem pip_count : faces.all (fun n => (pips n).length == n) = true := by decide

/-- Every pip lands on a spot that has an LED (no pip on the empty top/bottom-middle). -/
theorem pips_on_leds : faces.all (fun n => (pips n).all (fun p => (ledAt p).isSome)) = true := by
  decide

/-- Like a real die, every face looks the same upside down. -/
theorem faces_point_symmetric :
    faces.all (fun n => (pips n).all (fun p => (pips n).contains (rot180 p))) = true := by decide

/-! ## Facts about the compiled masks (through the netlist) -/

/-- Face n lights exactly n LEDs on the real board. -/
theorem mask_lights_n_leds : faces.all (fun n => popcount (mask n) == n) = true := by native_decide

/-- The six faces are pairwise distinct patterns. -/
theorem masks_distinct : (faces.map mask).eraseDups.length = 6 := by native_decide

/-- Firmware only ever drives GPIO17..GPIO23 — never the button (GPIO24) or anything else. -/
theorem masks_only_touch_led_pins :
    faces.all (fun n => mask n &&& (0x7F <<< 17) == mask n) = true ∧ ledMask = 0x7F <<< 17 := by
  native_decide

/-- The concrete table the firmware ships. -/
theorem mask_table :
    faces.map mask = [0x800000, 0x120000, 0x920000, 0x5A0000, 0xDA0000, 0x7E0000] := by
  native_decide

/-- ASCII preview of a face on the real LED layout. -/
def render (n : Nat) : String :=
  let cell (r c : Nat) := match ledAt (r, c) with
    | none => " "
    | some _ => if (pips n).contains (r, c) then "●" else "○"
  String.intercalate "\n" ((List.range 3).map fun r =>
    String.intercalate " " ((List.range 3).map fun c => cell r c))

end Sierrathon.Dice
