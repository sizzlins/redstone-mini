"""Compose: deterministic placement + wiring (no search, no seeds)."""

import os
import sys
import time
from types import SimpleNamespace

from core import DIRS, TORCH_BACK
from recipe import expand_gates
from tiles import (new_ctx, footprint, tap_lamps, own, ring, stamp_wire,
                   place_or, place_and, place_not, place_latch, place_xor,
                   seal_tiles)
from layout import build_netspec, check_shorts, check_opens, finish_assembly, _support, bridge_plan, astar

# last compose() run's coordinate shift (netspec frame -> check frame),
# for offline probes. Not part of the build contract.
_last_shift = (0, 0)

# Composer's vertical envelope for the astar fallback (env-tunable).
# Narrow y=1..3 is tried first (the proven band); the full envelope only
# runs if narrow finds nothing, because a marginal wide success poisons
# downstream routing worse than a loud failure.
_WIDE_YMIN = int(os.environ.get("REDSTONE_COMPOSE_YMIN", "-4"))
_WIDE_YMAX = int(os.environ.get("REDSTONE_COMPOSE_YMAX", "6"))

_VEC = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}


def _hop_free(ctx, sup, guard, feet, supports, dusts, victim, net):
    # adapted bridge_free (layout.py:582-634): unbounded field, plus sup.
    fx, _, fz = victim
    if ctx.wires.get((fx, 1, fz)) in (None, net) and not (
            (fx, fz) in ctx.rings and net not in ctx.rings[(fx, fz)]):
        return False  # nothing foreign to hop (a foreign ring counts: span it)
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


def _score_cells(ctx, cells, net, avoid, a, b):
    """Precheck cost of one corridor (0 = perfect). Factored out of
    _candidates so lwire's fast path can score just the L-paths."""
    ownset = {(c[0], c[2]) for c in cells} | {a, b}
    bad = 0
    # near_end exempts a cell from needing clearance around foreign wires.
    # Only the port cell itself may do that: a port genuinely lives inside
    # a tile's wire neighbourhood, but the outbound run must not hug —
    # the 3-cell window let parallel input stubs run one cell apart down
    # the port row and die on a touch (alu4 B3/A1 at y=1, z=7).
    for i, (x, _, z) in enumerate(cells):
        bad += _sealed(ctx, x, z, net, ownset, i < 1 or i >= len(cells) - 1)
    bad += sum(100 for (x, _, z) in cells if (x, z) in avoid)
    return bad


def _candidates(ctx, a, b, net, avoid):
    # direct Ls first (identical behavior where they already work), then
    # approach rays: straight final segments into the load from N/E/S/W at
    # distance 1..6. Rays route around tile bodies the straight march would
    # hit (e.g. a comparator sitting on the port row). Then offset trunks:
    # parallel corridors u rows north/south of the load row for jogs whose
    # own row is sealed (input E-W jogs through the top tile band: B's
    # (-7,16)->(159,16) march). Bounded (2 + 24 + 12), deterministic; the
    # single winner walks (loud on surprise). Longer detours lose ties
    # (sort keys bad, then L, then len), so open corridors keep cands[0].
    zc, xc = _path_cells(a, b, True), _path_cells(a, b, False)
    cands = [("L", zc), ("L", xc)]
    for k in range(1, 7):
        for dx, dz in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            rs = (b[0] + k * dx, b[1] + k * dz)
            ray = [(rs[0] - i * dx, 1, rs[1] - i * dz) for i in range(1, k + 1)]
            base = _path_cells(a, rs, True)
            cands.append(("ray", base + ray))
    for u in _JOGS:
        for dz in (-u, u):
            rs = (b[0], b[1] + dz)
            drop = [(rs[0], 1, rs[1] - i * (1 if dz > 0 else -1))
                    for i in range(1, abs(dz) + 1)]
            base = _path_cells(a, rs, True)
            cands.append(("ray", base + drop))
    out = []
    for kind, cells in cands:
        if not cells:
            continue
        bad = _score_cells(ctx, cells, net, avoid, a, b)
        out.append((bad, len(cells), kind, cells))
    out.sort(key=lambda t: (t[0], t[2] != "L", t[1]))
    return [c for _, _, _, c in out]


