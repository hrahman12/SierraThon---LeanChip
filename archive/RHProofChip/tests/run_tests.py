#!/usr/bin/env python3
"""RHProofChip automated tests.

Every result is PASS, FAIL or NOT_TESTED, and the script exits non-zero on any FAIL.

  1. lean_build        lake build: soundness proofs + kernel-checked example certificates
  2. lean_axioms       #print axioms on the main theorems: only standard axioms, no sorryAx
  3. c_build           device checker compiled for the host with -Wall -Werror, plus an
                       ASan/UBSan build
  4. corpus_expected   the Lean reference gives the expected verdict on every corpus file
  5. differential      device checker (C) vs Lean reference on the corpus
  6. fuzz              N random mutations of valid certificates through both checkers
  7. records           verification-record authentication (host build of the firmware code)
  8. protocol          USB line protocol (host build of the firmware code)

Agreement rule for 5 and 6. Let C = device verdict and L = Lean verdict.
  * C = ACCEPT must imply L = ACCEPT. This is what carries Lean's soundness theorem to the
    device: anything the device accepts, the proved checker also accepts.
  * If C is not REJECT_RESOURCE, C must equal L.
  * C = REJECT_RESOURCE is always allowed (bounded memory can only add rejections).
"""
import json
import os
import random
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
LEAN = os.path.join(ROOT, "lean")
CERTS = os.path.join(ROOT, "certificates")
results = []


def record(name, status, detail=""):
    results.append((name, status, detail))
    print(f"[{status:10s}] {name}: {detail}", flush=True)


def run(cmd, cwd=ROOT, check=True, **kw):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, **kw)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed ({p.returncode}):\n{p.stdout}\n{p.stderr}")
    return p


def lean_env():
    env = dict(os.environ)
    env["PATH"] = os.path.expanduser("~/.elan/bin") + os.pathsep + env.get("PATH", "")
    return env


CFLAGS = ["-std=c99", "-Wall", "-Wextra", "-Werror", "-pedantic", "-Ifirmware/src"]


def build_c():
    os.makedirs(BUILD, exist_ok=True)
    srcs = ["firmware/src/rhpc_checker.c", "tests/rhpc_host.c"]
    run(["gcc", "-O2", *CFLAGS, *srcs, "-o", "build/rhpc_host"])
    run(["gcc", "-O1", "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=all", *CFLAGS,
         *srcs, "-o", "build/rhpc_host_asan"])


def c_verdicts(files):
    out = {}
    for i in range(0, len(files), 400):
        p = run([os.path.join(BUILD, "rhpc_host_asan"), "check", *files[i:i + 400]])
        for line in p.stdout.splitlines():
            f, cls, err, *_ = line.split("\t")
            out[f] = (cls, err)
    return out


def lean_verdicts(files):
    out = {}
    for i in range(0, len(files), 400):
        p = run(["lake", "exe", "rhpc-lean", "check", *files[i:i + 400]], cwd=LEAN, env=lean_env())
        for line in p.stdout.splitlines():
            f, v = line.split("\t")
            out[f] = v
    return out


def agree(c, l):
    if c == "ACCEPT" and l != "ACCEPT":
        return False
    if c == "REJECT_RESOURCE":
        return True
    return c == l


