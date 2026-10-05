"""Is the post-merge "no ground" failure DISTANCE or CONGESTION?

`postmerge_run.py` proved the pin works but hit `no ground for S0` routing the
merged add8 field's S0 driver to the lever row. Two very different bugs hide
behind that message, and they need different fixes:

  - distance   -> the router needs repeaters/boosters over a long run
  - congestion -> the merged field is saturated and there is no corridor

Cheap discriminator: route the same net to targets at increasing distance and
find the radius where it dies. If it dies at 12 blocks it is congestion; if it
dies at 200 it is boosters.

NEVER HANGS: lwire under the astar cap, one call per target, no subprocess.
"""
import os
import pickle
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, r'D:\redstone-mini')
sys.path.insert(0, r'D:\redstone-mini\scratch')
os.environ.setdefault("REDSTONE_ASTAR_CAP", "20000")

import compose as C
from tiles import new_ctx
from core import TORCH_BACK

MERGE = r'D:\redstone-mini\scratch\add8merge.pkl'
NET = 'S0'


def load():
    d = pickle.load(open(MERGE, 'rb'))
    ctx = new_ctx(list(d['blocks']), dict(d['solid']), dict(d['rings']),
                  dict(d['wires']), dict(d['junctions']), dict(d['repeaters']),
                  dict(d['pos']), [], dict(d['sup']))
    guard = set()
    for x, y, z, bid in ctx.blocks:
        if 'wall_torch' in bid:
            guard.add((x, z))
            dx, dz = TORCH_BACK[bid.split('facing=')[1].rstrip(']')]
            guard.add((x + dx, z + dz))
    return d, ctx, guard, dict(d['sup'])


def free(cells, wires, solid):
    return [c for c in cells
            if (c[0], c[1]) not in solid and (c[0], 1, c[1]) not in wires]


def main():
    d, ctx, guard, sup = load()
    wires, solid = ctx.wires, ctx.solid
    a = tuple(ctx.pos[NET])
    print('net %s driver at %s' % (NET, a))

    # walk west along the driver's own row, then north, sampling free targets
    probes = []
    for dx in range(-4, -60, -4):
        probes.append((a[0] + dx, a[1]))
    for dz in range(-4, -60, -4):
        probes.append((a[0], a[1] + dz))

    last_ok = 0
    for t in probes:
        t = tuple(t)
        if not free([t], wires, solid):
            continue
        dist = abs(t[0] - a[0]) + abs(t[1] - a[1])
        t0 = time.time()
        try:
            cells = C.lwire(ctx, sup, guard, a, t, NET)
            n = len(cells) if cells else 0
            print('  target %-12s dist %3d  OK  %4d cells  %.1fs'
                  % (str(t), dist, n, time.time() - t0), flush=True)
            last_ok = dist
        except RuntimeError as e:
            print('  target %-12s dist %3d  DEAD: %s'
                  % (str(t), dist, str(e)[:60]), flush=True)
            print()
            print('VERDICT: %s routes %d blocks in this merged field and dies '
                  'beyond -> CONGESTION, not distance.' % (NET, last_ok))
            print('A distance problem wants boosters; a congestion problem '
                  'wants free corridors or the bank streets the stitch '
                  'already uses.')
            return
    print()
    print('VERDICT: %s reached every probe; the bank cell specifically is the '
          'problem, not the router.' % NET)


if __name__ == '__main__':
    main()