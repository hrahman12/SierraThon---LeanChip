/-!
# Component math for the Sierrathon board, kernel-checked

One section per component. Every number that comes from a datasheet or a standard is a
named definition with its source in the doc string, so each theorem says exactly what it
depends on. Quantities are exact rationals written as scaled natural numbers (units in
each name), so every proof is checked by the Lean kernel (`decide`, `omega`, `simp`).
There is no floating point and no `native_decide`.

Where an inequality needs π, we use only the rational bounds `3141/1000 < π < 3142/1000`
(true facts, proved in Mathlib as `Real.pi_gt_d2`/`Real.pi_lt_d2` and sharper). We state
results for *every* value of π in that interval, so nothing is assumed about π beyond them.
-/
namespace LeanVsDFM.Specs

/-! ## U3: W25Q128JV QSPI flash (Winbond datasheet) -/

/-- Capacity, bytes: 128 Mbit. -/
def flashBytes : Nat := 128 * 1024 * 1024 / 8
/-- Program page, erase sector and erase block sizes, bytes. -/
def pageBytes : Nat := 256
def sectorBytes : Nat := 4096
def blockBytes : Nat := 65536
/-- Maximum SCLK for Fast Read Quad I/O (0xEB), MHz. -/
def flashMaxQuadMHz : Nat := 133

theorem flash_is_16MiB : flashBytes = 2 ^ 24 := by decide
theorem flash_pages : flashBytes / pageBytes = 65536 ∧ flashBytes % pageBytes = 0 := by decide
theorem flash_sectors : flashBytes / sectorBytes = 4096 ∧ flashBytes % sectorBytes = 0 := by decide
theorem flash_blocks : flashBytes / blockBytes = 256 ∧ flashBytes % blockBytes = 0 := by decide

/-- Every byte is reachable with the flash's 24-bit address. -/
theorem flash_24bit_addresses : ∀ a, a < flashBytes → a < 2 ^ 24 := by
  intro a h; rw [flash_is_16MiB] at h; exact h

/-- Certificate store: the last 64 KiB block of flash. -/
def certStoreOffset : Nat := flashBytes - blockBytes

theorem certStore_block_aligned : certStoreOffset % blockBytes = 0 ∧ certStoreOffset % sectorBytes = 0 := by
  decide

/-- If the firmware image is no larger than `certStoreOffset`, it cannot overlap the store
(`arm-none-eabi-size` reports the actual image size; see benchmarks/). -/
theorem certStore_disjoint (fwBytes : Nat) (h : fwBytes ≤ certStoreOffset) :
    ∀ a, a < fwBytes → a < certStoreOffset := by
  intro a ha; omega

/-! ## U1 clocks: RP2040 PLLs from the 12 MHz crystal Y1 (RP2040 datasheet §2.18) -/

structure PLL where
  refMHz : Nat
  fbdiv : Nat
  post1 : Nat
  post2 : Nat

/-- RP2040 PLL constraints: REFDIV = 1, 16 ≤ FBDIV ≤ 320, VCO in [750, 1600] MHz,
1 ≤ POSTDIV ≤ 7 and POSTDIV1 ≥ POSTDIV2. -/
def PLL.valid (p : PLL) : Bool :=
  16 ≤ p.fbdiv && p.fbdiv ≤ 320 && 750 ≤ p.refMHz * p.fbdiv && p.refMHz * p.fbdiv ≤ 1600 &&
  1 ≤ p.post2 && p.post2 ≤ p.post1 && p.post1 ≤ 7

/-- Output frequency in kHz (exact when divisible). -/
def PLL.outKHz (p : PLL) : Nat := p.refMHz * p.fbdiv * 1000 / (p.post1 * p.post2)

/-- The pico-sdk defaults the firmware uses. -/
def pllSys : PLL := ⟨12, 125, 6, 2⟩
def pllUsb : PLL := ⟨12, 100, 5, 5⟩

theorem pllSys_valid : pllSys.valid = true := by decide
theorem pllUsb_valid : pllUsb.valid = true := by decide
theorem clk_sys_125MHz : pllSys.outKHz = 125000 ∧ (12 * 125 * 1000) % (6 * 2) = 0 := by decide
/-- USB full speed needs exactly 48 MHz (±0.25 %); the USB PLL gives it with zero error. -/
theorem clk_usb_exactly_48MHz : pllUsb.outKHz = 48000 ∧ (12 * 100 * 1000) % (5 * 5) = 0 := by decide

