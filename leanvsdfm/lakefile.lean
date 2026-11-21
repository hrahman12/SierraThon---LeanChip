import Lake
open Lake DSL

package leanvsdfm

/-- Manufacturer specifications of the Sierrathon board as Lean theorems, the failure
modes they rule out, and verified fixers that repair a failing design. -/
@[default_target]
lean_lib LeanVsDFM
