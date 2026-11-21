/-!
# 2D → 3D: does the flat design fit together as a physical board?

The 2D design gives every part a **courtyard** (its reserved rectangle on the board) and a
placement. The 3D world gives every part a **body** (measured from its STEP model with
OpenCascade). This file checks that the two agree, with exact integer arithmetic in
nanometres (KiCad's own unit):

1. every 3D body lies inside its own courtyard;
2. no two courtyards overlap;
3. every pad and every body is inside the board outline;
4. every drilled hole is at least the minimum drill size.

and proves the consequence that matters, for *any* board:

  `bodies_never_collide : fitOk ps = true → ps.Pairwise bodySep`

If the checker says yes, then no two part bodies overlap. That is a theorem about the
checker, proved once; each board is then decided by the kernel.
-/
namespace LeanVsDFM.Fit3D

/-- Axis-aligned rectangle, board coordinates, nm (x right, y down as in KiCad). -/
structure Box where
  x0 : Int
  y0 : Int
  x1 : Int
  y1 : Int
  deriving Repr, DecidableEq

/-- A placed part, as read from the KiCad board and the 3D model library. -/
structure Part where
  ref : String
  px : Int                -- placement of the footprint origin, nm
  py : Int
  rot : Int               -- rotation in degrees (KiCad: counter-clockwise on screen)
  court : Box             -- courtyard, board coordinates (from KiCad)
  pads : Box              -- bounding box of all pads/holes, board coordinates (from KiCad)
  model : Option Box      -- 3D body outline in MODEL coordinates (x right, y up); none = no model
  height : Int            -- body height above the board, nm
  minDrill : Int          -- smallest drill in this footprint, nm (0 = no holes)
  deriving Repr

/-- Where the 3D body lands on the board. Model (x, y↑) ↦ footprint (x, −y) ↦ rotate ↦ translate.
Only right-angle rotations are supported; anything else gives `none` and is reported. -/
def bodyBox (p : Part) : Option Box :=
  match p.model with
  | none => none
  | some m =>
    if p.rot == 0 then some ⟨p.px + m.x0, p.py - m.y1, p.px + m.x1, p.py - m.y0⟩
    else if p.rot == 90 then some ⟨p.px - m.y1, p.py - m.x1, p.px - m.y0, p.py - m.x0⟩
    else if p.rot == 180 || p.rot == -180 then some ⟨p.px - m.x1, p.py + m.y0, p.px - m.x0, p.py + m.y1⟩
    else if p.rot == 270 || p.rot == -90 then some ⟨p.px + m.y0, p.py + m.x0, p.px + m.y1, p.py + m.x1⟩
    else none

/-- `a` lies inside `b` (edges may touch). -/
def inside (a b : Box) : Bool := b.x0 ≤ a.x0 && a.x1 ≤ b.x1 && b.y0 ≤ a.y0 && a.y1 ≤ b.y1

/-- Separating-axis test for rectangles: they do not overlap (edges may touch). -/
def sepB (a b : Box) : Bool := a.x1 ≤ b.x0 || b.x1 ≤ a.x0 || a.y1 ≤ b.y0 || b.y1 ≤ a.y0

/-! ## The geometry lemmas -/

/-- Shrinking two separated rectangles keeps them separated. -/
theorem sep_of_inside {a b A B : Box} (ha : inside a A = true) (hb : inside b B = true)
    (h : sepB A B = true) : sepB a b = true := by
  simp only [inside, sepB, Bool.and_eq_true, Bool.or_eq_true, decide_eq_true_eq] at *
  omega

/-- Separated rectangles share no interior point. -/
theorem sep_no_common_point {a b : Box} (h : sepB a b = true) (x y : Int) :
    ¬ ((a.x0 < x ∧ x < a.x1 ∧ a.y0 < y ∧ y < a.y1) ∧ (b.x0 < x ∧ x < b.x1 ∧ b.y0 < y ∧ y < b.y1)) := by
  simp only [sepB, Bool.or_eq_true, decide_eq_true_eq] at h
  omega

/-! ## The checker -/

/-- All courtyards pairwise separated. -/
def courtSep : List Part → Bool
  | [] => true
  | p :: ps => ps.all (fun q => sepB p.court q.court) && courtSep ps

/-- Every body that exists is inside its own courtyard. -/
def bodiesInside (ps : List Part) : Bool :=
  ps.all fun p => match bodyBox p with
    | some b => inside b p.court
    | none => true

def fitOk (ps : List Part) : Bool := bodiesInside ps && courtSep ps

/-- Two parts' bodies do not overlap (when both have one). -/
def bodySep (p q : Part) : Prop := ∀ a b, bodyBox p = some a → bodyBox q = some b → sepB a b = true

theorem courtSep_pairwise : ∀ ps : List Part, courtSep ps = true →
    ps.Pairwise (fun p q => sepB p.court q.court = true)
  | [], _ => List.Pairwise.nil
  | p :: ps, h => by
    simp only [courtSep, Bool.and_eq_true, List.all_eq_true] at h
    exact List.Pairwise.cons (fun q hq => h.1 q hq) (courtSep_pairwise ps h.2)

/-- **Main theorem.** If the checker accepts a board, no two part bodies overlap. -/
theorem bodies_never_collide (ps : List Part) (h : fitOk ps = true) : ps.Pairwise bodySep := by
  simp only [fitOk, Bool.and_eq_true] at h
  have hin : ∀ p ∈ ps, ∀ a, bodyBox p = some a → inside a p.court = true := by
    intro p hp a ha
    have := (List.all_eq_true.mp h.1) p hp
    simp only [ha] at this
    exact this
  exact (courtSep_pairwise ps h.2).imp_of_mem
    (fun {p q} hp hq hpq a b ha hb => sep_of_inside (hin p hp a ha) (hin q hq b hb) hpq)

/-! ## Board outline (a convex polygon, vertices in order, nm) -/

def cross (ax ay bx bY cx cy : Int) : Int := (bx - ax) * (cy - ay) - (bY - ay) * (cx - ax)

def edges (poly : List (Int × Int)) : List ((Int × Int) × (Int × Int)) :=
  match poly with
  | [] => []
  | v :: vs => poly.zip (vs ++ [v])

/-- All turns have the same sign: the polygon is convex. -/
def isConvex (poly : List (Int × Int)) : Bool :=
  let es := edges poly
  let turns := (es.zip (es.drop 1 ++ es.take 1)).map fun ((a, b), (_, c)) => cross a.1 a.2 b.1 b.2 c.1 c.2
  3 ≤ poly.length && (turns.all (· ≥ 0) || turns.all (· ≤ 0))

/-- The point is on the inner side of every edge. -/
def pointIn (poly : List (Int × Int)) (x y : Int) : Bool :=
  let cs := (edges poly).map fun (a, b) => cross a.1 a.2 b.1 b.2 x y
  cs.all (· ≥ 0) || cs.all (· ≤ 0)

/-- A rectangle is inside a convex polygon exactly when its four corners are. -/
def boxIn (poly : List (Int × Int)) (b : Box) : Bool :=
  pointIn poly b.x0 b.y0 && pointIn poly b.x1 b.y0 && pointIn poly b.x0 b.y1 && pointIn poly b.x1 b.y1

/-! ## Findings -/

inductive Issue where
  | bodyOutsideCourtyard (ref : String)
  | courtyardsOverlap (a b : String)
  | padsOffBoard (ref : String)
  | bodyOffBoard (ref : String)
  | unsupportedRotation (ref : String)
  | drillTooSmall (ref : String)
  | outlineNotConvex
  deriving Repr, DecidableEq

def overlapPairs : List Part → List Issue
  | [] => []
  | p :: ps => (ps.filter (fun q => !sepB p.court q.court)).map (fun q => .courtyardsOverlap p.ref q.ref)
                 ++ overlapPairs ps

/-- Minimum drill from the Sierrathon instructions: 8 mil = 203 200 nm. -/
def minDrillNm : Int := 203200

/-- Everything wrong with the 3D fit of a board. `[]` means it fits. -/
def fit3d (outline : List (Int × Int)) (ps : List Part) : List Issue :=
  (if isConvex outline then [] else [.outlineNotConvex]) ++
  (ps.filter (fun p => p.model.isSome && (bodyBox p).isNone)).map (fun p => .unsupportedRotation p.ref) ++
  (ps.filter (fun p => match bodyBox p with | some b => !inside b p.court | none => false)).map
    (fun p => .bodyOutsideCourtyard p.ref) ++
  overlapPairs ps ++
  (ps.filter (fun p => !boxIn outline p.pads)).map (fun p => .padsOffBoard p.ref) ++
  (ps.filter (fun p => match bodyBox p with | some b => !boxIn outline b | none => false)).map
    (fun p => .bodyOffBoard p.ref) ++
  (ps.filter (fun p => p.minDrill != 0 && p.minDrill < minDrillNm)).map (fun p => .drillTooSmall p.ref)

/-- Parts with no 3D body model (mounting holes are holes, not parts). -/
def noBody (ps : List Part) : List String :=
  (ps.filter (fun p => p.model.isNone && !p.ref.startsWith "MH")).map (·.ref)

/-- Tallest body on the board, nm. -/
def maxHeight (ps : List Part) : Int := ps.foldl (fun m p => if p.height > m then p.height else m) 0

end LeanVsDFM.Fit3D
