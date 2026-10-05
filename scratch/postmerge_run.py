"""Post-merge routing pass: drive a sum net to the lever row. PROOF OF SHAPE.

The pin mechanism is done and gated, but it cannot reach the bank from inside a
band: `_last_shift` (compose.py:1797) is only known AFTER a band is composed and
centred, so a per-band pin cannot know where the merged bank lands. The fix has
to run where the merged field exists -- after the stitch.

This proves the shape on the real merged add8 field (44,634 blocks, pitch 2):
take S0's existing driver, route a fresh wire from it to a free cell beside the
lever row, lamp that cell, and sim the result. One run is the whole claim; if it
routes and reads, the other eight are the same shape.

NEVER HANGS: single lwire call under the astar cap, no subprocess, no server.
"""
import pickle
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, r'D:\redstone-mini')
sys.path.insert(0, r'D:\redstone-mini\scratch')

import os
os.environ.setdefault("REDSTONE_ASTAR_CAP", "20000")

import compose as C
from tiles import new_ctx, stamp_wire, ring, own
from core import DIRS, TORCH_BACK, base

PICK = sys.argv[1] if len(sys.argv) > 1 else 'S0'
MERGE = r'D:\redstone-mini\scratch\add8merge.pkl'


def main():
    d = pickle.load(open(MERGE, 'rb'))
    blocks = list(d['blocks'])
    solid = dict(d['solid'])
    rings = dict(d['rings'])
    wires = dict(d['wires'])
    junctions = dict(d['junctions'])
    repeaters = dict(d['repeaters'])
    pos = dict(d['pos'])
    sup = dict(d['sup'])
    io = dict(d['io'])

    ctx = new_ctx(blocks, solid, rings, wires, junctions, repeaters, pos,
                  [], sup)

    levers = io['levers']
    xs = sorted({x for x, z in levers})
    zs = sorted({z for x, z in levers})
    print('lever row: x=%s  z=%d..%d (%d levers)' % (xs, zs[0], zs[-1], len(levers)))
    print('sum lamps already in the build: %s' % sorted(
        {n for n in io['lamps'].values() if n.startswith('S')}))

    drv = pos.get(PICK)
    assert drv is not None, 'no driver for %s' % PICK
    print('%s driver at %s' % (PICK, drv))

    # guard: exactly what compose.py:1214-1219 derives from stamped torches
    guard = set()
    for x, y, z, bid in blocks:
        if 'wall_torch' in bid:
            guard.add((x, z))
            face = bid.split('facing=')[1].rstrip(']')
            dx, dz = TORCH_BACK[face]
            guard.add((x + dx, z + dz))

    # target: a free cell one row north of the lever row, lamp just east of it.
    # Scan outward so we take the first genuinely free pair rather than
    # assuming a cell is spare.
    target = None
    for tz in zs:
        for tx in range(xs[-1] + 2, xs[-1] + 14):
            if (tx, tz) in solid or (tx, 1, tz) in wires:
                continue
            lx, lz = tx + 1, tz
            if (lx, lz) in solid or (lx, 1, lz) in wires:
                continue
            if any(wires.get((lx + ax, 1, lz + az)) not in (None, '0')
                   for ax, az in DIRS):
                continue
            target = ((tx, tz), (lx, lz))
            break
        if target:
            break
    assert target, 'no free lamp cell beside the lever row'
    tap, lamp = target
    print('tap %s  lamp %s  (lever row is %.0f blocks north)'
          % (tap, lamp, abs(tap[1] - pos[PICK][1])))

    t0 = time.time()
    cells = C.lwire(ctx, sup, guard, tuple(pos[PICK]), tap, PICK)
    print('lwire -> %s cells in %.1fs' % (len(cells) if cells else 0,
                                          time.time() - t0))
    if not cells:
        print('NO ROUTE: the post-merge pass cannot reach the bank for %s'
              % PICK)
        return

    stamp_wire(ctx, list(cells), PICK)
    ctx.blocks.append((lamp[0], 1, lamp[1], 'minecraft:redstone_lamp'))
    ctx.solid[lamp] = ('lamp', PICK)
    for ddx, ddz in DIRS:
        ring(ctx, lamp[0] + ddx, lamp[1] + ddz, own(PICK))

    # repaint every wire this net owns, then read the NEW lamp in sim
    from sim import _parse_build, _run_vec
    nb = [tuple(b) for b in ctx.blocks]
    nio = dict(io)
    nio['lamps'] = dict(io['lamps'])
    nio['lamps'][(lamp[0], 1, lamp[1])] = PICK
    P = _parse_build(nb, nio)

    lit = dark = 0
    for v in ({}, {'A0': 1}, {'A0': 1, 'B0': 1}, {'A7': 1}):
        vec = {k: v.get(k, 0) for k in {n for _, n in levers.values()}}
        out, live, _, _, _, _ = _run_vec(vec, None, P)
        got = bool(out.get(PICK))
        print('  A-on=%-12s %s lamp=%s' % (','.join(sorted(v)) or '-',
                                         PICK, got))
        lit += got
        dark += not got
    print()
    print('POST-MERGE RUN OK: %s reaches the lever row, %d lit / %d dark over '
          '4 vectors, %d blocks added' % (PICK, lit, dark,
                                          len(ctx.blocks) - len(d['blocks'])))


if __name__ == '__main__':
    main()