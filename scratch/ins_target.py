"""Targeted insulate: swap EXACT pillars to glass, smoke 4 vectors.

Usage: python scratch/ins_target.py <in.pkl> <out.pkl> x,y,z [x,y,z ...]
Pillars are (x,y,z) of the COBBLE cell. Prints swap count + smoke.
Hard-bounded: one sim per smoke vector (4 total).
"""
import pickle
import sys

sys.path.insert(0, "D:/redstone-mini")


def _parse(s):
    x, y, z = s.split(",")
    return (int(x), int(y), int(z))


def _main():
    from recipe import parse_recipe, eval_net
    from sim import _parse_build, _latch_hold_seed, _run_vec
    pkl_in, pkl_out = sys.argv[1], sys.argv[2]
    targets = {_parse(s) for s in sys.argv[3:]}
    m = pickle.load(open(pkl_in, "rb"))
    blocks, io = m["blocks"], m["io"]
    swapped = 0
    out = []
    for x, y, z, bid in blocks:
        if (x, y, z) in targets and bid.split("[")[0] == "minecraft:cobblestone":
            out.append((x, y, z, "minecraft:glass"))
            swapped += 1
        else:
            out.append((x, y, z, bid))
    print("swapped %d/%d targets" % (swapped, len(targets)), flush=True)
    m2 = dict(m)
    m2["blocks"] = out
    pickle.dump(m2, open(pkl_out, "wb"))
    r = parse_recipe(open("scratch/cand_alu4hier.txt").read())
    P = _parse_build(out, io)
    hold = _latch_hold_seed(out, io)
    n = len(r["inputs"])
    bad = 0
    for bits in ([0] * n, [1] * n, [i % 2 for i in range(n)],
                 [1 - i % 2 for i in range(n)]):
        vec = dict(zip(r["inputs"], bits))
        try:
            got = _run_vec(vec, hold, P)[0]
        except RuntimeError as e:
            print("SMOKE %s RED %s" % ("".join(map(str, bits)),
                                       str(e)[:80]), flush=True)
            bad += 1
            continue
        want = eval_net(r, vec)
        miss = [o for o in r["outputs"]
                if bool(got.get(o, False)) != bool(want.get(o, False))]
        print("SMOKE %s %s" % ("".join(map(str, bits)),
                               "OK" if not miss else f"MISMATCH {miss}"),
              flush=True)
        bad += bool(miss)
    print("targeted: %s" % ("GREEN" if not bad else "RED"), flush=True)


if __name__ == "__main__":
    _main()
