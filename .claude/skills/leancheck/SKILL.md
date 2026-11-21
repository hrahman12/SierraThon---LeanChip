---
name: leancheck
description: Verify the Sierrathon RP2040 PCB with Lean 4. Use when asked to check, verify, rate or fix the board, a footprint, a pin mapping, the BOM, the stack-up, or whether the 2D design fits together in 3D; or when asked for a green / yellow / red verdict.
---
# leancheck: 2D → 3D verification of the Sierrathon PCB

This repository proves, with the Lean 4 kernel, that the flat design (schematic, BOM, stack-up,
footprints) becomes the intended physical board. It is scoped to this board and its 21 BOM lines.

## What to run

| Goal | Command |
|---|---|
| Verdict for a board | `python3 leanvsdfm/tools/leancheck.py <board.kicad_pcb> [--html out.html] [--json]` |
| Rebuild all boards and Lean data | `leanvsdfm/tools/make_boards.sh` |
| Re-prove everything | `cd leanvsdfm && lake build` |
| Rate many build options | `python3 leanvsdfm/tools/explore.py 40 leanvsdfm/explore/results.json` |
| 3D export and agreement test | see `.claude/commands/board3d.md` |

## Rules

- Lean is for the PCB design, not firmware on the chip.
- Keep the schematic and BOM unchanged (Sierrathon rules).
- A verdict counts only if `leancheck` prints "certified by the Lean kernel".
- No `sorry`, `admit` or `native_decide` in `leanvsdfm/`. Never weaken a theorem to make it pass.
- Tests (for example `check_step_agreement.py`) are tests: never call them proofs.
- Colours: red = not the intended design; yellow = buildable but needs an action; green = proved.

## Where things are

- `leanvsdfm/LeanVsDFM/PartsVerifier.lean`: package, pins, nets, polarity, land pattern.
- `leanvsdfm/LeanVsDFM/Fit3D.lean`: bodies inside courtyards, no collisions, inside the outline;
  theorem `bodies_never_collide`.
- `leanvsdfm/LeanVsDFM/Breaks.lean`: the four problems in the supplied package.
- `leanvsdfm/LeanVsDFM/Fixers.lean`: verified fixers (find a part value that meets the spec).
- `leanvsdfm/LeanVsDFM/Verify.lean`: verdicts for our board and the four fault boards.
