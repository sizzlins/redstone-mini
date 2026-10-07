"""Sum lamps at the lever row: pre-stamped rows, drops down the west margin.

Former geometry (rows south, drops at x=8, lamps at x=6/7) died three ways,
each measured: the merge dump mixes BLOCK-space blocks with MERGE-space
tables (shift=(8,104) -- rehydrate in one frame); stamp_wire fills dicts
only, so the dump shipped zero new wires/repeaters; and all nine drop legs
shared one column, each crossing every earlier net's tap.

Current geometry, crossing-free by construction (all coordinates MERGE
frame; levers live at x=-5, z=-101..-71):
  - 9 lamps in the empty west margin at x=-8, z=-99..-83 (pitch 2, alongside
    the levers, 3+ cells from any lever/indicator/stub);
  - taps at x=-9 (west of the lamp: the stub arrives from the west, so the
    lamp is never on the path; the run end aims along its axis at the lamp);
  - one drop column per net at x=-28..-12 (stitch's one-column-per-net rule);
    eastern-first order + eastern->southern lanes + eastern->ascending lamps
    means no drop crosses an existing row/column/stub (proved in LOG).
  - rows pre-stamped full driver->column in clear southern bands (9/9), drops
    routed column->lamp, stubs column->tap, boosters planted on the whole
    path (lwire plants none: a 2000-cell row arrives dark without them).
"""

MERGE = r'D:\redstone-mini\scratch\add8merge.pkl'
OUTS = ['S0', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'COUT']
LAMP_X = -8
TAP_X = -9
# eastern driver -> western column (existing columns stay west of every new
# stub), eastern -> southern lane, eastern -> ascending lamp.
ORDER = ['COUT', 'S7', 'S6', 'S5', 'S4', 'S3', 'S2', 'S1', 'S0']
COL = {'COUT': -28, 'S7': -26, 'S6': -24, 'S5': -22, 'S4': -20,
       'S3': -18, 'S2': -16, 'S1': -14, 'S0': -12}