def lwire(ctx, sup, guard, a, b, net, avoid=frozenset()):
    """L-path at y=1 (best prechecked candidate wins: direct Ls first);
    the proven 5-cell staircase hop over foreign dust (bridge_plan shape:
    y1->y2->y3->y2->y1), single y=2 span over tile cobble; boosters per
    full net-path after wiring. Anything that seals is a loud no-ground."""
    # REDSTONE_NOFLAT=1: skip the flat candidates, go straight to the astar
    # corridor and 3D overflight (diagnostic: do 3D paths even exist here?).
    if os.environ.get("REDSTONE_NOFLAT"):
        cands = []
    else:
        cands = _candidates(ctx, a, b, net, avoid)
    if not cands and (a == b or not os.environ.get("REDSTONE_NOFLAT")):
        return []  # already there: zero-length run
    # ponytail: fast path. Score just the 2 L-paths (O(2L), not O(38L)).
    # A perfect L (bad=0) is GUARANTEED to be cands[0] under full scoring:
    # nothing beats bad=0, and L wins every tie on kind. So if the best L
    # is perfect and walks, the other 36 corridors could never have won —
    # skip building and scoring them. If it fails to walk, or neither L is
    # perfect, fall through to full scoring (identical behavior).
    # Big-O: per net, O(L) amortized in open field vs O(38L); dense fields
    # pay the full O(38L) exactly as before. No layout can change: the fast
    # path only fires when full scoring would have picked the same cells.
    if not os.environ.get("REDSTONE_NOFLAT") and cands:
        _zc, _xc = _path_cells(a, b, True), _path_cells(a, b, False)
        _ls = [(c, _score_cells(ctx, c, net, avoid, a, b))
               for c in (_zc, _xc) if c]
        _ls.sort(key=lambda t: (t[1], len(t[0])))
        if _ls and _ls[0][1] == 0:
            _snap = (dict(ctx.wires), dict(sup), dict(ctx.sup),
                     dict(ctx.solid), len(ctx.blocks))
            try:
                return _walk(ctx, sup, guard, a, b, net, _ls[0][0])
            except RuntimeError:
                _sw, _ss, _sc, _so, _sb = _snap
                ctx.wires.clear()
                ctx.wires.update(_sw)
                sup.clear()
                sup.update(_ss)
                ctx.sup.clear()
                ctx.sup.update(_sc)
                ctx.solid.clear()
                ctx.solid.update(_so)
                del ctx.blocks[_sb:]
    # ponytail: candidate fallback. cands[0] wins wherever it walks (open
    # corridors: always, so small-build hashes must not move); a sealed
    # trunk falls through to the next-ranked corridor instead of dying
    # loud while a clean one sits below (alu1 AB: cands[0] dies on a
    # ring+torch wall, cand4 is open). Roll back each failure — phantom
    # same-net wire would read live-but-unboosted downstream. Loud iff
    # all fail, keeping the cands[0] error so sealed nets report as before.
    snap = (dict(ctx.wires), dict(sup), dict(ctx.sup), dict(ctx.solid),
            len(ctx.blocks))
    first_err = None
    for cells in cands:
        try:
            return _walk(ctx, sup, guard, a, b, net, cells)
        except RuntimeError as e:
            if first_err is None:
                first_err = e
            sw, ss, sc, so, sb = snap
            ctx.wires.clear()
            ctx.wires.update(sw)
            sup.clear()
            sup.update(ss)
            ctx.sup.clear()
            ctx.sup.update(sc)
            ctx.solid.clear()
            ctx.solid.update(so)
            del ctx.blocks[sb:]
    # ponytail: astar corridor. The 38 L/ray trunks miss zigzag corridors
    # that provably exist (alu1 AB: BFS finds a violation-free len-53 run;
    # layout.astar confirms under full coupling rules). Reuse the maze
    # search — with its sim-parity coupling, not a re-derivation — as the
    # last candidate. Fires only where today dies loud, so small builds
    # never reach here and their hashes must not move. Deterministic (astar's
    # heap order is total); cost bounded by REDSTONE_ASTAR_CAP.
    cells = _astar_wrap(ctx, sup, guard, a, b, net, avoid)
    if cells:
        try:
            return _walk(ctx, sup, guard, a, b, net, cells[1:-1])
        except RuntimeError:
            sw, ss, sc, so, sb = snap
            ctx.wires.clear()
            ctx.wires.update(sw)
            sup.clear()
            sup.update(ss)
            ctx.sup.clear()
            ctx.sup.update(sc)
            ctx.solid.clear()
            ctx.solid.update(so)
            del ctx.blocks[sb:]
    # ponytail: 3D overflight, the last resort. Ground routing cannot cross
    # two parallel wires 2 apart (the 5-cell hop needs 2 clear cells per
    # side) and every row of a long N-S column is blocked, so no candidate
    # helps: alu1 CIN faces n1's column at x=8 spanning z=12..36. astar's
    # 3D search flies over on pillars — the same mechanism the maze backend
    # already ships (micro1 is green through it). Supports are validated
    # with layout._support (torch-hug guard) and stamped here, never during
    # search, so a flyover cannot lid its own later slope. Self-lid and
    # support refusals fall through to the original loud error.
    # The proven y=1..3 band runs first; the full vertical envelope
    # (trenches + high decks) only runs if narrow finds nothing.
    for _ymin, _ymax in ((1, 3), (_WIDE_YMIN, _WIDE_YMAX)):
        _fly = _astar_wrap(ctx, sup, guard, a, b, net, avoid, flat=False,
                           ymin=_ymin, ymax=_ymax)
        if not (_fly and any(c[1] >= 2 for c in _fly)):
            continue
        fly = _fly
        needs = []
        try:
            for cell in fly:
                if cell[1] < 2:
                    continue
                r = _support(cell, net, ctx.solid, ctx.wires, sup,
                             ctx.repeaters, guard)
                if r is False:
                    raise RuntimeError("support sealed")
                if r is not None and r not in sup and r not in needs:
                    needs.append(r)
            # ponytail: cobf = every cell that can act as a support, not
            # just the ones this flight owns. _support returns None ("reuse")
            # when the cell below is ALREADY cobble — a tile's own body — and
            # that cobble lives in ctx.solid, not in sup, so the old cobf
            # missed it and the self-lid test below rejected every descent
            # that passed a tile. Measured: alu4's carry C1 (107,41)->(195,55)
            # found a 103-cell flight at y=1..3 and was killed by
            # "self-lid at (195,2,54)->(195,1,55)" — the last step onto the
            # load, whose support is the destination tile's own body.
            cobf = set(sup) | set(needs)
            cobf.update((x, 1, z) for (x, z), (k, _n) in ctx.solid.items()
                        if k == "cobble")
            for u, v in zip(fly, fly[1:]):
                if u[1] == v[1]:
                    continue
                lo, hi = (u, v) if u[1] < v[1] else (v, u)
                if (hi[0], hi[1] - 1, hi[2]) not in cobf or \
                        (lo[0], lo[1] + 1, lo[2]) in cobf:
                    raise RuntimeError("self-lid")
        except RuntimeError:
            pass
        else:
            for s_ in needs:
                sup[s_] = net
                ctx.sup[s_] = net
                ctx.blocks.append((s_[0], s_[1], s_[2], "minecraft:cobblestone"))
                if s_[1] == 1:
                    ctx.solid.setdefault((s_[0], s_[2]), ("cobble", net))
            try:
                from tiles import stamp_wire as _sw
                _sw(ctx, fly, net, (a, b))
            except RuntimeError:
                sw, ss, sc, so, sb = snap
                ctx.wires.clear()
                ctx.wires.update(sw)
                sup.clear()
                sup.update(ss)
                ctx.sup.clear()
                ctx.sup.update(sc)
                ctx.solid.clear()
                ctx.solid.update(so)
                del ctx.blocks[sb:]
            else:
                if not _flight_live(ctx, net, a, b, fly):
                    sw, ss, sc, so, sb = snap
                    ctx.wires.clear()
                    ctx.wires.update(sw)
                    sup.clear()
                    sup.update(ss)
                    ctx.sup.clear()
                    ctx.sup.update(sc)
                    ctx.solid.clear()
                    ctx.solid.update(so)
                    del ctx.blocks[sb:]
                else:
                    return fly[1:-1]
    if first_err is None:
        # REDSTONE_NOFLAT and the astar/3D paths all refused without a
        # recorded flat error: raise a generic no-ground so the ladder
        # treats it as retryable geometry, not a crash.
        raise RuntimeError(f"compose: no ground for {net}: {a} -> {b}")
    raise first_err


def _flight_live(ctx, net, a, b, flight):
    """Does the just-stamped flight actually deliver power from a to b?

    check_opens runs once at the very end, so a flight that stamps cleanly
    but lands on an isolated pocket is only caught 400 cells from its
    driver. Run the same coupling rules (same-y dust, repeaters, slope
    links with support-below/no-lid) as a BFS from a over THIS FLIGHT's
    cells, and require b. Cheap (flight cells only) and it lets lwire
    reject the flight and try another candidate instead of emitting a
    dead tail. Measured on alu1's CIN: the overflight ended in a 2-cell
    pocket with no coupling to the run, and check_opens reported it
    unconnected.

    BFS is over the flight's own cells plus a ONLY — never pre-existing
    own wires. Those can be dead stubs themselves (a tile port powered
    solely from the flight's endpoint), so walking through them proves
    nothing; the flight must deliver independently.
    """
    from core import DIRS as _D
    # NOTE: fly[1:-1] excludes a and b; re-add them for the walk.
    start, goal = (a[0], 1, a[1]), (b[0], 1, b[1])
    _FC = set(flight) | {start, goal}
    reps = ctx.repeaters
    cob = {(x, y, z) for x, y, z, bid in ctx.blocks
           if bid.split("[")[0] == "minecraft:cobblestone"}
    wires = ctx.wires
    seen, stack = set(), [start]
    while stack:
        c = stack.pop()
        if c in seen:
            continue
        seen.add(c)
        if c == goal:
            return True
        for dx, dz in _D:
            m = (c[0] + dx, c[1], c[2] + dz)
            # same-y step: only onto a flight cell (or goal), never a
            # pre-existing wire — see docstring.
            if m == goal or (wires.get(m) == net and m in _FC):
                if m not in seen:
                    stack.append(m)
            elif m in reps and reps[m][0] == net and m in _FC:
                if m not in seen:
                    stack.append(m)
            up = (c[0] + dx, c[1] + 1, c[2] + dz)
            if (up == goal or (wires.get(up) == net and up in _FC)) \
                    and (c[0] + dx, c[1], c[2] + dz) in cob \
                    and (c[0], c[1] + 1, c[2]) not in cob and up not in seen:
                stack.append(up)
            dn = (c[0] + dx, c[1] - 1, c[2] + dz)
            if (dn == goal or (wires.get(dn) == net and dn in _FC)) \
                    and (c[0], c[1] - 1, c[2]) in cob \
                    and (c[0] + dx, c[1], c[2] + dz) not in cob and dn not in seen:
                stack.append(dn)
    return False


