import LeanVsDFM.Check
/-!
# `leanchip`: the compiled checker

Reads one build on stdin (tab-separated lines, written by `tools/leancheck.py` and by the web page),
prints the report as JSON. It runs the same `reportK` the theorems are about.

    K  name  value          a design-package knob (see `Report.Knobs`)
    D  ref                  a part left unpopulated
    B  thickness  nm        board thickness
    O  x  y                 an outline vertex, in order
    F  ref  lib  rot        a footprint, followed by its pads:
    P  number  net  x  y  w  h
    T  ref px py rot  cx0 cy0 cx1 cy1  qx0 qy0 qx1 qy1  hasModel mx0 my0 mx1 my1  height minDrill
-/
open LeanVsDFM LeanVsDFM.Pcb LeanVsDFM.Report

structure St where
  knobs : Knobs := {}
  thickness : Int := 0
  outline : Array (Int × Int) := #[]
  fps : Array Footprint := #[]
  cur : Option (String × String × Int × Array Pad) := none
  parts : Array Fit3D.Part := #[]
  errors : Array String := #[]

def St.flush (s : St) : St :=
  match s.cur with
  | some (r, l, rot, pads) => { s with fps := s.fps.push ⟨r, l, rot, pads.toList⟩, cur := none }
  | none => s

def setKnob (k : Knobs) (name : String) (v : Nat) : Option Knobs :=
  match name with
  | "ledQty" => some { k with ledQty := v }
  | "cuStackup" => some { k with cuStackup := v }
  | "cuInstructions" => some { k with cuInstructions := v }
  | "pairW" => some { k with pairW := v }
  | "pairGap" => some { k with pairGap := v }
  | "ledOhm" => some { k with ledOhm := v }
  | "driveUA" => some { k with driveUA := v }
  | "loadmA" => some { k with loadmA := v }
  | "crystalC" => some { k with crystalC := v }
  | "rdOhm" => some { k with rdOhm := v }
  | _ => none

def ints (xs : List String) : Option (List Int) := xs.mapM String.toInt?

def step (s : St) (lineNo : Nat) (line : String) : St :=
  let bad (why : String) : St := { s with errors := s.errors.push s!"line {lineNo}: {why}" }
  match line.splitOn "\t" with
  | [""] => s
  | ["K", name, v] =>
    match v.toNat? >>= setKnob s.knobs name with
    | some k => { s with knobs := k }
    | none => bad s!"unknown knob or value: {name}"
  | ["D", ref] => { s with knobs := { s.knobs with dni := s.knobs.dni ++ [ref] } }
  | ["B", "thickness", v] => match v.toInt? with | some t => { s with thickness := t } | none => bad "thickness"
  | ["O", x, y] => match x.toInt?, y.toInt? with
    | some x, some y => { s with outline := s.outline.push (x, y) }
    | _, _ => bad "outline vertex"
  | ["F", ref, lib, rot] => match rot.toInt? with
    | some r => { s.flush with cur := some (ref, lib, r, #[]) }
    | none => bad "footprint rotation"
  | ["P", num, net, x, y, w, h] => match s.cur, ints [x, y, w, h] with
    | some (r, l, rot, pads), some [x, y, w, h] => { s with cur := some (r, l, rot, pads.push ⟨num, net, x, y, w, h⟩) }
    | _, _ => bad "pad"
  | "T" :: ref :: rest => match ints rest with
    | some [px, py, rot, c0, c1, c2, c3, q0, q1, q2, q3, m, m0, m1, m2, m3, h, d] =>
      { s with parts := s.parts.push ⟨ref, px, py, rot, ⟨c0, c1, c2, c3⟩, ⟨q0, q1, q2, q3⟩,
          (if m == 1 then some ⟨m0, m1, m2, m3⟩ else none), h, d⟩ }
    | _ => bad "part"
  | _ => bad "unknown line"

partial def readAll (h : IO.FS.Stream) (acc : Array String) : IO (Array String) := do
  let l ← h.getLine
  if l.isEmpty then pure acc
  else readAll h (acc.push ((((l.splitOn "\n").headD "").splitOn "\r").headD ""))

def main : IO UInt32 := do
  let lines ← readAll (← IO.getStdin) #[]
  let mut s : St := {}
  let mut i := 0
  for l in lines do
    i := i + 1
    s := step s i l
  s := s.flush
  if s.errors.size > 0 then
    IO.println ("{\"error\":" ++ Check.jstr (", ".intercalate (s.errors.toList.take 5)) ++ "}")
    return 2
  IO.println (Check.check s.knobs s.fps.toList s.outline.toList s.parts.toList s.thickness)
  return 0
