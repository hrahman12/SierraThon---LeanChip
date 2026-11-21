import Lake
open Lake DSL

package rhproofchip

/-- The restricted proof calculus, its executable checker and the soundness proofs. -/
lean_lib RHProofChip

/-- `rhpc-lean <cert.bin>...` : run the Lean reference checker on binary certificates. -/
@[default_target]
lean_exe «rhpc-lean» where
  root := `Main
