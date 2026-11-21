import Lake
open Lake DSL

package sierrathon

lean_lib Sierrathon

@[default_target]
lean_exe sierrathon where
  root := `Main
