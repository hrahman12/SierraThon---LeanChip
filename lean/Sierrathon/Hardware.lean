import Sierrathon.Design
/-!
# Hardware: walk the real netlist

Everything here is *computed* from `Design.nets`, so the firmware's LED table
comes from the circuit itself rather than from a hand-written pin list.
For each LED we trace:  RP2040 GPIO pin → net → series resistor → anode net → LED → GND.
-/
namespace Sierrathon.Hardware
open Design

/-- The net that `(ref, pin)` sits on, if any. -/
def netOf (ref pin : String) : Option String :=
  (nets.find? (fun (_, ms) => ms.contains (ref, pin))).map (·.1)

/-- Members of a named net. -/
def members (net : String) : List (String × String) :=
  ((nets.find? (·.1 == net)).map (·.2)).getD []

def u1PinName (pin : String) : Option String :=
  (u1PinNames.find? (·.1 == pin)).map (·.2)

/-- "GPIO17" ↦ 17. -/
def gpioNumber (name : String) : Option Nat :=
  if name.startsWith "GPIO" then (name.drop 4).toNat? else none

/-- Trace an LED's anode back to the RP2040 GPIO that drives it, through
exactly one series resistor. Returns `(gpio, resistor)`. -/
def ledDriver (led : String) : Option (Nat × String) := do
  let anode ← netOf led "2"
  -- the single resistor on the anode net
  let (r, rPin) ← (members anode).find? (fun (ref, _) => ref.startsWith "R")
  let otherPin := if rPin == "1" then "2" else "1"
  let drive ← netOf r otherPin
  let (_, u1pin) ← (members drive).find? (·.1 == "U1")
  let g ← gpioNumber (← u1PinName u1pin)
  pure (g, r)

/-- The LED's cathode goes straight to GND (so driving the GPIO high lights it). -/
def cathodeGrounded (led : String) : Bool := netOf led "1" == some "GND"

/-- GPIO wired to the user button SW3 (traced the same way). -/
def buttonGpio : Option Nat := do
  let n ← netOf "SW3" "1"
  let (_, p) ← (members n).find? (·.1 == "U1")
  gpioNumber (← u1PinName p)

/-- The button's other side is GND, i.e. active-low. -/
def buttonActiveLow : Bool := netOf "SW3" "3" == some "GND"

/-- And it has a pull-up to +3.3V on the GPIO side. -/
def buttonPulledUp : Bool :=
  match netOf "SW3" "1" with
  | some n => (members n).any (fun (ref, pin) => ref.startsWith "R" &&
                netOf ref (if pin == "1" then "2" else "1") == some "+3.3V")
  | none => false

/-! ## The "LED Placement" box on the schematic: (row, col) on a 3×3 grid. -/
def placement : List (String × (Nat × Nat)) :=
  [("D3", (0, 0)), ("D8", (0, 2)),
   ("D4", (1, 0)), ("D9", (1, 1)), ("D7", (1, 2)),
   ("D5", (2, 0)), ("D6", (2, 2))]

def ledAt (pos : Nat × Nat) : Option String :=
  (placement.find? (·.2 == pos)).map (·.1)

/-! ## Facts about the real circuit (checked against the netlist) -/

/-- Every placed LED is driven by a GPIO through a resistor, and its cathode is grounded. -/
theorem every_led_driven_and_grounded :
    placement.all (fun (d, _) => (ledDriver d).isSome && cathodeGrounded d) = true := by
  native_decide

/-- The exact GPIO each LED is wired to, recovered from the netlist. -/
theorem led_gpio_map :
    placement.map (fun (d, _) => (d, (ledDriver d).map (·.1))) =
      [("D3", some 17), ("D8", some 22), ("D4", some 18), ("D9", some 23),
       ("D7", some 21), ("D5", some 19), ("D6", some 20)] := by
  native_decide

/-- No two LEDs share a GPIO. -/
theorem led_gpios_distinct :
    let gs := placement.filterMap (fun (d, _) => (ledDriver d).map (·.1))
    gs.length = 7 ∧ gs.eraseDups.length = 7 := by
  native_decide

/-- The button is on GPIO24, active-low with a pull-up — and it is NOT an LED pin. -/
theorem button_wiring :
    buttonGpio = some 24 ∧ buttonActiveLow = true ∧ buttonPulledUp = true ∧
    ¬ (placement.any (fun (d, _) => (ledDriver d).map (·.1) == buttonGpio) = true) := by
  native_decide

end Sierrathon.Hardware
