"""Diagnose a routed-but-sim-red band: compose one forced rung, then settled
DIFF (build vs want) per net on a failing vector. Bounded: one compose (hard
capped) + one sim run. Import-safe.
"""
import os
import sys

sys.path.insert(0, r"D:\redstone-mini")


def _main():
    from recipe import parse_recipe, eval_net
    from compose import compose
    from sim import _parse_build, _latch_hold_seed, _run_vec, sim_verify
    path, force, vbits = sys.argv[1], sys.argv[2], sys.argv[3]
    os.environ["REDSTONE_FORCE"] = force
    os.environ["REDSTONE_COMPOSE_SECS"] = "240"
    r = parse_recipe(open(path).read())
    try:
        blocks, size, io = compose(r)
    except RuntimeError as e:
        print("compose RED: %s" % " ".join(str(e).split())[:150], flush=True)
        return
    print("routed %d blocks %s" % (len(blocks), size), flush=True)
    try:
        import compose as _C
        _ctx = _C._last_ctx
        if _ctx is not None:
            print("tile recs:", flush=True)
            for rec in _ctx.recs:
                print("  %s %s <- %s ports=%s" % (
                    rec[0], rec[1], rec[2], rec[3]), flush=True)
            for n in ("A0B0", "S1", "X1", "OP1"):
                if n in _ctx.pos:
                    print("  pos[%s] = %s" % (n, _ctx.pos[n]), flush=True)
    except Exception as e:
        print("recs unavailable: %s" % str(e)[:80], flush=True)
    try:
        sim_verify(r, blocks, io, quiet=True)
        print("sim GREEN", flush=True)
        return
    except RuntimeError as e:
        print("sim RED: %s" % " ".join(str(e).split())[:100], flush=True)
    vec = dict(zip(r["inputs"], [int(b) for b in vbits]))
    P = _parse_build(blocks, io)
    hold = _latch_hold_seed(blocks, io)
    got, live, tl, tk, ron, con = _run_vec(vec, hold, P)
    want = eval_net(r, vec)
    nets = io["nets"]
    for g in r["gates"]:
        o = g["out"]
        w = want.get(o)
        if w is None:
            continue
        cells = [(x, y, z) for (x, y, z), n in nets.items() if n == o]
        if not cells:
            continue
        mx = max([live.get(c, 0) for c in cells] or [0])
        gb = got.get(o)
        mark = ""
        if gb is not None and bool(gb) != bool(w):
            mark = "  <-- LAMP MISMATCH"
        if bool(mx) != bool(w):
            mark += "  <-- DUST MISMATCH"
        if mark or o in ("X1", "A0B0", "S1", "OP1", "OP0"):
            print("NET %s want=%d lamp=%s dustmax=%d cells=%d%s"
                  % (o, int(bool(w)), gb, mx, len(cells), mark),
                  flush=True)
    for n in r["inputs"]:
        cells = [(x, y, z) for (x, y, z), nn in nets.items() if nn == n]
        if cells:
            mx = max([live.get(c, 0) for c in cells] or [0])
            print("IN  %s want=%d dustmax=%d cells=%d" % (
                n, int(bool(vec.get(n, False))), mx, len(cells)), flush=True)


if __name__ == "__main__":
    _main()