/-- boot2 runs QSPI at clk_sys / 2. That is 62.5 MHz, within the flash's 133 MHz. -/
theorem qspi_clock_within_flash_limit : pllSys.outKHz / 2 ≤ flashMaxQuadMHz * 1000 := by decide

/-! ## Y1: ABM8-272-T3 load capacitance with C6 = C7 = 15 pF -/

/-- Capacitances in units of 0.1 pF. -/
def c6 : Nat := 150
def c7 : Nat := 150
/-- ABM8-272 specified load capacitance: 10 pF. -/
def crystalCL : Nat := 100

/-- Series value of C6 and C7: exactly 7.5 pF. -/
theorem series_caps : c6 * c7 / (c6 + c7) = 75 ∧ (c6 * c7) % (c6 + c7) = 0 := by decide

/-- For any board stray capacitance between 2 and 5 pF (pins plus traces, an ASSUMPTION
the layout must respect), the crystal sees between 9.5 and 12.5 pF. The 10 pF target is
met exactly at 2.5 pF stray. -/
theorem crystal_load_window (stray : Nat) (h1 : 20 ≤ stray) (h2 : stray ≤ 50) :
    95 ≤ 75 + stray ∧ 75 + stray ≤ 125 := by omega

theorem crystal_load_exact_at_2p5pF : 75 + 25 = crystalCL := by decide

/-! ## U2: AP2112K-3.3 LDO: headroom and junction temperature -/

/-- USB 2.0 VBUS at the connector, mV (USB 2.0 §7.2.1). -/
def vbusMin : Nat := 4750
def vbusMax : Nat := 5250
/-- AP2112K-3.3 output accuracy ±1.5 %, mV. -/
def voutMin : Nat := 3250
def voutMax : Nat := 3350
/-- Dropout at 600 mA, maximum (datasheet), mV. -/
def dropoutMax : Nat := 400
/-- Board load budget, mA (ASSUMPTIONS: RP2040 ≤ 50, flash ≤ 25, 7 LEDs ≤ 35, pull-ups etc. ≤ 2). -/
def loadMax : Nat := 50 + 25 + 35 + 2
/-- SOT-25 junction-to-ambient thermal resistance, °C/W (ASSUMPTION: datasheet-class value
for a 1-oz board; the 4-layer Sierrathon stack-up with planes should do better). -/
def thetaJA : Nat := 250
/-- Maximum ambient, °C (ASSUMPTION) and maximum junction temperature, °C (datasheet). -/
def ambientMax : Nat := 50
def tjMax : Nat := 125

/-- Even at the lowest VBUS, the regulator keeps more than its worst dropout. -/
theorem ldo_headroom : vbusMin - voutMax ≥ dropoutMax := by decide

/-- Load budget is within the AP2112's 600 mA rating and the board's 1 A rule. -/
theorem ldo_current_ok : loadMax ≤ 600 ∧ loadMax ≤ 1000 := by decide

/-- Worst-case dissipation, mW: (VBUS max − Vout min) × load max. -/
def pdissMax_mW : Nat := (vbusMax - voutMin) * loadMax / 1000

theorem ldo_dissipation : pdissMax_mW = 224 := by decide

/-- Junction temperature at worst case, °C (rounded up): ambient + θJA × P. -/
def tjWorst : Nat := ambientMax + (thetaJA * pdissMax_mW + 999) / 1000

theorem ldo_junction_ok : tjWorst = 106 ∧ tjWorst < tjMax := by decide

/-! ## J1, R1, R2: USB Type-C sink pull-downs -/

/-- Resistances in ohms. Type-C spec: Rd = 5.1 kΩ ± 10 %. BOM: 5.1 kΩ ± 5 %. -/
def rdNom : Nat := 5100

theorem rd_within_typeC_spec :
    ∀ r, rdNom * 95 ≤ r * 100 → r * 100 ≤ rdNom * 105 → rdNom * 90 ≤ r * 100 ∧ r * 100 ≤ rdNom * 110 := by
  intro r h1 h2; omega