def _astar_wrap(ctx, sup, guard, a, b, net, avoid, flat=True,
                ymin=None, ymax=None):
    """layout.astar for compose corridors (any coords, flat or 3D).

    ponytail: astar windows clip at 0 while compose lanes run negative, so
    shift a tight margin box to non-negative (shifted dict copies; unshift
    the path). O(field content) per call, failure-path only. Deterministic
    (astar's heap order is total); cost bounded by REDSTONE_ASTAR_CAP and
    the box (manhattan + 64 detour slack). Halos steer softly via congest
    (read-only cost; astar takes no avoid set). flat=False allows y>=2
    overflight, which is the only way past a long parallel column: the
    5-cell hop needs 2 clear cells each side, so two wires 2 apart are a
    canyon no ground candidate can cross (alu1 CIN vs n1@x8).
    """
    man = abs(a[0] - b[0]) + abs(a[1] - b[1])
    if man > 2000:
        return None
    m = man + 64
    ox = max(0, -min(a[0], b[0])) + 2
    oz = max(0, -min(a[1], b[1])) + 2
    solid2 = {(x + ox, z + oz): v for (x, z), v in ctx.solid.items()}
    rings2 = {(x + ox, z + oz): v for (x, z), v in ctx.rings.items()}
    wires2 = {(x + ox, y, z + oz): v for (x, y, z), v in ctx.wires.items()}
    junctions2 = {(x + ox, z + oz): v for (x, z), v in ctx.junctions.items()}
    reps2 = {(x + ox, y, z + oz): v for (x, y, z), v in ctx.repeaters.items()}
    sup2 = {(x + ox, y, z + oz): v for (x, y, z), v in sup.items()}
    guard2 = {(x + ox, z + oz) for (x, z) in guard}
    air = frozenset(c for c, n in ctx.wires.items() if c[1] >= 2 and n != net)
    air2 = frozenset((c[0] + ox, c[1], c[2] + oz) for c in air)
    congest = {(x + ox, 1, z + oz): 10 ** 6 for (x, z) in avoid}
    # ponytail: never overfly an endpoint's own column. A path that climbs
    # over its goal needs a pillar AT the goal cell, so the load holds
    # cobble instead of dust — self-lid, and the pillar also lids the
    # descent. astar cannot see that (it is a post-hoc check), so forbid it
    # in the cost: endpoints are reached at y=1 from the side, which is
    # what a hand route does anyway. Cost, not a wall, so a build with no
    # other way still routes.
    for _ex, _ez in ((a[0], a[1]), (b[0], b[1])):
        for _dy in range(2, 5):
            congest[(_ex + ox, _dy, _ez + oz)] = 10 ** 6
    W = max(a[0], b[0]) + ox + m + 1
    D = max(a[1], b[1]) + oz + m + 1
    found = astar([(a[0] + ox, 1, a[1] + oz)], (b[0] + ox, 1, b[1] + oz), net,
                  W, D, solid2, rings2, wires2, junctions2, m,
                  None, congest, guard2, sup2, reps2, None, flat, air2,
                  ymin, ymax)
    if not found or len(found) < 2:
        return None
    return [(x - ox, y, z - oz) for (x, y, z) in found]


def _walk(ctx, sup, guard, a, b, net, cells):
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
            if ((cx, cz) in ctx.rings and net not in ctx.rings[(cx, cz)]
                    and ctx.solid.get((cx, cz)) is None
                    and ctx.wires.get((cx, 1, cz)) is None
                    and ctx.repeaters.get((cx, 1, cz)) is None
                    and sup.get((cx, 1, cz)) is None
                    and ctx.sup.get((cx, 1, cz)) is None):
                # ponytail: ring-hop. A reservation-only ring cell seals a
                # corridor exactly like a wire does, so span it with the
                # proven hop shape instead of dying loud. Falls through to
                # the hop machinery below (same back/front + _hop_free
                # guards); the sim gates correctness. Open corridors never
                # reach here, so small-build hashes must not move.
                victim = (cx, cz)
            else:
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
    # ponytail: slope-link lids. sim couples a y=1 wire to a diagonal y=2
    # wire only when the upper has support AND the lower has no lid over it.
    # Hops and 3D overflights both mint y=2 dust on fresh cobble, and the
    # search that placed them could not see the foreign wire that lands
    # diagonally below (cmp2: d0 at (751,1,190) vs bridge dust at
    # (751,2,189)). Dropping one cobble directly ABOVE the lower foreign
    # wire is exactly the breaker the rule looks for, and a block over a
    # ground wire is inert. Runs once per walk over own elevated cells;
    # green builds never place y=2 dust beside foreign dust, so no hash moves.
    if any(y >= 2 for _, y, _ in done):
        # derived from ctx.blocks, not a side set, so lwire's rollback
        # (which truncates ctx.blocks) can never desync it.
        cob = {(bx, by, bz) for bx, by, bz, bid in ctx.blocks
               if bid.split("[")[0] == "minecraft:cobblestone"}
        for (x, y, z) in done:
            # mirrors check_shorts' dy=-1 case exactly: the UPPER cell is
            # ours, the LOWER is one step down and diagonal, and the link
            # needs support under us and no lid over it. Anything else is
            # already legal, so a build that passes check_shorts gets zero
            # extra blocks here.
            if y < 2 or (x, y - 1, z) not in cob:
                continue
            for dx, dz in DIRS:
                lx, ly, lz = x + dx, y - 1, z + dz
                fw = ctx.wires.get((lx, ly, lz))
                if fw is None or fw == net or (lx, y, lz) in cob:
                    continue
                if (ctx.wires.get((lx, y, lz)) is not None
                        or (lx, ly, lz) in ctx.repeaters):
                    continue
                cob.add((lx, y, lz))
                ctx.blocks.append((lx, y, lz, "minecraft:cobblestone"))
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
            # ponytail: boost elevated runs too. _plant_repeaters only fired
            # at y==1, so a 3D overflight (y=2/3, twenty cells of flat) bled
            # 15->0 and arrived dark — measured on ctrl_decode's OP2 lane,
            # whose y=3 span read 13,12,11..0 and never recovered. A repeater
            # needs flat ground and a solid foot: the triple must be level
            # (stairs are never planted, so bridge slopes keep their dust)
            # and y>1 needs cobble below (the flight guarantees a pillar).
            # Same straight-triple + single-flow rules as y=1; sim judges.
            if dist >= 8 and (dx, dz) == (nx - cx, nz - cz) and (dx, dz) in _VEC \
                    and py == cy == ny:
                if cy > 1 and not any(
                        b[:3] == (cx, cy - 1, cz) and "cobblestone" in b[3]
                        for b in ctx.blocks):
                    continue
                del ctx.wires[(cx, cy, cz)]
                ctx.repeaters[(cx, cy, cz)] = (net, _VEC[(dx, dz)])
                dist = 0


