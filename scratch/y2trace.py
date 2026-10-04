"""Trace lit-should-be-dark sources for one output on one vector.

Usage: python scratch/y2trace.py <pkl> <recipe> <vecbits> <output>
Hard-bounded: 1 sim run. Import-safe (all work inside _main).
"""
import pickle
import sys

sys.path.insert(0, "D:/redstone-mini")
from recipe import parse_recipe, eval_net
from sim import _parse_build, _latch_hold_seed, _run_vec


def _main():
    pkl, src, bits, out = (sys.argv[1], sys.argv[2], sys.argv[3],
                           sys.argv[4])
    m = pickle.load(open(pkl, "rb"))
    blocks, io = m["blocks"], m["io"]
    nets = io["nets"]
    r = parse_recipe(open(src).read())
    P = _parse_build(blocks, io)
    hold = _latch_hold_seed(blocks, io)
    vec = dict(zip(r["inputs"], [int(b) for b in bits]))
    got, live, tl, tk, ron, con = _run_vec(vec, hold, P)
    want = eval_net(r, vec)
    print("want %s=%s got=%s" % (out, int(bool(want[out])),
                                 int(bool(got.get(out, False)))), flush=True)
    bmap = {(x, y, z): bid for x, y, z, bid in blocks}
    by_out = {}
    for g in r["gates"]:
        by_out[g["out"]] = g["args"]
    fan = {out}
    changed = True
    while changed:
        changed = False
        for o in list(fan):
            for a in by_out.get(o, []):
                if a not in ("0", "1") and a not in fan:
                    fan.add(a)
                    changed = True
    print("fanin nets: %d" % len(fan), flush=True)
    torchpillars = {}
    for (x, y, z), n in nets.items():
        if n not in fan or not live.get((x, y, z), 0):
            continue
        w = want.get(n)
        if w is None or bool(w):
            continue
        if y < 2:
            continue
        s = (x, y - 1, z)
        if bmap.get(s, "").split("[")[0] != "minecraft:cobblestone":
            continue
        for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0),
                           (0, 0, 1), (0, 0, -1)):
            cc = (s[0] + dx, s[1] + dy, s[2] + dz)
            if cc == (x, y, z):
                continue
            if bmap.get(cc, "").split("[")[0] == \
                    "minecraft:redstone_wall_torch":
                torchpillars[s] = torchpillars.get(s, 0) + 1
                break
    print("torch-fed pillars on lit-dark fanin dust: %d" % len(torchpillars),
          flush=True)
    for s, k in sorted(torchpillars.items()):
        print("  TP %s feeds %d" % (s, k), flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    _main()
