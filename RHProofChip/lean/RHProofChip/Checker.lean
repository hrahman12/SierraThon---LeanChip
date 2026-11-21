import RHProofChip.Calculus
/-!
# The executable checker

A certificate is a goal and a list of steps. Each step either instantiates an axiom or
applies a rule to **earlier** lines, referenced by index. The checker replays the steps
in order (a single streaming pass) and accepts iff every step is valid and the **last**
line equals the goal.

The C checker in `firmware/src/rhpc_checker.c` implements exactly these rules; the only
differences are resource limits (it rejects certificates that exceed its bounded memory)
and hash-consing of formulas. Differential tests check that the two agree.
-/
namespace RHPC

/-- One proof step. Indices refer to earlier lines (0-based). -/
inductive Step where
  | axK (a b : Formula)
  | axS (a b c : Formula)
  | axDNE (a : Formula)
  | mp (i j : Nat)          -- line i : a → b,  line j : a   ⊢  b
  | refl (t : Term)
  | addZero (t : Term)
  | addSucc (t u : Term)
  | mulZero (t : Term)
  | mulSucc (t u : Term)
  | symm (i : Nat)
  | trans (i j : Nat)
  | congSucc (i : Nat)
  | congAdd (i j : Nat)
  | congMul (i j : Nat)
  deriving Repr, DecidableEq

/-- A proof certificate: the claimed theorem and its proof steps. -/
structure Cert where
  goal : Formula
  steps : List Step
  deriving Repr

/-- The formula a step produces, given the lines proved so far; `none` = invalid step. -/
def stepResult (prev : List Formula) : Step → Option Formula
  | .axK a b => some (.imp a (.imp b a))
  | .axS a b c => some (.imp (.imp a (.imp b c)) (.imp (.imp a b) (.imp a c)))
  | .axDNE a => some (.imp (.imp (.imp a .bot) .bot) a)
  | .mp i j =>
    match prev[i]?, prev[j]? with
    | some (.imp a b), some a' => if a = a' then some b else none
    | _, _ => none
  | .refl t => some (.eq t t)
  | .addZero t => some (.eq (.add t .zero) t)
  | .addSucc t u => some (.eq (.add t (.succ u)) (.succ (.add t u)))
  | .mulZero t => some (.eq (.mul t .zero) .zero)
  | .mulSucc t u => some (.eq (.mul t (.succ u)) (.add (.mul t u) t))
  | .symm i =>
    match prev[i]? with
    | some (.eq a b) => some (.eq b a)
    | _ => none
  | .trans i j =>
    match prev[i]?, prev[j]? with
    | some (.eq a b), some (.eq b' c) => if b = b' then some (.eq a c) else none
    | _, _ => none
  | .congSucc i =>
    match prev[i]? with
    | some (.eq a b) => some (.eq (.succ a) (.succ b))
    | _ => none
  | .congAdd i j =>
    match prev[i]?, prev[j]? with
    | some (.eq a b), some (.eq c d) => some (.eq (.add a c) (.add b d))
    | _, _ => none
  | .congMul i j =>
    match prev[i]?, prev[j]? with
    | some (.eq a b), some (.eq c d) => some (.eq (.mul a c) (.mul b d))
    | _, _ => none

/-- Replay steps left to right, appending each new line. -/
def runSteps : List Formula → List Step → Option (List Formula)
  | acc, [] => some acc
  | acc, s :: ss =>
    match stepResult acc s with
    | some f => runSteps (acc ++ [f]) ss
    | none => none

/-- The last line must be the goal. -/
def lastIs (lines : List Formula) (goal : Formula) : Bool :=
  match lines.reverse with
  | g :: _ => g == goal
  | [] => false

/-- **The checker.** Deterministic and total. -/
def check (c : Cert) : Bool :=
  match runSteps [] c.steps with
  | some lines => lastIs lines c.goal
  | none => false

end RHPC
