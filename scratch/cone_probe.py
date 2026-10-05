"""Influence-cone probe: which cells can each input pin reach via wake edges?

NEVER HANGS: one build, one BFS per pin over a finite graph (each id visited
once), no pool, no compose. Prints per-pin cone size and the union, as a
fraction of nid. Informs cone-restricted warm seeding: if a pin's cone is X%
of the build, seeding only the cone skips (100-X)% of seed evals.

Usage: python scratch/cone_probe.py [build.pkl] [recipe.txt]
"""
import os
import sys
import pickle
from collections import deque

sys.path.insert(0, r"D:\redstone-mini")
sys.path.insert(0, r"D:\redstone-mini\scratch")
os.environ.pop("REDSTONE_SIM_GATE", None)
import sim  # noqa: E402
import simvec  # noqa: E402
from recipe import parse_recipe  # noqa: E402


def main():
    dp = sys.argv[1] if len(sys.argv) > 1 else \
        r"D:\redstone-mini\scratch\alu4merge_g.pkl"
    rp = sys.argv[2] if len(sys.argv) > 2 else \
        r"D:\redstone-mini\recipes\alu4.txt"
    r = parse_recipe(open(rp).read())
    ins = r["inputs"]
    d = pickle.load(open(dp, "rb"))
    P = sim._parse_build(d["blocks"], d["io"])
    st = simvec._tables(P)
    nid = st["nid"]
    wake = st["wake"]
    # reverse wake: dependents of each cell (abs ids, bool+level = superset)
    rev = [[] for _ in range(nid)]
    for c in range(nid):
        for e in wake[c]:
            t = e if e >= 0 else ~e
            rev[c].append(t)
    # cells reading each pin directly (any class; lamp nets excluded: cone ends)
    seeds = {p: set() for p in ins}
    for c in range(nid):
        for nm in st["d_lev"][c]:
            if nm in seeds:
                seeds[nm].add(c)
        for nm in st["c_lev"][c]:
            if nm in seeds:
                seeds[nm].add(c)
    for c in range(nid):
        for spec in (st["r_src"][c],) + tuple(st["r_side"][c] or (None, None)) + \
                (st["k_rear"][c],) + tuple(st["k_side"][c] or (None, None)):
            if spec is not None and spec[0] == 2 and spec[1] in seeds:
                seeds[spec[1]].add(c)
    union = set()
    for p in ins:
        seen = set(seeds[p])
        q = deque(seeds[p])
        while q:
            c = q.popleft()
            for t in rev[c]:
                if t not in seen:
                    seen.add(t)
                    q.append(t)
        union |= seen
        print(f"pin {p}: seeds={len(seeds[p]):5d} cone={len(seen):6d} "
              f"({100.0 * len(seen) / nid:.1f}%)", flush=True)
    print(f"union: {len(union)} / {nid} ({100.0 * len(union) / nid:.1f}%)")


if __name__ == "__main__":
    main()
