import Sierrathon
open Sierrathon

def main : IO Unit := do
  IO.println "Sierrathon dice: faces rendered on the real LED layout"
  for n in Dice.faces do
    IO.println s!"\nface {n}  (GPIO mask 0x{(Nat.toDigits 16 (Dice.mask n)).asString})"
    IO.println (Dice.render n)
