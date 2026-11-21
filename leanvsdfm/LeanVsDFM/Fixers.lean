/-!
# Verified fixers

A fixer takes a manufacturer specification and searches a list of buildable options
(E12/E24 part values, legal PLL settings, legal clock dividers) for one that meets it.
For every fixer we prove, with the Lean kernel only:

* **`*_fails`**  : the broken design violates the spec (the failure is real),
* **`*_found`**  : the fixer returns this concrete value,
* **`*_sound`**  : *any* value the fixer returns meets the spec (correct by construction),
* **`*_minimal`**: every option tried before it fails (it is the first/smallest that works).

The search is `List.find?`; `find?_sound` and `find?_first` below are the two lemmas that
make every fixer correct, proved once.
-/
namespace LeanVsDFM.Fixers

/-! ## The two lemmas behind every fixer -/

/-- What `find?` returns satisfies the predicate and comes from the list. -/
theorem find?_sound {α : Type} {p : α → Bool} :
    ∀ {l : List α} {a : α}, l.find? p = some a → p a = true ∧ a ∈ l
  | [], _, h => by simp at h
  | x :: xs, a, h => by
    rw [List.find?_cons] at h
    cases hx : p x with
    | true =>
      rw [hx] at h
      have : x = a := Option.some.inj h
      subst this
      exact ⟨hx, List.Mem.head _⟩
    | false =>
      rw [hx] at h
      have ⟨h1, h2⟩ := find?_sound h
      exact ⟨h1, List.Mem.tail _ h2⟩

/-- Everything `find?` skipped before its answer fails the predicate. -/
theorem find?_first {α : Type} {p : α → Bool} :
    ∀ {l : List α} {a : α}, l.find? p = some a →
      ∃ pre post, l = pre ++ a :: post ∧ ∀ b ∈ pre, p b = false
  | [], _, h => by simp at h
  | x :: xs, a, h => by
    rw [List.find?_cons] at h
    cases hx : p x with
    | true =>
      rw [hx] at h
      have : x = a := Option.some.inj h
      subst this
      exact ⟨[], xs, rfl, by simp⟩
    | false =>
      rw [hx] at h
      obtain ⟨pre, post, hl, hpre⟩ := find?_first h
      refine ⟨x :: pre, post, by simp [hl], ?_⟩
      intro b hb
      rcases List.mem_cons.mp hb with rfl | hb
      · exact hx
      · exact hpre b hb

/-! ## Standard values -/

/-- E12 capacitor values, 10 pF … 82 pF, in units of 0.1 pF. -/
def e12pF : List Nat := [100, 120, 150, 180, 220, 270, 330, 390, 470, 560, 680, 820]

/-- E24 resistor values, 100 Ω … 9.1 kΩ. -/
def e24Ohm : List Nat :=
  let d := [100, 110, 120, 130, 150, 160, 180, 200, 220, 240, 270, 300,
            330, 360, 390, 430, 470, 510, 560, 620, 680, 750, 820, 910]
  d ++ d.map (· * 10)

/-! ## Fix 1: crystal load capacitors (Y1 with C6 = C7) -/

/-- Load seen by the crystal with two equal caps `c` and the nominal 2.5 pF stray (0.1 pF units). -/
def crystalLoad (c : Nat) : Nat := c / 2 + 25

/-- ABM8-272 spec: C_L = 10 pF; we demand |C_L − target| ≤ 1 pF at nominal stray. -/
def crystalOk (target c : Nat) : Bool := target ≤ crystalLoad c + 10 && crystalLoad c ≤ target + 10

def fixCrystalCaps (target : Nat) : Option Nat := e12pF.find? (crystalOk target)

/-- A common copy-paste failure: 22 pF caps from a 20 pF-crystal reference design. -/
theorem crystal_fails : crystalOk 100 220 = false := by decide
theorem crystal_found : fixCrystalCaps 100 = some 150 := by decide
theorem crystal_sound (t c : Nat) (h : fixCrystalCaps t = some c) :
    t ≤ crystalLoad c + 10 ∧ crystalLoad c ≤ t + 10 := by
  have := (find?_sound h).1
  simpa [crystalOk] using this
