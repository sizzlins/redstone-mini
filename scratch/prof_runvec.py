"""Bounded profile of the serial engine on the cached alu4 build.

NEVER HANGS: fixed small vector count, and cProfile only. No pool, no compose.
Usage: python scratch/prof_runvec.py [nvec] [build.pkl]
"""
import os, sys, pickle, cProfile, pstats, io, time

sys.path.insert(0, r"D:\redstone-mini")
os.environ.pop("REDSTONE_SIM_GATE", None)
from sim import _parse_build, _run_vec
from recipe import parse_recipe

n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
r = parse_recipe(open(r"D:\redstone-mini\scratch\cand_alu4hier.txt").read())
d = pickle.load(open(r"D:\redstone-mini\scratch\alu4merge_g.pkl", "rb"))
blocks, io_ = d["blocks"], d["io"]
ins = r["inputs"]

t = time.monotonic()
P = _parse_build(blocks, io_)
print("_parse_build: %.3fs  cells: dust=%d cob=%d rep=%d comp=%d torch=%d"
      % (time.monotonic() - t, len(P[0]), len(P[5]), len(P[3]), len(P[10]),
         len(P[1])), flush=True)

combos = [{ins[j]: (k >> j) & 1 for j in range(len(ins))} for k in range(n)]


def go():
    tot = 0
    for vec in combos:
        t0 = time.monotonic()
        _run_vec(vec, None, P)
        tot += time.monotonic() - t0
    return tot


t = time.monotonic()
tot = go()
print("serial: %d vectors in %.2fs (%.3fs each)" % (n, tot, tot / n), flush=True)

pr = cProfile.Profile()
pr.enable()
go()
pr.disable()
s = io.StringIO()
pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(22)
print(s.getvalue(), flush=True)
