import RHProofChip.Soundness
import RHProofChip.Codec
/-!
# Example certificates

These are the certificates shipped in `certificates/valid/` and built into the firmware.
Each acceptance is proved by `decide`, i.e. checked by the Lean **kernel** itself, and the
soundness theorem then turns acceptance into the mathematical statement.
-/
namespace RHPC.Examples

open RHPC

def p : Formula := .var 0
def two : Term := num 2
def four : Term := num 4

/-- `p → p` via the classic S K K proof. -/
def identity : Cert where
  goal := .imp p p
  steps := [
    .axS p (.imp p p) p,       -- 0
    .axK p (.imp p p),         -- 1
    .mp 0 1,                   -- 2 : (p → (p → p)) → (p → p)
    .axK p p,                  -- 3 : p → (p → p)
    .mp 2 3 ]                  -- 4 : p → p

/-- `2 + 2 = 4`. -/
def twoPlusTwo : Cert where
  goal := .eq (.add two two) four
  steps := [
    .addSucc two (num 1),      -- 0 : 2 + S1 = S(2 + 1)
    .addSucc two .zero,        -- 1 : 2 + S0 = S(2 + 0)
    .addZero two,              -- 2 : 2 + 0 = 2
    .congSucc 2,               -- 3 : S(2 + 0) = S2
    .trans 1 3,                -- 4 : 2 + 1 = 3
    .congSucc 4,               -- 5 : S(2 + 1) = 4
    .trans 0 5 ]               -- 6 : 2 + 2 = 4

/-- `2 × 2 = 4` (uses the multiplication axioms and congruence). -/
def twoTimesTwo : Cert where
  goal := .eq (.mul two two) four
  steps := [
    .mulSucc two (num 1),      -- 0 : 2·2 = 2·1 + 2
    .mulSucc two .zero,        -- 1 : 2·1 = 2·0 + 2
    .mulZero two,              -- 2 : 2·0 = 0
    .refl two,                 -- 3 : 2 = 2
    .congAdd 2 3,              -- 4 : 2·0 + 2 = 0 + 2
    .trans 1 4,                -- 5 : 2·1 = 0 + 2
    .addSucc .zero (num 1),    -- 6 : 0 + 2 = S(0 + 1)
    .addSucc .zero .zero,      -- 7 : 0 + 1 = S(0 + 0)
    .addZero .zero,            -- 8 : 0 + 0 = 0
    .congSucc 8,               -- 9 : S(0 + 0) = 1
    .trans 7 9,                -- 10 : 0 + 1 = 1
    .congSucc 10,              -- 11 : S(0 + 1) = 2
    .trans 6 11,               -- 12 : 0 + 2 = 2
    .trans 5 12,               -- 13 : 2·1 = 2
    .congAdd 13 3,             -- 14 : 2·1 + 2 = 2 + 2
    .trans 0 14,               -- 15 : 2·2 = 2 + 2
    .addSucc two (num 1),      -- 16 : 2 + 2 = S(2 + 1)
    .addSucc two .zero,        -- 17
    .addZero two,              -- 18
    .congSucc 18,              -- 19
    .trans 17 19,              -- 20 : 2 + 1 = 3
    .congSucc 20,              -- 21 : S(2 + 1) = 4
    .trans 16 21,              -- 22 : 2 + 2 = 4
    .trans 15 22 ]             -- 23 : 2·2 = 4

/-! Kernel-checked acceptance (`decide` runs `check` inside the Lean kernel). -/

theorem identity_ok : check identity = true := by decide
theorem twoPlusTwo_ok : check twoPlusTwo = true := by decide
theorem twoTimesTwo_ok : check twoTimesTwo = true := by decide

/-! What acceptance *means*, via the soundness theorem. -/

theorem identity_true (v : Nat → Bool) : (Formula.imp p p).sem v = true :=
  check_sound_sem identity identity_ok v

theorem two_plus_two : (Term.add two two).eval = four.eval :=
  check_sound_eq _ _ _ twoPlusTwo_ok

theorem two_times_two : (Term.mul two two).eval = four.eval :=
  check_sound_eq _ _ _ twoTimesTwo_ok

/-! The encoder/decoder round-trips on the shipped certificates (kernel-checked). -/

theorem identity_roundtrip : verdict identity.encode = .accept := by decide
theorem twoPlusTwo_roundtrip : verdict twoPlusTwo.encode = .accept := by decide

/-! Invalid inference steps are rejected. -/

/-- Claims `2 + 2 = 5`; the last step does not produce the goal. -/
def bogusFive : Cert := { twoPlusTwo with goal := .eq (.add two two) (num 5) }
theorem bogusFive_rejected : check bogusFive = false := by decide

/-- Modus ponens applied to the wrong premise. -/
def badMp : Cert where
  goal := .imp p p
  steps := [.axK p p, .axK p (.imp p p), .mp 0 1]
theorem badMp_rejected : check badMp = false := by decide

/-- A forward reference (line 0 citing line 1). -/
def forwardRef : Cert where
  goal := .eq two two
  steps := [.symm 1, .refl two]
theorem forwardRef_rejected : check forwardRef = false := by decide

end RHPC.Examples