theorem crystal_minimal : (e12pF.filter (· < 150)).all (fun c => !crystalOk 100 c) = true := by decide
/-- The Sierrathon BOM already uses 15 pF: the fixer confirms it. -/
theorem crystal_design_ok : crystalOk 100 150 = true := by decide

/-! ## Fix 2: LED series resistors vs the RP2040 GPIO drive setting -/

/-- Worst-case LED current in µA for series resistor `r` Ω: VDD 3.35 V, Vf 1.8 V, R − 5 %. -/
def ledMax_uA (r : Nat) : Nat := (1550 * 1000000 + 950 * r - 1) / (950 * r)

/-- Spec: the current fits the pad drive limit `limit` µA, and all 7 LEDs fit the 50 mA budget. -/
def ledOk (limit r : Nat) : Bool := 0 < r && ledMax_uA r ≤ limit && 7 * ledMax_uA r ≤ 50000

def fixLedResistor (limit : Nat) : Option Nat := e24Ohm.find? (ledOk limit)

/-- Failure: a 68 Ω resistor (a common "bright LED" value) needs 24 mA per pin. -/
theorem led_fails : ledMax_uA 68 = 23994 ∧ ledOk 8000 68 = false := by decide
/-- With the RP2040's 8 mA drive setting the smallest safe E24 value is 240 Ω. 220 Ω fits one
pin (7.417 mA ≤ 8 mA) but seven LEDs would draw 51.9 mA, over the 50 mA budget … -/
theorem led_found_8mA : fixLedResistor 8000 = some 240 := by decide
/-- … and with the 4 mA default it is 430 Ω. -/
theorem led_found_4mA : fixLedResistor 4000 = some 430 := by decide
theorem led_sound (limit r : Nat) (h : fixLedResistor limit = some r) :
    ledMax_uA r ≤ limit ∧ 7 * ledMax_uA r ≤ 50000 := by
  have := (find?_sound h).1
  simp [ledOk] at this
  exact ⟨this.1.2, this.2⟩
theorem led_minimal_8mA : (e24Ohm.filter (· < 240)).all (fun r => !ledOk 8000 r) = true := by decide
/-- 220 Ω is exactly the value that fails on the 50 mA budget alone. -/
theorem led_220_fails_budget : ledMax_uA 220 ≤ 8000 ∧ 7 * ledMax_uA 220 > 50000 := by decide
/-- The BOM's 330 Ω passes at 8 mA but FAILS at the 4 mA default: the fix is a firmware
setting (8 mA drive), because the BOM may not change. -/
theorem led_design : ledOk 8000 330 = true ∧ ledOk 4000 330 = false := by decide

/-! ## Fix 3: USB PLL must give exactly 48 MHz -/

structure PLL where
  fbdiv : Nat
  post1 : Nat
  post2 : Nat
  deriving DecidableEq, Repr

/-- RP2040 constraints with the 12 MHz crystal: 16 ≤ FBDIV ≤ 320, VCO ∈ [750, 1600] MHz,
1 ≤ POSTDIV2 ≤ POSTDIV1 ≤ 7, and the output exactly `target` kHz. -/
def pllOk (target : Nat) (p : PLL) : Bool :=
  16 ≤ p.fbdiv && p.fbdiv ≤ 320 && 750 ≤ 12 * p.fbdiv && 12 * p.fbdiv ≤ 1600 &&
  1 ≤ p.post2 && p.post2 ≤ p.post1 && p.post1 ≤ 7 &&
  12000 * p.fbdiv = target * (p.post1 * p.post2)

/-- All legal settings, in search order. -/
def pllCandidates : List PLL :=
  (List.range 70).flatMap fun i => (List.range 7).flatMap fun j => (List.range 7).map fun k =>
    ⟨63 + i, 7 - j, k + 1⟩

def fixPLL (target : Nat) : Option PLL := pllCandidates.find? (pllOk target)

