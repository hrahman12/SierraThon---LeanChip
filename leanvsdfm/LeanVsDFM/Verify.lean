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
      [.wrongPackage "U3" "SOIC-8_3.9x4.9mm_P1.27mm" "SOIC-8_5.23x5.23mm_P1.27mm",
       .landPattern "U3" "1", .landPattern "U3" "2", .landPattern "U3" "3", .landPattern "U3" "4",
       .landPattern "U3" "5", .landPattern "U3" "6", .landPattern "U3" "7", .landPattern "U3" "8"] := by
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

end LeanVsDFM.Verify
