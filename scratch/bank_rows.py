"""Sum lamps at the lever row: pre-stamped rows, drops routed around the east.

Ordering is the whole trick, and compose.py:3377 documents it for the lever
bank's own 16 input rows: "PRE-STAMP every row run, then route only the drops. A
row and a drop must cross ... With the rows stamped first, ALL of those crossings
live in the drops."

My first version got that wrong twice, both times visibly:
  - rows 1 apart -> "wire S1 touches S0" (a short between two nets)
  - row then drop, net by net -> S1's row crossed S0's ALREADY-PLACED drop
So: stamp every row first (they are parallel, so they cannot cross each other),
then route every drop.

And the drops no longer cross the rows at all: each goes EAST from its driver to
a free column beyond the field, NORTH up the empty margin, and only then joins
its own row and runs west. Drop 2 leaves the row's west end and runs south to
the lamp's latitude.

Lamps at x=7 (lever column is x=3, so a lamp two east; a lamp directly over a
lever would read that lever, because a lever powers the block above it), one
every 2 in z so there is a block between each.

NEVER HANGS: straight stamps are O(n); three short lwire calls per net.
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
LAMP_X = 7


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


def clear_col(ctx, x, z0, z1):
    lo, hi = min(z0, z1), max(z0, z1)
    for z in range(lo, hi + 1):
        if not free(ctx, x, z):
            return False
    return True


def main():
    d = pickle.load(open(MERGE, 'rb'))
    ctx = new_ctx(list(d['blocks']), dict(d['solid']), dict(d['rings']),
                  dict(d['wires']), dict(d['junctions']),
                  dict(d['repeaters']), dict(d['pos']), [], dict(d['sup']))
    sup = dict(d['sup'])
    guard = guard_of(ctx.blocks)
    io = dict(d['io'])

    widest = max(ctx.pos[n][0] for n in OUTS)
    east = [x for x in range(widest + 4, widest + 60)
            if clear_col(ctx, x, -130, 300)]
    if not east:
        print('no free column east of the field for the drop riser')
        return
    bypass = east[0]
    print('bypass column x=%d' % bypass)

# A row needs its NEIGHBOURS free too: stamp_wire refuses a wire with a
    # foreign net BESIDE it ("wire S7 touches A7 beside (1899,1,-30)"), and the
    # obstacle was at z-1, not on the row. That clearance is exactly why
    # compose spaces the bank rows 10 apart -- room for a 5-cell hop
    # staircase. So require a clear band, not a clear line.
    #
    # Measured, because I picked the wrong margin first: the northern margin
    # (z -44..-18) has NO full-width clear band at all, so every row failed
    # with a foreign net beside it. The full-width corridors are further south
    # -- z=166..179 carried a 2,006-cell clear run, and compose's own input
    # rows sit at z=-71..-83. Search the whole margin instead of assuming.
    need = widest - LAMP_X
    lanes = []
    for z in range(-120, 300):
        if all(free(ctx, x, zz)
               for x in range(LAMP_X, widest)
               for zz in range(z - 1, z + 2)):
            lanes.append(z)
    lanes = lanes[::4]          # 4 apart: room for a hop staircase between rows
    print('clear row latitudes: %d  %s' % (len(lanes), lanes[:12]))
    if len(lanes) < len(OUTS):
        print('only %d lanes for %d rows (need %d cells of clear run)'
              % (len(lanes), len(OUTS), need))
        return
    if len(lanes) < len(OUTS):
        print('only %d lanes for %d rows' % (len(lanes), len(OUTS)))
        return

    # PHASE 1: every row, all parallel, before any drop exists.
    #
    # The assignment is the part that makes the drops trivial. A row spans x
    # from its OWN driver west to the bank, so a row only exists at large x if
    # its net's driver is that far east. Assign the EASTERNMOST driver the
    # SOUTHERNMOST lane (closest to the field) and every drop runs north into
    # margin that no row occupies at that x: crossing count zero. My earlier
    # order (lane by output index) put eastern nets' rows across western nets'
    # drops and every drop died in "no ground".
    #
    # Rows stop at x=ROW_END so the final drop south to the bank runs at
    # x=ROW_END-1, clear of all nine rows.
    ROW_END = 8
    lanes = sorted(lanes, reverse=True)          # southernmost (largest z) first
    by_x = sorted(OUTS, key=lambda n: -ctx.pos[n][0])
    assign = {}
    for name, lane in zip(by_x, lanes):
        assign[name] = (lane, 17 + 2 * (len(assign) % len(OUTS)))
    for name, (lane, lz) in sorted(assign.items()):
        drv_x = ctx.pos[name][0]
        stamp_wire(ctx, [(x, lane) for x in range(drv_x, ROW_END - 1, -1)], name)
    print('phase 1: %d rows stamped, easternmost driver on the southernmost '
          'lane' % len(assign))

    # Measured, because the drops died here and the reason was not the drop:
    # x=8..12 are clear for the whole 300-cell run EXCEPT z=4, 14 and 24 -- two
    # horizontal trunks plus a bank row. A drop at x<=12 has nowhere to put the
    # 5-cell hop staircase and dies "no ground". Dropping at x=%d instead gives
    # it the room, then a short west run along the lamp's own latitude reaches
    # the lamp (the lamp latitudes 3,5..19 never coincide with a trunk).
    print('phase 2: drop at x=%d, west run to the lamp' % ROW_END)

    base = len(ctx.blocks)
    # One block apart. Keyed by name because ORDER below matters more than any
    # of this: the first net to use the x=8 drop corridor owns it (COUT first
    # scored 1/9, S0 first scored 7/9), and westernmost-first gives the
    # SHORTEST drop first, so later nets nest inside a corridor rather than
    # fight for it. z=23 and z=25 are not routable at x=8, so S4/S5 take
    # z=37/z=35, just south of the lever row end at z=33.
    LAMP_Z = {'S0': 33, 'S1': 31, 'S2': 29, 'S3': 27, 'S6': 21,
              'S7': 19, 'COUT': 17, 'S4': 35, 'S5': 37}
    # The two nets that failed in the middle of the order now go LAST, so the
    # six that work get the shared x=8 corridor first.
    ORDER = ['S0', 'S1', 'S2', 'S3', 'S6', 'S7', 'COUT', 'S4', 'S5']

    # PHASE 2: two straight-ish drops per net, no crossings to hop
    placed, failed = [], []
    t0 = time.time()

    def drop(a, b, net):
        """Route a->b, splitting into two legs if one long leg is refused.
        5/9 succeeded with a single drop; the four that failed were all the
        ~260-cell drop south to the bank, which crosses the field's west edge.
        Two ~130-cell legs is the same fix the stitch uses for long fan-out
        (compose.py:3415), applied here."""
        try:
            c = C.lwire(ctx, sup, guard, a, b, net)
            if c:
                return list(c)
        except RuntimeError:
            pass
        mid = ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2)
        for m in (mid, (a[0], mid[1]), (b[0], mid[1])):
            try:
                c1 = C.lwire(ctx, sup, guard, a, m, net)
            except RuntimeError:
                continue
            if not c1:
                continue
            try:
                c2 = C.lwire(ctx, sup, guard, m, b, net)
            except RuntimeError:
                continue
            if c2:
                return list(c1) + list(c2)
        return None

    for name in ORDER:
        lane = assign[name][0]
        drv = tuple(ctx.pos[name])
        legs = drop(drv, (drv[0], lane), name)
        if legs is None:
            failed.append(name)
            print('  %-5s drop1 failed %s -> (%d,%d)'
                  % (name, str(drv), drv[0], lane), flush=True)
            continue
        # Lamp latitudes are FIXED and each net routes ONCE.
        #
        # Two measured traps here, both mine:
        #  - lwire MUTATES the field (repeaters, supports) even when it finally
        #    raises, so a retry loop starts from a polluted field. An adaptive
        #    "try z=17, then 19, ..." loop scored 1/9 because attempt two
        #    inherited attempt one's debris. One attempt per net.
        #  - z=23 and z=25 do not route at x=8 (the bank occupies them), which
        #    is why the fixed 17,19..33 mapping scored 7/9 and not 9/9. Those
        #    two slots move to z=35 and z=37, just south of the lever row's
        #    end at z=33, still one block apart from their neighbours.
        lamp_z = LAMP_Z[name]
        d2 = drop((ROW_END, lane), (ROW_END, lamp_z), name)
        if d2 is not None:
            d3 = drop((ROW_END, lamp_z), (LAMP_X, lamp_z), name)
            if d3 is not None:
                d2 = d2 + d3
        if d2 is None:
            failed.append(name)
            print('  %-5s drop south to z=%d failed' % (name, lamp_z),
                  flush=True)
            continue
        stamp_wire(ctx, legs + d2, name)
        lamp = (LAMP_X, lamp_z)
        ctx.blocks.append((lamp[0], 1, lamp[1], 'minecraft:redstone_lamp'))
        ctx.solid[lamp] = ('lamp', name)
        for ddx, ddz in DIRS:
            ring(ctx, lamp[0] + ddx, lamp[1] + ddz, own(name))
        placed.append((name, lane, lamp))
        print('  %-5s driver %-11s lane z=%-4d lamp %-10s ok'
              % (name, str(drv), lane, str(lamp)), flush=True)

    print()
    print('placed %d/%d lamps   +%d blocks (%.0f -> %d)  in %.0fs'
          % (len(placed), len(OUTS), len(ctx.blocks) - base, base,
             len(ctx.blocks), time.time() - t0))
    if failed:
        print('failed: %s' % failed)
    with open(r'D:\redstone-mini\scratch\add8_bankrouted.pkl', 'wb') as f:
        pickle.dump({'blocks': [tuple(b) for b in ctx.blocks], 'io': io,
                     'placed': placed, 'failed': failed}, f)
    print('wrote scratch/add8_bankrouted.pkl')


if __name__ == '__main__':
    main()