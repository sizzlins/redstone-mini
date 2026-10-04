"""Diff the two engines' RING EVENT LOGS. Bounded, __main__ guard.

Usage: python scratch/evlog.py <vecindex> <build.pkl> <recipe.txt>

Both engines log every (tick, kind, cell) they pop off the Dial ring. The
first differing line is the exact instruction where the rewrite changed
behaviour -- which no amount of reading the two loops will tell you, because
the tables are provably equivalent (scratch/tbl_equiv.py) and the loop looks
the same. Prints a short window around the divergence and the totals.
"""
import os
import sys
import pickle

sys.path.insert(0, r"D:\redstone-mini")
sys.path.insert(0, r"D:\redstone-mini\scratch")
os.environ.pop("REDSTONE_SIM_GATE", None)
os.environ["REDSTONE_SIM_TICKS"] = "20000"
os.environ["REDSTONE_SIM_STEPS"] = "2000000"
import sim                      # noqa: E402
import simvec                   # noqa: E402
import simvec_old               # noqa: E402
from recipe import parse_recipe  # noqa: E402


KN = {0: "d", 1: "c", 2: "t", 4: "r", 6: "k"}
FIREK = {2: "T", 4: "R", 6: "K"}


def norm_new(log, ids):
    """(tick, int kind, id, fire) -> (tick, kind string, cell)."""
    return [(t, (FIREK[k] if f else KN[k]), ids[c]) for t, k, c, f in log]


def norm_old(log):
    return [(t, k, c) for t, k, c, _ in log]


def main():
    vi = int(sys.argv[1])
    # The log line lives INSIDE run_scalar's hot loop, so it is not present in
    # a shipped simvec.py (an append per event would cost real time). Re-add
    # these two lines to simvec.py to use this tool:
    #     _TR = []                     # next to _TBL = {}
    #     _TR.append((now, k, c, f))   # right after `k = kind[c]`
    if not hasattr(simvec, "_TR"):
        print("evlog: simvec.py carries no _TR instrumentation (it would cost "
              "an append per event in the hot loop).\n"
              "  re-add:  _TR = [] next to `_TBL = {}`\n"
              "           _TR.append((now, k, c, f)) right after `k = kind[c]`\n"
              "  Then re-run. Use scratch/tbl_diff.py for correctness -- it "
              "needs no instrumentation and compares all six outputs.")
        return
    dp = sys.argv[2] if len(sys.argv) > 2 else r"D:\redstone-mini\scratch\alu1merge.pkl"
    rp = sys.argv[3] if len(sys.argv) > 3 else r"D:\redstone-mini\recipes\alu1.txt"
    r = parse_recipe(open(rp).read())
    ins = r["inputs"]
    d = pickle.load(open(dp, "rb"))
    P = sim._parse_build(d["blocks"], d["io"])
    vec = {ins[j]: (vi >> j) & 1 for j in range(len(ins))}

    if hasattr(sim, "_BOUT"):
        sim._BOUT.clear()
    simvec_old.run_scalar(vec, P)
    A = norm_old(simvec_old._TR)
    ids = simvec._tables(P)["cell"]
    if hasattr(sim, "_BOUT"):
        sim._BOUT.clear()
    simvec.run_scalar(vec, P)
    B = norm_new(simvec._TR, ids)

    print(f"vec{vi}: old events={len(A)}  new events={len(B)}")
    n = min(len(A), len(B))
    first = None
    for i in range(n):
        if A[i] != B[i]:
            first = i
            break
    if first is None:
        if len(A) == len(B):
            print("event logs IDENTICAL")
        else:
            print(f"logs agree for the first {n} events, then lengths differ")
            print(f"  old tail: {A[n:n+6]}")
            print(f"  new tail: {B[n:n+6]}")
        return
    print(f"\nFIRST EVENT DIVERGENCE at index {first} of {n}")
    lo = max(0, first - 6)
    print(f"  ... context {lo}..{first + 8}")
    for i in range(lo, min(n, first + 8)):
        mark = ">>" if i == first else "  "
        print(f"  {mark} [{i:6d}] old={A[i]}  new={B[i]}"
              + ("   <<< DIFFERS" if i == first else ""))
    # how many events per tick up to the divergence
    ta, tb = A[first][0], B[first][0]
    print(f"\n  tick at divergence: old={ta} new={tb}")
    ca = sum(1 for e in A[:first + 1] if e[0] == ta)
    cb = sum(1 for e in B[:first + 1] if e[0] == tb)
    print(f"  events in that tick up to divergence: old={ca} new={cb}")
    ka = {}
    kb = {}
    for t, k, c in A[:first + 1]:
        ka[k] = ka.get(k, 0) + 1
    for t, k, c in B[:first + 1]:
        kb[k] = kb.get(k, 0) + 1
    print(f"  kind histogram old: {ka}")
    print(f"  kind histogram new: {kb}")


if __name__ == "__main__":
    main()