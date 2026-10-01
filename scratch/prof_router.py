"""Bounded profile of the router on a cached band recipe.

NEVER HANGS: hard wall-clock budget; the recipe is a small band so the router
has something to chew on, and the budget aborts before any unbounded rung.
Usage: python scratch/prof_router.py <recipe.txt> [secs]
"""
import os
import sys
import time
import cProfile
import pstats
import io as _io
import faulthandler

sys.path.insert(0, r"D:\redstone-mini")
os.environ.pop("REDSTONE_SIM_GATE", None)

recipe = sys.argv[1] if len(sys.argv) > 1 else \
    r"D:\redstone-mini\scratch\cand_cpu4hier.txt"
budget = float(sys.argv[2]) if len(sys.argv) > 2 else 240.0

from recipe import parse_recipe
from compose import compose


def main():
    # ponytail: the bound MUST be armed here, not at import. compose() spawns
    # rung children with multiprocessing 'spawn', so a module-level
    # dump_traceback_later is inherited by every child -- each one silently
    # self-killed at the parent's budget, mid-compose.
    faulthandler.dump_traceback_later(budget, exit=True)
    t0 = time.monotonic()
    r = parse_recipe(open(recipe).read())
    print("recipe: %d gates, %d bands, %d inputs"
          % (len(r["gates"]), len({g.get("band", 0) for g in r["gates"]}),
             len(r["inputs"])), flush=True)

    pr = cProfile.Profile()
    pr.enable()
    blocks, size, io = compose(r)
    pr.disable()
    dt = time.monotonic() - t0
    print("compose: %.1fs  blocks=%d size=%s" % (dt, len(blocks), size), flush=True)
    s = _io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(24)
    print(s.getvalue(), flush=True)


if __name__ == "__main__":
    main()