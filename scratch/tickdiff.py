"""Find the FIRST tick where the old and new table engines disagree.

NEVER HANGS: one vector, snap_at over a bounded tick range, both engines
in-process with caps forced. Usage:

    python scratch/tickdiff.py <vecindex> <build.pkl> <recipe.txt> [maxtick]

The rewrite settles some vectors exactly one tick EARLIER with an identical
final state, so the divergence is in scheduling, not physics. Rather than
guess which table caused it, run both engines with the same snap_at stops and
report the first tick whose live-dust map differs, plus the step counts.
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


def main():
    vi = int(sys.argv[1])
    dp = sys.argv[2] if len(sys.argv) > 2 else \
        r"D:\redstone-mini\scratch\alu4merge_g.pkl"
    rp = sys.argv[3] if len(sys.argv) > 3 else r"D:\redstone-mini\recipes\alu4.txt"
    maxt = int(sys.argv[4]) if len(sys.argv) > 4 else 400
    r = parse_recipe(open(rp).read())
    ins = r["inputs"]
    d = pickle.load(open(dp, "rb"))
    P = sim._parse_build(d["blocks"], d["io"])
    vec = {ins[j]: (vi >> j) & 1 for j in range(len(ins))}

    # ask both engines for the state at the end of every tick 0..maxt
    stop_a = {t: None for t in range(maxt + 1)}
    stop_b = {t: None for t in range(maxt + 1)}
    a = simvec_old.run_scalar(vec, P, snap_at=stop_a)
    b = simvec.run_scalar(vec, P, snap_at=stop_b)

    print(f"vec{vi}: old ticks={a[3]}  new ticks={b[3]}")
    print(f"final identical: {a[1] == b[1]}  lamps {a[0] == b[0]}  "
          f"torch {a[2] == b[2]}  rep {a[4] == b[4]}  comp {a[5] == b[5]}")

    first = None
    for t in range(maxt + 1):
        sa, sb = stop_a[t], stop_b[t]
        if sa is None or sb is None:
            continue
        if sa != sb:
            first = t
            break
    if first is None:
        print(f"no per-tick divergence in 0..{maxt} (settle-time only)")
        return
    print(f"\nFIRST DIVERGENT TICK: {first}")
    sa, sb = stop_a[first], stop_b[first]
    ka, kb = set(sa), set(sb)
    print(f"  lit cells: old={len(sa)} new={len(sb)}")
    only_a = sorted(ka - kb)[:6]
    only_b = sorted(kb - ka)[:6]
    print(f"  lit only in OLD: {[(c, sa[c]) for c in only_a]}")
    print(f"  lit only in NEW: {[(c, sb[c]) for c in only_b]}")
    diff = [(c, sa[c], sb[c]) for c in sorted(ka & kb) if sa[c] != sb[c]]
    print(f"  level differs on {len(diff)} shared cells: {diff[:6]}")
    if first > 0:
        pa, pb = stop_a[first - 1], stop_b[first - 1]
        print(f"  previous tick identical: {pa == pb}")
        if pa != pb:
            ka, kb = set(pa), set(pb)
            print(f"  prev lit: old={len(pa)} new={len(pb)}")
            d2 = [(c, pa[c], pb[c]) for c in sorted(ka & kb) if pa[c] != pb[c]]
            print(f"  prev level differs on {len(d2)}: {d2[:6]}")


if __name__ == "__main__":
    main()