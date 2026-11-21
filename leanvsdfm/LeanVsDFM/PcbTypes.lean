/-! Types for a PCB as extracted from KiCad (integer nanometres, KiCad's internal unit). -/
namespace LeanVsDFM.Pcb

structure Pad where
  number : String
  net : String
  x : Int       -- relative to the footprint origin, nm
  y : Int
  w : Int       -- pad size, nm
  h : Int
  deriving Repr, DecidableEq

structure Footprint where
  ref : String
  lib : String  -- KiCad footprint name (library item)
  rot : Int     -- degrees
  pads : List Pad
  deriving Repr

end LeanVsDFM.Pcb
