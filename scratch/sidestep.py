"""Does the full lwire (candidates+astar+3D) succeed from sidestepped starts?

Usage: python scratch/sidestep.py <band recipe> <net> <ax,az> <bx,bz>
Replays compose up to the failing leg to capture ctx/sup/guard/avoid, then
runs the REAL lwire from a-1, a, a+1, a+2 starts. Bounded: one compose
(capped) + a few lwire calls. Import-safe.
"""
import os
import sys

sys.path.insert(0, r"D:\redstone-mini")


def _main():
    import compose as C
    from recipe import parse_recipe
    path, net = sys.argv[1], sys.argv[2]
    ax, az = [int(v) for v in sys.argv[3].split(",")]
    bx, bz = [int(v) for v in sys.argv[4].split(",")]
    os.environ["REDSTONE_FORCE"] = "1,gates_first,short"
    os.environ["REDSTONE_COMPOSE_SECS"] = "240"
    r = parse_recipe(open(path).read())
    STATE = {}
    _orig = C.lwire

    def patched(ctx, sup, guard, a, b, n, avoid=frozenset()):
        try:
            return _orig(ctx, sup, guard, a, b, n, avoid)
        except RuntimeError:
            if n == net and "ctx" not in STATE:
                STATE.update(ctx=ctx, sup=dict(sup), guard=set(guard),
                             avoid=set(avoid))
            raise

    C.lwire = patched
    try:
        C.compose(r)
        print("compose unexpectedly GREEN", flush=True)
        return
    except RuntimeError as e:
        print("compose died: %s" % " ".join(str(e).split())[:100], flush=True)
    if "ctx" not in STATE:
        print("target leg never attempted", flush=True)
        return
    ctx, sup, guard, avoid = (STATE["ctx"], STATE["sup"], STATE["guard"],
                              STATE["avoid"])
    for dx in (0, -2, -1, 1, 2):
        na = (ax + dx, az)
        # fresh per-try state (lwire mutates ctx on success only, but a
        # failed _walk restores; snapshot anyway for isolation)
        import copy
        c2 = copy.deepcopy(ctx)
        s2 = dict(sup)
        try:
            out = _orig(c2, s2, set(guard), na, (bx, bz), net, set(avoid))
            print("start (%d,%d): WALKS %d cells" % (na[0], na[1], len(out)),
                  flush=True)
        except RuntimeError as e:
            print("start (%d,%d): fails %s" % (
                na[0], na[1], " ".join(str(e).split())[:80]), flush=True)


if __name__ == "__main__":
    _main()
