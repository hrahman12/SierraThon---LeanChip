import RHProofChip.Checker
/-!
# Binary certificate format `RHP1`

The exact byte format the RP2040 receives (see `docs/CERTIFICATE_FORMAT.md`).

```
cert    := "RHP1" formula u16le(nsteps) step*        (no trailing bytes)
formula := 0x01 u8(n)            var n
         | 0x02                  ⊥
         | 0x03 formula formula  a → b
         | 0x04 term term        a = b
term    := 0x10 | 0x11 term | 0x12 term term | 0x13 term term     0, S, +, ×
step    := 0x20 f f | 0x21 f f f | 0x22 f | 0x23 u16 u16
         | 0x24 t | 0x25 t | 0x26 t t | 0x27 t | 0x28 t t
         | 0x29 u16 | 0x2A u16 u16 | 0x2B u16 | 0x2C u16 u16 | 0x2D u16 u16
```

The decoder is **not** part of the proved core: it is a reference used for differential
testing against the C decoder. Soundness is about `check` on the decoded `Cert`.
-/
namespace RHPC

/-! ## Encoder -/

def u16le (n : Nat) : List UInt8 := [(n % 256).toUInt8, ((n / 256) % 256).toUInt8]

def Term.encode : Term → List UInt8
  | .zero => [0x10]
  | .succ t => 0x11 :: t.encode
  | .add a b => 0x12 :: (a.encode ++ b.encode)
  | .mul a b => 0x13 :: (a.encode ++ b.encode)

def Formula.encode : Formula → List UInt8
  | .var n => [0x01, n.toUInt8]
  | .bot => [0x02]
  | .imp a b => 0x03 :: (a.encode ++ b.encode)
  | .eq a b => 0x04 :: (a.encode ++ b.encode)

def Step.encode : Step → List UInt8
  | .axK a b => 0x20 :: (a.encode ++ b.encode)
  | .axS a b c => 0x21 :: (a.encode ++ b.encode ++ c.encode)
  | .axDNE a => 0x22 :: a.encode
  | .mp i j => 0x23 :: (u16le i ++ u16le j)
  | .refl t => 0x24 :: t.encode
  | .addZero t => 0x25 :: t.encode
  | .addSucc t u => 0x26 :: (t.encode ++ u.encode)
  | .mulZero t => 0x27 :: t.encode
  | .mulSucc t u => 0x28 :: (t.encode ++ u.encode)
  | .symm i => 0x29 :: u16le i
  | .trans i j => 0x2A :: (u16le i ++ u16le j)
  | .congSucc i => 0x2B :: u16le i
  | .congAdd i j => 0x2C :: (u16le i ++ u16le j)
  | .congMul i j => 0x2D :: (u16le i ++ u16le j)

def Cert.encode (c : Cert) : List UInt8 :=
  [0x52, 0x48, 0x50, 0x31] ++ c.goal.encode ++ u16le c.steps.length ++
    (c.steps.map Step.encode).flatten

/-! ## Decoder (fuel = remaining bytes, every call consumes at least one byte) -/

abbrev Bytes := List UInt8

def pU16 : Bytes → Option (Nat × Bytes)
  | lo :: hi :: r => some (lo.toNat + 256 * hi.toNat, r)
  | _ => none

def pTerm : Nat → Bytes → Option (Term × Bytes)
  | 0, _ => none
  | _, [] => none
  | fuel + 1, b :: r =>
    if b == 0x10 then some (.zero, r)
    else if b == 0x11 then do let (t, r) ← pTerm fuel r; pure (.succ t, r)
    else if b == 0x12 then do let (a, r) ← pTerm fuel r; let (c, r) ← pTerm fuel r; pure (.add a c, r)
    else if b == 0x13 then do let (a, r) ← pTerm fuel r; let (c, r) ← pTerm fuel r; pure (.mul a c, r)
    else none

def pFormula : Nat → Bytes → Option (Formula × Bytes)
  | 0, _ => none
  | _, [] => none
  | fuel + 1, b :: r =>
    if b == 0x01 then match r with
      | n :: r => some (.var n.toNat, r)
      | [] => none
    else if b == 0x02 then some (.bot, r)
    else if b == 0x03 then do let (a, r) ← pFormula fuel r; let (c, r) ← pFormula fuel r; pure (.imp a c, r)
    else if b == 0x04 then do let (a, r) ← pTerm fuel r; let (c, r) ← pTerm fuel r; pure (.eq a c, r)
    else none

def pStep (fuel : Nat) : Bytes → Option (Step × Bytes)
  | [] => none
  | b :: r =>
    if b == 0x20 then do let (x, r) ← pFormula fuel r; let (y, r) ← pFormula fuel r; pure (.axK x y, r)
    else if b == 0x21 then do
      let (x, r) ← pFormula fuel r; let (y, r) ← pFormula fuel r; let (z, r) ← pFormula fuel r
      pure (.axS x y z, r)
    else if b == 0x22 then do let (x, r) ← pFormula fuel r; pure (.axDNE x, r)
    else if b == 0x23 then do let (i, r) ← pU16 r; let (j, r) ← pU16 r; pure (.mp i j, r)
    else if b == 0x24 then do let (t, r) ← pTerm fuel r; pure (.refl t, r)
    else if b == 0x25 then do let (t, r) ← pTerm fuel r; pure (.addZero t, r)
    else if b == 0x26 then do let (t, r) ← pTerm fuel r; let (u, r) ← pTerm fuel r; pure (.addSucc t u, r)
    else if b == 0x27 then do let (t, r) ← pTerm fuel r; pure (.mulZero t, r)
    else if b == 0x28 then do let (t, r) ← pTerm fuel r; let (u, r) ← pTerm fuel r; pure (.mulSucc t u, r)
    else if b == 0x29 then do let (i, r) ← pU16 r; pure (.symm i, r)
    else if b == 0x2A then do let (i, r) ← pU16 r; let (j, r) ← pU16 r; pure (.trans i j, r)
    else if b == 0x2B then do let (i, r) ← pU16 r; pure (.congSucc i, r)
    else if b == 0x2C then do let (i, r) ← pU16 r; let (j, r) ← pU16 r; pure (.congAdd i j, r)
    else if b == 0x2D then do let (i, r) ← pU16 r; let (j, r) ← pU16 r; pure (.congMul i j, r)
    else none

def pSteps (fuel : Nat) : Nat → Bytes → Option (List Step × Bytes)
  | 0, r => some ([], r)
  | n + 1, r => do
    let (s, r) ← pStep fuel r
    let (ss, r) ← pSteps fuel n r
    pure (s :: ss, r)

/-- Decode a whole certificate; `none` = malformed (bad magic, bad tag, truncated, trailing bytes). -/
def decode (bs : Bytes) : Option Cert :=
  match bs with
  | 0x52 :: 0x48 :: 0x50 :: 0x31 :: r => do
    let fuel := bs.length + 1
    let (g, r) ← pFormula fuel r
    let (n, r) ← pU16 r
    let (ss, r) ← pSteps fuel n r
    if r.isEmpty then pure ⟨g, ss⟩ else none
  | _ => none

/-- Verdict of the reference pipeline on raw bytes. -/
inductive Verdict where
  | accept | rejectMalformed | rejectInvalid
  deriving Repr, DecidableEq

def verdict (bs : Bytes) : Verdict :=
  match decode bs with
  | none => .rejectMalformed
  | some c => if check c then .accept else .rejectInvalid

end RHPC