def main():
    fuzz_n = int(os.environ.get("RHPC_FUZZ", "3000"))

    # 1-2 Lean
    try:
        run(["lake", "build"], cwd=LEAN, env=lean_env())
        run(["lake", "build", "RHProofChip"], cwd=LEAN, env=lean_env())
        record("lean_build", "PASS", "soundness proofs and kernel-checked examples compile")
    except Exception as e:
        record("lean_build", "FAIL", str(e)[:400])
        return finish()
    with tempfile.NamedTemporaryFile("w", suffix=".lean", delete=False) as f:
        f.write("import RHProofChip\nopen RHPC\n" + "".join(
            f"#print axioms {n}\n" for n in ["check_sound", "derivable_sound", "check_sound_sem",
                                             "check_sound_eq", "check_rejects_bot", "Examples.two_plus_two",
                                             "Examples.two_times_two", "Examples.identity_true"]))
        ax = f.name
    p = run(["lake", "env", "lean", ax], cwd=LEAN, env=lean_env(), check=False)
    os.unlink(ax)
    lines = [l for l in p.stdout.splitlines() if "depends on axioms" in l or "does not depend" in l]
    allowed = {"propext", "Quot.sound", "Classical.choice"}
    bad = [l for l in lines if any(a not in allowed for a in
           (l.split("[")[1].rstrip("]").replace(" ", "").split(",") if "[" in l else []))]
    if p.returncode == 0 and len(lines) == 8 and not bad:
        record("lean_axioms", "PASS", "; ".join(l.split("'")[1] + " -> " + (l.split("[")[1].rstrip("]") if "[" in l else "none") for l in lines[:3]) + " …")
    else:
        record("lean_axioms", "FAIL", p.stdout[-400:] + p.stderr[-400:])

    # 3 C build
    try:
        build_c()
        record("c_build", "PASS", "gcc -Wall -Wextra -Werror -pedantic; ASan+UBSan build")
    except Exception as e:
        record("c_build", "FAIL", str(e)[:400])
        return finish()

    # corpus
    run([sys.executable, "-I", "host/rhpc_cert.py", "corpus", CERTS])
    run(["lake", "exe", "rhpc-lean", "emit", os.path.join(CERTS, "valid")], cwd=LEAN, env=lean_env())
    files = sorted(os.path.join(dp, f) for dp, _, fs in os.walk(CERTS) for f in fs if f.endswith(".rhpc"))
    cv, lv = c_verdicts(files), lean_verdicts(files)

    # 4 expected Lean verdicts
    exp = dict(l.split("\t") for l in open(os.path.join(CERTS, "EXPECTED_LEAN.tsv")).read().split("\n") if l)
    wrong = [(k, v, lv[os.path.join(CERTS, k)]) for k, v in exp.items() if lv[os.path.join(CERTS, k)] != v]
    record("corpus_expected", "FAIL" if wrong else "PASS",
           f"{len(exp)} files" + (f"; mismatches {wrong[:5]}" if wrong else ""))

    # 5 differential
    dis = [(os.path.relpath(f, CERTS), cv[f], lv[f]) for f in files if not agree(cv[f][0], lv[f])]
    counts = {}
    for f in files:
        counts[cv[f][0]] = counts.get(cv[f][0], 0) + 1
    record("differential", "FAIL" if dis else "PASS",
           f"{len(files)} certificates, device verdicts {counts}" + (f"; disagreements {dis[:5]}" if dis else ""))
    must = {"resource/term_too_deep.rhpc": "E_RESOURCE_DEPTH", "resource/too_many_lines.rhpc": "E_RESOURCE_LINES",
            "resource/node_exhaustion.rhpc": "E_RESOURCE_NODES", "resource/oversized_file.rhpc": "E_RESOURCE_SIZE"}
    miss = [(k, cv[os.path.join(CERTS, k)][1]) for k, v in must.items() if cv[os.path.join(CERTS, k)][1] != v]
    record("resource_limits", "FAIL" if miss else "PASS",
           "depth, lines, nodes and size limits each trigger" + (f"; wrong: {miss}" if miss else ""))

    # 6 fuzz
    rng = random.Random(0xC0FFEE)
    seeds = [open(f, "rb").read() for f in files if "/valid/" in f]
    with tempfile.TemporaryDirectory() as td:
        fz = []
        for k in range(fuzz_n):
            b = bytearray(rng.choice(seeds))
            for _ in range(rng.randint(1, 4)):
                op = rng.random()
                if op < 0.45 and b:
                    b[rng.randrange(len(b))] = rng.randrange(256)
                elif op < 0.6 and b:
                    del b[rng.randrange(len(b)):]
                elif op < 0.75:
                    b.insert(rng.randrange(len(b) + 1), rng.randrange(256))
                elif op < 0.9 and len(b) > 6:
                    i = rng.randrange(4, len(b))
                    b[i] = rng.choice([0x10, 0x11, 0x12, 0x13, 0x01, 0x02, 0x03, 0x04, 0x23, 0x2A])
                elif b:
                    i = rng.randrange(len(b))
                    b[i] ^= 1 << rng.randrange(8)
            path = os.path.join(td, f"f{k:05d}.rhpc")
            open(path, "wb").write(bytes(b))
            fz.append(path)
        cf, lf = c_verdicts(fz), lean_verdicts(fz)
        dis = [(os.path.basename(f), cf[f], lf[f]) for f in fz if not agree(cf[f][0], lf[f])]
        hist = {}
        for f in fz:
            hist[cf[f][0]] = hist.get(cf[f][0], 0) + 1
        record("fuzz", "FAIL" if dis else "PASS",
               f"{fuzz_n} mutants (seed 0xC0FFEE), device verdicts {hist}, ASan/UBSan clean"
               + (f"; disagreements {dis[:5]}" if dis else ""))

    # 7-8 records and protocol (host builds of firmware modules)
    for name, script in [("records", "tests/test_records.py"), ("protocol", "tests/test_protocol.py")]:
        if not os.path.exists(os.path.join(ROOT, script)):
            record(name, "NOT_TESTED", f"{script} not present")
            continue
        p = run([sys.executable, "-I", script], check=False)
        last = (p.stdout.strip().splitlines() or ["(no output)"])[-1]
        record(name, "PASS" if p.returncode == 0 else "FAIL", last if p.returncode == 0 else (p.stdout + p.stderr)[-600:])

    return finish()


def finish():
    os.makedirs(os.path.join(ROOT, "tests", "out"), exist_ok=True)
    with open(os.path.join(ROOT, "tests", "out", "results.json"), "w") as f:
        json.dump([{"test": n, "status": s, "detail": d} for n, s, d in results], f, indent=2)
    fails = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"\n{len(results)} checks: {sum(1 for _, s, _ in results if s == 'PASS')} PASS, "
          f"{fails} FAIL, {sum(1 for _, s, _ in results if s == 'NOT_TESTED')} NOT_TESTED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
