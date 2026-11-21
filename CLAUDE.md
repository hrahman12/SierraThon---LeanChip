# Project direction (from the project owner)

- **The goal: 2D → 3D verification in Lean.** Does the flat design (schematic, BOM, stack-up,
  footprints) really become the intended physical board? Lean proves it for the PCB designs we
  make: parts, pins and nets, land patterns, bodies inside courtyards, no collisions, inside the
  outline, stack-up, manufacturer specs.
- **Lean is for the PCB, not the chip.** It does not run on the RP2040; no firmware self-tests.
- **Lean vs DFM**: DFM checks fabrication geometry; Lean proves the design is the intended design.
- **This board, these exact parts only**: the 21-line Sierrathon BOM.
- The tool gives **green / yellow / red**, certified by the Lean kernel (`leanvsdfm/tools/leancheck.py`).
- AI (or any proposer) may suggest build combinations; only Lean's certified verdict counts.
- Use the official Sierrathon files as the source of truth. Do not invent circuits or results;
  show where the supplied design breaks. Keep the schematic and BOM unchanged.
- Proofs must be kernel-checked: no `sorry`, `admit` or `native_decide` in `leanvsdfm/`.
- Use real EDA tools (KiCad, OpenCascade), not hand-drawn diagrams.
- No Riemann Hypothesis content. `RHProofChip/` and `QuantumBioProof/` are parked.

# How to work here

- Check a board: `python3 leanvsdfm/tools/leancheck.py leanvsdfm/pcb/sierrathon.kicad_pcb`
- Rebuild boards and Lean data: `leanvsdfm/tools/make_boards.sh`, then `cd leanvsdfm && lake build`
- Slash commands: `/leancheck`, `/explore`, `/verify`, `/board3d` (see `.claude/commands/`).
- Lean toolchain: v4.36.0 (`leanvsdfm/lean-toolchain`). KiCad 7 with its Python API (`pcbnew`).
