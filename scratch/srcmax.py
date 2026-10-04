"""Local power maxima of one net (sources, not conduction).

Usage: python scratch/srcmax.py <band recipe> <force> <vecbits> <net>
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
    bmap = {(x, y, z): bid for x, y, z, bid in blocks}
    cells = [(x, y, z) for (x, y, z), n in nets.items() if n == net]
    print("net %s want=%s ncells=%d" % (
        net, int(bool(want.get(net, False))), len(cells)), flush=True)
    maxima = []
    for c in cells:
        v = live.get(c, 0)
        if not v:
            continue
        ismax = True
        for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0),
                           (0, 0, 1), (0, 0, -1)):
            cc = (c[0] + dx, c[1] + dy, c[2] + dz)
            if nets.get(cc) == net and live.get(cc, 0) > v:
                ismax = False
                break
        if ismax:
            nbrs = []
            for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0),
                               (0, 0, 1), (0, 0, -1)):
                cc = (c[0] + dx, c[1] + dy, c[2] + dz)
                bb = bmap.get(cc, "").split("[")[0]
                if "torch" in bb or "repeater" in bb or "lever" in bb:
                    nbrs.append((cc, bb, tl.get(cc, ron.get(cc, "?"))))
                elif cc in nets and nets[cc] != net:
                    nbrs.append((cc, nets[cc], live.get(cc, 0)))
            maxima.append((c, v, nbrs))
    print("local maxima: %d" % len(maxima), flush=True)
    for c, v, nbrs in sorted(maxima)[:15]:
        print("  %s=%d non-%s-nbrs=%s" % (c, v, net, nbrs), flush=True)


if __name__ == "__main__":
    _main()