def _strip_buffers(gates, outs=()):
    # fanout relay buffers are AND(x,x) = identity, emitted for maze hop-
    # shortening. The composer boosts by construction, so relays are pure
    # overhead (extra tiles + routes on an already-full field — the reverted
    # chaining lesson). Inline them: provably equivalent, maze untouched.
    # ponytail: never inline a recipe OUTPUT. `ALU1 = OP1 AND OP1` is a
    # hand-written buffer in a recipe, not an emitted relay, and tap_lamps
    # needs a real port cell to hang the lamp off — inlining it left
    # pos['ALU1'] unset and ctrl_decode died with a bare KeyError after
    # routing. The tile costs one AND; the identity saves nothing here.
    keep = set(outs)
    buf = {}
    for g in gates:
        if g["out"] in keep:
            continue
        if g["op"] == "AND" and g["args"][0] == g["args"][1] and not g.get("rep"):
            buf[g["out"]] = g["args"][0]
    if not buf:
        return gates

    def resolve(n):
        while n in buf:
            n = buf[n]
        return n

    out = []
    for g in gates:
        if g["out"] in buf:
            continue
        g = dict(g, args=[resolve(a) for a in g["args"]])
        out.append(g)
    return out


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


import functools as _functools


@_functools.lru_cache(maxsize=None)
def _expanded(op, ox, gz):
    # footprint + 4 halo for disjoint-testing: sibling tile yards merge
    # into one sealed super-block at +2 (alu1 m0/m1: O's feed + AB's
    # corridor + both stubs exceed a 5-wide street). 9-wide streets fit a
    # run + shadows + stubs with slack; runs lengthen (repeaters auto).
    # Pure in (op, ox, gz), so memoized: placement bumps east retrying the
    # same yards, and every rung re-places. O(1) amortized per repeat vs
    # O(footprint x 81) to rebuild. frozenset: callers only isdisjoint(),
    # and sharing a mutable set across placements would be a landmine.
    fp = footprint(op, ox, gz)
    return frozenset((x + ax, z + az) for (x, z) in fp for ax in (-4, -3, -2, -1, 0, 1, 2, 3, 4) for az in (-4, -3, -2, -1, 0, 1, 2, 3, 4))


