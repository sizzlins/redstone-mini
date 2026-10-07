"""Router regression gate: hash the composed build.

compose_hier's output must be bit-identical before/after any router change --
same block count, same order, same ids. Prints one hash and the block count.

NEVER HANGS: faulthandler budget armed inside main() (compose spawns rung
children with 'spawn', so an import-time budget would be inherited and would
kill every child mid-compose).

Usage: python scratch/router_hash.py <recipe.txt> [secs]
"""
import os
import sys
import time
import json
import hashlib
import faulthandler


def main():
    recipe = sys.argv[1]
    budget = float(sys.argv[2]) if len(sys.argv) > 2 else 600.0
    sys.path.insert(0, r"D:\redstone-mini")
    os.environ.pop("REDSTONE_SIM_GATE", None)
    # inside main on purpose: a module-level budget is inherited by every
    # spawned rung child under 'spawn' and silently kills it mid-compose
    faulthandler.dump_traceback_later(budget, exit=True)
    from recipe import parse_recipe
    from compose import compose
    t0 = time.monotonic()
    r = parse_recipe(open(recipe).read())
    blocks, size, io = compose(r)
    dt = time.monotonic() - t0
    h = hashlib.sha256()
    for x, y, z, bid in blocks:
        h.update(("%d,%d,%d,%s;" % (x, y, z, bid)).encode())
    rec = {"secs": round(dt, 2), "n": len(blocks), "size": list(size),
           "sha": h.hexdigest()}
    print("ROUTER " + json.dumps(rec), flush=True)
    open(r"D:\redstone-mini\scratch\router_hash.json", "w").write(
        json.dumps(rec, indent=1))


if __name__ == "__main__":
    main()