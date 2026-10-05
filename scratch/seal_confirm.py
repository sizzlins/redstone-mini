"""Confirm the seal: clear S0's own ring near its driver, retry the route.

`noground_why.py` says the merged-field failure is the net's own 3x3 ring
walling the driver in. That is a claim about a cause, so it deserves a test that
can come out wrong: remove ONLY S0's ring cells around its driver and re-run the
same `lwire`. If the route now succeeds, the seal was the cause and reserving a
street at compose time is the right fix. If it still fails, the diagnosis is
wrong and something else is sealing the driver.

This is a MEASUREMENT on a throwaway copy of the merged field -- nothing here is
committed as build output.

NEVER HANGS: one lwire call per attempt under the astar cap.
"""
import os
import pickle
import sys
import time

sys.path.insert(0, r'D:\redstone-mini')
sys.path.insert(0, r'D:\redstone-mini\scratch')
os.environ.setdefault("REDSTONE_ASTAR_CAP", "20000")

import compose as C
from tiles import new_ctx
from core import TORCH_BACK

MERGE = r'D:\redstone-mini\scratch\add8merge.pkl'
NET = 'S0'
RADIUS = 6


def build_ctx(d):
    return new_ctx(list(d['blocks']), dict(d['solid']), dict(d['rings']),
                   dict(d['wires']), dict(d['junctions']),
                   dict(d['repeaters']), dict(d['pos']), [], dict(d['sup']))


def guard_of(ctx):
    g = set()
    for x, y, z, bid in ctx.blocks:
        if 'wall_torch' in bid:
            g.add((x, z))
            dx, dz = TORCH_BACK[bid.split('facing=')[1].rstrip(']')]
            g.add((x + dx, z + dz))
    return g


def try_route(d, label, clear_ring=False):
    ctx = build_ctx(d)
    guard = guard_of(ctx)
    sup = dict(d['sup'])
    a = tuple(ctx.pos[NET])
    if clear_ring:
        # drop S0's own ring cells within RADIUS of the driver, and the ring
        # BLOCKS too, so the wall is genuinely gone for the test
        killed_ring = killed_blk = 0
        for key in [k for k, v in ctx.rings.items()
                    if v == NET and abs(k[0] - a[0]) <= RADIUS
                    and abs(k[1] - a[1]) <= RADIUS]:
            del ctx.rings[key]
            killed_ring += 1
        keep = set(ctx.rings)
        before = len(ctx.blocks)
        ctx.blocks[:] = [b for b in ctx.blocks
                         if not (b[3] == 'minecraft:cobblestone'
                                 and (b[0], b[2]) not in keep
                                 and any((b[0] + ax, b[2] + az) in keep
                                         for ax, az in ((1, 0), (-1, 0),
                                                         (0, 1), (0, -1))))]
        killed_blk = before - len(ctx.blocks)
        print('%s: cleared %d ring cells, %d cobble blocks near %s'
              % (label, killed_ring, killed_blk, a))
    t0 = time.time()
    try:
        cells = C.lwire(ctx, sup, guard, a, (13, 3), NET)
        print('%s: ROUTE OK, %d cells in %.1fs' % (label, len(cells),
                                                   time.time() - t0))
        return True
    except RuntimeError as e:
        print('%s: DEAD (%s)' % (label, str(e)[:70]))
        return False


def main():
    d = pickle.load(open(MERGE, 'rb'))
    print('rings entries owned by %s: %d'
          % (NET, sum(1 for v in d['rings'].values() if v == NET)))
    before = try_route(d, 'baseline (ring intact)  ')
    after = try_route(d, 'ring cleared            ', clear_ring=True)
    print()
    if before and not after:
        print('UNEXPECTED: clearing the ring made it worse')
    elif after and not before:
        print('CONFIRMED: the own-ring was the blocker. Reserving a street at '
              'compose time is the fix.')
    else:
        print('DIAGNOSIS WRONG: the ring is not the blocker '
              '(before=%s after=%s)' % (before, after))


if __name__ == '__main__':
    main()