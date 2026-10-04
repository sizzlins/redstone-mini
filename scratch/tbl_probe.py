"""Measure what one verify worker actually costs: table build time + heap.

NEVER HANGS: one build, one parse, one table build, all in-process, engine
caps forced, no pool, no compose. tracemalloc bounds the measurement.

Usage: python scratch/tbl_probe.py [build.pkl] [nvec]

Answers H1 from the perf hunt: simvec's tables are dicts keyed by (x,y,z)
3-tuples. If one worker's tables cost hundreds of MB, then N workers multiply
that and the sweep stops being CPU-bound -- which would explain the measured
"8 concurrent children run 2.1x slower each than one alone".
"""
import os
import sys
import time
import tracemalloc
import pickle

sys.path.insert(0, r"D:\redstone-mini")
os.environ.pop("REDSTONE_SIM_GATE", None)
os.environ["REDSTONE_SIM_TICKS"] = "20000"
os.environ["REDSTONE_SIM_STEPS"] = "2000000"
import sim          # noqa: E402
import simvec       # noqa: E402
from recipe import parse_recipe  # noqa: E402

BUILDS = {
    "alu4": r"D:\redstone-mini\scratch\alu4merge_g.pkl",
    "alu1": r"D:\redstone-mini\scratch\alu1merge.pkl",
    "ctrl": r"D:\redstone-mini\scratch\ctrl_decode.pkl",
    "glass7": r"D:\redstone-mini\scratch\alu4glass7.pkl",
}


def main():
    key = sys.argv[1] if len(sys.argv) > 1 else "alu4"
    path = BUILDS.get(key, key)
    nvec = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    rp = (r"D:\redstone-mini\recipes\alu4.txt" if "alu4" in path
          else r"D:\redstone-mini\recipes\ctrl_decode.txt")

    d = pickle.load(open(path, "rb"))
    blocks, io = d["blocks"], d["io"]
    nblocks = len(blocks)

    tracemalloc.start()
    base = tracemalloc.get_traced_memory()[0]
    t = time.monotonic()
    P = sim._parse_build(blocks, io)
    t_parse = time.monotonic() - t
    after_parse = tracemalloc.get_traced_memory()[0]
    t = time.monotonic()
    st = simvec._tables_from(P, {})
    t_tbl = time.monotonic() - t
    cur, peak = tracemalloc.get_traced_memory()

    dust, torch, rep, rblk, cob, repdelay, lever, lampnet, \
        attach_rev, comp, leveratt, glass, slab, target = P
    print(f"build        {os.path.basename(path)}  {nblocks} blocks")
    print(f"cells        dust={len(dust)} pwr={len(cob | slab)} rep={len(rep)} "
          f"comp={len(comp)} torch={len(torch)} lamp={len(lampnet)}")
    print(f"parse        {t_parse:.2f}s   heap {MB(after_parse - base)}")
    print(f"tables       {t_tbl:.2f}s   heap {MB(cur - after_parse)}")
    print(f"TABLE TOTAL  {MB(cur - base)} heap for ONE worker")
    print(f"  per cell   {KB(cur - base) / max(1, st['ncells']):.1f} KiB")
    print(f"  at 16 workers  {MB((cur - base) * 16)}")

    # how many times is each cell re-evaluated? That is the other half of the
    # wall: evaluations per cell per vector, not just table size.
    r = parse_recipe(open(rp).read())
    ins = r["inputs"]
    simvec.run_scalar({i: 0 for i in ins}, P)   # warm + one real solve
    tracemalloc.reset_peak()
    t = time.monotonic()
    simvec.run_scalar({i: 1 for i in ins}, P)
    dt = time.monotonic() - t
    print(f"one vector   {dt:.3f}s (all-ones), heap peak {MB(tracemalloc.get_traced_memory()[1])}")
    print(f"  evals/vec  dust={173242}  cob={149126}  (measured separately)")


def MB(n):
    return n / 1048576.0


def KB(n):
    return n / 1024.0


if __name__ == "__main__":
    main()