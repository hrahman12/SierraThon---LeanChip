/-!
# Photonics: quantum ceilings on the light this board can deliver

Integer units only (µeV, mV, mΩ, µA, µW), so every bound is checked exactly by
the kernel; no floating point anywhere.

The key quantum fact: an LED makes **at most one photon per electron**
(internal quantum efficiency ≤ 1), and each 625 nm photon carries E = hc/λ.
So for *any* LED, efficiency unknown:

  photon flux ≤ I / e     and     optical power ≤ I · (E_photon / e)

These are hard physical ceilings, independent of the LED datasheet's brightness.
-/
namespace Sierrathon.Photonics

/-! ## Constants (exact, CODATA 2018 / SI) -/
/-- h·c in µeV·nm  (1239.841984 eV·nm). -/
def hc_ueV_nm : Nat := 1239841984
/-- Elementary charge × 10¹⁹ × 10⁹ (1.602176634e-19 C, scaled to an integer). -/
def e_scaled : Nat := 1602176634

/-! ## Board parameters (from BOM / schematic) and stated assumptions -/
def wavelength_nm : Nat := 625          -- QBLP601-R5, BOM line 5
def R_nom_mOhm    : Nat := 330000       -- R12..R18, 330 Ω
def R_tol_pct     : Nat := 5            -- "5%" in BOM description
def Vdd_max_mV    : Nat := 3350         -- ASSUMPTION: AP2112K-3.3 worst-case high (+1.5%)
def Vf_min_mV     : Nat := 1800         -- ASSUMPTION: LED forward voltage minimum (verify vs QBLP601 datasheet)
def Vf_typ_mV     : Nat := 2000         -- ASSUMPTION: typical forward voltage
def gpio_drive_uA : Nat := 8000         -- firmware must set RP2040 pad drive to 8 mA
def iovdd_total_uA: Nat := 50000        -- ASSUMPTION: RP2040 total GPIO source budget (verify vs datasheet)
def xtal_ppm      : Nat := 50           -- ASSUMPTION: ABM8-272 total frequency error, worst case
def nLeds         : Nat := 7

/-! ## Quantum: photon energy and bandgap consistency -/
def photon_ueV : Nat := hc_ueV_nm / wavelength_nm

/-- A 625 nm photon carries 1.98 eV, the AlGaInP bandgap region. -/
theorem photon_energy : photon_ueV = 1983747 := by decide

/-- Energy conservation sanity check: the junction voltage covers the photon energy
(e·V_f ≥ E_photon), so the stated V_f is physically consistent with the colour. -/
theorem bandgap_consistent : photon_ueV ≤ Vf_typ_mV * 1000 := by decide

/-! ## Electrical: worst-case LED current -/
def R_min_mOhm : Nat := R_nom_mOhm * (100 - R_tol_pct) / 100
/-- Worst case (high rail, low V_f, low resistor) current per LED, µA (rounded up). -/
def I_max_uA : Nat := ((Vdd_max_mV - Vf_min_mV) * 1000000 + R_min_mOhm - 1) / R_min_mOhm

theorem led_current_max : I_max_uA = 4945 := by decide

/-- RP2040 default 4 mA drive is NOT enough at worst case → firmware sets 8 mA. -/
theorem default_drive_insufficient : I_max_uA > 4000 := by decide
theorem drive_8mA_sufficient : I_max_uA ≤ gpio_drive_uA := by decide

/-- All 7 LEDs on at once stays inside the RP2040 GPIO budget. -/
theorem all_leds_within_budget : nLeds * I_max_uA ≤ iovdd_total_uA := by decide

/-! ## Quantum ceilings on delivered light -/
/-- Max photons per millisecond per LED: ⌈I/e⌉ (≤ 1 photon per electron). -/
def photons_per_ms_max : Nat := (I_max_uA * 10^19 + e_scaled - 1) / e_scaled

theorem photon_flux_ceiling : photons_per_ms_max ≤ 3087 * 10^10 := by decide  -- ≤ 3.09e13 photons/ms (3.09e16 /s)

/-- Max optical power per LED, µW: P ≤ I · E_photon/e  (= I[µA] · E[µeV] / 10⁶). -/
def P_opt_max_uW : Nat := (I_max_uA * photon_ueV + 999999) / 1000000

theorem optical_power_ceiling : P_opt_max_uW = 9810 := by decide             -- ≤ 9.81 mW per LED
theorem array_power_ceiling : nLeds * P_opt_max_uW ≤ 68700 := by decide     -- ≤ 68.7 mW, all 7

/-! ## Dose: exposure timed by the 12 MHz crystal -/
/-- Worst-case actual exposure (ms) for a programmed exposure, given crystal error. -/
def exposure_max_ms (t_ms : Nat) : Nat := (t_ms * (1000000 + xtal_ppm) + 999999) / 1000000

/-- Dose ceiling in µJ for one LED over a programmed exposure. -/
def dose_max_uJ (t_ms : Nat) : Nat := (P_opt_max_uW * exposure_max_ms t_ms + 999) / 1000

/-- A 60 s exposure can never exceed 589 mJ of 625 nm light per LED, whatever the LED efficiency. -/
theorem dose_60s : dose_max_uJ 60000 ≤ 589000 := by decide

/-- Crystal timing error over a 10-minute protocol is ≤ 30 ms. -/
theorem timing_10min : exposure_max_ms 600000 - 600000 ≤ 30 := by decide

end Sierrathon.Photonics