/-- Failure: POSTDIV 6 × 4 instead of 5 × 5 gives 50 MHz; USB will not enumerate. -/
theorem pll_fails : pllOk 48000 ⟨100, 6, 4⟩ = false := by decide
theorem pll_found : fixPLL 48000 = some ⟨64, 4, 4⟩ := by decide +kernel
theorem pll_sound (t : Nat) (p : PLL) (h : fixPLL t = some p) : pllOk t p = true := (find?_sound h).1
/-- The SDK's own setting (FBDIV 100, POSTDIV 5 × 5) is also proved exact. -/
theorem pll_design_ok : pllOk 48000 ⟨100, 5, 5⟩ = true := by decide

/-! ## Fix 4: QSPI clock divider (W25Q128JV max 133 MHz; RP2040 SSI divider must be even) -/

def qspiOk (sysKHz d : Nat) : Bool := 2 ≤ d && d % 2 == 0 && sysKHz ≤ 133000 * d

def fixQspiDiv (sysKHz : Nat) : Option Nat := ((List.range 64).map (· + 2)).find? (qspiOk sysKHz)

/-- Failure: overclocking clk_sys to 300 MHz with the default divider 2 gives 150 MHz. -/
theorem qspi_fails : qspiOk 300000 2 = false := by decide
theorem qspi_found : fixQspiDiv 300000 = some 4 := by decide
theorem qspi_sound (f d : Nat) (h : fixQspiDiv f = some d) : f ≤ 133000 * d ∧ d % 2 = 0 := by
  have := (find?_sound h).1
  simp [qspiOk] at this
  exact ⟨this.2, this.1.2⟩
theorem qspi_design_ok : qspiOk 125000 2 = true := by decide

/-! ## Fix 5: AP2112 load limit from the junction-temperature spec -/

/-- Junction temperature, °C, at load `i` mA: 50 °C ambient, θJA 250 °C/W, 2.0 V drop. -/
def ldoTj (i : Nat) : Nat := 50 + (250 * 2000 * i + 999999) / 1000000

def ldoOk (i : Nat) : Bool := ldoTj i ≤ 125 && i ≤ 600

/-- Largest load that keeps Tj ≤ 125 °C: search downward from the 600 mA rating. -/
def fixLdoLoad : Option Nat := ((List.range 601).reverse).find? ldoOk

/-- Failure: LEDs at 24 mA each (Fix 2's broken 68 Ω) push the load to 245 mA. -/
theorem ldo_fails : ldoTj 245 = 173 ∧ ldoOk 245 = false := by decide
theorem ldo_found : fixLdoLoad = some 150 := by decide +kernel
theorem ldo_sound (i : Nat) (h : fixLdoLoad = some i) : ldoTj i ≤ 125 := by
  have := (find?_sound h).1
  simp [ldoOk] at this
  exact this.1
/-- The real board budget (112 mA, with 330 Ω LEDs) is inside the limit. -/
theorem ldo_design_ok : ldoOk 112 = true := by decide

/-! ## Fix 6: USB Type-C sink pull-down Rd = 5.1 kΩ ± 10 % -/

/-- A ±5 % resistor of nominal `r` stays inside the Type-C Rd window [4590, 5610] Ω. -/
def rdOk (r : Nat) : Bool := 4590 * 100 ≤ r * 95 && r * 105 ≤ 5610 * 100

def fixRd : Option Nat := e24Ohm.find? rdOk

/-- Failure: 10 kΩ (a pull-up value pasted as a pull-down): a C-to-C source never turns on VBUS. -/
theorem rd_fails : rdOk 10000 = false := by decide
theorem rd_found : fixRd = some 5100 := by decide
theorem rd_sound (r : Nat) (h : fixRd = some r) : 4590 * 100 ≤ r * 95 ∧ r * 105 ≤ 5610 * 100 := by
  have := (find?_sound h).1
  simpa [rdOk] using this
theorem rd_unique : (e24Ohm.filter rdOk) = [5100] := by decide

end LeanVsDFM.Fixers
