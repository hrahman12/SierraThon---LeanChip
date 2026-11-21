/-!
# The RHPC calculus

A deliberately small proof calculus that fits on an RP2040:

* **Propositional fragment**: implication and `⊥`, with the Hilbert axioms K, S and
  double-negation elimination (DNE), and modus ponens. This is complete for classical
  propositional logic over `→, ⊥`.
* **Equational arithmetic fragment**: equations between closed terms built from
  `0`, successor, `+` and `×`; the four defining equations of `+` and `×`, and the
  equality rules reflexivity, symmetry, transitivity and congruence.

Semantics is Boolean (`Formula.sem`), so everything here is decidable and the
soundness proof uses no axioms beyond Lean's core.
-/
namespace RHPC

/-- Closed arithmetic terms. -/
inductive Term where
  | zero
  | succ (t : Term)
  | add (a b : Term)
  | mul (a b : Term)
  deriving DecidableEq, Repr, Inhabited

/-- The value of a term in `ℕ`. -/
def Term.eval : Term → Nat
  | .zero => 0
  | .succ t => t.eval + 1
  | .add a b => a.eval + b.eval
  | .mul a b => a.eval * b.eval

/-- Formulas: propositional variables, `⊥`, implication, and term equations. -/
inductive Formula where
  | var (n : Nat)
  | bot
  | imp (a b : Formula)
  | eq (a b : Term)
  deriving DecidableEq, Repr, Inhabited

/-- Boolean semantics under a valuation `v` of the propositional variables. -/
def Formula.sem (v : Nat → Bool) : Formula → Bool
  | .var n => v n
  | .bot => false
  | .imp a b => !(a.sem v) || b.sem v
  | .eq a b => decide (a.eval = b.eval)

/-- Derivability in the RHPC calculus. This is the *specification*: the checker is proved
to accept only certificates whose goal is `Derivable`. -/
inductive Derivable : Formula → Prop where
  | axK (a b : Formula) : Derivable (.imp a (.imp b a))
  | axS (a b c : Formula) :
      Derivable (.imp (.imp a (.imp b c)) (.imp (.imp a b) (.imp a c)))
  | axDNE (a : Formula) : Derivable (.imp (.imp (.imp a .bot) .bot) a)
  | mp {a b : Formula} : Derivable (.imp a b) → Derivable a → Derivable b
  | refl (t : Term) : Derivable (.eq t t)
  | addZero (t : Term) : Derivable (.eq (.add t .zero) t)
  | addSucc (t u : Term) : Derivable (.eq (.add t (.succ u)) (.succ (.add t u)))
  | mulZero (t : Term) : Derivable (.eq (.mul t .zero) .zero)
  | mulSucc (t u : Term) : Derivable (.eq (.mul t (.succ u)) (.add (.mul t u) t))
  | symm {a b : Term} : Derivable (.eq a b) → Derivable (.eq b a)
  | trans {a b c : Term} : Derivable (.eq a b) → Derivable (.eq b c) → Derivable (.eq a c)
  | congSucc {a b : Term} : Derivable (.eq a b) → Derivable (.eq (.succ a) (.succ b))
  | congAdd {a b c d : Term} :
      Derivable (.eq a b) → Derivable (.eq c d) → Derivable (.eq (.add a c) (.add b d))
  | congMul {a b c d : Term} :
      Derivable (.eq a b) → Derivable (.eq c d) → Derivable (.eq (.mul a c) (.mul b d))

/-- Numerals as terms: `num 2 = succ (succ zero)`. -/
def num : Nat → Term
  | 0 => .zero
  | n + 1 => .succ (num n)

theorem num_eval (n : Nat) : (num n).eval = n := by
  induction n with
  | zero => rfl
  | succ n ih => simp [num, Term.eval, ih]

end RHPC
