# Project direction (from the project owner)

- **Lean for the PCB, not the chip.** Lean verifies the PCB designs we make (schematic, BOM,
  footprints, pin-to-net connections, land patterns, stack-up, manufacturer specs). It does not
  run on the RP2040, and on-board firmware self-tests are out of scope.
- The pitch is **Lean vs DFM**: DFM checks fabrication geometry; Lean proves the design is the
  intended design and meets manufacturer specifications, and its fixers repair failures.
- Use the official Sierrathon files (schematic PDF, BOM, Stack-Up.png, instructions, scorecard)
  as the source of truth. Do not invent circuits or results; show where the supplied design breaks.
- Keep the schematic and BOM unchanged (Sierrathon rules).
- Lean proofs must be kernel-checked: no `sorry`, `admit` or `native_decide` in `leanvsdfm/`.
- The Riemann Hypothesis direction (`RHProofChip/`) is parked.
