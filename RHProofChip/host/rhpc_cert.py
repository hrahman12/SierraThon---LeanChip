#!/usr/bin/env python3
"""RHP1 certificate encoder (mirror of lean/RHProofChip/Codec.lean) and test-corpus generator.

    python3 -I host/rhpc_cert.py corpus certificates/
writes certificates/invalid/*.rhpc and certificates/malformed/*.rhpc and
certificates/resource/*.rhpc. The valid ones are emitted by Lean itself
(`lake exe rhpc-lean emit certificates/valid`).
"""
import os
import struct
import sys

# ---- terms / formulas as nested tuples ----
Z = ("zero",)
def S(t): return ("succ", t)
def ADD(a, b): return ("add", a, b)
def MUL(a, b): return ("mul", a, b)
def num(n):
    t = Z
    for _ in range(n):
        t = S(t)
    return t
def VAR(n): return ("var", n)
BOT = ("bot",)
def IMP(a, b): return ("imp", a, b)
def EQ(a, b): return ("eq", a, b)


def enc_term(t):
    k = t[0]
    if k == "zero": return b"\x10"
    if k == "succ": return b"\x11" + enc_term(t[1])
    if k == "add": return b"\x12" + enc_term(t[1]) + enc_term(t[2])
    if k == "mul": return b"\x13" + enc_term(t[1]) + enc_term(t[2])
    raise ValueError(t)


def enc_formula(f):
    k = f[0]
    if k == "var": return bytes([0x01, f[1]])
    if k == "bot": return b"\x02"
    if k == "imp": return b"\x03" + enc_formula(f[1]) + enc_formula(f[2])
    if k == "eq": return b"\x04" + enc_term(f[1]) + enc_term(f[2])
    raise ValueError(f)


def u16(n): return struct.pack("<H", n)

OPS = {"K": 0x20, "S": 0x21, "DNE": 0x22, "MP": 0x23, "REFL": 0x24, "ADDZ": 0x25, "ADDS": 0x26,
       "MULZ": 0x27, "MULS": 0x28, "SYMM": 0x29, "TRANS": 0x2A, "CONGS": 0x2B, "CONGADD": 0x2C,
       "CONGMUL": 0x2D}


def enc_step(s):
    op, *args = s
    out = bytes([OPS[op]])
    if op in ("K", "S", "DNE"):
        return out + b"".join(enc_formula(a) for a in args)
    if op in ("REFL", "ADDZ", "ADDS", "MULZ", "MULS"):
        return out + b"".join(enc_term(a) for a in args)
    return out + b"".join(u16(a) for a in args)


def cert(goal, steps):
    return b"RHP1" + enc_formula(goal) + u16(len(steps)) + b"".join(enc_step(s) for s in steps)


P = VAR(0)
IDENTITY = (IMP(P, P), [("S", P, IMP(P, P), P), ("K", P, IMP(P, P)), ("MP", 0, 1), ("K", P, P), ("MP", 2, 3)])
TWO, FOUR = num(2), num(4)
TWO_PLUS_TWO = (EQ(ADD(TWO, TWO), FOUR), [
    ("ADDS", TWO, num(1)), ("ADDS", TWO, Z), ("ADDZ", TWO), ("CONGS", 2), ("TRANS", 1, 3),
    ("CONGS", 4), ("TRANS", 0, 5)])


def _nodes_of_step(step, pool):
    """Add the nodes the device would intern for a step's result to `pool` (a set)."""
    def term(t):
        pool.add(t)
        for x in t[1:]:
            if isinstance(x, tuple):
                term(x)
    op, a, b = step
    if op == "ADDS":
        lhs, rhs = ADD(a, S(b)), S(ADD(a, b))
    else:
        lhs, rhs = MUL(a, S(b)), ADD(MUL(a, b), a)
    term(lhs); term(rhs); pool.add(("eq", lhs, rhs))


