"""4-vector smoke on cached merges (post-change confidence, cheap).

Usage: python scratch/merge_smoke.py <merge.pkl> <recipe.txt>
Bounded: 4 serial sim runs, engine caps in force. Exit 0 iff all match.
"""
import pickle
import sys
import time

sys.path.insert(0, "D:/redstone-mini")


def _main():
    from recipe import parse_recipe, eval_net
    from sim import _parse_build, _latch_hold_seed, _run_vec
    pkl, src = sys.argv[1], sys.argv[2]
    m = pickle.load(open(pkl, "rb"))
    blocks, io = m["blocks"], m["io"]
    r = parse_recipe(open(src).read())
    P = _parse_build(blocks, io)
    hold = _latch_hold_seed(blocks, io)
    n = len(r["inputs"])
    bad = 0
    t0 = time.monotonic()
    for bits in ([0] * n, [1] * n, [i % 2 for i in range(n)],
                 [1 - i % 2 for i in range(n)]):
        vec = dict(zip(r["inputs"], bits))
        try:
            got = _run_vec(vec, hold, P)[0]
        except RuntimeError as e:
            print("SMOKE %s RED %s" % ("".join(map(str, bits)),
                                       str(e)[:100]), flush=True)
            bad += 1
            continue
        want = eval_net(r, vec)
        miss = [o for o in r["outputs"]
                if bool(got.get(o, False)) != bool(want.get(o, False))]
        print("SMOKE %s %s" % ("".join(map(str, bits)),
                               "OK" if not miss else f"MISMATCH {miss}"),
              flush=True)
        bad += bool(miss)
    print("smoke %s in %.0fs" % ("GREEN" if not bad else "RED",
                                 time.monotonic() - t0), flush=True)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    _main()
