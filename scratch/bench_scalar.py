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
d = pickle.load(open(r"D:\redstone-mini\scratch\alu4_build.pkl", "rb"))
ins = r["inputs"]
P = sim._parse_build(d["blocks"], d["io"])
combos = [{ins[j]: (k >> j) & 1 for j in range(len(ins))} for k in range(n)]

simvec.run_scalar(combos[0], P)              # warm the tables
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