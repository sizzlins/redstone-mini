"""Compose: deterministic placement + wiring (no search, no seeds)."""

from types import SimpleNamespace

from core import DIRS, TORCH_BACK
from recipe import expand_gates
from tiles import (new_ctx, footprint, tap_lamps, own, ring, stamp_wire,
                   place_or, place_and, place_not, place_latch, place_xor)
from layout import build_netspec, check_shorts, check_opens, finish_assembly, _support, bridge_plan

_VEC = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}


def _hop_free(ctx, sup, guard, feet, supports, dusts, victim, net):
    # adapted bridge_free (layout.py:582-634): unbounded field, plus sup.
    fx, _, fz = victim
    if ctx.wires.get((fx, 1, fz)) in (None, net):
        return False  # nothing foreign to hop
    for x, y, z in supports + dusts:
        if (x, z) in guard:
            return False
        if ctx.wires.get((x, y, z)) not in (None, net):
            return False
        if ctx.wires.get((x, y + 1, z)) not in (None, net):
            return False  # no pillaring under / dust over foreign wire
        if (x, y, z) in sup and sup[(x, y, z)] != net:
            return False
    cond2 = set(supports)
    for x, y, z in dusts:
        for dx, dz in DIRS:
            for dy in (1, -1):
                w = ctx.wires.get((x + dx, y + dy, z + dz))
                if w is None or w == net:
                    continue
                if dy == 1:
                    if ((x + dx, y, z + dz) in cond2
                            and (x, y + 1, z) not in cond2):
                        return False
                else:
                    if ((x, y - 1, z) in cond2
                            and (x + dx, y, z + dz) not in cond2):
                        return False
    for x, y, z in supports:
        if y == 1 and (x, z) in ctx.solid:
            return False
        if (x, y, z) in ctx.repeaters:
            return False
    if ctx.solid.get((fx, fz)) is not None or (fx, 1, fz) in ctx.repeaters:
        return False  # center column must hold only victim dust
    if ctx.wires.get((fx, 4, fz)) is not None:
        return False  # air above the hop
    for x, y, z in feet:
        if ctx.wires.get((x, y, z)) not in (None, net):
            return False
        if (x, z) in ctx.solid or (x, 1, z) in ctx.repeaters:
            return False
    return True


def _path_cells(a, b, zfirst):
    cells = []
    x, z = a
    if zfirst:
        while z != b[1]:
            z += 1 if b[1] > z else -1
            cells.append((x, 1, z))
        while x != b[0]:
            x += 1 if b[0] > x else -1
            cells.append((x, 1, z))
    else:
        while x != b[0]:
            x += 1 if b[0] > x else -1
            cells.append((x, 1, z))
        while z != b[1]:
            z += 1 if b[1] > z else -1
            cells.append((x, 1, z))
    return cells


def _sealed(ctx, x, z, net, ownset, near_end):
    # mirrors stamp_wire's guards for precheck: certain-loud cells score
    # fatal, hop/span-able cells cost 1 (the walk re-verifies everything).
    # Adjacency is graded: expected near endpoints (ports live inside tile
    # wire neighborhoods), avoidable contention mid-path.
    s = ctx.solid.get((x, z))
    if s is not None and s[0] != "cobble":
        return 100
    w = ctx.wires.get((x, 1, z))
    if w is not None and w != net:
        return 1
    if (x, z) in ctx.rings and net not in ctx.rings[(x, z)]:
        return 100
    if (x, 1, z) in ctx.sup and ctx.sup[(x, 1, z)] != net:
        return 100
    r = ctx.repeaters.get((x, 1, z))
    if r is not None and r[0] != net:
        return 100
    for ax, az in DIRS:
        nb = (x + ax, z + az)
        if nb in ownset:
            continue
        nw = ctx.wires.get((nb[0], 1, nb[1]))
        if nw is not None and nw != net and not (
                nb in ctx.junctions and net in ctx.junctions[nb]):
            return 1 if near_end else 100
    return 0


