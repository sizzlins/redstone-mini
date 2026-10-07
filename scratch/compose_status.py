"""compose-only dense status (fast, no maze fallback). Exit 0 iff all green."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from recipe import parse_recipe
from compose import compose
from sim import sim_verify

names = [a for a in sys.argv[1:] if not a.isdigit()] or [
    "recipes/micro1.txt", "recipes/alu1.txt", "recipes/alu4.txt",
    "recipes/cpu4.txt", "recipes/ctrl_decode.txt"]
bad = 0
for n in names:
    t0 = time.time()
    try:
        blocks, size, io = compose(parse_recipe(open(n).read()))
    except RuntimeError as e:
        bad += 1
        print(f"{n:16} COMPOSE-RED {time.time()-t0:7.1f}s  "
              f"{' '.join(str(e).split())[:120]}", flush=True)
        continue
    try:
        sim_verify(parse_recipe(open(n).read()), blocks, io, quiet=True)
    except RuntimeError as e:
        bad += 1
        print(f"{n:16} SIM-RED    {time.time()-t0:7.1f}s  "
              f"{' '.join(str(e).split())[:120]}", flush=True)
        continue
    print(f"{n:16} GREEN      {time.time()-t0:7.1f}s  {len(blocks)} blocks {size}",
          flush=True)
print("FAIL" if bad else "ALL OK", flush=True)
sys.exit(1 if bad else 0)
