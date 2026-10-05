"""A/B: simvec.run_scalar (OLD) vs simvec_numba.run_scalar (NEW), all six fields.

NEVER HANGS: fixed vector count (default 4), engine caps forced, no pool, no
compose. First call warms the njit compiler outside the timed region so the
ratio measures steady state, not compilation.

Usage: python scratch/nb_diff.py [nvec]
"""
import os
import sys
import time
import pickle

sys.path.insert(0, r"D:\redstone-mini")
sys.path.insert(0, r"D:\redstone-mini\scratch")
os.environ.pop("REDSTONE_SIM_GATE", None)
os.environ["REDSTONE_SIM_TICKS"] = "20000"
os.environ["REDSTONE_SIM_STEPS"] = "2000000"
import sim  # noqa: E402
import simvec  # noqa: E402
import simvec_numba as nb  # noqa: E402
from recipe import parse_recipe  # noqa: E402

FIELDS = ("lamps", "live", "torch", "ticks", "rep", "comp")


def cmp_field(name, i, a, b):
    if a == b:
        return None
    if isinstance(a, dict) and isinstance(b, dict):
        ka, kb = set(a), set(b)
        if ka != kb:
            return (f"vec{i} {name}: key sets differ "
                    f"(only-old={sorted(ka - kb)[:4]} "
                    f"only-new={sorted(kb - ka)[:4]})")
        diff = [(k, a[k], b[k]) for k in sorted(ka) if a[k] != b[k]]
        return f"vec{i} {name}: {len(diff)} differ, first {diff[:4]}"
    return f"vec{i} {name}: {a!r} != {b!r}"


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    dp = sys.argv[2] if len(sys.argv) > 2 else \
        r"D:\redstone-mini\scratch\alu4merge_g.pkl"
    rp = sys.argv[3] if len(sys.argv) > 3 else \
        r"D:\redstone-mini\recipes\alu4.txt"
    r = parse_recipe(open(rp).read())
    ins = r["inputs"]
    d = pickle.load(open(dp, "rb"))
    P = sim._parse_build(d["blocks"], d["io"])
    span = 2 ** len(ins)
    idxs = [round(k * (span - 1) / max(1, n - 1)) for k in range(n)] if n > 1 else [0]
    # warmup: compile njit outside the timed region
    vec0 = {ins[j]: (idxs[0] >> j) & 1 for j in range(len(ins))}
    nb.run_scalar(vec0, P)
    told = tnew = 0.0
    bad = 0
    for i in idxs:
        vec = {ins[j]: (i >> j) & 1 for j in range(len(ins))}
        if hasattr(sim, "_BOUT"):
            sim._BOUT.clear()
        t = time.monotonic()
        a = simvec.run_scalar(vec, P)
        told += time.monotonic() - t
        if hasattr(sim, "_BOUT"):
            sim._BOUT.clear()
        t = time.monotonic()
        b = nb.run_scalar(vec, P)
        tnew += time.monotonic() - t
        for f, x, y in zip(FIELDS, a, b):
            msg = cmp_field(f, i, x, y)
            if msg:
                print("DIVERGED  " + msg, flush=True)
                bad += 1
                break
        else:
            print(f"vec{i:5d} ok ticks={a[3]:5d}/{b[3]:5d} "
                  f"live={len(a[1]):6d}/{len(b[1]):6d}", flush=True)
    print(f"\n{n} vectors: old {told:.2f}s new {tnew:.2f}s "
          f"speedup {told/max(1e-9, tnew):.2f}x divergences={bad}")
    if bad:
        print("NB DIFF: DIVERGED")
        sys.exit(1)
    print("NB DIFF: IDENTICAL")


if __name__ == "__main__":
    main()