def _candidates(ctx, a, b, net, avoid):
    # direct Ls first (identical behavior where they already work), then
    # approach rays: straight final segments into the load from N/E/S/W at
    # distance 1..6. Rays route around tile bodies the straight march would
    # hit (e.g. a comparator sitting on the port row). Bounded (2 + 24),
    # deterministic; the single winner walks (loud on surprise).
    zc, xc = _path_cells(a, b, True), _path_cells(a, b, False)
    cands = [("L", zc), ("L", xc)]
    for k in range(1, 7):
        for dx, dz in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            rs = (b[0] + k * dx, b[1] + k * dz)
            ray = [(rs[0] - i * dx, 1, rs[1] - i * dz) for i in range(1, k + 1)]
            base = _path_cells(a, rs, True)
            cands.append(("ray", base + ray))
    out = []
    for kind, cells in cands:
        if not cells:
            continue
        ownset = {(c[0], c[2]) for c in cells} | {a, b}
        bad = 0
        for i, (x, _, z) in enumerate(cells):
            bad += _sealed(ctx, x, z, net, ownset, i < 3 or i >= len(cells) - 3)
        bad += sum(100 for (x, _, z) in cells if (x, z) in avoid)
        out.append((bad, len(cells), kind, cells))
    out.sort(key=lambda t: (t[0], t[2] != "L", t[1]))
    return [c for _, _, _, c in out]


def lwire(ctx, sup, guard, a, b, net, avoid=frozenset()):
    """L-path at y=1 (best prechecked candidate wins: direct Ls first);
    the proven 5-cell staircase hop over foreign dust (bridge_plan shape:
    y1->y2->y3->y2->y1), single y=2 span over tile cobble; boosters per
    full net-path after wiring. Anything that seals is a loud no-ground."""
    cands = _candidates(ctx, a, b, net, avoid)
    if not cands:
        return []  # already there: zero-length run
    cells = cands[0]
    # seq anchors both ends so a hop's feet may land on driver/load cells.
    seq = [(a[0], 1, a[1])] + cells + [(b[0], 1, b[1])]
    done, skip, j = [], set(), 1
    while j < len(seq) - 1:
        cx, cy, cz = seq[j]
        if (cx, cz) in skip:
            j += 1
            continue
        rep = ctx.repeaters.get((cx, cy, cz))
        if rep is not None and rep[0] == net:
            done.append((cx, cy, cz))  # pass through, no phantom re-stamp
            j += 1
            continue
        try:
            if rep is not None:
                raise RuntimeError(f"foreign repeater at {(cx, cy, cz)}")
            stamp_wire(ctx, [(cx, cz)], net)
            done.append((cx, cy, cz))
            j += 1
            continue
        except RuntimeError:
            pass
        # sealed: find the foreign dust column on the travel axis (here,
        # ahead, or behind — proximity seals as well as occupancy).
        if j >= 1 and (seq[j][0], seq[j][2]) != (seq[j - 1][0], seq[j - 1][2]):
            px, _, pz = seq[j - 1]
            d = (cx - px, cz - pz)
        else:
            raise RuntimeError(f"compose: no ground for {net}: {a} -> {b}")
        found, victim = None, None
        for (vx, vz) in ((cx, cz), (cx + d[0], cz + d[1]), (cx - d[0], cz - d[1])):
            w = ctx.wires.get((vx, 1, vz))
            if w is not None and w != net:
                victim = (vx, vz)
                break
        if victim is None:
            if ctx.solid.get((cx, cz), (None,))[0] == "cobble":
                # tile cobble underfoot: single y=2 span onto paid-for support.
                if ctx.wires.get((cx, 2, cz)) not in (None, net):
                    raise RuntimeError(f"compose: no ground for {net}: {a} -> {b}")
                stamp_wire(ctx, [(cx, 2, cz)], net)
                done.append((cx, 2, cz))
                j += 1
                continue
            raise RuntimeError(f"compose: no ground for {net}: {a} -> {b}")
        vx, vz = victim
        back, front = (vx - 2 * d[0], vz - 2 * d[1]), (vx + 2 * d[0], vz + 2 * d[1])
        seqflats = [(s[0], s[2]) for s in seq]
        if back not in seqflats or front not in seqflats:
            raise RuntimeError(f"compose: no ground for {net}: {a} -> {b}")
        bi, fi = seqflats.index(back), seqflats.index(front)
        if not (bi < j <= fi):
            raise RuntimeError(f"compose: no ground for {net}: {a} -> {b}")
        for t in range(bi, fi + 1):
            qx, qz = seqflats[t]
            if (qx - vx) * d[1] != (qz - vz) * d[0]:
                raise RuntimeError(f"compose: no ground for {net}: {a} -> {b}")
        axis = "ns" if d[0] == 0 else "ew"
        feet = [(back[0], 1, back[1]), (front[0], 1, front[1])]
        supports = [(vx - d[0], 1, vz - d[1]), (vx + d[0], 1, vz + d[1]), (vx, 2, vz)]
        dusts = [(vx - d[0], 2, vz - d[1]), (vx, 3, vz), (vx + d[0], 2, vz + d[1])]
        assert (set(feet) | set(supports) | set(dusts)) == \
            (set(bridge_plan(vx, vz, axis)[0]) | set(bridge_plan(vx, vz, axis)[1]) | set(bridge_plan(vx, vz, axis)[2])), (feet, supports, dusts)
        if not _hop_free(ctx, sup, guard, feet, supports, dusts, (vx, 1, vz), net):
            raise RuntimeError(f"compose: no ground for {net}: {a} -> {b}")
        # back flank: retrofit own path wire into the up-slope, else stamp
        # support on the free cell. Anything else (foreign, or own wire that
        # is not the live tail) is genuine contention -> loud.
        bf = (vx - d[0], vz - d[1])
        if ctx.wires.get((bf[0], 1, bf[1])) == net:
            if not (done and done[-1] == (bf[0], 1, bf[1])):
                raise RuntimeError(f"compose: no ground for {net}: {a} -> {b}")
            del ctx.wires[(bf[0], 1, bf[1])]
            done.pop()
        ff = (vx + d[0], vz + d[1])
        if ctx.wires.get((ff[0], 1, ff[1])) not in (None, net):
            raise RuntimeError(f"compose: no ground for {net}: {a} -> {b}")
        for sx, sy, sz in supports:
            sup[(sx, sy, sz)] = net
            ctx.blocks.append((sx, sy, sz, "minecraft:cobblestone"))
            if sy == 1:
                ctx.solid.setdefault((sx, sz), ("cobble", net))
        for dx_, dy_, dz_ in dusts:
            stamp_wire(ctx, [(dx_, dy_, dz_)], net)
            done.append((dx_, dy_, dz_))
        for q in (bf, victim, ff, front):
            skip.add(q)
        stamp_wire(ctx, [front], net)
        done.append((front[0], 1, front[1]))
        j = fi + 1
    # no planting here: boosters run per full net-path after all wiring
    # (a leg starts wherever the previous leg decayed to, so per-leg
    # spacing plants on dead wire). See compose() below.
    return done