/-- U4 USBLC6-2SC6 reverse stand-off voltage V_RWM, mV (BOM: "TVS DIODE 5.25VWM"). -/
def usblc6Vrwm : Nat := 5250

/-- The TVS does not conduct at any legal VBUS (V_RWM ≥ VBUS max), so it never loads the rail. -/
theorem esd_standoff_covers_vbus : vbusMax ≤ usblc6Vrwm := by decide

/-! ## R4, C5: ADC_AVDD RC filter, fc = 1 / (2πRC) -/

/-- R4 = 200 Ω ± 5 %, C5 = 2.2 µF ± 10 % (X7R, K tolerance). C in units of 10 nF. -/
def rMin : Nat := 190
def rMax : Nat := 210
def cMin : Nat := 198
def cMax : Nat := 242

/-- For every π with 3.141 < π < 3.142 (`piK` = π × 1000) and every in-tolerance R, C,
the corner frequency lies in [313 Hz, 424 Hz]. Statement: 313 ≤ 1/(2πRC) ≤ 424, cleared of
denominators (C is in units of 1e-8 F, π in units of 1e-3). -/
theorem adc_filter_corner (piK r c : Nat) (hp1 : 3141 < piK) (hp2 : piK < 3142)
    (hr1 : rMin ≤ r) (hr2 : r ≤ rMax) (hc1 : cMin ≤ c) (hc2 : c ≤ cMax) :
    313 * (2 * piK * r * c) ≤ 100000000000 ∧ 100000000000 ≤ 424 * (2 * piK * r * c) := by
  have hmax : 2 * piK * r * c ≤ 2 * 3142 * rMax * cMax := by
    have := Nat.mul_le_mul (Nat.mul_le_mul (Nat.mul_le_mul_left 2 (Nat.le_of_lt hp2)) hr2) hc2
    simpa [Nat.mul_assoc] using this
  have hmin : 2 * 3141 * rMin * cMin ≤ 2 * piK * r * c := by
    have := Nat.mul_le_mul (Nat.mul_le_mul (Nat.mul_le_mul_left 2 (Nat.le_of_lt hp1)) hr1) hc1
    simpa [Nat.mul_assoc] using this
  constructor
  · calc 313 * (2 * piK * r * c) ≤ 313 * (2 * 3142 * rMax * cMax) := Nat.mul_le_mul_left _ hmax
      _ ≤ 100000000000 := by decide
  · calc 100000000000 ≤ 424 * (2 * 3141 * rMin * cMin) := by decide
      _ ≤ 424 * (2 * piK * r * c) := Nat.mul_le_mul_left _ hmin

/-! ## D3–D9 with R12–R18 (330 Ω): LED current (see also lean/Sierrathon/Photonics.lean) -/

/-- Worst case: VDD 3.35 V, LED Vf 1.8 V (ASSUMPTION), R = 330 Ω − 5 %. µA, rounded up. -/
def ledMax_uA : Nat := ((voutMax - 1800) * 1000000 + 313500 - 1) / 313500

theorem led_current : ledMax_uA = 4945 ∧ 7 * ledMax_uA ≤ 50000 ∧ ledMax_uA ≤ 8000 := by decide

/-! ## Stack-up (Sierrathon Stack-Up.png): finished thickness vs the 62 mil target -/

/-- Layer thicknesses in µin (1 mil = 1000 µin): L1, prepreg, L2, core, L3, prepreg, L4, 2× mask. -/
def stackup_uin : List Nat := [1500, 4348, 600, 45600, 600, 4348, 1500, 500, 500]

theorem stackup_within_tolerance :
    stackup_uin.sum = 59496 ∧ 62000 * 90 ≤ stackup_uin.sum * 100 ∧ stackup_uin.sum * 100 ≤ 62000 * 110 := by
  decide

/-- The fab's simulated impedances (Stack-Up.png) are inside the ±10 % tolerance. Units 0.1 Ω. -/
theorem impedances_within_tolerance :
    (900 * 90 ≤ 897 * 100 ∧ 897 * 100 ≤ 900 * 110) ∧ (500 * 90 ≤ 497 * 100 ∧ 497 * 100 ≤ 500 * 110) := by
  decide

end LeanVsDFM.Specs
