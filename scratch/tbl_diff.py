"""Old-vs-NEW table-engine differ. The fast gate for the int-index rewrite.

NEVER HANGS: fixed vector count, engine caps forced, no pool, no compose, and
a hard per-vector subprocess timeout is NOT needed because both engines are
in-process with caps on. Usage:

    python scratch/tbl_diff.py [nvec] [build.pkl] [recipe.txt]

Compares ALL SIX returned values (lamps, live dust, torches, ticks, repeaters,
comparators) between scratch/simvec_old.py's run_scalar and the live simvec's,
vector by vector. Any difference prints the first diverging field and exits 1.
This is deliberately stricter than diff_engine (which compares the table engine
to the authority engine): during a rewrite the OLD table engine is the
specification, so this is the oracle that lets the rewrite land in seconds
instead of a full gate cycle.
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
import sim                      # noqa: E402
import simvec                   # noqa: E402
from recipe import parse_recipe  # noqa: E402

# The reference engine is selectable so a MICRO-optimisation can be A/B'd
# against the engine it is replacing, not only against the original tuple
# engine. Point it at a copy of the current simvec.py and the ratio answers
# "did this change help?" instead of "how much did the rewrite help?". Copy the
# file BEFORE editing, run, then interpret. Null check: point it at an identical
# copy and the ratio must read 1.00x.
_ref = os.environ.get("REDSTONE_TBLDIFF_REF", "simvec_old")
if _ref == "simvec":
    REF = simvec
else:
    import importlib
    REF = importlib.import_module(_ref)
simvec_old = REF                  # the rest of this file says simvec_old

FIELDS = ("lamps", "live", "torch", "ticks", "rep", "comp")


def cmp_field(name, i, a, b):
    if a == b:
        return None
    if isinstance(a, dict) and isinstance(b, dict):
        ka, kb = set(a), set(b)
        if ka != kb:
            only_a = sorted(ka - kb)[:4]
            only_b = sorted(kb - ka)[:4]
            return (f"vec{i} {name}: key sets differ "
                    f"(only-old={only_a} only-new={only_b})")
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

    # spread indices: 0..n-1 are the EASY vectors and would hide a divergence
    # that only shows on hard ones (the reason bench_scalar grew a spread mode).
    span = 2 ** len(ins)
    idxs = [round(k * (span - 1) / max(1, n - 1)) for k in range(n)] if n > 1 else [0]

    told = tnew = 0.0
    bad = 0
    # ponytail: the timed loop below measures STEADY-STATE per-vector cost
    # only. Two one-time costs used to swamp it: each engine builds its tables
    # (~1.8s on alu4) inside its first timed call, and the first vectors run
    # cold (page cache, malloc arenas, boost ramp) while later ones run hot.
    # With old-always-first ordering the second engine won every null by up
    # to 1.53x on identical code. So: build both tables up front (timed
    # separately, reported, not ratio'd), run one untimed warmup vector per
    # engine, then alternate run order per vector (old,new / new,old) and
    # accumulate by ENGINE, not position. The null must read ~1.00x.
    t = time.monotonic()
    simvec_old._tables(P)
    t_tables_old = time.monotonic() - t
    t = time.monotonic()
    simvec._tables(P)
    t_tables_new = time.monotonic() - t
    _wvec = {ins[j]: (idxs[0] >> j) & 1 for j in range(len(ins))}
    if hasattr(sim, "_BOUT"):
        sim._BOUT.clear()
    simvec_old.run_scalar(_wvec, P)
    if hasattr(sim, "_BOUT"):
        sim._BOUT.clear()
    simvec.run_scalar(_wvec, P)
    # Negative control: a differ that has never reported a difference is not
    # evidence, it is an untested hypothesis. REDSTONE_TBLDIFF_FAULT=<field>
    # corrupts ONE value in the NEW result so the harness must go red.
    fault = os.environ.get("REDSTONE_TBLDIFF_FAULT", "")
    # REDSTONE_TBLDIFF_ONLY=new|old runs ONE engine in this process. Two
    # engines in one process share sim._BOUT, a persistent torch-burnout
    # counter, so whichever runs second sees a hotter counter -- a way to turn
    # a harness artefact into an apparent physics divergence.
    only = os.environ.get("REDSTONE_TBLDIFF_ONLY", "")
    for pos, i in enumerate(idxs):
        vec = {ins[j]: (i >> j) & 1 for j in range(len(ins))}
        if only == "old":
            if hasattr(sim, "_BOUT"):
                sim._BOUT.clear()
            a = simvec_old.run_scalar(vec, P)
            print(f"vec{i:5d} OLD-only ticks={a[3]:5d} live={len(a[1]):6d} "
                  f"lamps={sum(1 for v in a[0].values() if v)}", flush=True)
            continue
        if only == "new":
            if hasattr(sim, "_BOUT"):
                sim._BOUT.clear()
            b = simvec.run_scalar(vec, P)
            print(f"vec{i:5d} NEW-only ticks={b[3]:5d} live={len(b[1]):6d} "
                  f"lamps={sum(1 for v in b[0].values() if v)}", flush=True)
            continue
        # ponytail: alternate run order per vector and clear the shared
        # sim._BOUT before EACH engine run. Old-always-first baked a
        # second-wins warmup bias into every ratio, and the burnout counter
        # is process-global, so the second engine also saw a hotter counter.
        ra = simvec_old.run_scalar
        rb = simvec.run_scalar
        if hasattr(sim, "_BOUT"):
            sim._BOUT.clear()
        t = time.monotonic()
        first = ra(vec, P) if pos % 2 == 0 else rb(vec, P)
        t_first = time.monotonic() - t
        if hasattr(sim, "_BOUT"):
            sim._BOUT.clear()
        t = time.monotonic()
        second = rb(vec, P) if pos % 2 == 0 else ra(vec, P)
        t_second = time.monotonic() - t
        if pos % 2 == 0:
            a, b, told, tnew = first, list(second), told + t_first, tnew + t_second
        else:
            b, a, tnew, told = list(first), second, tnew + t_first, told + t_second
        if fault == "ticks":
            b[3] = b[3] + 1
        elif fault == "live" and b[1]:
            k = sorted(b[1])[0]
            b[1] = dict(b[1])
            b[1][k] = 99
        elif fault == "lamp":
            k = sorted(b[0])[0]
            b[0] = dict(b[0])
            b[0][k] = not b[0][k]
        for f, x, y in zip(FIELDS, a, b):
            msg = cmp_field(f, i, x, y)
            if msg:
                print("DIVERGED  " + msg, flush=True)
                bad += 1
                break
        else:
            print(f"vec{i:5d} ok   ticks={a[3]:5d} live={len(a[1]):6d} "
                  f"lamps={sum(1 for v in a[0].values() if v)}", flush=True)

    print(f"\n{n} vectors: old {told:.2f}s  new {tnew:.2f}s  "
          f"speedup {told/max(1e-9,tnew):.2f}x  divergences={bad}")
    print(f"tables build (one-time, excluded from ratio): "
          f"old {t_tables_old:.2f}s  new {t_tables_new:.2f}s")
    if bad:
        print("TBL DIFF: DIVERGED")
        sys.exit(1)
    print("TBL DIFF: IDENTICAL")


if __name__ == "__main__":
    main()