def node_exhaustion_steps():
    pool, steps, size = {Z}, [], 0
    k = 0
    while len(pool) <= 1040:
        a, b, c = k % 7, (k // 7) % 7, (k // 49) % 5
        t = MUL(num(a), num(b)) if (k // 245) % 2 == 0 else ADD(num(b), MUL(num(a), num(c)))
        step = ("ADDS" if k % 2 == 0 else "MULS", t, num(c))
        trial = set(pool)
        _nodes_of_step(step, trial)
        if len(trial) > len(pool):
            pool = trial
            steps.append(step)
            size += len(enc_step(step))
        k += 1
        assert len(steps) < 255 and size < 4000, (len(steps), size, len(pool))
    return steps


def corpus():
    """name -> (bytes, expected Lean verdict class)."""
    g, st = TWO_PLUS_TWO
    ok = cert(g, st)
    c = {}
    # ---- valid (also built by Lean; duplicated here so the encoders are cross-checked) ----
    c["valid/py_identity"] = (cert(*IDENTITY), "ACCEPT")
    c["valid/py_two_plus_two"] = (ok, "ACCEPT")
    c["valid/dne_axiom"] = (cert(IMP(IMP(IMP(P, BOT), BOT), P), [("DNE", P)]), "ACCEPT")
    c["valid/refl_big"] = (cert(EQ(num(40), num(40)), [("REFL", num(40))]), "ACCEPT")
    # ---- invalid inference / statement mismatch ----
    c["invalid/two_plus_two_eq_five"] = (cert(EQ(ADD(TWO, TWO), num(5)), st), "REJECT_INVALID")
    c["invalid/wrong_goal_shape"] = (cert(IMP(P, P), st), "REJECT_INVALID")
    c["invalid/mp_wrong_premise"] = (cert(IMP(P, P), [("K", P, P), ("K", P, IMP(P, P)), ("MP", 0, 1)]), "REJECT_INVALID")
    c["invalid/mp_on_equation"] = (cert(EQ(Z, Z), [("REFL", Z), ("REFL", Z), ("MP", 0, 1)]), "REJECT_INVALID")
    c["invalid/forward_reference"] = (cert(EQ(TWO, TWO), [("SYMM", 1), ("REFL", TWO)]), "REJECT_INVALID")
    c["invalid/self_reference"] = (cert(EQ(TWO, TWO), [("SYMM", 0)]), "REJECT_INVALID")
    c["invalid/index_out_of_range"] = (cert(EQ(TWO, TWO), [("REFL", TWO), ("TRANS", 0, 9)]), "REJECT_INVALID")
    c["invalid/trans_mismatch"] = (cert(EQ(Z, num(1)), [("REFL", Z), ("REFL", num(1)), ("TRANS", 0, 1)]), "REJECT_INVALID")
    c["invalid/symm_on_implication"] = (cert(IMP(P, P), [("K", P, P), ("SYMM", 0)]), "REJECT_INVALID")
    c["invalid/no_steps"] = (cert(EQ(Z, Z), []), "REJECT_INVALID")
    c["invalid/bottom_goal"] = (cert(BOT, [("K", P, P)]), "REJECT_INVALID")
    c["invalid/goal_not_last"] = (cert(EQ(Z, Z), [("REFL", Z), ("REFL", num(1))]), "REJECT_INVALID")
    c["invalid/one_eq_zero"] = (cert(EQ(num(1), Z), [("ADDZ", num(1)), ("SYMM", 0)]), "REJECT_INVALID")
    # ---- malformed ----
    c["malformed/empty_file"] = (b"", "REJECT_MALFORMED")
    c["malformed/bad_magic"] = (b"RHP2" + ok[4:], "REJECT_MALFORMED")
    c["malformed/truncated_mid_step"] = (ok[:-3], "REJECT_MALFORMED")
    c["malformed/truncated_header"] = (ok[:5], "REJECT_MALFORMED")
    c["malformed/trailing_garbage"] = (ok + b"\x00", "REJECT_MALFORMED")
    c["malformed/unknown_formula_tag"] = (b"RHP1\x07" + ok[5:], "REJECT_MALFORMED")
    c["malformed/unknown_step_opcode"] = (cert(EQ(Z, Z), []).replace(b"\x00\x00", b"\x01\x00") + b"\x7f", "REJECT_MALFORMED")
    c["malformed/term_tag_in_formula"] = (b"RHP1\x10" + ok[5:], "REJECT_MALFORMED")
    c["malformed/step_count_too_large"] = (ok[:ok.index(b"\x07\x00", 4)] + b"\x08\x00" + ok[ok.index(b"\x07\x00", 4) + 2:], "REJECT_MALFORMED")
    # invalid step followed later by a malformed byte: malformed wins (Lean decodes first)
    bad_then_trunc = cert(EQ(TWO, TWO), [("SYMM", 5), ("REFL", TWO)])[:-1]
    c["malformed/invalid_step_then_truncated"] = (bad_then_trunc, "REJECT_MALFORMED")
    # ---- resource limits (Lean reference accepts or rejects; device must reject) ----
    deep = num(60)
    c["resource/term_too_deep"] = (cert(EQ(deep, deep), [("REFL", deep)]), "ACCEPT")
    c["resource/too_many_lines"] = (cert(EQ(Z, Z), [("REFL", Z)] * 300), "ACCEPT")
    c["resource/oversized_file"] = (ok + b"\x00" * 5000, "REJECT_MALFORMED")
    # Pick steps greedily by simulating the device's hash-consed pool until it would exceed
    # 1024 distinct nodes, while staying under 256 lines and 4096 bytes.
    many = node_exhaustion_steps()
    c["resource/node_exhaustion"] = (cert(EQ(Z, Z), many + [("REFL", Z)]), "ACCEPT")
    return c


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "corpus":
        root = sys.argv[2]
        exp = []
        for name, (data, expected) in sorted(corpus().items()):
            path = os.path.join(root, name + ".rhpc")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
            exp.append(f"{name}.rhpc\t{expected}")
        with open(os.path.join(root, "EXPECTED_LEAN.tsv"), "w") as f:
            f.write("\n".join(exp) + "\n")
        print(f"wrote {len(exp)} certificates under {root}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
