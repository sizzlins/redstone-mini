"""Authoritative dense status: layout_retry (compose -> maze fallback, verified).

Usage: python scratch/dense_status.py [recipe ...] [tries]
Prints one line per recipe: OK(blocks) or the loud wall. Exit 0 iff all OK.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from recipe import parse_recipe
from sim import layout_retry

def main():
    names = [a for a in sys.argv[1:] if not a.isdigit()] or [
        "recipes/micro1.txt", "recipes/alu1.txt", "recipes/alu4.txt",
        "recipes/cpu4.txt", "recipes/ctrl_decode.txt"]
    tries = int(next((a for a in sys.argv[1:] if a.isdigit()), 6))
    bad = 0
    for n in names:
        t0 = time.time()
        try:
            blocks, size, io, st = layout_retry(parse_recipe(open(n).read()),
                                                tries=tries, verify=True)
            print(f"{n:16} OK  {len(blocks):7d} blocks  {size}  "
                  f"{time.time()-t0:6.1f}s", flush=True)
        except RuntimeError as e:
            bad += 1
            msg = " ".join(str(e).split())
            print(f"{n:16} RED {time.time()-t0:6.1f}s  {msg[:150]}",
                  flush=True)
    print("FAIL" if bad else "ALL OK", flush=True)
    return 1 if bad else 0


# ponytail: main guard + flush. This file composes -> sim_verify -> the
# bit-parallel path, so an unguarded top-level loop re-imports itself under
# spawn and duplicates the whole fleet run in parallel with the parent; and
# piped stdout is block-buffered, so without flush a healthy run prints
# nothing until it exits (indistinguishable from a hang).
if __name__ == "__main__":
    sys.exit(main())
