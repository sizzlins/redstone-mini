"""Is astar wasting expansions BEYOND the optimal path's f? (decides prunes)

Wraps layout.astar and heapq to record, per search: pops, the f of the goal
pop (the optimal cost it settled for), and the max f it ever pushed. If
max_f >> goal_f, a bound prune is free money; if they match, the field is
maze-inherent and IDWL/pruning would only add passes.

Bounded: one compose of a band recipe under the caller's own time budget.
Usage: python scratch/astar_waste.py [recipe.txt] [secs]
"""
import heapq as _hq
import os
import sys
import time

ROOT = os.environ.get("RS_ROOT", r"D:\redstone-mini")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scratch"))
os.environ.pop("REDSTONE_SIM_GATE", None)


def main():
    recipe = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(ROOT, "scratch", "cand_alu4hierb1.txt")
    budget = float(sys.argv[2]) if len(sys.argv) > 2 else 120.0
    import faulthandler
    faulthandler.dump_traceback_later(budget + 30, exit=True)
    import layout
    import compose
    from recipe import parse_recipe

    real_astar = layout.astar
    stats = []

    def astar_spy(*a, **k):
        cur = {"push": [], "pop": [], "goal_f": None,
               "env": (a[18] if len(a) > 18 else None, a[19] if len(a) > 19 else None, a[16] if len(a) > 16 else None),
               "goal": a[1] if len(a) > 1 else k.get("goal")}
        stats.append(cur)
        old_push, old_pop = _hq.heappush, _hq.heappop

        def push(heap, item, *aa, **kk):
            cur["push"].append(item[0])
            return old_push(heap, item, *aa, **kk)

        def pop(heap, *aa, **kk):
            item = old_pop(heap, *aa, **kk)
            cur["pop"].append(item[0])
            return item

        _hq.heappush, _hq.heappop = push, pop
        try:
            out = real_astar(*a, **k)
        finally:
            _hq.heappush, _hq.heappop = old_push, old_pop
        # the goal pop is the LAST pop of a successful search (astar returns
        # immediately on it)
        if out and cur["pop"]:
            cur["goal_f"] = cur["pop"][-1]
        return out

    layout.astar = astar_spy
    compose.astar = astar_spy
    t0 = time.monotonic()
    try:
        blocks, size, io = compose.compose(parse_recipe(open(recipe).read()))
        print("compose ok: %d blocks %s in %.1fs"
              % (len(blocks), size, time.monotonic() - t0), flush=True)
    except Exception as e:
        print("compose ended: %s: %s"
              % (type(e).__name__, str(e)[:90]), flush=True)
    tot_pop = tot_waste = 0
    for i, c in enumerate(stats):
        gf = c["goal_f"]
        mx = max(c["push"]) if c["push"] else 0
        pops = len(c["pop"])
        waste = (len([f for f in c["pop"] if gf is not None and f > gf])
                 if gf is not None else 0)
        tot_pop += pops
        tot_waste += waste
        print("  astar[%d] pops=%-6d goal_f=%-8s max_push_f=%-8d "
              "pops_above_goal=%-4d env=%s" % (i, pops, gf, mx, waste, c["env"]), flush=True)
    print("TOTAL pops=%d above-goal=%d (%.1f%% prunable)"
          % (tot_pop, tot_waste,
             100.0 * tot_waste / tot_pop if tot_pop else 0.0), flush=True)


if __name__ == "__main__":
    main()