def _plant_repeaters(ctx, cells, net, flow):
    # two passes per leg: forward every 8 (feeds hop zones) and backward
    # every 8 from the load end (tail freshness — the latch S-row needs
    # level 9 at its port). Hop dusts break straight triples, so one
    # direction alone strands the other side; over-boosting is cheap
    # (block count is reported, never scored). Facing always along travel.
    # Safe on shared prefixes: composer runs are driver->load L-paths, so a
    # shared cell flows away from the driver for every run using it.
    # ponytail: same-net repeaters passed through by later runs are assumed
    # flow-compatible (topology argument, not per-cell checked — sim judges).
    # NEVER plant on multi-direction cells: opposite traversals share the
    # plain wire fine (same net, same signal), but a diode would rectify
    # one of them — measured: a ray base ran south up a northbound lane and
    # its backward diodes killed the lane (xor b).
    for _pass in (range(1, len(cells) - 1), range(len(cells) - 2, 0, -1)):
        dist = 0
        for k in _pass:
            if (cells[k][0], cells[k][1], cells[k][2]) in ctx.repeaters:
                dist = 0
                continue
            (px, py, pz), (cx, cy, cz), (nx, ny, nz) = cells[k - 1], cells[k], cells[k + 1]
            dist += 1
            if len(flow.get((cx, cy, cz), {(0, 0)})) != 1:
                continue
            dx, dz = cx - px, cz - pz
            if dist >= 8 and (dx, dz) == (nx - cx, nz - cz) and (dx, dz) in _VEC and py == cy == ny == 1:
                del ctx.wires[(cx, cy, cz)]
                ctx.repeaters[(cx, cy, cz)] = (net, _VEC[(dx, dz)])
                dist = 0


def _topo(gates):
    by_out, order = {}, []
    for i, g in enumerate(gates):
        by_out.setdefault(g["out"], i)
    deps = {i: {by_out[a] for a in g["args"] if a in by_out and by_out[a] != i}
            for i, g in enumerate(gates)}
    ready = sorted(i for i, d in deps.items() if not d)
    while ready:
        i = ready.pop(0)
        order.append(i)
        for j, d in deps.items():
            if i in d:
                d.discard(i)
                if not d and j not in order and j not in ready:
                    ready.append(j)
        ready.sort()
    if len(order) != len(gates):
        raise RuntimeError("compose: gate cycle")
    return [gates[i] for i in order]


