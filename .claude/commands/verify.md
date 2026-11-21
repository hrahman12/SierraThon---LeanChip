---
description: Rebuild every Lean proof and audit the axioms
allowed-tools: Bash(lake build:*), Bash(cd leanvsdfm && lake build:*), Bash(grep:*), Read
---
Check that every proof in `leanvsdfm/` still holds.

1. Run `cd leanvsdfm && lake build`. Report any error with its file and line.
2. Confirm there is no `sorry`, `admit` or `native_decide`:
   `grep -rn "sorry\|admit\|native_decide" leanvsdfm/LeanVsDFM/` (comments that mention the words do not count).
3. Report the number of theorems per module (`grep -c "^theorem" leanvsdfm/LeanVsDFM/*.lean`).
Never weaken a theorem statement to make it pass. If a proof fails, say what the kernel found.
