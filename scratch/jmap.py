"""Map an OR-junction fault: junction dust, input diodes, neighbors.

Usage: python scratch/jmap.py <band recipe> <force> <vecbits> <net>
Bounded: one compose (capped) + one sim run. Import-safe.
"""
import os
import sys

sys.path.insert(0, r"D:\redstone-mini")


def _main():
    from recipe import parse_recipe, eval_net
    from compose import compose
    from sim import _parse_build, _latch_hold_seed, _run_vec
    path, force, vbits, net = (sys.argv[1], sys.argv[2], sys.argv[3],
                               sys.argv[4])
    os.environ["REDSTONE_FORCE"] = force
    os.environ["REDSTONE_COMPOSE_SECS"] = "240"
    r = parse_recipe(open(path).read())
    blocks, size, io = compose(r)
    vec = dict(zip(r["inputs"], [int(b) for b in vbits]))
    P = _parse_build(blocks, io)
    hold = _latch_hold_seed(blocks, io)
    got, live, tl, tk, ron, con = _run_vec(vec, hold, P)
    want = eval_net(r, vec)
    nets = io["nets"]
    cells = sorted((x, y, z) for (x, y, z), n in nets.items() if n == net)
    print("net %s want=%s cells=%d" % (net, int(bool(want.get(net, False))),
                                       len(cells)), flush=True)
    for c in cells:
        print("  %s=%s" % (c, live.get(c, 0)), flush=True)
    print("repeaters within 3:", flush=True)
    rset = {}
    for x, y, z, bid in blocks:
        if "repeater" in bid:
            rset[(x, y, z)] = bid
    import re as _re
    for c in cells:
        for dx in range(-3, 4):
            for dz in range(-3, 4):
                for dy in (-1, 0, 1):
                    cc = (c[0] + dx, c[1] + dy, c[2] + dz)
                    if cc in rset:
                        _m = _re.search(r"facing=([a-z]+)", rset[cc])
                        print("  rep %s facing=%s ron=%s adj-dust=%s" % (
                            cc, _m.group(1) if _m else "?",
                            ron.get(cc, "?"),
                            [(kk, nets.get(kk), live.get(kk, 0))
                             for kk in ((cc[0] + 1, cc[1], cc[2]),
                                        (cc[0] - 1, cc[1], cc[2]),
                                        (cc[0], cc[1], cc[2] + 1),
                                        (cc[0], cc[1], cc[2] - 1))
                             if kk in nets]), flush=True)


if __name__ == "__main__":
    _main()
