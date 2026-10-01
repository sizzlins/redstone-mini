"""Differential gate for engine optimisations.

Runs the FROZEN reference engine (scratch/ref_sim.py, extracted from git HEAD)
and the LIVE sim._run_vec over the same vectors and demands EXACT equality of
every returned quantity: lamps, live dust levels, torch states, repeater
states, comparator levels and the tick count. An optimisation that changes any
of those is not an optimisation.

NEVER HANGS: fixed vector list, and every engine call runs under the engine's
own tick/step caps. Prints PASS/FAIL per case and exits nonzero on any diff.

Usage:  python scratch/diff_engine.py [nvec]
"""
import os
import sys
import time

sys.path.insert(0, r"D:\redstone-mini")
sys.path.insert(0, r"D:\redstone-mini\scratch")
os.environ.pop("REDSTONE_SIM_GATE", None)

import pickle

import ref_sim
import sim
import simvec
from recipe import parse_recipe


def cmp_run(a, b, tag):
    """Exact comparison of two _run_vec results (or two exceptions)."""
    if isinstance(a, BaseException) or isinstance(b, BaseException):
        ae = type(a).__name__ if isinstance(a, BaseException) else None
        be = type(b).__name__ if isinstance(b, BaseException) else None
        if ae != be:
            print("  %-22s EXC MISMATCH ref=%s live=%s" % (tag, ae, be))
            return False
        return True
    names = ("lamps", "live", "torch", "ticks", "rep", "comp")
    for i, nm in enumerate(names):
        if a[i] != b[i]:
            print("  %-22s %s MISMATCH ref=%s live=%s"
                  % (tag, nm,
                     list(a[i].items())[:4] if isinstance(a[i], dict) else a[i],
                     list(b[i].items())[:4] if isinstance(b[i], dict) else b[i]))
            return False
    return True


def cmp3(r, v, s, tag):
    """Compare reference vs live vs run_scalar, all three exactly."""
    ok = cmp_run(r, v, tag)
    names = ("lamps", "live", "torch", "ticks", "rep", "comp")
    if isinstance(r, BaseException) or isinstance(s, BaseException):
        ae = type(r).__name__ if isinstance(r, BaseException) else None
        se = type(s).__name__ if isinstance(s, BaseException) else None
        if ae != se:
            print("  %-22s scalar EXC ref=%s scalar=%s" % (tag, ae, se))
            return False
        return ok
    for i, nm in enumerate(names):
        if r[i] != s[i]:
            print("  %-22s scalar %s MISMATCH  ref=%s scalar=%s"
                  % (tag, nm,
                     list(r[i].items())[:3] if isinstance(r[i], dict) else r[i],
                     list(s[i].items())[:3] if isinstance(s[i], dict) else s[i]))
            return False
    return ok


def case(blocks, io, vec, tag):
    Pref = ref_sim._parse_build(blocks, io)
    Plive = sim._parse_build(blocks, io)
    t = time.monotonic()
    try:
        r = ref_sim._run_vec(vec, None, Pref)
    except BaseException as e:                      # noqa: BLE001
        r = e
    tr = time.monotonic() - t
    t = time.monotonic()
    try:
        v = sim._run_vec(vec, None, Plive)
    except BaseException as e:                      # noqa: BLE001
        v = e
    tv = time.monotonic() - t
    t = time.monotonic()
    try:
        s = simvec.run_scalar(vec, Plive)
    except BaseException as e:                      # noqa: BLE001
        s = e
    ts = time.monotonic() - t
    ok = cmp3(r, v, s, tag)
    print("  %-22s %s ref=%.3f live=%.3f scalar=%.3f  (%.2fx)"
          % (tag, "ok " if ok else "FAIL", tr, tv, ts,
             tr / max(ts, 1e-9)), flush=True)
    return ok


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    allok = True
    print("== alu4 (34672 blocks, 1024 vectors) ==", flush=True)
    r = parse_recipe(open(r"D:\redstone-mini\scratch\cand_alu4hier.txt").read())
    d = pickle.load(open(r"D:\redstone-mini\scratch\alu4_build.pkl", "rb"))
    ins = r["inputs"]
    combos = [{ins[j]: (k >> j) & 1 for j in range(len(ins))} for k in range(n)]
    for k, vec in enumerate(combos):
        allok &= case(d["blocks"], d["io"], vec, "alu4 vec%03d" % k)

    print("== small routed build (XOR/OR/AND, all 8 vectors) ==", flush=True)
    from compose import compose
    r2 = parse_recipe("IN a, b, c\nOUT y\nt = a AND b\n"
                      "u = t OR c\nv = u XOR a\ny = v OR c\n")
    b2, _s, io2 = compose(r2)
    i2 = r2["inputs"]
    for k in range(8):
        vec = {i2[j]: (k >> j) & 1 for j in range(len(i2))}
        allok &= case(b2, io2, vec, "small vec%d" % k)

    print("\n%s" % ("ALL IDENTICAL" if allok else "DIFFERENCES FOUND"), flush=True)
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())