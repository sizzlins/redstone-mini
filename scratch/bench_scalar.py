"""Stable A/B benchmark for run_scalar. Repeats to beat scheduler noise.

NEVER HANGS: fixed vector count, engine caps in force, no pool, no compose.
Usage: python scratch/bench_scalar.py [nvec] [reps]
"""
import os
import sys
import time
import pickle
import statistics

sys.path.insert(0, r"D:\redstone-mini")
os.environ.pop("REDSTONE_SIM_GATE", None)
import sim
import simvec
from recipe import parse_recipe

n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
reps = int(sys.argv[2]) if len(sys.argv) > 2 else 3
r = parse_recipe(open(r"D:\redstone-mini\scratch\cand_alu4hier.txt").read())
d = pickle.load(open(sys.argv[3] if len(sys.argv) > 3 else
                     r"D:\redstone-mini\scratch\alu4_build.pkl", "rb"))
ins = r["inputs"]
P = sim._parse_build(d["blocks"], d["io"])
# "spread" = evenly spaced vector indices, not 0..n-1. The easy low-index
# vectors settle in ~0.5s; the average over 2^n is set by hard ones (the
# verify log's slowest need 20000 ticks), so a 0..n-1 benchmark measures
# the wrong end of the distribution and hides where the wall time goes.
spread = len(sys.argv) > 4 and sys.argv[4] == "spread"
if spread:
    combos = [{ins[j]: (k >> j) & 1 for j in range(len(ins))}
              for k in (round(i * (2 ** len(ins) - 1) / (n - 1))
                        for i in range(n))] if n > 1 else [{}]
else:
    combos = [{ins[j]: (k >> j) & 1 for j in range(len(ins))} for k in range(n)]

simvec.run_scalar(combos[0], P)              # warm the tables
if spread:
    # per-vector wall time, the distribution that decides chunk wall time
    for i, vec in enumerate(combos):
        t = time.monotonic()
        simvec.run_scalar(vec, P)
        print("  spread[%d/%d] %.2fs" % (i, len(combos),
                                        time.monotonic() - t), flush=True)
    raise SystemExit(0)
sc, rs = [], []
for _ in range(reps):
    t = time.monotonic()
    for vec in combos:
        simvec.run_scalar(vec, P)
    sc.append((time.monotonic() - t) / n)
    t = time.monotonic()
    for vec in combos:
        sim._run_vec(vec, None, P)
    rs.append((time.monotonic() - t) / n)
print("run_scalar  best=%.3fs med=%.3fs per vector"
      % (min(sc), statistics.median(sc)), flush=True)
print("_run_vec    best=%.3fs med=%.3fs per vector"
      % (min(rs), statistics.median(rs)), flush=True)
print("speedup     best=%.2fx med=%.2fx"
      % (min(rs) / min(sc), statistics.median(rs) / statistics.median(sc)),
      flush=True)
