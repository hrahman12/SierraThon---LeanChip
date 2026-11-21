import Sierrathon.Dice
/-!
# Blinded, balanced randomization of 6 sample wells

The 6 outer LEDs form a ring of sample sites (wells, Petri dishes, plant pots,
larvae chambers). Each run, firmware randomly picks **3 to illuminate and 3 as sham
controls**. The centre LED (D9) is the "exposure running" indicator.

We prove the randomizer is balanced (always 3 vs 3) and **exactly uniform** over all
C(6,3) = 20 balanced assignments, the property a blinded trial needs.
-/
namespace Sierrathon.Protocol
set_option maxRecDepth 200000
open Hardware

/-- Ring order of the outer sites, clockwise from top-left (from the placement box). -/
def ring : List String := ["D3", "D8", "D7", "D6", "D5", "D4"]

/-- All 6-bit masks with exactly 3 bits set, in increasing order. -/
def balanced : List Nat :=
  (List.range 64).filter (fun m => (List.range 6).countP (fun i => m.testBit i) == 3)

theorem twenty_designs : balanced.length = 20 := by decide

/-- Rejection sampling: bytes ≥ 240 are redrawn, so 240 = 12 × 20 maps evenly. -/
def assign (b : Nat) : Option Nat :=
  if b < 240 then balanced[b % 20]? else none

/-- Every accepted assignment treats exactly 3 wells and shams exactly 3. -/
theorem always_balanced :
    (List.range 240).all (fun b => match assign b with
      | some m => (List.range 6).countP (fun i => m.testBit i) == 3
      | none => false) = true := by decide

/-- Exactly uniform: each of the 20 designs has exactly 12 of the 256 byte values. -/
theorem uniform_over_designs :
    balanced.all (fun m => ((List.range 256).filter (fun b => assign b == some m)).length == 12)
      = true := by decide

/-- Each individual well is treated in exactly half the designs, so no site bias. -/
theorem each_well_half :
    (List.range 6).all (fun i => (balanced.filter (fun m => m.testBit i)).length == 10) = true := by
  decide

/-- Convert a design (bit i = ring[i]) to the GPIO mask that lights the treated wells. -/
def designGpioMask (m : Nat) : Nat :=
  (List.range 6).foldl (fun acc i =>
    if m.testBit i then
      match ring[i]? >>= ledDriver with
      | some (g, _) => acc ||| (1 <<< g)
      | none => acc
    else acc) 0

/-- Every design lights exactly 3 real LEDs, never the centre indicator (GPIO23) or the button (GPIO24). -/
theorem design_masks_safe :
    balanced.all (fun m =>
      Dice.popcount (designGpioMask m) == 3 &&
      !((designGpioMask m).testBit 23) && !((designGpioMask m).testBit 24)) = true := by
  native_decide

end Sierrathon.Protocol
