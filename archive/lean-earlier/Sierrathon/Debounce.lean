/-!
# Button debouncer (SW3, active-low)

Sampled every 1 ms. A press counts only after `N` consecutive pressed samples,
and fires once per press: it's latched until the button is seen released.
-/
namespace Sierrathon.Debounce

def N : Nat := 5   -- 5 ms of stable "pressed"

structure State where
  count : Nat := 0
  latched : Bool := false
deriving Repr, DecidableEq

/-- One sample step; returns the new state and whether a roll event fires. -/
def step (s : State) (pressed : Bool) : State × Bool :=
  if !pressed then ({ count := 0, latched := false }, false)
  else if s.latched then (s, false)
  else if s.count + 1 ≥ N then ({ count := 0, latched := true }, true)
  else ({ s with count := s.count + 1 }, false)

/-- Run over a sample trace; return the number of events. -/
def run (s : State) : List Bool → Nat
  | [] => 0
  | x :: xs => let (s', e) := step s x; (if e then 1 else 0) + run s' xs

/-- An event only fires on a pressed sample. -/
theorem event_needs_press (s : State) (p : Bool) : (step s p).2 = true → p = true := by
  cases p <;> simp [step]

/-- While latched (held down), no further events — no auto-repeat. -/
theorem latched_silent (s : State) (p : Bool) (h : s.latched = true) : (step s p).2 = false := by
  cases p <;> simp [step, h]

/-- A released sample always clears everything. -/
theorem release_resets (s : State) : step s false = ({ count := 0, latched := false }, false) := by
  simp [step]

/-- Glitches shorter than N samples never fire. -/
theorem short_glitch_ignored :
    ∀ k, k < N → run {} (List.replicate k true ++ [false]) = 0 := by
  intro k hk; simp only [N] at hk
  match k, hk with
  | 0, _ | 1, _ | 2, _ | 3, _ | 4, _ => rfl

/-- Holding the button for a long time fires exactly once. -/
theorem long_hold_fires_once : run {} (List.replicate 1000 true) = 1 := by native_decide

/-- Exhaustive check: over *every* 10-sample trace, events ≤ number of separate presses. -/
def presses (t : List Bool) : Nat :=
  -- count rising edges (start of each run of `true`)
  (t.foldl (fun (acc : Nat × Bool) x => (if x && !acc.2 then acc.1 + 1 else acc.1, x)) (0, false)).1

def allTraces : Nat → List (List Bool)
  | 0 => [[]]
  | n + 1 => (allTraces n).flatMap (fun t => [true :: t, false :: t])

theorem never_double_counts : (allTraces 10).all (fun t => run {} t ≤ presses t) = true := by
  native_decide

end Sierrathon.Debounce
