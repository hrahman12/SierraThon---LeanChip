import LeanVsDFM.PartsVerifier
import LeanVsDFM.PcbData
import LeanVsDFM.PcbFaultNarrowFlash
import LeanVsDFM.PcbFaultLedReversed
import LeanVsDFM.PcbFaultWrongCapSize
import LeanVsDFM.PcbFaultFlashPinsSwapped
/-!
# Verdicts on our PCB designs, as kernel-checked theorems

`pcb/sierrathon.kicad_pcb` is our board. The four `pcb/fault_*.kicad_pcb` boards are the same
board with one realistic mistake each. All are real KiCad 7 files, read back with KiCad's own
API (`tools/extract_pcb.py`). Each verdict below is proved by the Lean kernel (`decide +kernel`).
-/
namespace LeanVsDFM.Verify
open LeanVsDFM.Parts

/-- **Our board.** Every package, every one of the schematic's pin↔net connections, LED
polarity and the U3 manufacturer land pattern verify. The only findings are the four parts
still on KiCad library stand-ins, which need the manufacturer's footprint. -/
theorem our_board :
    verify PcbData.board =
      [.wrongPackage "J1" "USB_C_Receptacle_HRO_TYPE-C-31-M-12" "MFR:UJ20-C-H-G-SMT-TR",
       .wrongPackage "SW1" "SW_SPST_TL3342" "MFR:PTS526SM15SMTR2",
       .wrongPackage "SW2" "SW_SPST_TL3342" "MFR:PTS526SM15SMTR2",
       .wrongPackage "SW3" "SW_PUSH_6mm" "MFR:D6R90F2LFS"] := by
  decide +kernel

/-- Equivalently: no electrical, polarity or land-pattern issue at all on our board. -/
theorem our_board_electrically_clean : electrical (verify PcbData.board) = [] := by decide +kernel

/-- Fault: the 150 mil SOIC-8 used for the 208 mil W25Q128JVSIQ. Clean geometry, wrong part. -/
theorem catches_narrow_flash :
    electrical (verify PcbFaultNarrowFlash.board) =
      [.wrongPackage "U3" "SOIC-8_3.9x4.9mm_P1.27mm" "SOIC-8_5.23x5.23mm_P1.27mm"] := by
  decide +kernel

/-- Fault: D5 placed with anode and cathode swapped. -/
theorem catches_reversed_led :
    electrical (verify PcbFaultLedReversed.board) =
      [.wrongNet "D5" "1" "LED3_A" "GND", .wrongNet "D5" "2" "GND" "LED3_A",
       .strayNet "D5" "1" "LED3_A", .strayNet "D5" "2" "GND", .polarity "D5"] := by
  decide +kernel

/-- Fault: an 0603 footprint on an 0402 BOM line (C4). -/
theorem catches_wrong_cap_size :
    electrical (verify PcbFaultWrongCapSize.board) =
      [.wrongPackage "C4" "C_0603_1608Metric" "C_0402_1005Metric"] := by
  decide +kernel

/-- Fault: flash DO/D1 and DI/D0 pins swapped on the footprint. -/
theorem catches_swapped_flash_pins :
    electrical (verify PcbFaultFlashPinsSwapped.board) =
      [.wrongNet "U3" "2" "QSPI_D0" "QSPI_D1", .wrongNet "U3" "5" "QSPI_D1" "QSPI_D0",
       .strayNet "U3" "2" "QSPI_D0", .strayNet "U3" "5" "QSPI_D1"] := by
  decide +kernel

/-! ## 2D → 3D: the placed board fits together -/

/-- **Our board fits.** Every 3D body is inside its courtyard, no two courtyards overlap, every
pad and body is inside the hexagonal outline, and every drill is at least 8 mil. -/
theorem our_board_fits : Fit3D.fit3d PcbData.outline PcbData.parts = [] := by decide +kernel

/-- **No two part bodies overlap on our board.** This is the general theorem
`Fit3D.bodies_never_collide` applied to our board; the kernel checks the hypothesis. -/
theorem our_board_bodies_never_collide : PcbData.parts.Pairwise Fit3D.bodySep :=
  Fit3D.bodies_never_collide _ (by decide +kernel)

/-- The only part without a 3D body model is the USB-C connector (library stand-in). -/
theorem our_board_unmodelled : Fit3D.noBody PcbData.parts = ["J1"] := by decide +kernel

/-- Assembled height: 1.511 mm board (59.496 mil stack-up) + 4.300 mm tallest body
(SW3's stand-in model) = 5.811 mm. -/
theorem our_board_envelope :
    PcbData.thicknessNm = 1511198 ∧ Fit3D.maxHeight PcbData.parts = 4300000 := by decide +kernel

/-- All 54 parts are on the board model, 49 of them with a 3D body. -/
theorem our_board_counts :
    PcbData.parts.length = 54 ∧ (PcbData.parts.filter (·.model.isSome)).length = 49 := by decide +kernel

end LeanVsDFM.Verify
