"""Route all nine sum nets to lamps at the lever row, by chained stages.

Measurement trail, because each version was wrong in an instructive way:
  direct from the driver -> S0/S1 only; S2..S7, COUT "no ground" on all 31
    bank targets.
  perimeter (driver -> free lane, then west) -> S2, in a 529-cell west leg.
  So the ceiling is LEG LENGTH (~500), not the field being 2,000 wide.
  three stages -> S3 (38 + 319 + 502) and S4 (4 legs, 1,105 cells).

Two bugs of mine that hid the working shape, both fixed here:
  - a FAILED chain used to keep its legs stamped, so the next net inherited a
    field full of another net's half-built run (this is why S2/S3 regressed to
    FAILED once chaining existed). Nothing is stamped until the whole chain
    succeeds.
  - a SUCCESSFUL chain stamped every leg twice.

Chaining is legitimate, not a hack: a repeater's output is strong power, so
each stage's last repeater is a genuine driver for the next leg.

NEVER HANGS: bounded stages, capped astar, global deadline.
"""
import os
import pickle
import sys
import time

sys.path.insert(0, r'D:\redstone-mini')
sys.path.insert(0, r'D:\redstone-mini\scratch')
os.environ.setdefault("REDSTONE_ASTAR_CAP", "30000")

import compose as C
from tiles import new_ctx, stamp_wire, ring, own
from core import DIRS, TORCH_BACK

MERGE = r'D:\redstone-mini\scratch\add8merge.pkl'
OUTS = ['S0', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'COUT']
LAMP_X = 6
LANES = (2, 3, 36, 40)
MAX_STAGES = 8
DEADLINE = time.time() + 2400


def guard_of(blocks):
    g = set()
    for x, y, z, bid in blocks:
        if 'wall_torch' in bid:
            g.add((x, z))
            dx, dz = TORCH_BACK[bid.split('facing=')[1].rstrip(']')]
            g.add((x + dx, z + dz))
    return g


def free(ctx, x, z, y=1):
    return (x, z) not in ctx.solid and (x, y, z) not in ctx.wires \
        and (x, y, z) not in ctx.repeaters


def att(ctx, sup, guard, src, dst, net):
    if dst[0] < LAMP_X:
        return None
    try:
        cells = C.lwire(ctx, sup, guard, src, dst, net)
    except RuntimeError:
        return None
    return cells or None


def zlist(want, used):
    out = []
    for z in [want] + [q for q in range(3, 34) if q != want]:
        if z not in used and free_marker(z):
            out.append(z)
    return out


_used_ctx = None


def free_marker(z):
    return free(_used_ctx, LAMP_X, z)


def route(net, driver, want_z, used_z):
    """Return (legs, lamp_z, how). Stamps ONLY on success. legs = list of cell lists."""
    global _used_ctx
    _used_ctx = ctx
    sup, guard = SUP, GUARD

    # 1) direct -- near nets finish in one leg
    for z in zlist(want_z, used_z)[:6]:
        c = att(ctx, sup, guard, driver, (LAMP_X, z), net)
        if c:
            return [c], z, 'direct'

    # 2) chained along a lane
    for lane in LANES:
        for dx in (0, -2, 2, -4, 4):
            start = (driver[0] + dx, lane)
            if start[0] < LAMP_X or not free(ctx, *start):
                continue
            legs, cur = [], start
            for _ in range(MAX_STAGES):
                zs = zlist(want_z, used_z)
                if not zs:
                    break
                done = False
                # if the foot is inside one leg's reach, land on it
                for z in zs[:6]:
                    c = att(ctx, sup, guard, cur, (LAMP_X, z), net)
                    if c:
                        legs.append(c)
                        return legs, z, 'chain lane z=%d, %d legs' % (lane,
                                                                      len(legs))
                hop = None
                for step in (LAMP_X + 520, LAMP_X + 300, LAMP_X + 180,
                             LAMP_X + 90):
                    cand = (max(LAMP_X, cur[0] - step), lane)
                    if cand == cur or not free(ctx, *cand):
                        continue
                    c = att(ctx, sup, guard, cur, cand, net)
                    if c:
                        hop, cur = c, cand
                        break
                if not hop:
                    break
                legs.append(hop)
            # chain exhausted with nothing to land on: throw it away UNSTAMPED
    return None, None, None


def main():
    global ctx, SUP, GUARD
    d = pickle.load(open(MERGE, 'rb'))
    ctx = new_ctx(list(d['blocks']), dict(d['solid']), dict(d['rings']),
                  dict(d['wires']), dict(d['junctions']),
                  dict(d['repeaters']), dict(d['pos']), [], dict(d['sup']))
    SUP, GUARD = dict(d['sup']), guard_of(ctx.blocks)
    io = dict(d['io'])

    want = {n: 3 + 2 * i for i, n in enumerate(OUTS)}
    used_z, placed, failed = set(), [], []
    base = len(ctx.blocks)
    t0 = time.time()

    for name in OUTS:
        if time.time() > DEADLINE:
            failed += [n for n in OUTS if n not in [p[0] for p in placed]]
            print('DEADLINE reached', flush=True)
            break
        a = tuple(ctx.pos[name])
        legs, z, how = route(name, a, want[name], used_z)
        if not legs:
            failed.append(name)
            print('  %-5s driver x=%-5d  FAILED' % (name, a[0]), flush=True)
            continue
        for lg in legs:                       # stamp exactly once, on success
            stamp_wire(ctx, list(lg), name)
        lamp = (LAMP_X + 1, z)
        ctx.blocks.append((lamp[0], 1, lamp[1], 'minecraft:redstone_lamp'))
        ctx.solid[lamp] = ('lamp', name)
        for ddx, ddz in DIRS:
            ring(ctx, lamp[0] + ddx, lamp[1] + ddz, own(name))
        used_z.add(z)
        total = sum(len(l) for l in legs)
        placed.append((name, how, z, total))
        print('  %-5s driver x=%-5d  %-24s %4d cells  lamp %s'
              % (name, a[0], how, total, str(lamp)), flush=True)

    print()
    print('routed %d/%d   +%d blocks (%.0f -> %d)  in %.0fs'
          % (len(placed), len(OUTS), len(ctx.blocks) - base, base,
             len(ctx.blocks), time.time() - t0))
    if failed:
        print('failed: %s' % failed)
    with open(r'D:\redstone-mini\scratch\add8_bankrouted.pkl', 'wb') as f:
        pickle.dump({'blocks': [tuple(b) for b in ctx.blocks], 'io': io,
                     'placed': placed, 'failed': failed,
                     'lamp_x': LAMP_X}, f)
    print('wrote scratch/add8_bankrouted.pkl')


if __name__ == '__main__':
    main()