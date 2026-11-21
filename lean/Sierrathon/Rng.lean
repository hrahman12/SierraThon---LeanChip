/-!
# Fair roll from random bytes

The RP2040's ring oscillator gives random bits; we turn a byte into a face with
rejection sampling. `b % 6` alone would be biased (256 isn't a multiple of 6), so bytes
≥ 252 are rejected and redrawn.
-/
namespace Sierrathon.Rng

def limit : Nat := 252   -- largest multiple of 6 ≤ 256

/-- `some face` (1..6), or `none` = reject and draw another byte. -/
def roll (b : Nat) : Option Nat := if b < limit then some (b % 6 + 1) else none

/-- Every accepted result is a valid face. -/
theorem roll_in_range : ∀ b, b < 256 → ∀ f, roll b = some f → 1 ≤ f ∧ f ≤ 6 := by
  intro b _ f h
  unfold roll at h
  split at h
  · cases h; omega
  · cases h

/-- Exact fairness: each face has exactly 42 of the 256 bytes mapping to it. -/
theorem roll_uniform :
    [1, 2, 3, 4, 5, 6].all (fun f => ((List.range 256).filter (fun b => roll b == some f)).length == 42)
      = true := by decide

/-- Rejection is rare: only 4/256 bytes (1.6%) need a redraw. -/
theorem reject_count : ((List.range 256).filter (fun b => roll b == none)).length = 4 := by decide

/-- The naive `b % 6 + 1` really is biased (faces 1–4 get 43 bytes, 5–6 get 42). -/
theorem naive_is_biased :
    ((List.range 256).filter (fun b => b % 6 + 1 == 1)).length = 43 ∧
    ((List.range 256).filter (fun b => b % 6 + 1 == 6)).length = 42 := by decide

end Sierrathon.Rng