def _compose_once(recipe):
    gates = _strip_buffers(expand_gates(recipe["gates"], recipe["inputs"]),
                           recipe["outputs"])
    blocks, solid, rings, wires, junctions, repeaters, pos, recs, sup = [], {}, {}, {}, {}, {}, {}, [], {}
    ctx = new_ctx(blocks, solid, rings, wires, junctions, repeaters, pos, recs, sup)
    guard = set()
    ordered = _topo(gates)
    # placement: recursive locality — each gate goes just south of its
    # drivers (children next to parents, so runs are short by
    # construction), bumping east until disjoint. Driverless gates seed a
    # top row. Flow invariant: signals run south+east only.
    used_fp = []
    placed = {}

    def c_spot_free(op, ox, gz, i):
        fp = footprint(op, ox, gz)
        if any(not fp.isdisjoint(u) for u in used_fp):
            return False
        return all((x, z) not in solid and (x, 1, z) not in wires for x, z in fp)

    def c_gridrows(ox, gz):
        while True:
            yield ox, gz
            gz += 14 * _SPREAD

    c_place = SimpleNamespace(spot_free=c_spot_free, gridrows=c_gridrows,
                              snap=lambda: None, restore=lambda s: None)
    topx = 6
    for i, g in enumerate(ordered):
        drvs = [a for a in g["args"] if a in placed]
        if not drvs:
            ox, gz = topx, 12
            topx += 30 * _SPREAD
        else:
            bottom = max(z for a in drvs for (_, z) in placed[a][3])
            n = sum(len(placed[a][3]) for a in drvs)
            cx = sum(x for a in drvs for (x, _) in placed[a][3]) // n
            gz = bottom + 8 * _SPREAD
            ox = max(4, cx)
            while any(not _expanded(g["op"], ox, gz).isdisjoint(u) for u in used_fp):
                ox += 2 * _SPREAD
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
            fp = footprint(g["op"], ox2, gz2)
            placed[g["out"]] = (g["op"], ox2, gz2, fp)
            used_fp.append(_expanded(g["op"], ox2, gz2))
            break
        else:
            raise RuntimeError(f"compose blocked for {g['out']}")
    # bbox of placed tiles drives ties + input buses (both hug the field
    # instead of living at fixed far coordinates).
    BB = [(x, z) for u in used_fp for (x, z) in u]
    minx, maxx = min(x for x, _ in BB), max(x for x, _ in BB)
    minz, maxz = min(z for _, z in BB), max(z for _, z in BB)
    # ties: hot "1" east of bbox at z=3 (north of every tile — footprints
    # bottom out at z>=7 — and clear of buses, which live at z>=minz-6).
    # "0" needs nothing (dark by absence; netspec never routes it).
    uses = {a for g in gates for a in g["args"]}
    if "1" in uses:
        stamp_wire(ctx, [(maxx + 3, 3)], "1")
        pos["1"] = (maxx + 3, 3)
        blocks.append((maxx + 4, 1, 3, "minecraft:redstone_block"))
        solid[(maxx + 4, 3)] = ("block", "1")
        for dx, dz in DIRS:
            ring(ctx, maxx + 4 + dx, 3 + dz, own("1"))
    # inputs: lever row on the bbox edge nearest the loads' centroid
    # (north minz-6, south maxz+6, tie south), pitched clear per edge.
    # Runs stay short: bus hugs the field, loads tap in. Loads come from
    # netspec (same cells the router targets — no second recs walk).
    netspec = build_netspec(recs, recipe, pos)
    # ponytail: input port approaches — TRIED AND REVERTED (twice, both
    # measured). A tile's apron seals its west-edge port, so alu1 OP1's leg
    # (-15,12)->(4,12) has NO flat and NO 3D path: x=3..0 at z=12 are the
    # NOT tile's reserved apron. Empty-ringing the port fixes the wall and
    # costs correctness instead: v1 (port + 4 neighbours, all nets) broke
    # example_xor's input lane outright; v2 (input nets, 3 cells west) made
    # example_and SIM MISMATCH — the opened approach lengthens the run, and
    # it reaches the OR junction at level 9 where the junction needs a
    # strong 15. The two failures are the real shape of this idea: opening a
    # port buys reach with signal strength, and the booster pass cannot pay
    # it back. Kept as evidence; a correct fix needs the booster to guarantee
    # 15 at every port (a `_plant_repeaters` change), not a wider hole.
    edge_n, edge_s = {}, {}
    # ponytail: each lever sits AT its lane, so d1 is zero-length. The old
    # code put the lever at its loads' centroid x (deep in the tile field)
    # and marched 100+ cells to the lane — a march that dies on any dense
    # field (alu1 OP1, decode3 C, every new candidate). Lane x is shared
    # with the router below (minx-2-4*SPREAD*index); the lever goes one
    # west so its stub IS the lane start. Levers stay banked along the
    # north edge (2-pitch in z) per the build contract.
    for k, name in enumerate(recipe["inputs"]):
        loads = netspec.get(name, {}).get('loads', [])
        if not loads:
            continue  # unused input: no lever, nothing to drive
        # ponytail: lane pitch doubles past 9 inputs. 10 input lanes at
        # 4*spread collide in the approach cone (alu4 B3/A1 touch); at
        # 8*spread each lane owns twice the room. Gated so the 16 green
        # builds (max 9 inputs, mux4) keep their exact geometry.
        _pitch = (8 if len(recipe["inputs"]) > 9 else 4) * _SPREAD
        lx = minx - 2 - _pitch * recipe["inputs"].index(name)
        lz = minz - 6 - 2 * len(edge_n)
        edge_n[name] = lz
        cx = lx - 1
        blocks.append((cx, 1, lz, "minecraft:lever[face=floor,facing=north,powered=false]"))
        solid[(cx, lz)] = ("lever", name)
        for dx, dz in DIRS:
            ring(ctx, cx + dx, lz + dz, own(name))
        # stub juts east along the empty lever row (west collides with
        # other lanes' columns; rows sit outside tile z-span so east runs
        # free until the lane turns north/south).
        stamp_wire(ctx, [(cx + 1, lz)], name)
        pos[name] = (cx + 1, lz)
    # ponytail: lamp taps stamped BEFORE routing, not after. tap_lamps picks
    # the first of four spots (E/S/N/W) that is clear of wire AND of foreign
    # wire BESIDE it. On the post-routing field a dense tile band has no such
    # spot left: alu1 died `lamp spot taken for Y at (239,95)` with OP0's run
    # filling E and S two cells out and Y's own boosters filling N and W. The
    # same search on the tile-only field has all four streets open, and the
    # tap then becomes ordinary fixed geometry the router routes around.
    # Cost: each lamp's 3x3 own-ring is a hard seal for foreign nets (the old
    # reason for the late stamp). Measured below, not assumed.
    tap_lamps(ctx, recipe, pos, 10**6, 10**6)
    # Snapshot which nets may sit beside each tile's torch host. Must run
    # after every tile AND the lamp taps are stamped (those are wire too) and
    # before any routing: from here on stamp_wire refuses a wire that would
    # power a foreign tile's host. See tiles.seal_tiles for the measurement.
    seal_tiles(ctx)
    # guard from stamped torches, exactly like layout.py:1419-1425.    # guard from stamped torches, exactly like layout.py:1419-1425.
    for x, y, zz, bid in blocks:
        if "wall_torch" in bid:
            guard.add((x, zz))
            face = bid.split("facing=")[1].rstrip("]")
            dx, dz = TORCH_BACK[face]
            guard.add((x + dx, zz + dz))
    paths = []
    # other nets' load cells are reserved: a candidate stepping on one
    # would steal a future port (then that net dies loud at its endpoint).
    # Halo (Chebyshev 1 around each foreign load): feeds must never sit
    # adjacent either (different nets side-touching = a vanilla short).
    allloads = {}
    for n2, spec in netspec.items():
        for cell in spec['loads']:
            allloads.setdefault(n2, set()).add(cell)
    halos = {}
    for net in netspec:
        if net in ("0", "1"):
            # "1" routes now (constant stubs need a driver); it carries no
            # halo of its own. "0" is dark by absence and never routes.
            halos[net] = frozenset()
            continue
        h = set()
        for n2, s in allloads.items():
            if n2 == net:
                continue
            for (lx, lz) in s:
                h.update((lx + ax, lz + az) for ax in (-1, 0, 1) for az in (-1, 0, 1))
        # ponytail: driver halos. Load halos protect future ports, but the
        # seal that kills is stamped on drivers (alu1 m0's driver pocketed
        # by O's feed to a SIBLING tile). Reserve every foreign driver +
        # Chebyshev-1 the same way. Own driver never penalizes self (skipped
        # as n2 == net). Steers _candidates scoring AND the astar fallback
        # (via congest below — astar takes no avoid set).
        for n2, spec in netspec.items():
            if n2 == net or n2 in ("0", "1"):
                continue
            drv2 = spec.get('drv') or pos.get(n2)
            if drv2 is None:
                continue
            h.update((drv2[0] + ax, drv2[1] + az) for ax in (-1, 0, 1) for az in (-1, 0, 1))
        halos[net] = frozenset(h)
    flow = {}
    inps = list(recipe["inputs"])
    # ponytail: input trunk rows — REVERTED (measured, kept as a note).
    # Routing each input's long E-W travel on reserved rows south of every
    # tile (open ground, always walks) fixed alu1's B/CIN legs, but
    # example_and went 182 green -> 314 SIM MISMATCH: the boosted trunk runs
    # bleed 15->5 before the hop dust and the OR junction reads weak. Two
    # failure classes at once is not a fix. Levers/loads keep the load-row
    # lane; the astar wrapper is what actually bought the CIN/B legs.
    # Transit segregation: recursive placement keeps runs short, but runs
    # still share columns without lanes — per-input N-S lanes in the west
    # field (strictly west of all tiles AND levers, pitch 4) give every
    # input private ground; E-W jogs cross them perpendicularly
    # (hop-able). Gate nets route first (short direct runs stamp before
    # lanes fill).
    # "1" is a routable net (constant stubs are real dust needing a
    # driver); "0" stays dark by absence and is never routed.
    gate_nets = sorted(n for n in netspec if n not in inps and n != "0")
    # ponytail: confinement ordering. A driver pocketed by already-stamped
    # wires dies loud at y=1 although ground existed earlier (alu1 m0 sealed
    # by O's feed: 27-cell pocket, 19-shadow boundary). Greedy: route the
    # most-confined bottleneck first, re-measuring after every net (shadows
    # are stamped wires, invisible at placement end). Ties break by name so
    # open fields keep sorted order; inputs keep lane order (positional).
    # Ceiling: greedy, no lookahead — blame restart below repairs its misses.
    def _cell_confined(n, cell):
        c = 0
        for ax, az in DIRS:
            nb = (cell[0] + ax, cell[1] + az)
            if ctx.solid.get(nb) is not None:
                c += 1
                continue
            w = ctx.wires.get((nb[0], 1, nb[1]))
            if w is not None and w != n:
                c += 1
                continue
            if nb in ctx.rings and n not in ctx.rings[nb]:
                c += 1
                continue
            if nb in guard:
                c += 1
                continue
            rp = ctx.repeaters.get((nb[0], 1, nb[1]))
            if rp is not None and rp[0] != n:
                c += 1
                continue
            if ctx.sup.get((nb[0], 1, nb[1])) not in (None, n):
                c += 1
        return c

    def _confined(n):
        # ponytail: bottleneck-first. The driver can sit in open field
        # while a load is tile-pocketed (alu1 m4: drv pocket 2084, load
        # pocket 194, disjoint) — driver-only confinement routes the
        # sealer first. Take the max over driver + loads.
        cells = []
        drv = netspec[n]['drv'] or pos.get(n)
        if drv is not None:
            cells.append(drv)
        cells.extend(netspec[n].get('loads', []))
        if not cells:
            return -1
        return max(_cell_confined(n, cell) for cell in cells)

    def _order(precede):
        # confinement-greedy order honoring (earlier, later) blame
        # constraints (topo: only nets with placed predecessors are ready).
        preds = {}
        for e, l in precede:
            preds.setdefault(l, set()).add(e)
        pending = list(gate_nets)
        out = []
        while pending:
            ready = [n for n in pending
                     if all(p in out for p in preds.get(n, ()))]
            if not ready:
                raise RuntimeError(f"compose: order cycle in {sorted(precede)}")
            ready.sort(key=lambda n: (-_confined(n), n))
            out.append(ready[0])
            pending.remove(ready[0])
        # _ORDER selects gates-first (proven) vs inputs-first (inputs get
        # clean ground; gates route around lanes). Set by compose()'s retry.
        if _ORDER == "inputs_first":
            return sorted(n for n in netspec if n in inps) + out
        return out + sorted(n for n in netspec if n in inps)

    def _blame(failed, ordered, stub_wires):
        # top foreign wired-net owner on the failed net's driver+load
        # pockets (y=1 BFS: solid/foreign-wire/foreign-ring/foreign-rep/
        # guard/sup/adacency; hops span singles, pockets are the seal).
        # Must be reorderable (a gate net), earlier this attempt (later nets
        # cast no shadow), and ROUTED (its wires postdate the placement-end
        # snapshot — tile stubs never move, so blaming them burns restarts:
        # alu1 O blamed m2/m3 stubs 5x). Inputs fail loud (lanes positional).
        # None if the seal is tile geometry.
        from collections import deque, Counter
        if failed not in gate_nets:
            return None
        seen = set()
        q = deque()
        for cell in ([netspec[failed]['drv'] or pos.get(failed)]
                     + list(netspec[failed].get('loads', []))):
            if cell is not None and cell not in seen:
                seen.add(cell)
                q.append(cell)
        own = Counter()
        seals = {}
        # ponytail: BFS is capped (30k cells). compose's field is unbounded
        # and early-attempt pockets can flood open ground — the cap bounds
        # RAM; blame from partial owners stays valid (Counter already fed).
        while q and len(seen) <= 30000:
            x, z = q.popleft()
            for ax, az in DIRS:
                nb = (x + ax, z + az)
                if nb in seen:
                    continue
                s = ctx.solid.get(nb)
                w = ctx.wires.get((nb[0], 1, nb[1]))
                if w is not None and w != failed:
                    own[w] += 1
                    seals.setdefault(w, []).append((nb[0], 1, nb[1]))
                    continue
                if s is not None and s[0] != 'cobble':
                    continue
                if nb in ctx.rings and failed not in ctx.rings[nb]:
                    continue
                rp = ctx.repeaters.get((nb[0], 1, nb[1]))
                if rp is not None and rp[0] != failed:
                    continue
                if (nb in guard
                        or ctx.sup.get((nb[0], 1, nb[1])) not in (None, failed)):
                    continue
                shadow = False
                for bx, bz in DIRS:
                    nbc = (nb[0] + bx, 1, nb[1] + bz)
                    nw = ctx.wires.get(nbc)
                    if nw is not None and nw != failed:
                        own[nw] += 1
                        seals.setdefault(nw, []).append(nbc)
                        shadow = True
                if shadow:
                    continue
                seen.add(nb)
                q.append(nb)
        try:
            cut = ordered.index(failed)
        except ValueError:
            return None
        for owner, _ in own.most_common():
            # ponytail: the owner's SEALING cells must postdate the snapshot.
            # A net with runs elsewhere but only stubs on the seal (alu1 O
            # vs AB) is tile geometry, not order — blaming it burns restarts.
            if (owner in gate_nets and owner != failed
                    and owner in ordered[:cut]
                    and (owner, failed) not in precede
                    and any(c not in stub_wires for c in seals.get(owner, ()))):
                return owner
        return None

    def _displace(failed, owner, death):
        """Move the sealer's wire instead of reordering (cycle-breaker).

        Order repair dead-ends on mutual seals (alu1 AB-t0-n1: every order
        dies). Displacement deletes the owner's runs, routes the failed net
        through the freed ground, then re-routes the owner around it —
        single-victim rip-up, depth 1, no chains. Uses only proven shapes
        (lwire with its candidates + astar fallback). Restores everything
        and re-raises the death error if any leg fails. Both nets join
        `routed`; the caller's order constraints between them go moot.
        """
        if failed in inps or owner in inps:
            raise death
        snap = (dict(ctx.wires), dict(sup), dict(ctx.solid), len(ctx.blocks))
        stub = wsnap[0]
        try:
            for n in (owner,):
                for (rn, cells) in [p for p in paths if p[0] == n]:
                    for c in cells:
                        if c not in stub and ctx.wires.get(c) == n:
                            del ctx.wires[c]
            for c, n in list(sup.items()):
                if n == owner:
                    del sup[c]
                    ctx.blocks[:] = [
                        b for b in ctx.blocks
                        if not (b[0] == c[0] and b[1] == c[1] and b[2] == c[2]
                                and "cobblestone" in b[3])]
                    if ctx.solid.get((c[0], c[2])) == ("cobble", owner):
                        del ctx.solid[(c[0], c[2])]
            paths[:] = [(n, p) for (n, p) in paths
                        if n != failed and n != owner]
            for n in (failed, owner):
                av = halos[n]
                dv = netspec[n]['drv'] or pos.get(n)
                for cell in sorted(netspec[n]['loads']):
                    paths.append((n, lwire(ctx, sup, guard, dv, cell, n, av)))
            routed.add(failed)
            routed.add(owner)
        except RuntimeError:
            ww, su, so, sb = snap
            ctx.wires.clear()
            ctx.wires.update(ww)
            sup.clear()
            sup.update(su)
            ctx.solid.clear()
            ctx.solid.update(so)
            del ctx.blocks[sb:]
            paths[:] = [(n, p) for (n, p) in paths
                        if n != failed and n != owner]
            raise death

    # ponytail: blame restart. Greedy order still seals nets (alu1: m0 by O,
    # m4 by o1 — the sealer always looks routable when measured). On a loud
    # death, blame the top sealing wire-owner, constrain failed-before-owner,
    # and re-run wiring from the placement-end snapshot (wiring is a pure
    # function of order; snapshot covers exactly what lwire mutates: wires,
    # sup, solid, appended blocks). Restarts fire only where today dies loud,
    # so green builds behave bit-identically. Bounded: 8 restarts, then loud.
    wsnap = (dict(ctx.wires), dict(sup), dict(ctx.solid), len(ctx.blocks))
    precede = set()
    if os.environ.get("RS_WATCH82"):
        print(f"WATCH after placement (82,1,29)={ctx.wires.get((82,1,29))}",
              flush=True)
    first_err = None
    last_pair = None
    displaced = set()
    paths = []
    routed = set()
    keep_staged = False
    for _attempt in range(25):
        try:
            ordered = _order(precede)
        except RuntimeError:
            # ponytail: order cycle = mutual seal (no static order works).
            # One displacement shot at the most recent blame pair (geometry
            # instead of order); the pair's order constraint goes moot.
            # Beyond that, report the true wall, not the bookkeeping failure.
            if (first_err is not None and last_pair is not None
                    and last_pair not in displaced and len(displaced) < 8):
                displaced.add(last_pair)
                precede.discard(last_pair)
                precede.discard((last_pair[1], last_pair[0]))
                try:
                    _displace(last_pair[0], last_pair[1], first_err)
                except RuntimeError:
                    raise RuntimeError(
                        f"{first_err} [order cycle in {sorted(precede)}]") from None
                last_pair = None
                try:
                    ordered = _order(precede)
                except RuntimeError:
                    raise RuntimeError(
                        f"{first_err} [order cycle in {sorted(precede)}]") from None
                keep_staged = True
            elif first_err is not None:
                raise RuntimeError(
                    f"{first_err} [order cycle in {sorted(precede)}]") from None
            else:
                raise
        if not keep_staged:
            paths = []
            routed = set()
        keep_staged = False
        need_restart = False
        for net in ordered:
            if net in routed:
                continue
            avoid = halos[net]
            drv = netspec[net]['drv'] or pos.get(net)
            # Load order decides how far each successive leg has to reach, and
            # a leg that starts far away is the one that crosses the other
            # inputs' cones. With 10+ inputs the (x,z)-lexicographic order
            # sends the last leg clean across the field. Nearest-first from
            # the port keeps every leg short. Gated at >9 inputs so the 13
            # green builds (max 9, mux4) keep their exact geometry.
            _loads = netspec[net]['loads']
            if net in inps and len(inps) > 9:
                _loads = sorted(_loads, key=lambda c: (abs(c[0] - drv[0])
                                                       + abs(c[1] - drv[1]), c))
            else:
                _loads = sorted(_loads)
            try:
                for cell in _loads:
                    if net in inps:
                        # ponytail: offset 8 / pitch 6 was TRIED and REVERTED.
                        # It does not move the measured wall: alu1 CIN's hop
                        # still lands its far foot on the neighbouring column
                        # (B@x6 vs n1@x8 — a gate port, not the input lane),
                        # 38 refusals unchanged, and small builds grew
                        # 182/396/250/282 -> 238/492/306/354 for nothing.
                        # (same _pitch as port placement above; lanes must align).
                        _pitch = (8 if len(inps) > 9 else 4) * _SPREAD
                        lx = minx - 2 - _pitch * inps.index(net)
                        d1 = lwire(ctx, sup, guard, drv, (lx, drv[1]), net, avoid)
                        # ponytail: ONE lane leg, not two. Splitting the
                        # N-S march (drv row -> load row) from the E-W
                        # approach pinned the turn cell (lx, load_row), and
                        # a turn cell is exactly where an already-routed
                        # input's E-W run crosses the lane column — a hop
                        # cannot save it (the hop needs its far foot on the
                        # path, so a blocked ENDPOINT is unhoppable).
                        # ctrl_decode OP2 died exactly there: `no ground for
                        # OP2: (-3,1) -> (-3,12)` with (-3,12) stamped by
                        # OP1. Merging hands the whole leg the candidate set,
                        # whose offset trunks jog the turn by u rows and then
                        # come back into the load. Lane discipline is intact:
                        # every candidate's zfirst base runs the N-S march at
                        # x=lx, only the final approach varies. On an open
                        # field cands[0] IS the old two legs concatenated
                        # (same cells, same order), so green builds are
                        # bit-identical — verified by scratch/blockhash.py.
                        d2 = lwire(ctx, sup, guard, (lx, drv[1]), cell, net, avoid)
                        paths.append((net, d1 + d2))
                    else:
                        paths.append((net, lwire(ctx, sup, guard, drv, cell, net, avoid)))
            except RuntimeError:
                # ponytail: drop the failed net's partial runs (their cells
                # restore away below; stale entries would plant diodes on air
                # and KeyError).
                paths[:] = [(n, p) for (n, p) in paths if n != net]
                if _attempt >= 24:
                    raise
                if first_err is None:
                    first_err = sys.exc_info()[1]
                owner = _blame(net, ordered, wsnap[0])
                if owner is None:
                    raise
                if (owner, net) in precede:
                    # direct cycle: order can't separate them; displace the
                    # sealer's wire once, then resume remaining nets.
                    if ((net, owner) in displaced or (owner, net) in displaced
                            or len(displaced) >= 8):
                        raise
                    displaced.add((net, owner))
                    precede.discard((owner, net))
                    last_pair = None
                    _displace(net, owner, sys.exc_info()[1])
                    print(f"compose displace: {net} rerouted around {owner}",
                          flush=True)
                    routed.add(net)
                    routed.add(owner)
                    continue
                last_pair = (net, owner)
                precede.add((net, owner))
                print(f"compose restart {_attempt + 1}: {net} sealed by {owner}; precede={sorted(precede)}", flush=True)
                ww, su, so, sb = wsnap
                ctx.wires.clear()
                ctx.wires.update(ww)
                sup.clear()
                sup.update(su)
                ctx.solid.clear()
                ctx.solid.update(so)
                del ctx.blocks[sb:]
                # The wire field just went back to the placement-end
                # snapshot, so any staged work is void: keep_staged would
                # carry `routed` across the restart, and a net still listed
                # there is SKIPPED with no run to its loads. Measured on
                # ctrl_decode: net OP0's port at (112,29) held n1's dust and
                # OP0 had no route at all, while the build sailed through
                # check_shorts and check_opens.
                keep_staged = False
                need_restart = True
                break
            routed.add(net)
        if need_restart:
            continue
        break
    for net, full in paths:
        for u, v in zip(full, full[1:]):
            d = (v[0] - u[0], v[2] - u[2])
            flow.setdefault((u[0], u[1], u[2]), set()).add(d)
            flow.setdefault((v[0], v[1], v[2]), set()).add(d)
    for net, full in paths:
        _plant_repeaters(ctx, full, net, flow)
    if os.environ.get("RS_WATCH82"):
        print(f"WATCH after boost (82,1,29)={ctx.wires.get((82,1,29))} "
              f"rep={ctx.repeaters.get((82,1,29))}", flush=True)
    # normalize to non-negative coords (lanes run west of zero; the shared
    # tap routine bounds-checks 0<=lx<W like the maze field). Shift every
    # live structure; recs is dead past wiring (netspec already built).
    _minx = min([x for (x, z) in ctx.solid] + [x for (x, _, z) in ctx.wires] + [x for (x, _, z) in ctx.repeaters])
    _minz = min([z for (x, z) in ctx.solid] + [z for (x, _, z) in ctx.wires] + [z for (x, _, z) in ctx.repeaters])
    _dx, _dz = max(0, 1 - _minx), max(0, 1 - _minz)
    global _last_shift
    _last_shift = (_dx, _dz)
    if _dx or _dz:
        ctx.blocks[:] = [(x + _dx, y, z + _dz, b) for x, y, z, b in ctx.blocks]
        # clear+update (never pop-and-set: an eastward shift overwrites
        # not-yet-moved keys and cascades corruption through the dict).
        _nw = {(x + _dx, y, z + _dz): v for (x, y, z), v in ctx.wires.items()}
        ctx.wires.clear()
        ctx.wires.update(_nw)
        _ns = {(x + _dx, z + _dz): v for (x, z), v in ctx.solid.items()}
        ctx.solid.clear()
        ctx.solid.update(_ns)
        _nr = {(x + _dx, z + _dz): v for (x, z), v in ctx.rings.items()}
        ctx.rings.clear()
        ctx.rings.update(_nr)
        _nj = {(x + _dx, z + _dz): v for (x, z), v in ctx.junctions.items()}
        ctx.junctions.clear()
        ctx.junctions.update(_nj)
        _nrep = {(x + _dx, y, z + _dz): v for (x, y, z), v in ctx.repeaters.items()}
        ctx.repeaters.clear()
        ctx.repeaters.update(_nrep)
        for _n in list(pos.keys()):
            _p = pos[_n]
            pos[_n] = (_p[0] + _dx, _p[1] + _dz)
        _nsup = {(x + _dx, y, z + _dz): v for (x, y, z), v in sup.items()}
        sup.clear()
        sup.update(_nsup)
        _g = {(x + _dx, z + _dz) for (x, z) in guard}
        guard.clear()
        guard.update(_g)
    # ponytail: a load must never hold a FOREIGN net. "holds nothing" is
    # legal - a tile's port can be a zero-wire tap satisfied by adjacency to
    # the driver's own cell, so an unwired load is normal and every green
    # build has some. Holding a different net is not normal.
    # Coordinates: netspec is pre-shift, wires are post-shift, so translate.
    for _n, _s in netspec.items():
        for _c in _s["loads"]:
            _c3 = (_c[0] + _dx, 1, _c[1] + _dz)
            _own = ctx.wires.get(_c3)
            if _own is not None and _own != _n:
                raise RuntimeError(f"compose: load {_c} of {_n} holds {_own}")
            _rep = ctx.repeaters.get(_c3)
            if _rep is not None and _rep[0] != _n:
                raise RuntimeError(
                    f"compose: load {_c} of {_n} holds a {_rep[0]} repeater")
    check_shorts(wires, junctions, blocks)
    check_opens(wires, junctions, repeaters, solid, pos, blocks)
    return finish_assembly(blocks, solid, wires, rings, junctions, repeaters, pos)


