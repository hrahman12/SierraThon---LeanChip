/-!
# Measurement arithmetic, kernel-checked

The firmware measures itself with three on-chip instruments. These lemmas make sure the
arithmetic that turns raw readings into reported numbers is right.

1. **SysTick** (24-bit down-counter at clk_sys). The Cortex-M0+ has no DWT cycle counter,
   so cycle counts come from SysTick. Elapsed cycles are `(start − end) mod 2²⁴`, which is
   correct exactly when the true interval is shorter than one wrap.
2. **Die temperature** (RP2040 ADC input 4, datasheet §4.9.5):
   T = 27 − (V − 0.706) / 0.001721 °C, with V = raw × 3.3 / 4096.
   The firmware uses an integer formula; we prove its error bound for all 4096 raw codes.
3. **Frequency counter** (RP2040 FC0): reports kHz; we prove what tolerance the 12 MHz
   crystal reading is checked against.
-/
namespace RHPC.Measurement

/-! ## 1. SysTick -/

def wrap : Nat := 2 ^ 24

/-- What the firmware computes from two SysTick readings. -/
def elapsed (start stop : Nat) : Nat := (start + wrap - stop) % wrap

/-- If the counter was at `start`, counted down `d < 2²⁴` ticks (wrapping) and reads `stop`,
then `elapsed start stop = d`. -/
theorem elapsed_correct (start d : Nat) (hs : start < wrap) (hd : d < wrap) :
    elapsed start ((start + wrap - d) % wrap) = d := by
  unfold elapsed wrap at *
  omega

/-- At 125 MHz one wrap lasts 134 ms, so the firmware times work in chunks of at most
100 ms (12.5 M cycles), safely inside one wrap. -/
theorem chunk_fits_in_wrap : 125000000 / 10 < wrap ∧ wrap * 1000 / 125000000 = 134 := by decide

/-! ## 2. Die temperature -/

/-- Firmware formula (`firmware/src/rhpc_measure.c`), milli-°C. `raw` is the 12-bit ADC code.
`uv` = raw × 3 300 000 / 4096 µV (floor); result = 27 000 − (uv − 706 000) × 1000 / 1721,
with C's truncating division (Int.tdiv). -/
def tempFirmware_mC (raw : Nat) : Int :=
  let uv : Int := (raw * 3300000 / 4096 : Nat)
  27000 - Int.tdiv ((uv - 706000) * 1000) 1721

/-- The exact value, scaled: T_exact(raw) × (4096 × 1721) in milli-°C. -/
def tempExactScaled (raw : Nat) : Int :=
  27000 * (4096 * 1721) - ((raw : Int) * 3300000 - 706000 * 4096) * 1000

/-- **Error bound for every ADC code.** The firmware's integer temperature differs from the
exact formula by less than 2 m°C: flooring the voltage to whole µV costs up to ≈0.58 m°C and
the truncating division up to 1 m°C (the worst case over all codes is 1.57 m°C). That is far
below the sensor's own accuracy of a few °C. Checked by the kernel on all 4096 codes. -/
theorem temp_error_lt_2mC :
    (List.range 4096).all (fun raw =>
      let e := tempFirmware_mC raw * (4096 * 1721) - tempExactScaled raw
      decide (-(2 * (4096 * 1721)) < e ∧ e < 2 * (4096 * 1721))) = true := by
  decide +kernel

/-- …and the 1 m°C bound I first claimed is false: some code exceeds it. -/
theorem temp_error_not_lt_1mC :
    (List.range 4096).all (fun raw =>
      let e := tempFirmware_mC raw * (4096 * 1721) - tempExactScaled raw
      decide (-(4096 * 1721) < e ∧ e < 4096 * 1721)) = false := by
  decide +kernel

/-- Sanity: raw 876 (0.70577 V, the code nearest 0.706 V) reads 27.138 °C. -/
theorem temp_at_raw_876 : tempFirmware_mC 876 = 27138 := by decide

/-! ## 3. Frequency counter -/

/-- A frequency-counter reading in [11 999, 12 001] kHz is accepted as "crystal OK". -/
def xoscOk (kHz : Nat) : Bool := 11999 ≤ kHz && kHz ≤ 12001

/-- **Every** crystal within ABM8-272's ±20 ppm (ASSUMPTION: datasheet tolerance class), i.e.
f ∈ [11 999 760, 12 000 240] Hz, read through FC0 whose result `r` (kHz) is within one count
of the truth (|1000·r − f| < 1000 Hz), passes the check. So a failing reading really means
the clock is outside tolerance or the counter is wrong. -/
theorem xosc_check_complete (f r : Nat) (hf1 : 11999760 ≤ f) (hf2 : f ≤ 12000240)
    (hr1 : f < r * 1000 + 1000) (hr2 : r * 1000 < f + 1000) : xoscOk r = true := by
  have h1 : 11999 ≤ r := by omega
  have h2 : r ≤ 12001 := by omega
  simp [xoscOk, h1, h2]

theorem nominal_xosc_accepted : xoscOk 12000 = true := by decide

end RHPC.Measurement