def _depths(gates, inputs):
    ins, depth = set(inputs), {}
    for g in _topo(gates):
        if all(a in ins or a in ("0", "1") for a in g["args"]):
            depth[g["out"]] = 2
        else:
            depth[g["out"]] = 1 + max(depth[a] for a in g["args"] if a not in ins and a not in ("0", "1"))
    return depth


def compose(recipe):
    gates = expand_gates(recipe["gates"], recipe["inputs"])
    blocks, solid, rings, wires, junctions, repeaters, pos, recs, sup = [], {}, {}, {}, {}, {}, {}, [], {}
    ctx = new_ctx(blocks, solid, rings, wires, junctions, repeaters, pos, recs, sup)
    guard = set()
    ordered = _topo(gates)
    depth = _depths(gates, recipe["inputs"])
    # placement: topo bands in Z, padding from subtree depth; 4 X-lanes stride 30.
    gz_of, z = {}, 12
    for g in ordered:
        gz_of[g["out"]] = z
        z += 4 + depth[g["out"]] + 6
    used_fp = []

    def c_spot_free(op, ox, gz, i):
        fp = footprint(op, ox, gz)
        if any(not fp.isdisjoint(u) for u in used_fp):
            return False
        return all((x, z) not in solid and (x, 1, z) not in wires for x, z in fp)

    def c_gridrows(ox, gz):
        while True:
            yield ox, gz
            gz += 14

    c_place = SimpleNamespace(spot_free=c_spot_free, gridrows=c_gridrows,
                              snap=lambda: None, restore=lambda s: None)
    for i, g in enumerate(ordered):
        ox, gz = 6 + (i % 4) * 30, gz_of[g["out"]]
        for ox2, gz2 in c_gridrows(ox, gz):
            if not c_spot_free(g["op"], ox2, gz2, i):
                continue
            if g["op"] == "OR":
                place_or(ctx, c_place, g, ox2, gz2, pos, 10**6, 10**6)
            elif g["op"] == "AND":
                place_and(ctx, c_place, g, i, ox2, gz2, pos)
            elif g["op"] == "NOT":
                place_not(ctx, c_place, g, i, ox2, gz2, pos)
            elif g["op"] == "LATCH":
                place_latch(ctx, c_place, g, i, ox2, gz2, pos)
            elif g["op"] == "XOR":
                place_xor(ctx, c_place, g, i, ox2, gz2, pos)
            else:
                raise RuntimeError(f"compose: bad primitive {g['op']}")
            used_fp.append(footprint(g["op"], ox2, gz2))
            break
        else:
            raise RuntimeError(f"compose blocked for {g['out']}")
    # ties: layout.py:895-903 convention at fixed west sites (tiles live z>=12).
    if any(a in ("0", "1") for g in gates for a in g["args"]):
        stamp_wire(ctx, [(0, 3)], "0")
        pos["0"] = (0, 3)
        blocks.append((2, 1, 3, "minecraft:redstone_block"))
        solid[(2, 3)] = ("block", "1")
        for dx, dz in DIRS:
            ring(ctx, 2 + dx, 3 + dz, own("1"))
        stamp_wire(ctx, [(1, 3)], "1")
        pos["1"] = (1, 3)
    # inputs: one edge bus per input at pitch 5 on the west edge. Stub on
    # the lever's west side so the lane jog never crosses its own block.
    for k, name in enumerate(recipe["inputs"]):
        lz = z + 6 + k * 5
        blocks.append((4, 1, lz, "minecraft:lever"))
        solid[(4, lz)] = ("lever", name)
        for dx, dz in DIRS:
            ring(ctx, 4 + dx, lz + dz, own(name))
        stamp_wire(ctx, [(3, lz)], name)
        pos[name] = (3, lz)
    # guard from stamped torches, exactly like layout.py:1419-1425.
    for x, y, zz, bid in blocks:
        if "wall_torch" in bid:
            guard.add((x, zz))
            face = bid.split("facing=")[1].rstrip("]")
            dx, dz = TORCH_BACK[face]
            guard.add((x + dx, zz + dz))
    netspec = build_netspec(recs, recipe, pos)
    inps = list(recipe["inputs"])
    # order: gate nets before input nets. A long input jog is a wall no
    # 5-cell hop can cross (feet land on the wall itself); stamped last, it
    # hops each short gate run it meets instead — single victims, free feet.
    ordered_nets = sorted(n for n in netspec if n not in inps and n not in ("0", "1"))
    ordered_nets += sorted(n for n in netspec if n in inps)
    paths = []
    # other nets' load cells are reserved: a candidate stepping on one
    # would steal a future port (then that net dies loud at its endpoint).
    # Halo (Chebyshev 1 around each foreign load): feeds must never sit
    # adjacent either (different nets side-touching = a vanilla short) —
    # e.g. a@(6,9) would seal b's (6,10) port forever, and vice versa.
    allloads = {}
    for n2, spec in netspec.items():
        for cell in spec['loads']:
            allloads.setdefault(n2, set()).add(cell)
    halos = {}
    for net in ordered_nets:
        h = set()
        for n2, s in allloads.items():
            if n2 == net:
                continue
            for (lx, lz) in s:
                h.update((lx + ax, lz + az) for ax in (-1, 0, 1) for az in (-1, 0, 1))
        halos[net] = frozenset(h)
    flow = {}
    for net in ordered_nets:
        avoid = halos[net]
        drv = netspec[net]['drv'] or pos.get(net)
        for cell in sorted(netspec[net]['loads']):
            if net in inps:
                # per-input lane: N-S runs never share a column, so one
                # net's overpass pillars can never seal another's. Lanes
                # spread west (x<=2, south of tile country) at pitch 4:
                # pitch 2 put adjacent lanes inside one hop's feet, so a
                # jog crossing two lanes died loud; at pitch 4 every
                # crossing is a single victim with free feet.
                lx = 2 - 4 * inps.index(net)
                d1 = lwire(ctx, sup, guard, drv, (lx, drv[1]), net, avoid)
                d2 = lwire(ctx, sup, guard, (lx, drv[1]), (lx, cell[1]), net, avoid)
                d3 = lwire(ctx, sup, guard, (lx, cell[1]), cell, net, avoid)
                paths.append((net, d1 + d2 + d3))
            else:
                paths.append((net, lwire(ctx, sup, guard, drv, cell, net, avoid)))
    for net, full in paths:
        for u, v in zip(full, full[1:]):
            d = (v[0] - u[0], v[2] - u[2])
            flow.setdefault((u[0], u[1], u[2]), set()).add(d)
            flow.setdefault((v[0], v[1], v[2]), set()).add(d)
    for net, full in paths:
        _plant_repeaters(ctx, full, net, flow)
    # lamps via the shared tap routine (same E/S/N/W order, same loud
    # failure) — AFTER wiring (maze order): lamp rings would otherwise seal
    # lanes routed past them with a foreign-only ring set.
    tap_lamps(ctx, recipe, pos, 10**6, 10**6)
    check_shorts(wires, junctions, blocks)
    check_opens(wires, junctions, repeaters, solid, pos, blocks)
    return finish_assembly(blocks, solid, wires, rings, junctions, repeaters, pos)


if __name__ == "__main__":
    from tiles import new_ctx, stamp_wire
    _blocks, _solid, _rings, _wires, _junc, _reps, _pos, _recs, _sup0 = [], {}, {}, {}, {}, {}, {}, [], {}
    _ctx = new_ctx(_blocks, _solid, _rings, _wires, _junc, _reps, _pos, _recs, _sup0)
    _sup, _guard = {}, set()
    # two nets must cross: A runs east, B must bridge over it.
    stamp_wire(_ctx, [(10, 1, 20), (11, 1, 20), (12, 1, 20), (13, 1, 20)], "A")
    lwire(_ctx, _sup, _guard, (11, 18), (11, 22), "B")
    assert _wires.get((11, 1, 20)) == "A", _wires
    assert any(y >= 2 for (x, y, z), n in _wires.items() if n == "B"), "B never left the ground"
    print("lwire ok: bridge-over crosses without touching")

    from recipe import parse_recipe
    from sim import sim_verify
    _r = parse_recipe("IN a, b\nOUT y\ny = a AND b\n")
    _out, _size, _io = compose(_r)
    sim_verify(_r, _out, _io, quiet=True)
    print("compose ok: AND verifies through the sim gate")