LAMP_Z = {'COUT': -99, 'S7': -97, 'S6': -95, 'S5': -93, 'S4': -91,
          'S3': -89, 'S2': -87, 'S1': -85, 'S0': -83}
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
    # ponytail: the dump carries tables in MERGE space but blocks/io in BLOCK
    # space (shift=(8,104) here). Rehydrating across frames routes on phantom
    # ground and stamps onto live nets -- the recorded "7/9 routed but
    # DUAL-ENGINE FAIL + indicators wrong" was this frame mix, not the
    # corridor (wires/blocks overlap was 551/19088). Work in merge frame
    # throughout; shift back only at the dump.
    try:
        _dx, _dz = d['shift']
    except KeyError:
        raise RuntimeError('merge pkl carries no shift; refusing to mix frames')
    ctx = new_ctx([(x - _dx, y, z - _dz, bid) for (x, y, z, bid) in d['blocks']],
                  dict(d['solid']), dict(d['rings']),
                  dict(d['wires']), dict(d['junctions']),
                  dict(d['repeaters']), dict(d['pos']), [], dict(d['sup']))
    _bcells = set((x, y, z) for (x, y, z, _b) in ctx.blocks)
    _overlap = sum(1 for c in ctx.wires if c in _bcells)
    print('frame check: %d/%d wire cells in blocks' % (_overlap, len(ctx.wires)))
    if _overlap < 0.9 * len(ctx.wires):
        raise RuntimeError('blocks/tables frame mismatch (overlap %d/%d)'
                           % (_overlap, len(ctx.wires)))
    _w0 = set(d['wires'])          # pre-existing wire cells (merge frame)
    _r0 = set(d['repeaters'])      # pre-existing repeater cells (merge frame)
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

    # PHASE 1: every row, all parallel, before any drop exists. Rows run in
    # clear southern bands from each driver west to that net's OWN drop
    # column (staggered ends: no drop column pierces another net's row).
    lanes = sorted(lanes, reverse=True)          # southernmost (largest z) first
    by_x = sorted(OUTS, key=lambda n: -ctx.pos[n][0])
    assign = {}
    for name, lane in zip(by_x, lanes):
        assign[name] = lane
    rowcells = {}
    for name in ORDER:
        lane = assign[name]
        drv_x = ctx.pos[name][0]
        cells = [(x, lane) for x in range(drv_x, COL[name] - 1, -1)]
        stamp_wire(ctx, cells, name)
        rowcells[name] = cells
    print('phase 1: %d rows stamped, easternmost driver on the southernmost '
          'lane' % len(assign))

    print('phase 2: drops down the empty west margin to the lamp platform')
    base = len(ctx.blocks)

    # PHASE 2: two straight-ish drops per net, no crossings to hop
    placed, failed = [], []
    t0 = time.time()

    # ponytail: reserve every lamp cell BEFORE any route runs, for no net.
    # lwire legs wander (measured tails: S1 approached its tap from x=4),
    # and an unreserved lamp site gets stomped by an earlier net's detour --
    # exactly how S4/S5's (6,35)/(6,37) died. A foreign-owned ring makes any
    # stamp there raise instead of silently occupying the lamp's cell. Taps
    # are reserved for their own net (a route must still end there).
    _LAMPS = {}
    for _name in ORDER:
        _lz = LAMP_Z[_name]
        _tap = (TAP_X, _lz)
        _lamp = (LAMP_X, _lz)
        _LAMPS[_name] = (_tap, _lamp)
        ctx.rings.setdefault(_lamp, set()).add('bankrsv')
        ctx.rings.setdefault(_tap, set()).add(_name)

    def drop(a, b, net):
        """Route a->b, splitting into two legs if one long leg is refused.
        5/9 succeeded with a single drop; the four that failed were all the
        ~260-cell drop south to the bank, which crosses the field's west edge.
        Two ~130-cell legs is the same fix the stitch uses for long fan-out
        (compose.py:3415), applied here."""
        errs = []
        try:
            c = C.lwire(ctx, sup, guard, a, b, net)
            if c:
                return list(c)
        except RuntimeError as e:
            errs.append('%s->%s: %s' % (a, b, str(e)[:100]))
        mid = ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2)
        for m in (mid, (a[0], mid[1]), (b[0], mid[1])):
            try:
                c1 = C.lwire(ctx, sup, guard, a, m, net)
            except RuntimeError as e:
                errs.append('%s->%s: %s' % (a, m, str(e)[:100]))
                continue
            if not c1:
                continue
            try:
                c2 = C.lwire(ctx, sup, guard, m, b, net)
            except RuntimeError as e:
                errs.append('%s->%s: %s' % (m, b, str(e)[:100]))
                continue
            if c2:
                return list(c1) + list(c2)
        print('  %-5s no route %s; first errors: %s'
              % (net, (a, b), ' | '.join(errs[:2])), flush=True)
        return None

    for name in ORDER:
        lane = assign[name]
        col = COL[name]
        lamp_z = LAMP_Z[name]
        # ponytail: the tap is the lamp's WEST neighbour: the stub arrives
        # from the west (own column), so the lamp is never on the path. The
        # run end aims along its own axis both ways, lighting the lamp east.
        tap, lamp = _LAMPS[name]
        if lamp in ctx.solid or (lamp[0], 1, lamp[1]) in ctx.wires:
            failed.append(name)
            print('  %-5s lamp cell %s occupied' % (name, lamp), flush=True)
            continue
        # Lamp latitudes are FIXED and each net routes ONCE: lwire MUTATES
        # the field (repeaters, supports) even when it finally raises, so a
        # retry loop starts from debris. One attempt per net.
        # ponytail: the riser driver->lane is routed (not pre-stamped): it
        # crosses the sum field and needs the maze. The row/drop/stub chain
        # hangs off its actual end.
        drv = tuple(ctx.pos[name])
        legs0 = drop(drv, (drv[0], lane), name)
        if legs0 is None:
            failed.append(name)
            print('  %-5s riser failed %s -> (%d,%d)'
                  % (name, str(drv), drv[0], lane), flush=True)
            continue
        d2 = drop((col, lane), (col, lamp_z), name)
        if d2 is not None:
            d3 = drop((col, lamp_z), tap, name)
            if d3 is not None:
                d2 = d2 + d3
        if d2 is None:
            failed.append(name)
            print('  %-5s drop south to z=%d failed' % (name, lamp_z),
                  flush=True)
            continue
        legs = legs0 + rowcells[name]
        stamp_wire(ctx, legs + d2, name)
        _tail = [(c[0], c[2]) if len(c) == 3 else c for c in (legs + d2)[-6:]]
        # ponytail: lwire plants no boosters, so a 2000-cell row arrives
        # dark no matter how clean its geometry (dust decays 1/cell). Plant
        # the stitch's own every-8 + end_boost stations on the stamped path,
        # with a flow map built from the path order. sim judges facing.
        # Consecutive duplicates (leg joints) carry no direction; drop them
        # so the planter sees straight triples, not standstills.
        _cells3 = []
        for c in legs + d2:
            c3 = c if len(c) == 3 else (c[0], 1, c[1])
            if not _cells3 or _cells3[-1] != c3:
                _cells3.append(c3)
        _flow = {}
        for _k in range(len(_cells3) - 1):
            _a, _b = _cells3[_k], _cells3[_k + 1]
            _flow.setdefault(_a, set()).add((_b[0] - _a[0], _b[2] - _a[2]))
        C._plant_repeaters(ctx, _cells3, name, _flow, end_boost=True)
        ctx.blocks.append((lamp[0], 1, lamp[1], 'minecraft:redstone_lamp'))
        ctx.solid[lamp] = ('lamp', name)
        for ddx, ddz in DIRS:
            ring(ctx, lamp[0] + ddx, lamp[1] + ddz, own(name))
        placed.append((name, lane, lamp))
        print('  %-5s lane z=%-4d lamp %-10s tail %s ok'
              % (name, lane, str(lamp), _tail), flush=True)

    print()
    print('placed %d/%d lamps   +%d blocks (%.0f -> %d)  in %.0fs'
          % (len(placed), len(OUTS), len(ctx.blocks) - base, base,
             len(ctx.blocks), time.time() - t0))
    if failed:
        print('failed: %s' % failed)
    with open(r'D:\redstone-mini\scratch\add8_bankrouted.pkl', 'wb') as f:
        # ponytail: stamp_wire fills ctx.wires only -- wire/repeater BLOCKS
        # are emitted by finish_assembly, which this post-pass never calls.
        # Dumping ctx.blocks without them shipped 19088/19088 old wires and
        # zero new ones, so every lamp sat on nothing and read dark. Emit
        # exactly what finish_assembly emits (wire_bid over dust-minus-
        # repeaters, repeater facing verbatim, stone pads under y=1 cells),
        # in place, no re-shrink-wrap (that would move the whole build and
        # invalidate io).
        from layout import wire_bid
        _dust = set(ctx.wires) - set(ctx.repeaters)
        _have = set((x, y, z) for (x, y, z, _b) in ctx.blocks)
        _emit_w = [c for c in ctx.wires
                   if c not in _w0 and c not in ctx.repeaters]
        _emit_r = [c for c in ctx.repeaters if c not in _r0]
        for c in sorted(_emit_w):
            if c in _have:
                raise RuntimeError('new wire cell %s already holds a block '
                                   '(wire owner %s)' % (c, ctx.wires.get(c)))
            ctx.blocks.append((c[0], c[1], c[2], wire_bid(c, _dust)))
            _have.add(c)
        for c in sorted(_emit_r):
            if c in _have:
                raise RuntimeError('new repeater cell %s already holds a block' % (c,))
            ctx.blocks.append((c[0], c[1], c[2],
                               "minecraft:repeater[facing=%s,delay=1]"
                               % (ctx.repeaters[c][1],)))
            _have.add(c)
        for c in sorted(set(_emit_w) | set(_emit_r)):
            if c[1] != 1:
                continue
            if (c[0], 0, c[2]) not in _have:
                ctx.blocks.append((c[0], 0, c[2], "minecraft:stone"))
                _have.add((c[0], 0, c[2]))
        print('emitted %d wires, %d repeaters' % (len(_emit_w), len(_emit_r)))
        # blocks back to BLOCK space (the repo convention: exports and sim
        # read block frame); io never left it. New lamps registered so the
        # sim gate and the export see them.
        blocks_out = [(x + _dx, y, z + _dz, bid)
                      for (x, y, z, bid) in ctx.blocks]
        io_out = dict(d['io'])
        lamps_out = dict(io_out['lamps'])
        nets_out = dict(io_out['nets'])
        placed_block = []
        for (name, lane, lamp) in placed:
            lb = (lamp[0] + _dx, lamp[1] + _dz)
            lamps_out[lb] = name + '@bank'
            placed_block.append((name, lane, lb))
        io_out['lamps'] = lamps_out
        for c in sorted(set(_emit_w) | set(_emit_r)):
            nets_out[(c[0] + _dx, c[1], c[2] + _dz)] = (
                ctx.wires[c] if c in ctx.wires else ctx.repeaters[c][0])
        io_out['nets'] = nets_out
        pickle.dump({'blocks': [tuple(b) for b in blocks_out], 'io': io_out,
                     'placed': placed_block, 'failed': failed}, f)
    print('wrote scratch/add8_bankrouted.pkl')


if __name__ == '__main__':
    main()