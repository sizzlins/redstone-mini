"""Verify-driven insulation: swap pillars that can only carry parasites.

Rule (fail-safe direction): swap cobble pillar P to glass iff
 1. some dust cell directly above P exists, is sim-lit but logically
    dark on the SAME vector (per-vector parasitic evidence via recipe
    eval_net), AND
 2. a non-attached torch feeds P (attach = facing-vector points at P,
    mirroring scratch/pillars.py; attached/lever/repeater-adjacent
    pillars are load-bearing and skipped), AND
 3. no adjacent dust is logically lit on that vector (no shared use), AND
 4. y>=2, cobble.

Rationale: per-vector evidence catches runs that light legitimately on
some vectors but parasitically on others (an all-vectors-dark rule finds
nothing -- correct nets are rarely dark everywhere). Errors go toward
UNDER-fixing (a skipped pillar keeps today's behavior). A full re-verify
after swapping is mandatory (the gate, not this rule).

Usage: python scratch/ins_allvec.py <merge.pkl> <recipe.txt> <states.pkl>
       <out.pkl>
Hard-bounded: states load + one pass, no sim. Import-safe.
"""
import pickle
import sys

sys.path.insert(0, "D:/redstone-mini")
from recipe import parse_recipe, eval_net


def _base(bid):
    return bid.split("[")[0]


_V = {"east": (-1, 0), "west": (1, 0), "south": (0, -1),
      "north": (0, 1)}


def _torch_feeds_pillar(bmap, nets, want, s, skip):
    """True iff a torch beside pillar s can inject parasitic power.

    Mirrors scratch/pillars.py attach logic (facing f, vector V[f]:
    attached iff neighbor + v == pillar). An attached torch makes the
    pillar load-bearing (skip); a merely adjacent torch is a feed.
    Dust-fed pillars are normal vertical conduction, never candidates
    (blanket insulate() proved they carry legitimate signal). Lever or
    repeater adjacent: skip (load-bearing or directional).
    """
    fed = False
    for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0),
                       (0, 0, 1), (0, 0, -1)):
        cc = (s[0] + dx, s[1] + dy, s[2] + dz)
        if cc == skip:
            continue
        nb = bmap.get(cc, "")
        bb = _base(nb)
        if bb == "minecraft:redstone_wire":
            nn = nets.get(cc)
            if nn is not None and want.get(nn, False):
                return False
        elif bb == "minecraft:lever":
            return False
        elif bb == "minecraft:repeater":
            return False
        elif bb == "minecraft:redstone_wall_torch":
            f = nb.split("facing=")[1].rstrip("]") if "facing=" in nb \
                else "east"
            v = _V.get(f, (0, 0))
            if (cc[0] + v[0], cc[1], cc[2] + v[1]) == s:
                return False  # attached: pillar is its host
            fed = True
    return fed


def find_pillars(blocks, io, recipe, states):
    nets = io["nets"]
    bmap = {(x, y, z): bid for x, y, z, bid in blocks}
    vecs = states["vectors"]
    # ponytail: per-VECTOR parasitic evidence, not all-vector darkness.
    # A run that lights legitimately on some vectors (Y2's fanin) is still
    # parasitic where it is sim-lit but logically dark on the SAME vector.
    # The earlier all-vectors-dark version found nothing (correct nets are
    # rarely dark everywhere) -- and its alu1 "specificity" zero was
    # vacuous for the same reason. Precision comes from the mandatory
    # full re-verify after swapping, not from over-filtering here.
    out = {}
    for vkey, st in vecs.items():
        vals = dict(zip(recipe["inputs"], [int(b) for b in vkey]))
        want = eval_net(recipe, vals)
        # ponytail: states store dust keys as "x,y,z" strings (JSON
        # round-trip); translate once per vector. A tuple lookup against
        # string keys misses everything (measured: 0 pillars found).
        live = {}
        for k, v in st["w"].items():
            if v:
                try:
                    x, y, z = k.split(",")
                    live[(int(x), int(y), int(z))] = v
                except (ValueError, AttributeError):
                    pass
        for (x, y, z), n in nets.items():
            if y < 2 or not live.get((x, y, z), 0):
                continue
            if want.get(n, True):
                continue
            s = (x, y - 1, z)
            if _base(bmap.get(s, "")) != "minecraft:cobblestone":
                continue
            if _torch_feeds_pillar(bmap, nets, want, s, (x, y, z)):
                out.setdefault(s, set()).add(vkey)
    return sorted(out.items())


def _main():
    pkl, src, spkl, outp = (sys.argv[1], sys.argv[2], sys.argv[3],
                            sys.argv[4])
    m = pickle.load(open(pkl, "rb"))
    blocks, io = m["blocks"], m["io"]
    recipe = parse_recipe(open(src).read())
    states = pickle.load(open(spkl, "rb"))
    found = find_pillars(blocks, io, recipe, states)
    print("pillars: %d" % len(found), flush=True)
    for s, vkeys in found[:40]:
        print("  P %s on %d vectors" % (s, len(vkeys)), flush=True)
    ss = set(s for s, _ in found)
    m2 = dict(m)
    m2["blocks"] = [(x, y, z, "minecraft:glass")
                    if (x, y, z) in ss
                    and bid.split("[")[0] == "minecraft:cobblestone"
                    else (x, y, z, bid) for x, y, z, bid in blocks]
    pickle.dump(m2, open(outp, "wb"))
    print("wrote %s" % outp, flush=True)


if __name__ == "__main__":
    _main()
