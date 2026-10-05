"""Route all nine sum nets to lamps at the lever row. The original request.

Feasibility is already measured, not hoped for: on the real merged pitch-2 add8
field, `lwire` from S0's driver reaches bank cells (13,28) in 32 cells and
(13,10) in 48. Other bank cells fail for *target-local* reasons (a solid pair at
x=36-37 on z=30..32; the merge's own `bridge support lands on wire` limit near
z=3..5). So the implementation is a candidate sweep: for each sum net try bank
cells nearest-the-levers-first and take the first that routes.

Earlier claims this was impossible, and why they were wrong:
- "the driver is sealed by its own ring" -- FALSIFIED. S0 owns 0 ring cells, and
  the driver routes 24 blocks north, 16 south, 8 east. My first probe only ran
  west into a solid wall and I read that as a seal.
- "shift is only known after compose, so a pin cannot work" -- true for a
  per-band pin, irrelevant here: this runs post-merge on the real ctx.

NEVER HANGS: bounded candidate list, one lwire call each under the astar cap.
"""
import os
import pickle
import sys
import time

sys.path.insert(0, r'D:\redstone-mini')
sys.path.insert(0, r'D:\redstone-mini\scratch')
os.environ.setdefault("REDSTONE_ASTAR_CAP", "20000")

import compose as C
from tiles import new_ctx, stamp_wire, ring, own
from core import DIRS, TORCH_BACK

MERGE = r'D:\redstone-mini\scratch\add8merge.pkl'
OUTS = ['S0', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'COUT']


def main():
    d = pickle.load(open(MERGE, 'rb'))
    ctx = new_ctx(list(d['blocks']), dict(d['solid']), dict(d['rings']),
                  dict(d['wires']), dict(d['junctions']),
                  dict(d['repeaters']), dict(d['pos']), [], dict(d['sup']))
    sup = dict(d['sup'])
    guard = set()
    for x, y, z, bid in ctx.blocks:
        if 'wall_torch' in bid:
            guard.add((x, z))
            dx, dz = TORCH_BACK[bid.split('facing=')[1].rstrip(']')]
            guard.add((x + dx, z + dz))
    io = dict(d['io'])
    levers = io['levers']
    bank_x = max(x for x, z in levers)
    bank_zs = sorted({z for x, z in levers})
    print('bank: levers x=%d, z=%d..%d' % (bank_x, bank_zs[0], bank_zs[-1]))

    # one lamp row per sum bit, spread down the bank; candidates run from
    # nearest-the-levers outward because that is what the user asked to look at
    plan = []
    for i, name in enumerate(OUTS):
        z = bank_zs[min(i * 2, len(bank_zs) - 1)]
        cands = [(bank_x + dx, z) for dx in (2, 4, 6, 8, 10, 12)]
        plan.append((name, cands))

    base_blocks = len(ctx.blocks)
    routed, failed = [], []
    t_start = time.time()
    for name, cands in plan:
        if name not in ctx.pos:
            failed.append((name, 'no driver'))
            continue
        a = tuple(ctx.pos[name])
        done = None
        for tap in cands:
            lamp = (tap[0] + 1, tap[1])
            if (tap[0], tap[1]) in ctx.solid or (tap[0], 1, tap[1]) in ctx.wires:
                continue
            if (lamp[0], lamp[1]) in ctx.solid or (lamp[0], 1, lamp[1]) in ctx.wires:
                continue
            try:
                cells = C.lwire(ctx, sup, guard, a, tap, name)
            except RuntimeError:
                continue
            if not cells:
                continue
            stamp_wire(ctx, list(cells), name)
            ctx.blocks.append((lamp[0], 1, lamp[1], 'minecraft:redstone_lamp'))
            ctx.solid[lamp] = ('lamp', name)
            for ddx, ddz in DIRS:
                ring(ctx, lamp[0] + ddx, lamp[1] + ddz, own(name))
            done = (tap, lamp, len(cells))
            break
        if done:
            routed.append(name)
            print('  %-5s -> tap %-9s lamp %-9s %3d cells' %
                  ((name,) + done[:2] + (done[2],)), flush=True)
        else:
            failed.append((name, 'no candidate routed'))
            print('  %-5s -> NO ROUTE from %s over %d candidates'
                  % (name, a, len(cands)), flush=True)

    print()
    print('routed %d/%d sum nets to the lever row in %.1fs, +%d blocks'
          % (len(routed), len(OUTS), time.time() - t_start,
             len(ctx.blocks) - base_blocks))
    if failed:
        print('failed: %s' % failed)

    with open(r'D:\redstone-mini\scratch\add8_banklamps.pkl', 'wb') as f:
        pickle.dump({'blocks': [tuple(b) for b in ctx.blocks],
                     'io': io, 'routed': routed, 'failed': failed}, f)
    print('wrote scratch/add8_banklamps.pkl')


if __name__ == '__main__':
    main()