# Placement spread factor (module-global so _compose_once's spacing reads
# it). 1 = the tight layout every green build was verified on.
_SPREAD = 1

# Routing order: gates-first is proven; inputs-first gives inputs clean
# ground (measured: alu1's OP1/OP0 input collision vanishes, micro1 stays
# green). compose() tries gates-first at every spread, then inputs-first.
_ORDER = "gates_first"

# Trunk jog depth candidates. SHORT is the proven baseline (every currently
# green build verifies on it). LONG reaches past a sealed band but can let a
# long input march wander unsealed (add2 lost all four input ports on LONG),
# so compose() only escalates to it after SHORT has failed everywhere.
_JOGS_SHORT = (2, 4, 6, 8, 10, 12)
_JOGS_LONG = (2, 4, 6, 8, 10, 12, 16, 20, 24, 32)
_JOGS = _JOGS_SHORT

# Total wall-clock ceiling for the whole retry ladder, so a hard recipe can
# never spin forever (20 attempts x unbounded astar = a hang). 0 = no cap.
# REDSTONE_MAX_SECS still bounds a single attempt inside layout/sim.
_COMPOSE_SECS = float(os.environ.get("REDSTONE_COMPOSE_SECS", "0") or 0)

# Routing/geometry failures worth retrying with more room (NOT logic or
# sim failures — those are deterministic and spread cannot fix them).
_RETRYABLE = ("no ground", "no route", "OPEN ", "blocked", "lamp spot taken",
              "order cycle", "SHORT", "touches", "repeater loop",
              "compose blocked")


