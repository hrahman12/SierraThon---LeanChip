#!/usr/bin/env python3
"""Read a lean4export (format 3.x) NDJSON file and audit theorem statements.

For each requested declaration this tool
  * rebuilds its type (and, for definitions, its value) from the export's expression DAG,
  * pretty-prints it in fully explicit form (every implicit argument shown), and
  * computes a structural fingerprint: a Merkle hash of the expression tree in which
    constants are identified by their full name and universe levels, bound variables by
    de Bruijn index, and binder names are ignored (they do not affect meaning).

The fingerprint pins *what is stated*, given the definitions of the constants it mentions.
Those definitions are in turn pinned by the SHA-256 of the export file itself.

This is an audit of the statement only. It does not check any proof.

    python3 -I host/lean_export.py challenge.ndjson riemannHypothesis RiemannHypothesis ...
"""
import hashlib
import json
import sys


def load(path):
    names, levels, exprs, decls = {0: ""}, {0: ("zero", None)}, {}, {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if "in" in d:
                if "str" in d:
                    pre = names[d["str"]["pre"]]
                    names[d["in"]] = (pre + "." if pre else "") + d["str"]["str"]
                else:
                    pre = names[d["num"]["pre"]]
                    names[d["in"]] = (pre + "." if pre else "") + str(d["num"]["i"])
            elif "il" in d:
                k = next(x for x in d if x != "il")
                levels[d["il"]] = (k, d[k])
            elif "ie" in d:
                k = next(x for x in d if x != "ie")
                exprs[d["ie"]] = (k, d[k])
            else:
                for k in ("def", "thm", "axiom", "opaque"):
                    if k in d and "name" in d[k]:
                        decls[names[d[k]["name"]]] = (k, d[k])
    return names, levels, exprs, decls


class Audit:
    def __init__(self, names, levels, exprs):
        self.n, self.l, self.e = names, levels, exprs
        self._h = {}

    def level(self, i):
        k, v = self.l[i]
        if k == "zero":
            return "0"
        if k == "succ":
            return f"({self.level(v)}+1)"
        if k in ("max", "imax"):
            a, b = v
            return f"{k}({self.level(a)},{self.level(b)})"
        if k == "param":
            return self.n[v]
        return f"?{k}"

    def hash(self, i):
        """Merkle hash of expression i (iterative, memoised)."""
        stack = [i]
        while stack:
            j = stack[-1]
            if j in self._h:
                stack.pop()
                continue
            k, v = self.e[j]
            kids = []
            if k == "app":
                kids = [v["fn"], v["arg"]]
            elif k in ("lam", "forallE"):
                kids = [v["type"], v["body"]]
            elif k == "letE":
                kids = [v["type"], v["value"], v["body"]]
            elif k == "proj":
                kids = [v["struct"]]
            elif k == "mdata":
                kids = [v["expr"]]
            todo = [c for c in kids if c not in self._h]
            if todo:
                stack.extend(todo)
                continue
            stack.pop()
            if k == "bvar":
                payload = f"bvar:{v}"
            elif k == "sort":
                payload = f"sort:{self.level(v)}"
            elif k == "const":
                payload = "const:" + self.n[v["name"]] + ":" + ",".join(self.level(u) for u in v["us"])
            elif k == "natVal":
                payload = f"nat:{v}"
            elif k == "strVal":
                payload = "str:" + json.dumps(v)
            elif k in ("lam", "forallE"):
                payload = f"{k}:{v['binderInfo']}"
            elif k == "proj":
                payload = f"proj:{self.n[v['typeName']]}:{v['idx']}"
            else:
                payload = k
            h = hashlib.sha256(payload.encode())
            for c in kids:
                h.update(self._h[c])
            self._h[j] = h.digest()
        return self._h[i]

    def pp(self, i, ctx=(), depth=0):
        if depth > 200:
            return "…"
        k, v = self.e[i]
        if k == "bvar":
            return ctx[-1 - v] if v < len(ctx) else f"#{v}"
        if k == "sort":
            return f"Sort {self.level(v)}"
        if k == "const":
            us = ".{" + ", ".join(self.level(u) for u in v["us"]) + "}" if v["us"] else ""
            return "@" + self.n[v["name"]] + us
        if k == "natVal":
            return str(v)
        if k == "strVal":
            return json.dumps(v)
        if k == "app":
            fn, args = i, []
            while self.e[fn][0] == "app":
                args.append(self.e[fn][1]["arg"])
                fn = self.e[fn][1]["fn"]
            return "(" + " ".join([self.pp(fn, ctx, depth + 1)] +
                                  [self.pp(a, ctx, depth + 1) for a in reversed(args)]) + ")"
        if k in ("lam", "forallE"):
            nm = self.n[v["name"]] or "_"
            b = {"default": "()", "implicit": "{}", "instImplicit": "[]", "strictImplicit": "⦃⦄"}[v["binderInfo"]]
            sym = "λ" if k == "lam" else "∀"
            return (f"{sym} {b[0]}{nm} : {self.pp(v['type'], ctx, depth + 1)}{b[1]}, "
                    f"{self.pp(v['body'], ctx + (nm,), depth + 1)}")
        if k == "letE":
            nm = self.n[v["name"]]
            return (f"let {nm} : {self.pp(v['type'], ctx, depth + 1)} := {self.pp(v['value'], ctx, depth + 1)}; "
                    f"{self.pp(v['body'], ctx + (nm,), depth + 1)}")
        if k == "proj":
            return f"{self.pp(v['struct'], ctx, depth + 1)}.{v['idx'] + 1}"
        return f"<{k}>"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    path, wanted = sys.argv[1], sys.argv[2:]
    names, levels, exprs, decls = load(path)
    a = Audit(names, levels, exprs)
    out = {}
    for w in wanted:
        if w not in decls:
            out[w] = {"found": False}
            continue
        kind, d = decls[w]
        rec = {"found": True, "kind": kind,
               "type": a.pp(d["type"]), "type_fingerprint": a.hash(d["type"]).hex()}
        if kind == "def":
            rec["value"] = a.pp(d["value"])
            rec["value_fingerprint"] = a.hash(d["value"]).hex()
        if kind == "thm":
            # Is the proof a bare `sorryAx` application? (expected in a challenge file)
            vk, vv = exprs[d["value"]]
            head = d["value"]
            while exprs[head][0] == "app":
                head = exprs[head][1]["fn"]
            hk, hv = exprs[head]
            rec["proof_head"] = names[hv["name"]] if hk == "const" else hk
        out[w] = rec
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
