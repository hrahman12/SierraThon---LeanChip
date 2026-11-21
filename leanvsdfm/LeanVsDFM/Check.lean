import LeanVsDFM.Report
/-!
# The checker the website and the command line both run

`check` takes a board (footprints, placed parts, outline) and a setting of the design-package
knobs, and returns the report rows, the verdict for **every component**, and the geometry Lean
used. `Main.lean` compiles it into the `leanchip` binary: the page sends a board, this code
answers. There is one checker, so the page and `leancheck` cannot disagree.

A component's colour is the worst colour among the findings that name it; the bare board takes
the findings that name no component. `comp_le_overall` proves no component is ever worse than the
overall verdict.
-/
namespace LeanVsDFM.Check
open LeanVsDFM.Pcb LeanVsDFM.Parts LeanVsDFM.Report

/-- Findings that name this component, each with the colour of its row. -/
def hits (rows : List Row) (ref : String) : List (Color × String) :=
  rows.flatMap fun r => (r.items.filter (·.1.contains ref)).map fun it => (r.color, it.2)

/-- Findings about the bare board (they name no component). -/
def boardHits (rows : List Row) : List (Color × String) :=
  rows.flatMap fun r => (r.items.filter (·.1.isEmpty)).map fun it => (r.color, it.2)

def worstOf (cs : List Color) : Color := cs.foldl Color.worst .green

/-- **The verdict for one component.** -/
def compColor (rows : List Row) (ref : String) : Color := worstOf ((hits rows ref).map (·.1))

def boardColor (rows : List Row) : Color := worstOf ((boardHits rows).map (·.1))

theorem worst_le {a b : Color} {m : Nat} (ha : a.rank ≤ m) (hb : b.rank ≤ m) : (a.worst b).rank ≤ m := by
  unfold Color.worst; split <;> assumption

theorem foldl_worst_le (cs : List Color) (c : Color) (m : Nat) (hc : c.rank ≤ m)
    (h : ∀ x ∈ cs, x.rank ≤ m) : (cs.foldl Color.worst c).rank ≤ m := by
  induction cs generalizing c with
  | nil => exact hc
  | cons x xs ih =>
    exact ih _ (worst_le hc (h x (List.mem_cons_self ..))) (fun y hy => h y (List.mem_cons_of_mem _ hy))

/-- No component is ever worse than the overall verdict. -/
theorem comp_le_overall (rows : List Row) (ref : String) :
    (compColor rows ref).rank ≤ (overall rows).rank := by
  unfold compColor worstOf
  apply foldl_worst_le
  · exact Nat.zero_le _
  · intro x hx
    simp only [hits, List.mem_map, List.mem_flatMap, List.mem_filter] at hx
    obtain ⟨⟨c, msg⟩, ⟨r, hr, it, _, hit⟩, rfl⟩ := hx
    cases hit
    exact overall_is_worst rows r hr

/-- Nor is the bare board. -/
theorem board_le_overall (rows : List Row) : (boardColor rows).rank ≤ (overall rows).rank := by
  unfold boardColor worstOf
  apply foldl_worst_le
  · exact Nat.zero_le _
  · intro x hx
    simp only [boardHits, List.mem_map, List.mem_flatMap, List.mem_filter] at hx
    obtain ⟨⟨c, msg⟩, ⟨r, hr, it, _, hit⟩, rfl⟩ := hx
    cases hit
    exact overall_is_worst rows r hr

/-! ## JSON out -/

def hex (n : Nat) : Char := if n < 10 then Char.ofNat (48 + n) else Char.ofNat (87 + n)

def escJson (s : String) : String :=
  s.foldl (fun acc c =>
    if c == '"' then acc ++ "\\\"" else if c == '\\' then acc ++ "\\\\"
    else if c.toNat < 32 then acc ++ "\\u00" ++ String.singleton (hex (c.toNat / 16)) ++ String.singleton (hex (c.toNat % 16))
    else acc.push c) ""

def jstr (s : String) : String := "\"" ++ escJson s ++ "\""
def jarr (xs : List String) : String := "[" ++ ",".intercalate xs ++ "]"
def jbox (b : Fit3D.Box) : String := s!"[{b.x0},{b.y0},{b.x1},{b.y1}]"

def rowJson (r : Row) : String :=
  "{\"section\":" ++ jstr r.section_ ++ ",\"check\":" ++ jstr r.check ++ ",\"color\":" ++ jstr r.color.name ++
  ",\"detail\":" ++ jstr r.detail ++ ",\"refs\":" ++ jarr ((r.items.flatMap (·.1)).eraseDups.map jstr) ++ "}"

def compJson (rows : List Row) (b : List Footprint) (ps : List Fit3D.Part) (dni : List String) (ref : String) : String :=
  let lib := ((b.find? (·.ref == ref)).map (·.lib)).getD ""
  let geo := match ps.find? (·.ref == ref) with
    | some p => ",\"court\":" ++ jbox p.court ++ ",\"pads\":" ++ jbox p.pads ++ ",\"body\":" ++
        (match Fit3D.bodyBox p with | some bb => jbox bb | none => "null") ++ s!",\"h\":{p.height},\"x\":{p.px},\"y\":{p.py},\"rot\":{p.rot}"
    | none => ""
  "{\"ref\":" ++ jstr ref ++ ",\"color\":" ++ jstr (compColor rows ref).name ++ ",\"lib\":" ++ jstr lib ++
  ",\"placed\":" ++ (if (b.any (·.ref == ref)) then "true" else "false") ++
  ",\"fitted\":" ++ (if dni.contains ref then "false" else "true") ++
  ",\"notes\":" ++ jarr ((hits rows ref).map fun h => jstr h.2) ++ geo ++ "}"

/-- Everything the page shows for one build. -/
def check (k : Knobs) (b : List Footprint) (outline : List (Int × Int)) (ps : List Fit3D.Part) (thickness : Int) : String :=
  let rows := reportK k b outline ps
  let refs := b.map (·.ref) ++ Package.schematicRefdes.filter (fun r => !(b.any (·.ref == r)))
  let cols := refs.map (compColor rows)
  let n (c : Color) : Nat := (cols.filter (· == c)).length
  "{\"overall\":" ++ jstr (overall rows).name ++
  ",\"rows\":" ++ jarr (rows.map rowJson) ++
  ",\"components\":" ++ jarr (refs.map (compJson rows b ps k.dni)) ++
  ",\"board\":{\"color\":" ++ jstr (boardColor rows).name ++ ",\"notes\":" ++ jarr ((boardHits rows).map fun h => jstr h.2) ++ "}" ++
  ",\"outline\":" ++ jarr (outline.map fun (x, y) => s!"[{x},{y}]") ++
  s!",\"counts\":\{\"green\":{n .green},\"yellow\":{n .yellow},\"red\":{n .red}}" ++
  s!",\"envelope\":\{\"thickness_nm\":{thickness},\"tallest_nm\":{Fit3D.maxHeight ps}}" ++
  ",\"collision_free\":" ++ (if Fit3D.fitOk ps then "true" else "false") ++
  ",\"rails\":" ++ jarr (rails.map fun r => "{\"net\":" ++ jstr r.net ++ s!",\"minTotalNF\":{r.minTotalNF},\"minSmall\":{r.minSmall}" ++
    ",\"why\":" ++ jstr r.why ++ ",\"caps\":" ++ jarr ((railCaps r.net).map fun c => "{\"ref\":" ++ jstr c ++ s!",\"nF\":{capNF c}}") ++ "}") ++
  ",\"checker\":\"Lean 4, compiled from LeanVsDFM/Check.lean\"}"

end LeanVsDFM.Check
