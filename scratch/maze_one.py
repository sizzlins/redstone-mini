"""Try the maze backend (layout.py) on one band recipe. Bounded."""
import os
import sys
import time

sys.path.insert(0, r"D:\redstone-mini")


def _main():
    from recipe import parse_recipe
    from layout import layout
    from sim import sim_verify
    path = sys.argv[1]
    seed = None if len(sys.argv) < 3 else int(sys.argv[2])
    grow = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    r = parse_recipe(open(path).read())
    t0 = time.monotonic()
    try:
        out = layout(r, seed=seed, grow=grow)
    except RuntimeError as e:
        print("maze RED: %s (%.1fs)"
              % (" ".join(str(e).split())[:120], time.monotonic() - t0),
              flush=True)
        return
    blocks, size, io = out
    print("maze routed %d blocks in %.1fs" % (len(blocks),
                                             time.monotonic() - t0), flush=True)
    try:
        sim_verify(r, blocks, io, quiet=True)
        print("maze GREEN", flush=True)
    except RuntimeError as e:
        print("maze sim RED: %s" % " ".join(str(e).split())[:120], flush=True)


if __name__ == "__main__":
    _main()
