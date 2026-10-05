"""Two-stage perimeter route: short leg north, long leg west.

Measured facts this is built on:
 - From its OWN driver, S2/S7/COUT fail all 31 bank targets with "no ground".
 - S0 (x=39) alone routes 30/31.
 - In a sequential run, COUT (x=1997) DID reach the bank in 2,049 cells --
   i.e. astar CAN cross the whole field, it just will not start from a congested
   interior driver.

So do not start from the driver. Two short legs instead:
   1. driver -> the free lane at z=LANE (north of the bank, outside the bands)
   2. that lane -> the lamp foot, travelling west along the empty perimeter

Each leg is short and starts in open ground, which is what the direct attempt
never had. If this works it is also the shape that generalises: the stitch
already carries cross-band nets this way.

NEVER HANGS: two lwire calls per net under the astar cap.
"""
import os
import pickle
import sys
import time

sys.path.insert(0, r'D:\redstone-mini')
sys.path.insert(0, r'D:\redstone-mini\scratch')
os.environ.setdefault("REDSTONE_ASTAR_CAP", "30000")

import compose as C
from tiles import new_ctx, stamp_wire
from core import TORCH_BACK

MERGE = r'D:\redstone-mini\scratch\add8merge.pkl'
OUTS = ['S0', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'COUT']
LAMP_X = 6
LAMP_ZS = [3 + 2 * i for i in range(len(OUTS))]


def guard_of(blocks):
    g = set()
    for x, y, z, bid in blocks:
        if 'wall_torch' in bid:
            g.add((x, z))
            dx, dz = TORCH_BACK[bid.split('facing=')[1].rstrip(']')]
            g.add((x + dx, z + dz))
    return g


def main():
    d = pickle.load(open(MERGE, 'rb'))
    ctx = new_ctx(list(d['blocks']), dict(d['solid']), dict(d['rings']),
                  dict(d['wires']), dict(d['junctions']),
                  dict(d['repeaters']), dict(d['pos']), [], dict(d['sup']))
    sup = dict(d['sup'])
    guard = guard_of(ctx.blocks)

    # which northern lanes are actually free?
    for lane in (2, 3, 4, 36, 40):
        free = sum(1 for x in range(6, 1990)
                   if (x, lane) not in ctx.solid
                   and (x, 1, lane) not in ctx.wires)
        print('lane z=%-3d free cells x=6..1990: %4d / 1984' % (lane, free))
    print()

    ok, bad = [], []
    for name, lz in zip(OUTS, LAMP_ZS):
        a = tuple(ctx.pos[name])
        done = False
        for lane in (2, 3, 4, 36, 40):
            if done:
                break
            # leg 1: driver -> the lane, staying near its own x
            for dx in (0, -2, -4, 2, 4):
                hub = (a[0] + dx, lane)
                if (hub[0], hub[1]) in ctx.solid or (hub[0], 1, hub[1]) in ctx.wires:
                    continue
                try:
                    leg1 = C.lwire(ctx, sup, guard, a, hub, name)
                except RuntimeError:
                    continue
                if not leg1:
                    continue
                # leg 2: hub -> the lamp foot, west along the lane
                try:
                    leg2 = C.lwire(ctx, sup, guard, hub, (LAMP_X, lz), name)
                except RuntimeError:
                    continue
                if not leg2:
                    continue
                total = len(leg1) + len(leg2)
                print('  %-5s driver %-11s lane z=%-3d hub %-11s '
                      'leg1 %4d + leg2 %4d = %4d cells'
                      % (name, str(a), lane, str(hub), len(leg1), len(leg2),
                         total), flush=True)
                ok.append((name, hub, total))
                done = True
                break
        if not done:
            print('  %-5s driver %-11s FAILED on every lane'
                  % (name, str(a)), flush=True)
            bad.append(name)

    print()
    print('two-stage perimeter route: %d/%d succeeded  %s'
          % (len(ok), len(OUTS), ('failed: %s' % bad) if bad else ''))


if __name__ == '__main__':
    main()