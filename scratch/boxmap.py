"""Map a 3D box: all dust (any net, live values) + devices.

Usage: python scratch/boxmap.py <band recipe> <force> <vecbits> x0,x1,y0,y1,z0,z1
Bounded: one compose (capped) + one sim run. Import-safe.
"""
import os
import sys

sys.path.insert(0, r"D:\redstone-mini")


def _main():
    from recipe import parse_recipe, eval_net
    from compose import compose
    from sim import _parse_build, _latch_hold_seed, _run_vec
    path, force, vbits = sys.argv[1], sys.argv[2], sys.argv[3]
    x0, x1, y0, y1, z0, z1 = [int(v) for v in sys.argv[4].split(",")]
    os.environ["REDSTONE_FORCE"] = force
    os.environ["REDSTONE_COMPOSE_SECS"] = "240"
    r = parse_recipe(open(path).read())
    blocks, size, io = compose(r)
    vec = dict(zip(r["inputs"], [int(b) for b in vbits]))
    P = _parse_build(blocks, io)
    hold = _latch_hold_seed(blocks, io)
    got, live, tl, tk, ron, con = _run_vec(vec, hold, P)
    nets = io["nets"]
    dev = {}
    for x, y, z, bid in blocks:
        if x0 <= x <= x1 and y0 <= y <= y1 and z0 <= z <= z1:
            b = bid.split("[")[0].split(":")[-1]
            if b not in ("minecraft:cobblestone", "minecraft:stone",
                         "minecraft:glass"):
                dev[(x, y, z)] = bid
    print("   " + "".join(f"{x % 100:>4d}" for x in range(x0, x1 + 1)),
          flush=True)
    for y in range(y0, y1 + 1):
        for z in range(z0, z1 + 1):
            row = []
            for x in range(x0, x1 + 1):
                n = nets.get((x, y, z), "")
                v = live.get((x, y, z), 0)
                if n and v:
                    row.append("%2s*" % n[:2].upper())
                elif n:
                    row.append("%2s." % n[:2].lower())
                elif (x, y, z) in dev:
                    b = dev[(x, y, z)].split("[")[0].split(":")[-1]
                    row.append({"wall_torch": "TT", "repeater": "RR",
                                "lever": "LL", "lamp": "[]",
                                "cobblestone": "##"}.get(b, "??") +
                               ("!" if (tl.get((x, y, z), False)
                                        or ron.get((x, y, z), False)) else " "))
                else:
                    row.append(" . ")
            print("y=%d z=%-4d" % (y, z) + "".join(row), flush=True)


if __name__ == "__main__":
    _main()