def compose(recipe):
    """Deterministic place+route, retrying wider/reordered/deeper on failure.

    Ladder: short jogs across spreads 1..5 x {gates_first, inputs_first},
    then long jogs across the same grid. Every currently-green build
    succeeds on the FIRST attempt (short, spread 1, gates-first)
    bit-identical, so the gates never move. Only a routing/geometry death
    escalates. The build may sprawl across chunks (wires run long,
    repeaters carry them).
    """
    global _SPREAD, _ORDER, _JOGS
    last = None
    deadline = time.monotonic() + _COMPOSE_SECS if _COMPOSE_SECS else None
    # REDSTONE_FORCE="spread,order,jog" pins one rung (diagnostics: bisect a
    # single config instead of climbing the whole ladder).
    force = os.environ.get("REDSTONE_FORCE", "").strip()
    if force:
        f_spread, _, rest = force.partition(",")
        f_order, _, f_jog = rest.partition(",")
        attempts = [(f_jog or "short", int(f_spread), f_order or "gates_first")]
    else:
        attempts = [(j, s, o)
                    for j in ("short", "long")
                    for s in (1, 2, 3, 4, 5, 6, 8, 10)
                    for o in ("gates_first", "inputs_first")]
    for i, (jog, spread, order) in enumerate(attempts):
        _SPREAD, _ORDER = spread, order
        _JOGS = _JOGS_SHORT if jog == "short" else _JOGS_LONG
        try:
            return _compose_once(recipe)
        except RuntimeError as e:
            last = e
            if (i == len(attempts) - 1
                    or (deadline and time.monotonic() > deadline)
                    or not any(k in str(e) for k in _RETRYABLE)):
                raise
            print(f"compose {jog} spread {spread} {order} failed "
                  f"({str(e)[:60]}); retrying", flush=True)
    raise last


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

    from recipe import parse_recipe, expand_gates, eval_net
    from sim import sim_verify
    _r = parse_recipe("IN a, b\nOUT y\ny = a AND b\n")
    _out, _size, _io = compose(_r)
    sim_verify(_r, _out, _io, quiet=True)
    print("compose ok: AND verifies through the sim gate")
    _fan = {"inputs": ["s", "x", "y", "z"], "outputs": ["o1", "o2", "o3"],
            "gates": [{"out": "t", "op": "AND", "args": ["s", "x"]},
                      {"out": "o1", "op": "AND", "args": ["t", "y"]},
                      {"out": "o2", "op": "AND", "args": ["t", "z"]},
                      {"out": "o3", "op": "AND", "args": ["t", "s"]},
                      {"out": "big", "op": "OR", "args": ["o1", "o2"]}]}
    _fx = expand_gates(_fan["gates"], _fan["inputs"])
    assert any(g["out"].startswith("_bf") for g in _fx), "want real buffers"
    _sx = _strip_buffers(_fx)
    assert not any(g["out"].startswith("_bf") for g in _sx), _sx
    from itertools import product as _prod
    for _bits in _prod([0, 1], repeat=4):
        _v = dict(zip(["s", "x", "y", "z"], _bits))
        _a = eval_net(dict(_fan, gates=_sx), _v)
        _b = eval_net(dict(_fan, gates=_fx), _v)
        assert all(_a[o] == _b[o] for o in ["o1", "o2", "o3", "big"]), _v
    print("buffers ok: relay chains inline to identical logic on all vectors")
