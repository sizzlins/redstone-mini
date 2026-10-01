"""Bounded profile of simvec.run_scalar vs sim._run_vec on cached alu4.

NEVER HANGS: fixed small vector count, engine caps in force, no pool.
Usage: python scratch/prof_scalar.py [nvec]
"""
import os
import sys
import pickle
import time
import cProfile
import pstats
import io as _io

sys.path.insert(0, r"D:\redstone-mini")
os.environ.pop("REDSTONE_SIM_GATE", None)
import sim
import simvec
from recipe import parse_recipe

n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
r = parse_recipe(open(r"D:\redstone-mini\scratch\cand_alu4hier.txt").read())
d = pickle.load(open(r"D:\redstone-mini\scratch\alu4_build.pkl", "rb"))
ins = r["inputs"]
P = sim._parse_build(d["blocks"], d["io"])
combos = [{ins[j]: (k >> j) & 1 for j in range(len(ins))} for k in range(n)]

simvec.run_scalar(combos[0], P)          # build tables once, outside the timing
t = time.monotonic()
for vec in combos:
    simvec.run_scalar(vec, P)
dt = time.monotonic() - t
print("run_scalar: %d vectors in %.2fs (%.3fs each) [tables warm]"
      % (n, dt, dt / n), flush=True)

pr = cProfile.Profile()
pr.enable()
for vec in combos:
    simvec.run_scalar(vec, P)
pr.disable()
s = _io.StringIO()
pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(16)
print(s.getvalue(), flush=True)