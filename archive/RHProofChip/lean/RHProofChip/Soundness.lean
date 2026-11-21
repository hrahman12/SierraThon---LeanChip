import RHProofChip.Checker
/-!
# Soundness of the checker

Main results:

* `check_sound` : an accepted certificate's goal is `Derivable`.
* `derivable_sound` : every `Derivable` formula is true under every valuation.
* `check_sound_sem` : so an accepted goal is true under every valuation.
* `check_sound_eq` : an accepted equation `a = b` has `a.eval = b.eval`.
* `not_derivable_bot`, `check_rejects_bot` : the calculus is consistent and the
  checker never accepts `⊥`.
-/
namespace RHPC

private theorem mem_of_getElem? {α : Type} :
    ∀ {l : List α} {n : Nat} {a : α}, l[n]? = some a → a ∈ l
  | [], _, _, h => by simp at h
  | x :: xs, 0, a, h => by
      have hx : x = a := by simpa using h
      subst hx; exact List.Mem.head _
  | x :: xs, n + 1, a, h => by
      have h' : xs[n]? = some a := by simpa using h
      exact List.Mem.tail _ (mem_of_getElem? h')

/-- Each valid step produces a derivable formula, given derivable earlier lines. -/
theorem stepResult_sound {prev : List Formula} (hprev : ∀ f ∈ prev, Derivable f)
    {s : Step} {f : Formula} (hs : stepResult prev s = some f) : Derivable f := by
  have get : ∀ {i : Nat} {g : Formula}, prev[i]? = some g → Derivable g :=
    fun h => hprev _ (mem_of_getElem? h)
  cases s with
  | axK a b => simp only [stepResult, Option.some.injEq] at hs; subst hs; exact .axK a b
  | axS a b c => simp only [stepResult, Option.some.injEq] at hs; subst hs; exact .axS a b c
  | axDNE a => simp only [stepResult, Option.some.injEq] at hs; subst hs; exact .axDNE a
  | refl t => simp only [stepResult, Option.some.injEq] at hs; subst hs; exact .refl t
  | addZero t => simp only [stepResult, Option.some.injEq] at hs; subst hs; exact .addZero t
  | addSucc t u => simp only [stepResult, Option.some.injEq] at hs; subst hs; exact .addSucc t u
  | mulZero t => simp only [stepResult, Option.some.injEq] at hs; subst hs; exact .mulZero t
  | mulSucc t u => simp only [stepResult, Option.some.injEq] at hs; subst hs; exact .mulSucc t u
  | mp i j =>
    simp only [stepResult] at hs
    split at hs
    · rename_i a b a' hi hj
      split at hs
      · rename_i heq
        simp only [Option.some.injEq] at hs
        subst hs; subst heq
        exact .mp (get hi) (get hj)
      · cases hs
    · cases hs
  | symm i =>
    simp only [stepResult] at hs
    split at hs
    · rename_i a b hi
      simp only [Option.some.injEq] at hs; subst hs
      exact .symm (get hi)
    · cases hs
  | trans i j =>
    simp only [stepResult] at hs
    split at hs
    · rename_i a b b' c hi hj
      split at hs
      · rename_i heq
        simp only [Option.some.injEq] at hs; subst hs; subst heq
        exact .trans (get hi) (get hj)
      · cases hs
    · cases hs
  | congSucc i =>
    simp only [stepResult] at hs
    split at hs
    · rename_i a b hi
      simp only [Option.some.injEq] at hs; subst hs
      exact .congSucc (get hi)
    · cases hs
  | congAdd i j =>
    simp only [stepResult] at hs
    split at hs
    · rename_i a b c d hi hj
      simp only [Option.some.injEq] at hs; subst hs
      exact .congAdd (get hi) (get hj)
    · cases hs
  | congMul i j =>
    simp only [stepResult] at hs
    split at hs
    · rename_i a b c d hi hj
      simp only [Option.some.injEq] at hs; subst hs
      exact .congMul (get hi) (get hj)
    · cases hs

/-- Replaying steps preserves "every line is derivable". -/
theorem runSteps_sound : ∀ (acc : List Formula) (ss : List Step) (out : List Formula),
    (∀ f ∈ acc, Derivable f) → runSteps acc ss = some out → ∀ f ∈ out, Derivable f
  | acc, [], out, h, hr => by
      simp only [runSteps, Option.some.injEq] at hr
      subst hr; exact h
  | acc, s :: ss, out, h, hr => by
      simp only [runSteps] at hr
      split at hr
      · rename_i f hf
        refine runSteps_sound (acc ++ [f]) ss out ?_ hr
        intro g hg
        rcases List.mem_append.mp hg with hg | hg
        · exact h g hg
        · have : g = f := by simpa using hg
          subst this
          exact stepResult_sound h hf
      · cases hr

theorem lastIs_mem {lines : List Formula} {goal : Formula} (h : lastIs lines goal = true) :
    goal ∈ lines := by
  unfold lastIs at h
  split at h
  · rename_i g rest hrev
    have hg : g = goal := by simpa using h
    subst hg
    have : g ∈ lines.reverse := by rw [hrev]; exact List.Mem.head _
    exact List.mem_reverse.mp this
  · cases h

/-- **Soundness (syntactic):** the checker only accepts derivable goals. -/
theorem check_sound (c : Cert) (hc : check c = true) : Derivable c.goal := by
  unfold check at hc
  split at hc
  · rename_i lines hl
    exact runSteps_sound [] c.steps lines (by simp) hl c.goal (lastIs_mem hc)
  · cases hc

/-- Truth of an equation is equality of values. -/
theorem sem_eq (v : Nat → Bool) (a b : Term) : (Formula.eq a b).sem v = true ↔ a.eval = b.eval := by
  simp only [Formula.sem, decide_eq_true_eq]

/-- **Soundness of the calculus:** derivable formulas are true under every valuation. -/
theorem derivable_sound {φ : Formula} (h : Derivable φ) (v : Nat → Bool) : φ.sem v = true := by
  induction h with
  | axK a b =>
    simp only [Formula.sem]; cases a.sem v <;> cases b.sem v <;> rfl
  | axS a b c =>
    simp only [Formula.sem]; cases a.sem v <;> cases b.sem v <;> cases c.sem v <;> rfl
  | axDNE a =>
    simp only [Formula.sem]; cases a.sem v <;> rfl
  | mp _ _ ih1 ih2 =>
    simp only [Formula.sem, ih2, Bool.not_true, Bool.false_or] at ih1
    exact ih1
  | refl t => exact (sem_eq v t t).mpr rfl
  | addZero t => exact (sem_eq v _ _).mpr (by simp only [Term.eval]; omega)
  | addSucc t u => exact (sem_eq v _ _).mpr (by simp only [Term.eval]; omega)
  | mulZero t => exact (sem_eq v _ _).mpr (by simp only [Term.eval]; exact Nat.mul_zero _)
  | mulSucc t u => exact (sem_eq v _ _).mpr (by simp only [Term.eval]; exact Nat.mul_succ _ _)
  | symm _ ih => exact (sem_eq v _ _).mpr ((sem_eq v _ _).mp ih).symm
  | trans _ _ ih1 ih2 => exact (sem_eq v _ _).mpr (((sem_eq v _ _).mp ih1).trans ((sem_eq v _ _).mp ih2))
  | congSucc _ ih =>
    exact (sem_eq v _ _).mpr (by simp only [Term.eval]; rw [(sem_eq v _ _).mp ih])
  | congAdd _ _ ih1 ih2 =>
    exact (sem_eq v _ _).mpr (by simp only [Term.eval]; rw [(sem_eq v _ _).mp ih1, (sem_eq v _ _).mp ih2])
  | congMul _ _ ih1 ih2 =>
    exact (sem_eq v _ _).mpr (by simp only [Term.eval]; rw [(sem_eq v _ _).mp ih1, (sem_eq v _ _).mp ih2])

/-- **Main theorem:** an accepted certificate's goal is true under every valuation. -/
theorem check_sound_sem (c : Cert) (hc : check c = true) (v : Nat → Bool) :
    c.goal.sem v = true :=
  derivable_sound (check_sound c hc) v

/-- **Arithmetic corollary:** an accepted equation is true in `ℕ`. -/
theorem check_sound_eq (a b : Term) (steps : List Step) (hc : check ⟨.eq a b, steps⟩ = true) :
    a.eval = b.eval := by
  exact (sem_eq (fun _ => false) a b).mp (check_sound_sem ⟨.eq a b, steps⟩ hc (fun _ => false))

/-- The calculus is consistent. -/
theorem not_derivable_bot : ¬ Derivable .bot := fun h => by
  have := derivable_sound h (fun _ => false)
  simp [Formula.sem] at this

/-- No certificate for `⊥` is ever accepted. -/
theorem check_rejects_bot (steps : List Step) : check ⟨.bot, steps⟩ = false := by
  cases h : check ⟨.bot, steps⟩ with
  | false => rfl
  | true => exact absurd (check_sound _ h) not_derivable_bot

end RHPC
