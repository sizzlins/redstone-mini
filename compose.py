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
from layout import build_netspec, check_shorts, check_opens, finish_assembly, _support, bridge_plan, bridge_plan_tall, astar
from layout import _sup3 as _layout_sup3, _src3 as _layout_src3, _flood3 as _layout_flood3
from layout import _torch_hosts, _inverter_ring_at

# last compose() run's coordinate shift (netspec frame -> check frame),
# for offline probes. Not part of the build contract.
_last_shift = (0, 0)

# last _compose_once's live ctx (partition merge reads tile ports). Write-only
# hook, same precedent as _last_shift; never read on the standard path.
_last_ctx = None

# Composer's vertical envelope for the astar fallback (env-tunable).
# Narrow y=1..3 is tried first (the proven band); the full envelope only
# runs if narrow finds nothing, because a marginal wide success poisons
# downstream routing worse than a loud failure.
_WIDE_YMIN = int(os.environ.get("REDSTONE_COMPOSE_YMIN", "-4"))
_WIDE_YMAX = int(os.environ.get("REDSTONE_COMPOSE_YMAX", "6"))

_VEC = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}


def _hop_free(ctx, sup, guard, feet, supports, dusts, victim, net, apex=3):
    # adapted bridge_free (layout.py:582-634): unbounded field, plus sup.
    # apex=4 for the tall hop (air check one above the apex).
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
    if ctx.wires.get((fx, apex + 1, fz)) is not None:
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
    # The proven y=1..4 band runs first; the full vertical envelope
    # (trenches + high decks) only runs if narrow finds nothing.
    # (Narrow starts at 1, not 0: ground cobble roofs trench slopes, so a
    # downward first attempt self-lids its own candidates — layout.py
    # documents the measured case. Trenches come via the wide band.)
    # ponytail: REDSTONE_NO3D=1 skips astar overflights entirely (flat
    # corridors + flat astar + _walk hops only). Hier stitches fly y=2/3
    # highways over whole partition fields and slope-short against partition
    # flights they cannot see (measured: stitch C2-hop vs band-5 n0_5
    # flight, SHORT3D, un-liddable because the lid cell holds own dust).
    # _walk's 5-cell hops stay (single columns, lidded); only the long
    # blind flights go. Env-gated; greens never set it.
    _bands3d = [] if os.environ.get("REDSTONE_NO3D") else (
        (1, 4), (_WIDE_YMIN, _WIDE_YMAX))
    for _ymin, _ymax in _bands3d:
        _fly = _astar_wrap(ctx, sup, guard, a, b, net, avoid, flat=False,
                           ymin=_ymin, ymax=_ymax)
        if not (_fly and any(c[1] >= 2 for c in _fly)):
            continue
        fly = _fly
        needs = []
        try:
            _fcells = set(fly)
            # ponytail: a y>=2 `sup` entry is a COMMITTED pillar -- the
            # block list already owes a cobblestone there (this path's
            # own needs, _walk's hop/bridge supports, or layout's route).
            # Dust on top of one is two blocks in one cell and
            # finish_assembly rejects the WHOLE build (measured on the
            # hier input fan-out: R1Q1's pillar at (1852,2,25) with its
            # own dust over it -> "duplicate block"). _support reports
            # such a cell as reusable (returns None), so the test has to
            # be on the flight itself, not on `needs`. Fatal for every
            # net including the pillar's own: the block is committed.
            if any(c in sup for c in _fcells if c[1] >= 2):
                raise RuntimeError("dust over own pillar")
            for cell in fly:
                if cell[1] == 1:
                    continue
                r = _support(cell, net, ctx.solid, ctx.wires, sup,
                             ctx.repeaters, guard)
                if r is False:
                    raise RuntimeError("support sealed")
                if r is not None and r not in sup and r not in needs:
                    # ponytail: a one-cell DESCENT makes the lower step
                    # the support for the cell above it, so the flight
                    # would put dust and cobble in one block. The
                    # self-lid test below cannot see it -- it asks
                    # hi.y-1 in cobf, and that cell is in `needs` only
                    # because it is about to become dust too. Refuse the
                    # flight; the next y band / strategy / rung retries.
                    if r in _fcells:
                        raise RuntimeError("support under own dust")
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
        _tall_done = False
        if not _hop_free(ctx, sup, guard, feet, supports, dusts, (vx, 1, vz), net):
            # ponytail: tall hop fallback (7-cell y=4 staircase). The short
            # footprint sealed but the wider/higher one may be free. Same
            # physics, same guards; short stays primary so green builds keep
            # their exact geometry.
            _b3 = (vx - 3 * d[0], vz - 3 * d[1])
            _f3 = (vx + 3 * d[0], vz + 3 * d[1])
            if _b3 in seqflats and _f3 in seqflats:
                _bi3, _fi3 = seqflats.index(_b3), seqflats.index(_f3)
                _straight3 = all(
                    (qx - vx) * d[1] == (qz - vz) * d[0]
                    for t in range(_bi3, _fi3 + 1)
                    for (qx, qz) in [seqflats[t]])
                if _bi3 < j <= _fi3 and _straight3:
                    _axis3 = "ns" if d[0] == 0 else "ew"
                    _feet3 = [(_b3[0], 1, _b3[1]), (_f3[0], 1, _f3[1])]
                    _tp = bridge_plan_tall(vx, vz, _axis3)
                    assert (set(_feet3) | set(_tp[1]) | set(_tp[2])) == \
                        (set(_tp[0]) | set(_tp[1]) | set(_tp[2])), (_feet3, _tp)
                    if _hop_free(ctx, sup, guard, _feet3, _tp[1], _tp[2],
                                 (vx, 1, vz), net, apex=4):
                        _ok3 = True
                        for _k in (1, 2):
                            _bc = (vx - _k * d[0], vz - _k * d[1])
                            if ctx.wires.get((_bc[0], 1, _bc[1])) == net:
                                if not (done and done[-1] == (_bc[0], 1, _bc[1])):
                                    _ok3 = False
                                    break
                                del ctx.wires[(_bc[0], 1, _bc[1])]
                                done.pop()
                        for _k in (1, 2):
                            _fc = (vx + _k * d[0], vz + _k * d[1])
                            if ctx.wires.get((_fc[0], 1, _fc[1])) not in (None, net):
                                _ok3 = False
                                break
                        if _ok3:
                            _bad = _supports_free(_tp[1], ctx)
                            if _bad:
                                raise RuntimeError(
                                    f"bridge support lands on wire at {_bad[0]}")
                            for sx, sy, sz in _tp[1]:
                                sup[(sx, sy, sz)] = net
                                ctx.blocks.append((sx, sy, sz, "minecraft:cobblestone"))
                                if sy == 1:
                                    ctx.solid.setdefault((sx, sz), ("cobble", net))
                            for dx_, dy_, dz_ in _tp[2]:
                                stamp_wire(ctx, [(dx_, dy_, dz_)], net)
                                done.append((dx_, dy_, dz_))
                            for q in ((_b3), (victim), (_f3)):
                                skip.add(q)
                            for q in ((vx - 2 * d[0], vz - 2 * d[1]),
                                      (vx - d[0], vz - d[1]),
                                      (vx + d[0], vz + d[1]),
                                      (vx + 2 * d[0], vz + 2 * d[1])):
                                skip.add(q)
                            stamp_wire(ctx, [(_f3[0], _f3[1])], net)
                            done.append((_f3[0], 1, _f3[1]))
                            j = _fi3 + 1
                            _tall_done = True
            if not _tall_done:
                raise RuntimeError(f"compose: no ground for {net}: {a} -> {b}")
        if _tall_done:
            continue
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
        _bad = _supports_free(supports, ctx)
        if _bad:
            raise RuntimeError(f"hop support lands on wire at {_bad[0]}")
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


def _ends_ok(ctx, net, cx, cy, cz, dx, dz):
    # a diode may only sit between its own dust: back and front cells must
    # both carry this net (bare defaults pass — an unstamped front gets its
    # dust from the same run; a foreign front would be driven backwards).
    # Measured: R1Q2's east booster fired straight into R0Q2's stub dust,
    # forcing R0Q2=1 whenever R1Q2=1 (bit2 XOR/AND wrong). Checkers are
    # diode-blind (no dust touch), so the planter must not plant it.
    _bd = (cx - dx, cy, cz - dz)
    _fd = (cx + dx, cy, cz + dz)
    if ctx.wires.get(_bd, net) != net or ctx.wires.get(_fd, net) != net:
        return False
    # ponytail: no booster may push power into a tile torch that feeds this
    # same net back — one inverter plus one wire is a ring, and a ring hunts
    # forever instead of settling. Found on alu4 (2026-10-02): OP1x_3's booster
    # at (2044,1,35) drove the host of the tile torch at (2044,1,34), which
    # drives OP1x_3, latching the handoff (18059 churn cells, 15 of 24 sampled
    # vectors hunting). Neither the same-net front/back test above nor the
    # dust-only loop flooders can see it: the ring leaves the dust THROUGH a
    # torch. The torch host map is cached on ctx because tile torches never
    # move once placed, and this runs per candidate (alu4 plants ~2400).
    if getattr(ctx, "torch_hosts_n", -1) != len(ctx.blocks):
        ctx.torch_hosts = _torch_hosts(ctx.blocks)
        ctx.torch_hosts_n = len(ctx.blocks)
    return _inverter_ring_at(_fd, net, ctx.wires, ctx.torch_hosts) is None


def _supports_free(cells, ctx):
    """Support cells that cannot take a pillar: a cell already holding wire or
    a repeater is a cell the run itself (or a foreign one) occupies, and one
    cell is one block.

    ponytail: found on alu4 (2026-10-02), where a support stamp landed on the
    run's own dust at 24 cells in a 3-level input-bank staircase (OP1/B2/B3/
    OP0x_3). The sim read both blocks and called it supported; vanilla refuses
    dust on dust, so all 24 popped on paste. layout._support has refused this
    since the beginning, but compose's bridge/hop sites stamp their own
    supports and never asked. Returns the offenders so the caller can refuse
    the strategy and try another. A cobble already there is fine (idempotent).
    """
    return [c for c in cells
            if c in ctx.wires or c in ctx.repeaters]


def _plant_repeaters(ctx, cells, net, flow, end_boost=False, fresh=None,
                     own=None):
    # two passes per leg: forward every 8 (feeds hop zones) and backward
    # every 8 from the load end (tail freshness — the latch S-row needs
    # level 9 at its port). Hop dusts break straight triples, so one
    # direction alone strands the other side; over-boosting is cheap
    # (block count is reported, never scored). Vanilla facing points
    # output->input (toward the driver), so emission negates travel.
    # ponytail: end_boost (hier stitches only) plants one extra repeater at
    # the nearest straight triple to the ENDPOINT. Every-8 leaves the endpoint
    # up to 7 cells past the last booster (level 7), and a consumer-side tail
    # that was boosted for a lever-driven 15 (its own partition sim) dies on
    # 7 (measured: A0B0 stub reads 7, 8-cell tail to dark, Y1 wrong). One more
    # diode near the end delivers 14-15 and the tail survives. Default off:
    # partition and green geometry never see it.
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
            # ponytail: fresh-only (hier stitches). Planting on pre-existing
            # dust risks facing against that run's own boosters: opposite
            # diodes on one run close a bistable loop (measured: AL_AB3 loop
            # at (3042,1,60), front joins back). Fresh street dust has no
            # prior flow, so facing travel is always safe there. Shared with
            # the standard path as default None (plant anywhere straight).
            if fresh is not None and (cells[k][0], cells[k][1], cells[k][2]) not in fresh:
                dist = 0
                continue
            # ponytail: never on TILE dust (own=). A tile's own run is
            # delay-critical by construction — place_xor merges two
            # comparator tails through two facing diodes, and a booster
            # landing between them faces the wrong way and cuts the merge.
            # Measured: AL_X2 went dark in the merged cpu4 build (Y2 wrong)
            # while band 6 simmed green standalone, because the band sim runs
            # on `out` and boosting happens after. `own` is the placement-end
            # wire snapshot, so a routed cell is never in it.
            if own is not None and (cells[k][0], cells[k][1], cells[k][2]) in own:
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
            # y<=0 trench likewise needs its stamped pillar below.
            if dist >= 8 and (dx, dz) == (nx - cx, nz - cz) and (dx, dz) in _VEC \
                    and py == cy == ny \
                    and _ends_ok(ctx, net, cx, cy, cz, dx, dz):
                if cy != 1 and not any(
                        b[:3] == (cx, cy - 1, cz) and "cobblestone" in b[3]
                        for b in ctx.blocks):
                    continue
                del ctx.wires[(cx, cy, cz)]
                # ponytail: vanilla facing points output->input (toward the
                # driver), so negate travel. Sim stores travel (negates back).
                ctx.repeaters[(cx, cy, cz)] = (net, _VEC[(-dx, -dz)])
                dist = 0
    if end_boost and len(cells) > 3:
        for k in range(len(cells) - 2, 0, -1):
            if (cells[k][0], cells[k][1], cells[k][2]) in ctx.repeaters:
                break  # an earlier diode already covers the run-in
            if own is not None and (cells[k][0], cells[k][1], cells[k][2]) in own:
                continue  # tile dust: see the guard in the main pass
            (px, py, pz), (cx, cy, cz), (nx, ny, nz) = cells[k - 1], cells[k], cells[k + 1]
            if len(flow.get((cx, cy, cz), {(0, 0)})) != 1:
                continue
            dx, dz = cx - px, cz - pz
            if ((dx, dz) == (nx - cx, nz - cz) and (dx, dz) in _VEC
                    and py == cy == ny
                    and _ends_ok(ctx, net, cx, cy, cz, dx, dz)
                    and not (cy != 1 and not any(
                        b[:3] == (cx, cy - 1, cz) and "cobblestone" in b[3]
                        for b in ctx.blocks))):
                del ctx.wires[(cx, cy, cz)]
                ctx.repeaters[(cx, cy, cz)] = (net, _VEC[(-dx, -dz)])
                break
        # ponytail: same for the HEAD. Latch Q tails are ~10 dust cells, so
        # a register fan-out stitch starts at level ~5 and the every-8
        # planter's first diode (8 cells out) never fires — measured: R0Q0's
        # stitch lit 5 cells then dark for 850, whole R1/R0 banks unreadable.
        # One diode on the first straight flat triple re-drives the weak
        # head to 15 (its back is the live tail, so it always fires when the
        # driver does; a bare driver leaves it dark and the open stays loud).
        for k in range(1, len(cells) - 1):
            if (cells[k][0], cells[k][1], cells[k][2]) in ctx.repeaters:
                break  # head already driven
            if own is not None and (cells[k][0], cells[k][1], cells[k][2]) in own:
                continue  # tile dust: see the guard in the main pass
            (px, py, pz), (cx, cy, cz), (nx, ny, nz) = cells[k - 1], cells[k], cells[k + 1]
            if len(flow.get((cx, cy, cz), {(0, 0)})) != 1:
                continue
            dx, dz = cx - px, cz - pz
            if ((dx, dz) == (nx - cx, nz - cz) and (dx, dz) in _VEC
                    and py == cy == ny
                    and _ends_ok(ctx, net, cx, cy, cz, dx, dz)
                    and not (cy != 1 and not any(
                        b[:3] == (cx, cy - 1, cz) and "cobblestone" in b[3]
                        for b in ctx.blocks))):
                del ctx.wires[(cx, cy, cz)]
                ctx.repeaters[(cx, cy, cz)] = (net, _VEC[(-dx, -dz)])
                break


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
    # ponytail: territorial bands. Each BAND owns an x territory TERR_W wide;
    # streets between territories stay empty for cross-band trunks. Clamp +
    # modulo keep every tile inside its own territory; the south-march below
    # resolves whatever the clamp collides with. Off unless _TERR (fallback
    # rung only), so standard placement is byte-identical.
    _bands = sorted({gg.get("band", 0) for gg in gates}) if _TERR else []
    _base = {b: 6 + i * _TERR_W for i, b in enumerate(_bands)}
    _band_topx = dict(_base)
    topx = 6
    for i, g in enumerate(ordered):
        _gb = g.get("band", 0) if _TERR else None
        drvs = [a for a in g["args"] if a in placed]
        if not drvs:
            if _TERR:
                ox, gz = _band_topx[_gb], 12
                _band_topx[_gb] += 30 * _SPREAD
            else:
                ox, gz = topx, 12
                topx += 30 * _SPREAD
        else:
            bottom = max(z for a in drvs for (_, z) in placed[a][3])
            n = sum(len(placed[a][3]) for a in drvs)
            cx = sum(x for a in drvs for (x, _) in placed[a][3]) // n
            gz = bottom + 8 * _SPREAD
            ox = max(4, cx)
            if _TERR:
                ox = max(_base[_gb], ox)
            while any(not _expanded(g["op"], ox, gz).isdisjoint(u) for u in used_fp):
                ox += 2 * _SPREAD
            if _TERR and ox - _base[_gb] >= _TERR_W:
                ox = _base[_gb] + (ox - _base[_gb]) % _TERR_W
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
    # ponytail: hier edge nets defer (levered on the producer-facing edge
    # below, not the north row). Only hier subs / EDGE lines carry them.
    _edgemap = recipe.get("edge", {})
    _edge = set(_edgemap)
    for k, name in enumerate(recipe["inputs"]):
        loads = netspec.get(name, {}).get('loads', [])
        if not loads:
            continue  # unused input: no lever, nothing to drive
        if name in _edge:
            continue  # edge lever below
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
    # ponytail: hier edge levers. A boundary input levered on the north row
    # buries its stub in the live lever bank; the stitch must then cross the
    # whole consumer field to reach it (measured: t23 no-ground even at 33
    # cells into a north stub). On the edge FACING its producer the stub is
    # one street-crossing from the driver. Stub juts away from the field
    # (into the street side); lane legs work unchanged from pos. z = median
    # load row keeps legs short. Standard recipes never carry west/east keys.
    for _side, _sgn in (("W", -1), ("E", 1)):
        _enets = sorted(n for n, s in _edgemap.items() if s == _side)
        # ponytail: minx/maxx are the tile bbox; lanes live west of minx, so
        # a west stub column must clear them (lane pitch 4*spread per input).
        _x0 = (minx - 2 - 4 * _SPREAD * len(recipe["inputs"]) - 4
               if _side == "W" else maxx + 6)
        for _i, name in enumerate(_enets):
            loads = netspec.get(name, {}).get('loads', [])
            if not loads:
                continue
            _zc = sorted(c[1] for c in loads)[len(loads) // 2]
            cx = _x0 + _sgn * 2 * _i
            blocks.append((cx, 1, _zc, "minecraft:lever[face=floor,facing=north,powered=false]"))
            solid[(cx, _zc)] = ("lever", name)
            for dx, dz in DIRS:
                ring(ctx, cx + dx, _zc + dz, own(name))
            stamp_wire(ctx, [(cx + _sgn, _zc)], name)
            pos[name] = (cx + _sgn, _zc)
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
        # REDSTONE_ORDER_SEED: diversify tie-breaks for parallel search.
        # _confined ties are broken by name deterministically; with a seed
        # they break by hash(seed:name), giving each seed a different
        # starting trajectory through order space. Precede constraints still
        # hold (topology preserved, only ties shuffled). Off by default:
        # greens keep exact name order. O(1) per comparison.
        _oseed = os.environ.get("REDSTONE_ORDER_SEED")
        def _tie(n):
            if not _oseed:
                return n
            import hashlib as _hl
            return _hl.md5(f"{_oseed}:{n}".encode()).hexdigest()
        while pending:
            ready = [n for n in pending
                     if all(p in out for p in preds.get(n, ()))]
            if not ready:
                raise RuntimeError(f"compose: order cycle in {sorted(precede)}")
            ready.sort(key=lambda n: (-_confined(n), _tie(n)))
            out.append(ready[0])
            pending.remove(ready[0])
        if _TERR:
            # ponytail: intra-band nets first (short local runs stamp before
            # cross-band trunks need the streets). Stable partition: relative
            # confinement order preserved inside each class.
            _prod = {gg["out"]: gg.get("band", 0) for gg in gates}
            _cons = {}
            for gg in gates:
                for a in gg["args"]:
                    _cons.setdefault(a, set()).add(gg.get("band", 0))
            def _cross(n):
                return bool(_cons.get(n, set()) - {_prod.get(n)})
            out = [n for n in out if not _cross(n)] + [n for n in out if _cross(n)]
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
    # so green builds behave bit-identically. 25 restarts: precede constraints
    # converge, so more orders do not help (100 was tried: 50min per rung).
    # Diversity comes from REDSTONE_ORDER_SEED across processes.
    # Rule 7: restarts respect the compose() deadline. 25 restarts x 30s
    # routing = 12min per rung; without this check the ladder's
    # REDSTONE_COMPOSE_SECS never fires mid-rung and a doomed rung grinds.
    wsnap = (dict(ctx.wires), dict(sup), dict(ctx.solid), len(ctx.blocks))
    # ponytail: tile-owned dust, snapshotted at placement end. A booster may
    # only sit on ROUTED cells: a tile's own output run is delay-critical by
    # construction (place_xor doles two facing diodes to merge two comparator
    # tails, and a booster between them faces the wrong way and cuts the
    # merge). Measured: a booster planted on AL_X2's own Odust turned the
    # XOR dark in the merged cpu4 build while the band simmed green
    # standalone — the same cells, the tile never re-verified after boosting.
    tile_dust = frozenset(ctx.wires)
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
        if _DEADLINE is not None and time.monotonic() > _DEADLINE:
            if first_err is not None:
                raise first_err
            raise RuntimeError("compose: deadline exceeded before first route")
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
        _plant_repeaters(ctx, full, net, flow, own=tile_dust)
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
    global _last_ctx
    _last_ctx = ctx
    return finish_assembly(blocks, solid, wires, rings, junctions, repeaters, pos)


# Space between merged partitions. Wide on purpose: the stitch has to jog
# around a whole field to reach a boundary port (measured: with a 60-cell
# street every hop row was blocked, because "the whole span is empty" fails
# the moment it crosses any tile). The street costs blocks — reported, never
# scored — and buys the route a corridor.
_HIER_GAP = int(os.environ.get("REDSTONE_HIER_GAP", "160"))

# Hard kill for one pinned band rung (REDSTONE_HIER_RUNG_SECS, default 90s).
_RUNG_SECS = float(os.environ.get("REDSTONE_HIER_RUNG_SECS", "90") or 90)


def _hier_ctx(d):
    # Child state comes back as plain dicts (SimpleNamespace does not survive
    # the spawn boundary), so rewrap for the merge, which reads .blocks/.pos/
    # .recs attributes like the in-process ctx does.
    return SimpleNamespace(**d)


def _rung_worker(conn, sub, force):
    # Module level, not a closure: Windows spawn re-imports __main__ and
    # pickles the target by reference (a nested def dies with
    # "module '__main__' has no attribute ..."). State comes back as plain
    # dicts for the same reason (SimpleNamespace pickles by reference).
    os.environ["REDSTONE_FORCE"] = force
    try:
        out = compose(sub)
        # ponytail: the partition sim gate runs HERE, not in the parent. The
        # merge reads pctx (the UNSHIFTED tables) and never reads `out` at all
        # (compose_hier_parts unpacks it and ignores it) -- `out` existed only
        # to be handed to sim_verify here. So doing the sim in the child drops
        # a whole shifted block list from the pipe: pickling was 7.9s of a 42s
        # profiled compose, 573 dumps for 106 children. It also parallelises
        # the gate, which was running serially in the parent between bands.
        # A partition that routes but miscomputes (measured: band-1 COUT dark
        # standalone) still poisons the merge if unchecked, so the gate must
        # not be dropped -- only moved.
        if sub["outputs"]:
            from sim import sim_verify as _sv
            _sv(sub, out[0], out[2], quiet=True)
        c = _last_ctx
        conn.send(("ok", (None, out[1], out[2]),
                   {"blocks": c.blocks, "solid": c.solid,
                    "rings": c.rings, "wires": c.wires,
                    "junctions": c.junctions,
                    "repeaters": c.repeaters, "pos": c.pos,
                    "sup": c.sup, "recs": c.recs}, _last_shift))
    except RuntimeError as e:
        conn.send(("err", str(e)))
    except Exception as e:  # never let a child wedge the parent
        conn.send(("err", f"{type(e).__name__}: {e}"))
    finally:
        conn.close()


def _rung_child(sub, force, secs):
    """compose(sub) under REDSTONE_FORCE in a killable child.

    Returns (result, msg): result is (out, ctx, shift) on success, a string
    on RuntimeError, or None when the child was hard-killed at `secs`.
    Rule 7 needs a KILL, not a polled deadline: a pinned rung is one
    _compose_once and nothing inside it checks a clock (measured: a rung
    burning >11 min with no output, twice). The child is spawned, joined
    with a timeout, then terminate()d — no unbounded wait, ever.
    """
    import multiprocessing as _mp
    parent, child = _mp.Pipe(duplex=False)
    p = _mp.Process(target=_rung_worker, args=(child, sub, force), daemon=True)
    p.start()
    child.close()
    got = None
    if parent.poll(secs):
        try:
            got = parent.recv()
        except EOFError:
            got = ("err", "child died (EOF)")
    p.join(2)
    if p.is_alive():
        p.terminate()
        p.join(5)
        if p.is_alive():
            p.kill()
            p.join(5)
        return None, f"killed at {secs:g}s"
    parent.close()
    if got is None:
        return None, "no result (child died)"
    if got[0] == "ok":
        return (got[1], got[2], got[3]), None
    return None, got[1]


def _rung_children(jobs, secs):
    """_rung_child for several bands at once.

    jobs is [(key, sub, force)]. Returns [(key, result, errmsg)] in job order.
    Every child is launched BEFORE any is joined, so the bands genuinely run
    concurrently; each still gets its own hard `secs` kill measured from its
    own launch (they all launch at the same instant, so no band can be starved
    by queueing behind an earlier one). Results are collected in job order so
    the caller sees a deterministic sequence regardless of finish order.
    """
    import multiprocessing as _mp
    pend = []
    for key, sub, force in jobs:
        parent, child = _mp.Pipe(duplex=False)
        p = _mp.Process(target=_rung_worker, args=(child, sub, force),
                        daemon=True)
        p.start()
        child.close()
        pend.append((key, p, parent))
    out = []
    for key, p, parent in pend:
        got = None
        if parent.poll(secs):
            try:
                got = parent.recv()
            except EOFError:
                got = ("err", "child died (EOF)")
        p.join(2)
        if p.is_alive():
            p.terminate()
            p.join(5)
            if p.is_alive():
                p.kill()
                p.join(5)
            parent.close()
            out.append((key, None, f"killed at {secs:g}s"))
            continue
        parent.close()
        if got is None:
            out.append((key, None, "no result (child died)"))
        elif got[0] == "ok":
            out.append((key, (got[1], got[2], got[3]), None))
        else:
            out.append((key, None, got[1]))
    return out


def _hier_drv(recs, net):
    # driver port cell of net from tile records (build_netspec's drv half;
    # the load half is unneeded: loads routed inside their own partition).
    for op, o, a, cell in recs:
        if o != net:
            continue
        if op in ("AND", "LATCH", "XOR"):
            return cell[2]
        if op == "NOT":
            return (cell[0] + 2, cell[1])
        if op == "OR":
            return cell[0]
    return None


def compose_hier_part(sub):
    """Compose ONE partition (hier's per-band entry point).

    Goes through the standard ladder (REDSTONE_FORCE pins one rung) rather
    than _compose_once: a single-shot with no ladder ignored spread/order
    entirely, so every rung reported the same wall (measured: band 0
    "no ground for OP1" identical at spreads 1-4). Split out so a caller can
    compose partitions itself, in parallel, each hard-bounded
    (scratch/hier_bands.py).
    """
    global _SPREAD, _ORDER, _JOGS, _TERR
    _SPREAD, _ORDER, _TERR = 1, "gates_first", 0
    _JOGS = _JOGS_SHORT
    return compose(sub)


def compose_hier(recipe):
    """Split-and-stitch macros for big banded fields (the bus router, v1).

    Each BAND composes alone (15-gate scale: rung 1, seconds), partitions
    merge side by side with a street gap, boundary nets stitch point to
    point through empty streets. Recipe inputs keep per-partition levers
    (short local legs); only cross-band gate nets stitch. Raises loud on
    any partition or stitch failure. Deterministic: band order, sorted nets.
    """
    global _SPREAD, _ORDER, _JOGS, _TERR, _last_shift, _DEADLINE
    # ponytail: sub ladders call compose(), which re-arms the global deadline
    # from _COMPOSE_SECS (a fresh full budget each — the outer budget would
    # never fire). Snapshot the outer deadline for rung checks and restore
    # the global on every exit so the outer ladder keeps its own clock.
    _dl_saved = _DEADLINE
    gates = _strip_buffers(expand_gates(recipe["gates"], recipe["inputs"]),
                           recipe["outputs"])
    bands = sorted({g.get("band", 0) for g in gates})
    if len(bands) < 2:
        raise RuntimeError("hier: need >= 2 bands")
    prod, cons = {}, {}
    for g in gates:
        prod[g["out"]] = g.get("band", 0)
        for a in g["args"]:
            cons.setdefault(a, set()).add(g.get("band", 0))
    cross = sorted(n for n in cons if n in prod and (cons[n] - {prod[n]}))
    _SPREAD, _ORDER, _TERR = 1, "gates_first", 0
    _JOGS = _JOGS_SHORT
    # ponytail: partitions ride the full standard ladder (44 rungs, shared
    # deadline), not a single _compose_once shot: a 16-gate slice hits the
    # same sealed-port walls a medium build does (measured: sub0 OP1
    # (-11,-5)->(4,12), the documented tile-apron seal). Unset HIER around
    # the call so subs take the standard path (they are small anyway).
    _hier_saved = os.environ.pop("REDSTONE_HIER", None)
    built = []
    # ---- phase 1: build every band's partition recipe (pure, no routing) ----
    subs = {}
    for b in bands:
        bg = [g for g in gates if g.get("band", 0) == b]
        need = set()
        for g in bg:
            for a in g["args"]:
                if a in ("0", "1"):
                    continue
                if a in recipe["inputs"] or prod.get(a, b) != b:
                    need.add(a)
        # ponytail: strip band tags inside the partition. Tags exist so the
        # GLOBAL pass replicates shared controls per band (each band then
        # computes its own copy, no stitch); re-expanding WITH tags inside a
        # single-band sub can orphan clone-adjacent runs (measured: _rc3
        # corridor orphaned OP1's port legs, OPEN at (111,1,21)). Untagged,
        # the sub is an ordinary 15-gate compose in the proven regime.
        _bd = sorted(x for x in need if x not in recipe["inputs"])
        sub = {"inputs": ([x for x in recipe["inputs"] if x in need] + _bd),
               "outputs": sorted(g["out"] for g in bg
                                 if g["out"] in recipe["outputs"]),
               "gates": [{k: v for k, v in g.items() if k != "band"}
                         for g in bg],
               # ponytail: edge-lever classification for _compose_once (see
               # edge levers): boundary nets lever on the producer-facing
               # edge so stitches cross one street, not a field. EDGE lines
               # let the standalone extractor route identical geometry.
               "edge": {n: ("W" if prod.get(n, b) < b else "E")
                        for n in _bd}}
        subs[b] = sub
    _force_saved = os.environ.get("REDSTONE_FORCE")
# ponytail: staged pipeline. Pin a short rung subset once per recipe
    # (REDSTONE_HIER_RUNGS="jog,spread,order;jog,spread,order;...") so
    # merge+stitch probes run in seconds instead of re-climbing 44-rung
    # ladders (30 min) every iteration. Discovered from standalone band
    # probes; first compose+sim-green rung wins as usual.
    _hr = os.environ.get("REDSTONE_HIER_RUNGS", "").strip()
    _full = [(j, s, o) for j in ("short", "long")
             for s in (1, 2, 3, 4, 5, 6, 8, 10)
             for o in ("gates_first", "inputs_first")]
    if _hr:
        _rungs = []
        for _spec in _hr.split(";"):
            _j, _s, _o = _spec.split(",")
            _rungs.append((_j.strip(), int(_s), _o.strip()))
    else:
        # ponytail: pinned-first default. The three rungs below win every
        # alu4hier band (measured across all six partitions), so trying
        # them first turns a 10-minute climb into ~3 minutes; the full
        # ladder follows unchanged for anything else. Order only.
        _pin = [("short", 1, "gates_first"),
                ("short", 1, "inputs_first"),
                ("long", 1, "gates_first")]
        _rungs = _pin + [r for r in _full if r not in _pin]

    # ---- phase 2: climb the ladder for every band IN LOCKSTEP -------------
    # ponytail: bands used to be climbed one at a time, so a recipe with six
    # partitions paid six sequential climbs (measured alu4hier: 27s wall, of
    # which only ~5s was routing -- the parent spent 10.3s blocked on children
    # and 7.3s pickling their results). The partitions are INDEPENDENT, so the
    # same rung can be tried for all of them at once. Lockstep preserves the
    # per-band semantics exactly (same rung order, same first-green-wins, same
    # hard kill) and only changes WHEN they run. Verified by
    # scratch/router_hash.py: identical block list and sha before/after.
    def _port_ok(b, _pctx, _sh):
        # boundary-port openness. A produced cross net whose port has no open
        # orthogonal (diode slots + foreign runs on all sides) can never be
        # stitched, no matter how green the partition sims.
        for _n in cross:
            if prod.get(_n) != b:
                continue
            _c = _hier_drv(_pctx["recs"], _n)
            if _c is None:
                continue
            _d = (_c[0] + _sh[0], _c[1] + _sh[1])
            _free = (_pctx["solid"].get((_d[0], _d[1])) is None
                     and _pctx["wires"].get((_d[0], 1, _d[1])) in (None, _n))
            _open = 0
            for _ax, _az in DIRS:
                _w = _pctx["wires"].get((_d[0] + _ax, 1, _d[1] + _az))
                _sd = _pctx["solid"].get((_d[0] + _ax, _d[1] + _az))
                if _sd is None and _w in (None, _n):
                    _open += 1
            # ponytail: the port cell must be STAMPABLE (free), not just have
            # an open side. A port whose own cell is a foreign wire is a short
            # waiting to happen (measured: A2B2 "touches n1_2 beside
            # (708,1,46)"). One open side is enough to leave by; a free cell
            # plus one exit is the real bar.
            if not _free or _open < 1:
                return _n
        return None

    pending = list(bands)
    got_band, err_band = {}, {}
    for (_jog, _s, _o) in _rungs:
        if not pending:
            break
        if _dl_saved is not None and time.monotonic() > _dl_saved:
            break
        # ponytail: rule 7 AT RUNG GRANULARITY, by hard kill. A pinned rung is
        # a single _compose_once and nothing inside it checks a clock
        # (lwire/astar can spin), so the deadline cannot be polled in-process.
        # Every pending band gets its own child, launched together.
        _jobs = [(b, subs[b], f"{_s},{_o},{_jog}") for b in pending]
        for b, _res, _e in _rung_children(_jobs, _RUNG_SECS):
            sub = subs[b]
            if _res is None:
                err_band[b] = RuntimeError(
                    f"hier band {b}: rung {_s}/{_o}/{_jog} "
                    f"killed at {_RUNG_SECS:g}s")
                continue
            if isinstance(_res, str):
                err_band[b] = RuntimeError(_res)
                continue
            out, _pctx, _sh = _res
            # the partition sim gate already ran inside the child (see
            # _rung_worker): it needs out[0], which no longer crosses the pipe
            _closed = _port_ok(b, _pctx, _sh)
            if _closed is not None:
                err_band[b] = RuntimeError(f"hier band {b}: port {_closed} walled")
                continue
            got_band[b] = (out, _pctx, _sh)
            print(f"hier band {b} rung {_jog} spread {_s} {_o}", flush=True)
        pending = [b for b in pending if b not in got_band]

    if _force_saved is None:
        os.environ.pop("REDSTONE_FORCE", None)
    else:
        os.environ["REDSTONE_FORCE"] = _force_saved
    if pending:
        _b = pending[0]
        if _hier_saved is not None:
            os.environ["REDSTONE_HIER"] = _hier_saved
        raise RuntimeError(f"hier band {_b}: {err_band.get(_b)}") from None
    for b in bands:
        out, _pctx, _sh = got_band[b]
        # recs coords are pre-shift; everything else post-shift (snapshot now:
        # _last_shift is global and the next sub overwrites it -- measured
        # stitch aiming 1 shift off into A0's runs without this).
        built.append((b, subs[b], out, _hier_ctx(_pctx), _sh))
    if _hier_saved is not None:
        os.environ["REDSTONE_HIER"] = _hier_saved
    return compose_hier_parts(built, gates, recipe)


def check_hier_ports(sub, ctx, shift, cross=None, prod=None):
    """Reject a partition whose produced boundary port cannot be stitched.

    The bar (measured, both halves necessary):
      - the port cell itself must be free (no solid, no foreign wire): the
        stitch lays dust there and stamp_wire refuses a foreign neighbour
        (A2B2 "touches n1_2 beside (708,1,46)"), and
      - at least one orthogonal must be free-or-own to leave by.
    Shared by compose_hier's rung acceptance and scratch/hier_bands.py so the
    parallel cache rejects exactly what the ladder would.
    """
    if not cross:
        return
    for _n in cross:
        if prod.get(_n) != sub.get("_band"):
            continue
        _c = _hier_drv(ctx.recs, _n)
        if _c is None:
            continue
        _d = (_c[0] + shift[0], _c[1] + shift[1])
        _free = (ctx.solid.get((_d[0], _d[1])) is None
                 and ctx.wires.get((_d[0], 1, _d[1])) in (None, _n))
        # A foreign wire ORTHOGONALLY BESIDE the port blocks the stamp, not
        # just the exit: stamp_wire's same-level adjacency guard raises when
        # the port's own dust would touch it (measured: A2B2 "touches n1_2
        # beside (708,1,46)"). So the bar is zero foreign neighbours, plus at
        # least one free side to leave by.
        _bad = 0
        _open = 0
        for _ax, _az in DIRS:
            _w = ctx.wires.get((_d[0] + _ax, 1, _d[1] + _az))
            if _w is not None and _w != _n:
                _bad += 1
            if (ctx.solid.get((_d[0] + _ax, _d[1] + _az)) is None
                    and _w in (None, _n)):
                _open += 1
        if not _free or _bad or _open < 1:
            raise RuntimeError(f"port {_n} at {_d} not stitchable "
                               f"(free={_free} foreign={_bad} open={_open})")


def compose_hier_parts(built, gates, recipe):
    """Merge pre-composed partitions, stitch, check. compose_hier's stage 2.

    Split out so cached partitions can be stitched without re-composing
    bands (measured: a full hier run is ~30 min of band ladders; the merge is
    seconds, so stitch-strategy iteration must never pay the bands again).
    `built` is compose_hier's list: [(band, sub, out, ctx, shift)].
    """
    prod, cons = {}, {}
    for g in gates:
        prod[g["out"]] = g.get("band", 0)
        for a in g["args"]:
            cons.setdefault(a, set()).add(g.get("band", 0))
    cross = sorted(n for n in cons if n in prod and (cons[n] - {prod[n]}))
    blocks, solid, rings, wires, junctions, repeaters, pos, sup = (
        [], {}, {}, {}, {}, {}, {}, {})
    offs, cur, drv_of = {}, 0, {}
    for (b, sub, out, pctx, sh) in built:
        dx = cur
        offs[b] = dx
        for x, y, z, bid in pctx.blocks:
            blocks.append((x + dx, y, z, bid))
        for (x, z), v in pctx.solid.items():
            solid[(x + dx, z)] = v
        for (x, z), v in pctx.rings.items():
            rings.setdefault((x + dx, z), set()).update(v)
        for (x, y, z), v in pctx.wires.items():
            wires[(x + dx, y, z)] = v
        for (x, z), v in pctx.junctions.items():
            junctions.setdefault((x + dx, z), set()).update(v)
        for (x, y, z), v in pctx.repeaters.items():
            repeaters[(x + dx, y, z)] = v
        for n, (px, pz) in pctx.pos.items():
            pos[n] = (px + dx, pz)
        for (x, y, z), v in pctx.sup.items():
            sup[(x + dx, y, z)] = v
        # boundary-input levers out (the stitch drives these stubs now);
        # recipe inputs keep their levers. Stub dust stays as the target.
        for n in sub["inputs"]:
            if n in recipe["inputs"]:
                continue
            lever = next((c for c, v in pctx.solid.items() if v == ("lever", n)),
                         None)
            if lever is None:
                raise RuntimeError(f"hier band {b}: no lever for {n}")
            lx, lz = lever[0] + dx, lever[1]
            blocks[:] = [bb for bb in blocks
                         if not (bb[0] == lx and bb[1] == 1 and bb[2] == lz
                                 and "lever" in bb[3])]
            del solid[(lx, lz)]
            for ax, az in DIRS:
                s = rings.get((lx + ax, lz + az))
                if s is not None:
                    s.discard(n)
        for n in cross:
            if prod[n] == b:
                c = _hier_drv(pctx.recs, n)
                if c is None:
                    raise RuntimeError(f"hier band {b}: no driver for {n}")
                # recs is pre-shift; everything else post-shift.
                drv_of[n] = (c[0] + sh[0] + dx, c[1] + sh[1])
        maxx = max([x for (x, z) in solid] + [x for (x, _, z) in wires]
                   + [x for (x, _, z) in repeaters])
        cur = maxx + 1 + _HIER_GAP
    # ---- one input bank ---------------------------------------------------
    # Every band composed its own lever per recipe input, so a 10-input /
    # 6-band build shipped 21 levers strung along x (measured on the merged
    # caches: alu4 spanned 1757 blocks, cpu4 3352) and flipping an input meant
    # walking to whichever band's copy was nearest. Worse, "keep the westernmost
    # lever per input" is NOT one place either: each input's westernmost copy
    # lives in a different band (alu4 put A0's at x=13, A1's at x=437, A2's at
    # x=832, A3's at x=1482), so that made FOUR clusters.
    #
    # So: one lever COLUMN north of the entire merge, one row per input, and
    # the ordinary stitch fans each row out to the stubs it used to drive
    # directly. Rows north of everything means the east run is open ground for
    # the whole width, and the lever needs no riser -- its stub IS the west end
    # of its row. That matters: a column of levers sharing one stub column
    # walls each riser with the other nine stubs (measured: A2's riser ran
    # into A3's and B3's).
    # REDSTONE_INPUT_BANK=0 restores the old per-partition levers.
    _banknets = {}
    _bankrow = {}
    if os.environ.get("REDSTONE_INPUT_BANK", "0") == "1":
        _lev = {}
        for (b, sub, out, pctx, sh) in built:
            for (x, z), v in pctx.solid.items():
                if v[0] == "lever" and v[1] in recipe["inputs"]:
                    _lev.setdefault(v[1], []).append((x + offs[b], z, b))
        if _lev:
            _names = sorted(_lev)
            _bz0 = min([z for (x, z) in solid]
                       + [z for (x, _, z) in wires]
                       + [z for (x, _, z) in repeaters])
            _cx = min(x for (x, z) in solid) - 6
            # ponytail: ROW ORDER = how far east each input reaches, longest
            # first, so the longest row is the SOUTHERNMOST. A band's stub is
            # reached by dropping south from its row at the stub's own column,
            # and that drop crosses exactly the rows south of it -- which, in
            # this order, are only the rows that reach FURTHER east than the
            # drop. Without it every drop crossed all ten rows and the gate
            # nets lost their north-around descent (measured: "hier stitch
            # A3B3: band 4 stub (1566,63): no ground for A3B3: (1834,50) ->
            # (1341,1)", whose only open margin is north of the bank).
            _reach = {n: max(offs[b] for (_, _, b) in _lev[n]) for n in _names}
            _rows = {}
            for _i, _n in enumerate(sorted(_names, key=lambda n: -_reach[n])):
                _rows[_n] = _bz0 - 16 - 4 * _i
            for _try in range(400):
                _cells = [(_cx, _rows[_n]) for _n in _names]
                if not any(
                        c in solid or (c[0] + 1, c[1]) in solid
                        or (c[0], 1, c[1]) in wires
                        or (c[0] + 1, 1, c[1]) in wires
                        or (c[0], 1, c[1]) in repeaters
                        or (c[0] + 1, 1, c[1]) in repeaters
                        or (c[0] - 1, c[1]) in solid
                        or (c[0] - 1, 1, c[1]) in wires
                        or (c[0] - 1, 1, c[1]) in repeaters
                        for c in _cells):
                    break
                _cx -= 4
            else:
                raise RuntimeError("hier bank: no free column north-west of "
                                   f"the merge after 400 steps (x={_cx})")
            _bb = min(b for L in _lev.values() for (_, _, b) in L)
            for _n in _names:
                lx, lz = _cx, _rows[_n]
                blocks.append((lx, 1, lz,
                               "minecraft:lever[face=floor,facing=north,"
                               "powered=false]"))
                solid[(lx, lz)] = ("lever", _n)
                for dx, dz in DIRS:
                    rings.setdefault((lx + dx, lz + dz), set()).add(_n)
                # the stub is the driver's own cell: the lever powers it (and
                # only it) at 15, exactly as a partition bank did.
                wires[(lx + 1, 1, lz)] = _n
                drv_of[_n] = (lx + 1, lz)
                prod[_n] = _bb
                _banknets[_n] = (lx, lz)
                _bankrow[_n] = lz
            for _n in _names:
                for (lx, lz, b) in _lev[_n]:
                    blocks[:] = [bb for bb in blocks
                                 if not (bb[0] == lx and bb[1] == 1
                                         and bb[2] == lz and "lever" in bb[3])]
                    solid.pop((lx, lz), None)
                    for ax, az in DIRS:
                        s_ = rings.get((lx + ax, lz + az))
                        if s_ is not None:
                            s_.discard(_n)
    _stitchnets = list(cross) + [n for n in sorted(_banknets)
                                 if n not in cross]
    # merged pos holds the last band's cell per net name; stitch addressing
    # uses partition-local pos + offsets (exact), so collisions are harmless.
    # check_opens/finish_assembly only need each listed cell to be live.
    mctx = new_ctx(blocks, solid, rings, wires, junctions, repeaters, pos,
                   [], sup)
    # ponytail: producer ports with no in-band loads carry no dust (nothing
    # ever stamped a leg there), so a seal snapshot records the driver's own
    # tile torch as forbidding that net — outlawing the stitch at its first
    # cell (measured: C1 no-ground on an empty row). Allow-list the driver
    # net on every adjacent torch instead; lwire stamps the port under the
    # same endpoint path normal legs use. (Pre-stamping the stub directly is
    # wrong: the same-level adjacency guard fires with no ends context —
    # measured: C1 touches A0 at stale coords (42,1,13).)
    seal_tiles(mctx)
    # ponytail: bare torches forbid everything. seal_tiles only records a
    # torch when dust already sits beside it — but a torch with bare
    # surroundings gets NO entry, so later stamping walks dust right past a
    # foreign torch and the sim reads the torch's value into the net
    # (measured: A0B0's y=3 flight beside A0B0_0's torches reads lit when the
    # net is dark -> Y1 mismatch on 1010101010). Recording every torch with
    # an empty allow turns that silent corruption loud (no-ground) instead.
    # Merge-only: partitions sealed themselves during sub-compose, so no
    # green geometry moves.
    for (x, z), (kind, _n) in solid.items():
        if kind == "torch" and (x, z) not in mctx.tile_adj:
            mctx.tile_adj[(x, z)] = set()
    # ponytail: allow-list ONLY owner torches. A stitch wire beside a
    # NEIGHBOR tile's torch is driven by lever AND inverter at once — a ring
    # oscillator that sim reports as "not settling" (measured: merged alu4
    # churn=7557 on one vector after all stitches landed). Broad allow (any
    # adjacent torch) turned that shipping failure silent; owner-only keeps
    # it loud (no-ground) instead. The driver's own output torch is owned by
    # the net itself, so legitimate ports stay routable.
    for n, d in drv_of.items():
        for ax, az in DIRS:
            t = (d[0] + ax, d[1] + az)
            if solid.get(t) == ("torch", n):
                s = mctx.tile_adj.get(t)
                if s is not None:
                    s.add(n)
    guard = set()
    for x, y, zz, bid in blocks:
        if "wall_torch" in bid:
            guard.add((x, zz))
            face = bid.split("facing=")[1].rstrip("]")
            dx, dz = TORCH_BACK[face]
            guard.add((x + dx, zz + dz))
    # ponytail: longest stitch first. Every stitch adds dust the later ones
    # must route around; the longest span is the most constrained, so it
    # goes while the field is emptiest (measured: C3 died last behind A0B0
    # + C2 dust). Span from producer driver to first consumer stub.
    def _span(n):
        d = drv_of[n]
        # banked inputs have no producer band, so their "consumers" are the
        # other bands' lever stubs -- the fan-out chain, longest leg first.
        stubs = [(pctx.pos[n][0] + offs[b], pctx.pos[n][1])
                 for (b, sub, out, pctx, sh) in built
                 if n in sub["inputs"]
                 and (n not in recipe["inputs"] or n in _banknets)]
        if not stubs:
            return 0
        return -min(abs(d[0] - s[0]) + abs(d[1] - s[1]) for s in stubs)
    # ponytail: LONG jogs for stitches. Partitions used SHORT (their fields
    # are small); a stitch crosses a whole neighboring field, and the short
    # 2..12-row jogs cannot get around a band to enter from the open side
    # (measured: C3 died at the same endpoints twice). Deep jogs cost
    # wandering in open streets, which is free here.
    # ponytail: SHORT jogs for stitches (was LONG). LONG's deep offset
    # trunks wander off-corridor into foreign runs and die there (measured:
    # R0Q1's proven south corridor dies "touches E0" under LONG, routes in
    # 0.1s under SHORT — same cells, jog depth is the only delta). Corridor,
    # south-around and hop-row strategies pick their own geometry; they need
    # disciplined short jogs, not deep ones. Set explicitly: sub ladders
    # leave whatever their winning rung used, which is not ours to inherit.
    # ponytail: overflights STAY allowed for stitches (no REDSTONE_NO3D).
    # Tried flat+hops-only: south legs that must cross a live run die on the
    # ground (measured: R0Q1's south exit needs its hop over E0's leg) while
    # the same legs fly clean with 3D allowed. Slope-shorts stay loud and
    # honest instead (next strategy / next rung), never silent.
    global _JOGS
    _JOGS = _JOGS_SHORT
    # ponytail: snapshot the pre-stitch maxz ONCE. South-around margins
    # computed live creep upward (each prior margin becomes part of maxz),
    # stretching later south legs through 200+ cells of field for no reason.
    # Fixed base + per-net stagger keeps every margin minimal and open.
    _maxz0 = max([z for (x, z) in solid] + [z for (x, _, z) in wires]
                 + [z for (x, _, z) in repeaters])
    _maxx0 = max([x for (x, z) in solid] + [x for (x, _, z) in wires]
                 + [x for (x, _, z) in repeaters])
    _minz0 = min([z for (x, z) in solid] + [z for (x, _, z) in wires]
                 + [z for (x, _, z) in repeaters])
    # ponytail: purge stale lids at merge start. Partition _walks drop lids
    # for pairs in their own field; post-merge the same cobble can sit over
    # a stitch hop it never anticipated, breaking a legitimate slope into an
    # OPEN (measured: lid over C3's hop lower with no foreign pair needing it
    # anymore). A lid is cobble with dust directly below and nothing directly
    # above (pillars always carry dust above); remove exactly those, then the
    # fresh pass below lids current pairs only. Tile bodies live in solid,
    # never blocks, so they are untouched.
    _wset = {(x, y, z) for (x, y, z), _nw in wires.items()}
    blocks[:] = [bb for bb in blocks
                 if not (bb[3].split("[")[0] == "minecraft:cobblestone"
                         and (bb[0], bb[1] - 1, bb[2]) in _wset
                         and not any((bb[0] + _ex, bb[1] + 1, bb[2] + _ez) in _wset
                                     for _ex, _ez in list(DIRS) + [(0, 0)]))]
    _dump = os.environ.get("REDSTONE_HIERDUMP")
    if _dump:
        metas = [{"b": b, "sub": sub, "shift": sh, "dx": offs[b],
                   "recs": pctx.recs, "pos": dict(pctx.pos)}
                  for (b, sub, out, pctx, sh) in built]
        hier_dump(_dump,
                  {"blocks": blocks, "solid": solid, "rings": rings,
                   "wires": wires, "junctions": junctions,
                   "repeaters": repeaters, "pos": pos, "sup": sup},
                   metas, cross, prod, recipe["inputs"])
    # ponytail: point pos at the drivers for cross nets. Merged pos[] is
    # last-band-wins (a consumer stub, often bare after lever removal), but
    # check_opens seeds its flood from pos cells — a connected network whose
    # pos cell is bare fails OPEN despite being fully driven (measured:
    # AL_C3 flagged with zero orphans). The producer driver port always
    # carries the net, so seed there.
    for _n, _dd in drv_of.items():
        pos[_n] = _dd
    # ponytail: consumer lever-bank minima (post-shift z; merge offsets x
    # only, so partition z applies directly). A stitch target stub sits in
    # its band's live lever row; the row north of the bank is empty margin.
    levermin = {}
    for (b, sub, out, pctx, sh) in built:
        lz = [z for (x, z), v in pctx.solid.items() if v[0] == "lever"]
        if lz:
            levermin[b] = min(lz)
    # ponytail: street waypoints between every adjacent band pair (for
    # relay stations below): street center x, computed from real offsets.
    _sts = sorted(offs.values())
    _streets = [(a + b) // 2 for a, b in zip(_sts, _sts[1:])]

    # ponytail: stitch atomicity. Every multi-leg strategy below (relay,
    # corridor, south-around, two-hop, west) can part-succeed: early legs
    # stamp dust (and relay stations) and a later leg fails, leaving net
    # dust in the field that the NEXT strategy — and every later stitch —
    # must route around or short against (measured: R0Q1's proven south
    # corridor died inside _stitch after longer stitches' partial relay legs
    # polluted it). Snapshot once per _stitch call; each strategy restores
    # first, so every attempt starts pristine. Same 5-tuple lwire itself
    # snapshots (wires, sup, ctx.sup, solid, blocks); repeaters join it here
    # because relay stations live there.
    def _snap():
        return (dict(wires), dict(sup), dict(mctx.sup), dict(solid),
                dict(repeaters), len(blocks))

    def _restore(snap):
        _w, _su, _sc, _so, _rp, _sb = snap
        wires.clear()
        wires.update(_w)
        sup.clear()
        sup.update(_su)
        mctx.sup.clear()
        mctx.sup.update(_sc)
        solid.clear()
        solid.update(_so)
        repeaters.clear()
        repeaters.update(_rp)
        del blocks[_sb:]

    # the wire set as it stood when the CURRENT stitch started. The
    # contiguity gate in _landed judges only cells NOT in it: a step inside a
    # tile is that tile's own construction (its merge-tail diodes chain
    # repeater->repeater on purpose and the band already simmed them), and
    # the producer hand-off is the stub-connect pass's job. Rebound per leg
    # below; a list so the nested defs can rebind without nonlocal.
    _prews = [frozenset()]
    # set by _try once it has planted the leg's boosters, so the stitch loop
    # does not plant them a second time.
    _planted = [False]

    def _landed(full, n, stub, _mile=False):
        # every stitch must DELIVER: the path must conduct (sim rules) onto
        # the stub. lwire stops at the target xz whatever y it arrives with,
        # so an elevated end over a lidded/unsupported cell is dark in sim
        # while checkers stay silent (measured: R1Q1 ends y=2 over a lidded
        # stub, whole bank unreadable; E1 ends y=2 over a valid slope and
        # works; R0Q3 ends 1-off adjacent and conducts). Fail loud so the
        # next strategy tries another approach (or splice one bounded last
        # mile, below). Link terms mirror sim.py dust_lvl/rep_on (support +
        # no-lid + diode-forward; keep in sync — vanilla physics, stable):
        # support is cobble now, or any y=1 block now (finish_assembly pads
        # stone under every y=1 comp later, except trench x,z which stay
        # open). Flood goes WITH power flow (driver -> stub), so diodes are
        # traversed forward only.
        if os.environ.get("REDSTONE_NOLAND") == "1":
            return full  # escape hatch: loose landings (diagnosis only)
        from layout import _VEC as _VV
        if not full:
            raise RuntimeError(f"hier stitch {n}: empty path")
        _trench = {(x, z) for (x, y, z) in wires if y <= 0}
        _trench |= {(x, z) for (x, y, z) in repeaters if y <= 0}
        # ponytail: index once (a linear blocks scan per link check is
        # 70k x links = hours per merge; sets make it seconds).
        _bset = {(b[0], b[1], b[2]) for b in blocks}
        _cobset = {(b[0], b[1], b[2]) for b in blocks
                   if b[3].split("[")[0] == "minecraft:cobblestone"}
        # ponytail: support roles split for glass/slab (layout sets): lids
        # stay cobblestone-only, up-reads need opaque sources, down-reads
        # accept any solid rest. Router geometry is glass-free, so empty
        # deltas there; hand-glass stitches land honestly.
        _supset = _layout_sup3(blocks)
        _srcset = _layout_src3(blocks)

        def _cob(c):
            return c in _cobset

        def _sup(c):
            return c in _supset or (c[1] == 1 and c in _bset
                                    and (c[0], c[2]) not in _trench)

        def _nbrs(c):
            # sim-conducting neighbors of c (power-flow direction irrelevant
            # except diodes: forward only).
            if c in mctx.repeaters:
                _rn, _f = mctx.repeaters[c]
                if _rn != n:
                    return
                _dx, _dz = _VV[_f]
                _m = (c[0] + _dx, c[1], c[2] + _dz)
                if wires.get(_m) == n:
                    yield _m
                return
            for dx, dz in DIRS:
                m = (c[0] + dx, c[1], c[2] + dz)
                if wires.get(m) == n:
                    yield m
                elif m in mctx.repeaters and mctx.repeaters[m][0] == n:
                    _dx, _dz = _VV[mctx.repeaters[m][1]]
                    if (m[0] - _dx, m[1], m[2] - _dz) == c:
                        yield m
                up = (c[0] + dx, c[1] + 1, c[2] + dz)
                if wires.get(up) == n and (c[0] + dx, c[1], c[2] + dz) \
                        in _srcset and (c[0], c[1] + 1, c[2]) not in _cobs:
                    yield up
                dn = (c[0] + dx, c[1] - 1, c[2] + dz)
                if wires.get(dn) == n and _sup((c[0], c[1] - 1, c[2])) \
                        and not _cob((dn[0], c[1], dn[2])):
                    yield dn

        _cobs = _cobset
        _seen, _st = set(full), list(full)
        for _ in range(6000):
            if not _st:
                break
            _c = _st.pop()
            for _m in _nbrs(_c):
                if _m not in _seen:
                    _seen.add(_m)
                    _st.append(_m)
        if (stub[0], 1, stub[1]) in _seen:
            # ponytail: contiguity. check_opens seeds from pos/levers/torches
            # and floods the WHOLE field, so a break anywhere on the path
            # orphans everything past it — and the stub flood above (seeded at
            # the path) cannot see that, so the merge died at check_opens with
            # "OPEN" on cells the stitch never joined (measured: AL_C3, 6 cells
            # past a break, 0 orphans reported). Every consecutive pair must be
            # a sim link, so the path is one conductor end to end.
            _freshc = {c for c in full if c not in _prews[0]}
            for _a, _b2 in zip(full, full[1:]):
                if _a == _b2:
                    continue  # a leg boundary re-emits its joint cell
                if (_a in _freshc or _b2 in _freshc) \
                        and _b2 not in set(_nbrs(_a)):
                    # only FRESH cells are the stitch's responsibility: a
                    # step inside a TILE is that tile's own construction (its
                    # merge-tail diodes legitimately chain repeater->repeater
                    # and the band already simmed them), and the producer
                    # stub hand-off is the stub-connect pass's job.
                    raise RuntimeError(
                        f"hier stitch {n}: broken link {_a} -> {_b2}")
            return full
        if _mile:
            raise RuntimeError(f"hier stitch {n}: unlanded at {full[-1]}")
        # ponytail: one bounded last mile instead of instant failure.
        # Backtrack to the last y=1 cell near the stub and lwire in (the
        # bulk path stays; the abandoned tail remains a lit connected
        # branch, so nothing orphans). Fails loud (next strategy) if walled.
        _ss = _snap()
        try:
            _bi = -1
            for _i, _cc in enumerate(full):
                if _cc[1] == 1 and abs(_cc[0] - stub[0]) \
                        + abs(_cc[2] - stub[1]) <= 12:
                    _bi = _i
            if _bi < 0:
                raise RuntimeError(f"hier stitch {n}: no mile start")
            _m = lwire(mctx, sup, guard, (full[_bi][0], full[_bi][2]),
                       stub, n)
            if not _m or _m[0] != full[_bi]:
                raise RuntimeError(f"hier stitch {n}: mile disjoint")
            return _landed(full[:_bi + 1] + _m[1:], n, stub, True)
        except RuntimeError:
            _restore(_ss)
            raise

    def _relay(drv, stub, n, wps):
        # lwire drv -> (wp, drv_z) -> ... -> (wp, stub_z) -> stub, stamping a
        # repeater facing travel at each waypoint. Each leg is street-bounded
        # (hundreds of cells shorter than the whole span). Raises loud.
        # Atomic: a failed waypoint chain restores (stations and legs vanish
        # instead of poisoning later strategies).
        _rsnap = _snap()
        try:
            _pts = [drv] + [(x, drv[1]) for x in wps] + [(wps[-1], stub[1]),
                                                          stub]
            full = []
            for _a, _bb in zip(_pts, _pts[1:]):
                if os.environ.get("REDSTONE_HIER_TRACE"):
                    print(f"hier relay leg {n} {_a}->{_bb}", flush=True)
                full += lwire(mctx, sup, guard, _a, _bb, n)
        except RuntimeError:
            _restore(_rsnap)
            raise
        for _wx, _wz in ([(x, drv[1]) for x in wps]
                         + [(wps[-1], stub[1])]):
            if (_wx, 1, _wz) in mctx.repeaters:
                continue
            if mctx.wires.get((_wx, 1, _wz)) != n:
                continue
            _dx = 1 if stub[0] >= drv[0] else -1
            # ponytail: stations only on straight runs. A station is a diode;
            # on a corner it rectifies the turn away (measured: E1's relay
            # station at a south turn faced east, orphaning the whole south
            # leg — 1100+ E1 cells dark, R1 bank unwritable). Corners stay
            # dust (the turn conducts fine); the every-8 planter below
            # covers levels on the straight stretches.
            _cell = (_wx, 1, _wz)
            _ii = [i for i, _c in enumerate(full) if _c == _cell]
            _straight = False
            for _i in _ii:
                if 0 < _i < len(full) - 1:
                    _p, _q = full[_i - 1], full[_i + 1]
                    _tx, _tz = _wx - _p[0], _wz - _p[2]
                    if ((_q[0] - _wx, _q[2] - _wz) == (_tx, _tz)
                            and (_tx, _tz) in _VEC
                            and _p[1] == 1 == _q[1]):
                        _straight = True
            if not _straight:
                continue
            if not _ends_ok(mctx, n, _wx, 1, _wz, _dx, 0):
                continue
            del mctx.wires[(_wx, 1, _wz)]
            # ponytail: dict only, no blocks.append — finish_assembly emits
            # repeater blocks from this dict, and appending here too ships
            # every station twice (measured: duplicate block entries).
            mctx.repeaters[(_wx, 1, _wz)] = (
                n, "east" if _dx > 0 else "west")
        return full

    def _loop_near(cells, nn):
        # True if any repeater near `cells` closes a front~back ring through
        # same-net dust+cobble (layout._loop_rep's rule, neighborhood-scoped
        # so it costs cells not the field). A stitch overlapping existing
        # same-net legs can close such a ring (measured: AL_AB3's stitch
        # retraced band-8's legs and ringed through their boosters) — the run
        # is live but bistable, and finish_assembly rejects it. Fail the
        # strategy here (rollback) instead of the whole merge downstream.
        from layout import _VEC as _VV
        # A real radius-25 box per path cell. The old shape (every dx at the
        # path's own z, plus only the two extreme z rows) left a hole in the
        # middle of the window, so a ring a few cells off the path's z was
        # invisible and finish_assembly killed the whole merge on it
        # (measured: R1Q3 at (2850,1,43) against a path sitting at z=52).
        _near = set()
        for (_x, _y, _z) in cells:
            for _dx in range(-25, 26):
                for _dz in range(-25, 26):
                    _near.add((_x + _dx, _y, _z + _dz))
        _cob = _layout_flood3(blocks)
        for (_x, _y, _z), (_rn, _f) in mctx.repeaters.items():
            if _rn != nn or (_x, _y, _z) not in _near:
                continue
            _dx, _dz = _VV[_f]
            _front, _back = ((_x + _dx, _y, _z + _dz),
                             (_x - _dx, _y, _z - _dz))
            _seen, _stack = set([_front]), [_front]
            while _stack:
                _u = _stack.pop()
                if _u == _back:
                    return True
                for _ox, _oz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    _m = (_u[0] + _ox, _u[1], _u[2] + _oz)
                    if _m in _seen:
                        continue
                    if _m in wires and wires[_m] == nn:
                        _seen.add(_m)
                        _stack.append(_m)
                    elif _m in _cob and _u in wires:
                        _seen.add(_m)
                        _stack.append(_m)
        return False

    def _legs(pts, _tag="legs"):
        # One multi-leg attempt, atomic: partial legs roll back so the next
        # strategy (and the next stitch) starts pristine. Single lwires
        # self-restore; only chained shapes need this.
        if os.environ.get("REDSTONE_HIER_TRACE"):
            print(f"hier {_tag} {n} {'->'.join(str(p) for p in pts)}", flush=True)
        _ssnap = _snap()
        try:
            # ponytail: splice joints IN ORDER (not appended). Appending them
            # at the end breaks path order, which _plant_repeaters reads as
            # travel direction — backwards diodes on a live run. Interleaved,
            # each joint sits between its legs exactly where power flows.
            _legs_list = []
            for _a, _bb in zip(pts, pts[1:]):
                _legs_list.append(lwire(mctx, sup, guard, _a, _bb, n))
            full = []
            for _k, _leg in enumerate(_legs_list):
                full += _leg
                if _k < len(pts) - 2:
                    _j = pts[_k + 1]
                    _jc = (_j[0], 1, _j[1])
                    # ponytail: stamp the joints. lwire never stamps its
                    # endpoints (pre-wired stubs on the standard path), so
                    # every intermediate waypoint arrives bare — a 1-cell hole
                    # (measured: C3's corridor joint, whole merge flagged
                    # OPEN for it). Stamping closes the run; a foreign
                    # neighbour fails loud (rollback, next strategy).
                    if mctx.wires.get(_jc) is None:
                        from tiles import stamp_wire as _sw
                        _sw(mctx, [_jc], n)
                    full.append(_jc)
            # ponytail: contiguity gate. A same-level diagonal step is a hole
            # dust never connects (see above); level changes must keep x/z
            # (slope/hop links, validated by the checkers). Fails loud so the
            # next strategy runs.
            for _u, _v in zip(full, full[1:]):
                if (abs(_v[0] - _u[0]) + abs(_v[2] - _u[2]) > 1
                        and _v[1] == _u[1]):
                    raise RuntimeError(
                        f"compose: stitch joint gap for {n}: {_u} -> {_v}")
            if _loop_near(full, n):
                raise RuntimeError(f"compose: stitch rings for {n}")
            return full
        except RuntimeError:
            _restore(_ssnap)
            raise

    def _stitch(drv, stub, n, b, relay_min=350):
        # direct first (proven for short spans); else spiral-start: the
        # producer port itself can sit pocketed by its own tile's input runs
        # (measured: C3 port walled on all 4 sides, every axis RED). A start
        # cell dust-adjacent to the live port is electrically the same node
        # (same-y dust touch conducts; checkers allow same-net touch), so
        # try the port then each open orthogonal neighbor.
        # Repeater relay: a span over ~350 cells neither routes nor arrives
        # live (measured: R1Q3 no-ground at 1600 cells). Split it at street
        # waypoints with a repeater station each (re-drives 15, breaks both
        # the route and the decay into short legs). Stations face travel;
        # dust on both sides is the same net, so checkers pass.
        def _try(fn):
            # one strategy, atomic + landed: a routed-but-unlanded path
            # restores (its dust would otherwise poison later strategies;
            # measured: a landing-failed relay left its whole run in the
            # field and every classic after it died on the corpse) and the
            # failure falls into the next strategy.
            _s = _snap()
            from layout import _loop_rep as _lr
            _dust0 = set(mctx.wires) - set(mctx.repeaters)
            _cob0 = _layout_flood3(blocks)
            _pre_loop = _lr(mctx.wires, mctx.repeaters, _dust0, _cob0)
            try:
                _p = _landed(fn(), n, stub)
                # ponytail: a run must be a SIMPLE path. A path that re-enters
                # its own cell is a ring waiting for a booster: the diode lands
                # where the path doubles back and front joins back (measured:
                # R1Q3's leg ends ...(2849,25),(2848,25),(2847,25) then turns
                # north past its own (2848,26),(2849,26)). Rejecting the
                # overlap is cheaper and more direct than hunting the ring.
                # An ADJACENT repeat is legal (a leg boundary re-emits its
                # joint cell) and is the only one allowed.
                _hit = set()
                for _i2, _c in enumerate(_p):
                    if _c in _hit and not (
                            _i2 and _p[_i2 - 1] == _c):
                        raise RuntimeError(
                            f"hier stitch {n}: path re-enters {_c}")
                    _hit.add(_c)
                # Every strategy's own boosters can close a front-joins-back
                # ring, and finish_assembly kills the WHOLE merge on one
                # (measured: E0 at (559,1,54), R1Q3 at (2850,1,43)). Ask the
                # checker the merge will ask — layout._loop_rep, which picks
                # the net from the diode's FRONT cell and so also sees
                # cross-net rings a net-scoped probe misses. Only a NEW loop
                # rejects: a band tile can leave one behind, and that is not
                # this strategy's to fix.
                _dust = set(mctx.wires) - set(mctx.repeaters)
                _cob = _layout_flood3(blocks)
                _post = _lr(mctx.wires, mctx.repeaters, _dust, _cob)
                if _post is not None and _post != _pre_loop:
                    raise RuntimeError(f"hier stitch {n}: rings at {_post[0]}")
                # Boost HERE, not in the caller: a booster can close a ring
                # where the path doubles back on an EARLIER LEG of the same
                # net (R1Q3 is consumed by two bands and the legs chain stub
                # to stub), and the ring gate only sees the truth once the
                # diodes exist. Inside _try that rolls back and the NEXT
                # strategy runs; outside it the whole net failed.
                for _u, _v in zip(_p, _p[1:]):
                    _d = (_v[0] - _u[0], _v[2] - _u[2])
                    flow.setdefault((_u[0], _u[1], _u[2]), set()).add(_d)
                    flow.setdefault((_v[0], _v[1], _v[2]), set()).add(_d)
                _plant_repeaters(mctx, _p, n, flow, end_boost=True,
                                 fresh={c for c in _p if c not in _prews[0]})
                _dust = set(mctx.wires) - set(mctx.repeaters)
                _cob = _layout_flood3(blocks)
                _post = _lr(mctx.wires, mctx.repeaters, _dust, _cob)
                if _post is not None and _post != _pre_loop:
                    raise RuntimeError(f"hier stitch {n}: rings at {_post[0]}")
                _planted[0] = True
                return _p
            except RuntimeError:
                _restore(_s)
                raise
        # ponytail: the BANK strategy, tried FIRST and only for a banked
        # input. Its driver is one lever column in the empty margin west of
        # the whole merge, so the open-ground shape is exact: north to a
        # per-net margin row (north of every band), east along it, then south
        # down the stub's own column into the band. Every cell of that route
        # is outside every band field.
        #
        # It has to come first because the generic ladder cannot express it:
        # _relay puts its waypoints at the DRIVER's z, which for a bank means
        # dragging a run east at the lever latitude, straight through every
        # band (measured: A2 died "no ground for A2: (-4,2) -> (1123,1)"),
        # and the stub->stub chain needs one leg to cross every intervening
        # field (measured: OP1 band2->band4, 642 cells through band 3, "path
        # re-enters (1341,1,2)"). Rows 4 apart, so no two bank nets touch.
        if n in _banknets:
            if os.environ.get("REDSTONE_HIER_TRACE"):
                print(f"hier bank {n} {drv}->{stub}", flush=True)
            try:
                return _try(lambda: _legs([drv, (stub[0], drv[1]), stub],
                                          "bank"))
            except RuntimeError as e:
                _err = e
        _spanlen = abs(stub[0] - drv[0]) + abs(stub[1] - drv[1])
        # ponytail: relay_min. The street-relay split is tried first and
        # rolls back cleanly, so lowering it for a caller that knows its
        # legs are hard is free. The banked input fan-out does: it crosses
        # one street per leg but starts in the empty margin west of the
        # merge, and the direct/hop-row strategies returned self-entering
        # paths for its last two legs (measured: "path re-enters
        # (1341,1,2)" band 4, "(1653,2,2)" band 5). Default unchanged so
        # every gate net keeps the geometry it verified green with.
        if _spanlen > relay_min:
            _wps = [x for x in _streets if min(drv[0], stub[0]) < x < max(drv[0], stub[0])]
            if _wps:
                try:
                    return _try(lambda: _relay(drv, stub, n, sorted(_wps)))
                except RuntimeError as e:
                    _err = e
                # fall through to the classic strategies below
        # Last resort: two-hop via a hop row just north of the consumer
        # lever bank (street north, east-west along the empty margin, step
        # south into the stub).
        # ponytail: REDSTONE_HIER_FAST bounds the SEARCH, not the process. A
        # chained fan-out leg 400+ cells long makes astar the dominant cost
        # (measured: >150s wall even forked, twice). Fast mode tries the
        # cheap deterministic strategies only — direct from each open port
        # neighbour, then the west approach — and skips astar-backed hop rows
        # entirely, so the stage is seconds. Default stays exhaustive.
        _fast = os.environ.get("REDSTONE_HIER_FAST") == "1"
        starts = [drv] + [(drv[0] + dx, drv[1] + dz) for dx, dz in DIRS
                          if solid.get((drv[0] + dx, drv[1] + dz)) is None
                          and wires.get((drv[0] + dx, 1, drv[1] + dz)) is None]
        _err = None
        for s in starts:
            try:
                return _try(lambda: lwire(mctx, sup, guard, s, stub, n))
            except RuntimeError as e:
                _err = e
        if _fast:
            for _k in (2, 4, 6):
                _ax, _az = stub[0] - _k, stub[1]
                if solid.get((_ax, _az)) is not None:
                    continue
                try:
                    return _try(lambda: _legs([drv, (_ax, _az), stub],
                                                 "fastwest"))
                except RuntimeError as e:
                    _err = e
            # ponytail: _err can still be None here (all three west cells
            # solid skips every attempt). Raising None is a TypeError that
            # masks the real wall — fall through to the next strategy, which
            # is what every other strategy block already does.
            if _err is not None:
                raise _err
        # ponytail: west approach — an edge-lever stub sits at the head of a
        # lane that runs INTO the field, so the cell west of it on its own
        # row is the empty lever row, not tile. Drive to that cell, then one
        # step east into the stub. Cheapest last resort: no vertical search.
        for _k in (2, 4, 6):
            _ax, _az = stub[0] - _k, stub[1]
            if solid.get((_ax, _az)) is not None:
                continue
            try:
                return _try(lambda: _legs([drv, (_ax, _az), stub]))
            except RuntimeError as e:
                _err = e
        # ponytail: 3-segment corridor stitch. lwire's own L-paths are
        # 2-segment (one turn); a port walled on its row AND column needs two
        # turns: out along the driver's row to an intermediate x, across to
        # the stub's row, then into the stub. Measured: A0B0 drv(89,22) dies
        # on every 2-segment shape (B0's lever row walls the north exit, the
        # leg walls the south one) but (89,22)>(200,22)>(200,39)>(413,39)
        # routes in 0.3s — the corridor row z=22 runs open for 100+ cells.
        # Try intermediate x at quarters between the endpoints, both row
        # orders; each leg is one bounded lwire, so the whole attempt is
        # seconds, never the minutes a blind astar burns.
        # ponytail: south-around. Producer-exit walls (every axis RED out
        # of the driver) yield to leaving SOUTH past the whole field, running
        # east along the empty south margin, then coming back north onto the
        # stub. Measured: R1Q3's driver entombed on N/E/S/W at y=1, but south
        # to z=140 then 1564 cells east then north routed in 0.1s — the south
        # margin is empty because nothing stamps there (lanes/lever rows live
        # north, tiles end at maxz). Margin = maxz+12; legs fail loud if a
        # lamp tap or sprawl owns it, and the ladder falls through.
        try:
            # ponytail: stagger the margin per net. Every south-around sharing
            # one margin row collides with the earlier stitches' dust there
            # (measured: R0Q1's margin run died on a prior stitch's corridor).
            # Rows 4 apart never side-touch (different nets need adjacency to
            # short), so each stitch gets its own empty highway. Deterministic
            # (cross order), costs nothing.
            _maxz = _maxz0 + 12 + 4 * _stitchnets.index(n)
            _sa = (drv[0], _maxz)
            _sb = (stub[0], _maxz)
            if os.environ.get("REDSTONE_HIER_TRACE"):
                print(f"hier south {n} {drv}->{_sa}->{_sb}->{stub}", flush=True)
            return _try(lambda: _legs([drv, _sa, _sb, stub]))
        except RuntimeError as e:
            _err = e
        # ponytail: east-around. Same idea rotated: past the last band the
        # east margin is empty by construction (nothing stamps east of the
        # eastmost field edge). Staggered like the south margin. Measured
        # need: AL_X3's driver walled on west/south/north attempts.
        try:
            _maxx = _maxx0 + 12 + 4 * _stitchnets.index(n)
            _ea = (_maxx, drv[1])
            _eb = (_maxx, stub[1])
            if os.environ.get("REDSTONE_HIER_TRACE"):
                print(f"hier east {n} {drv}->{_ea}->{_eb}->{stub}", flush=True)
            return _try(lambda: _legs([drv, _ea, _eb, stub], "east"))
        except RuntimeError as e:
            _err = e
        # ponytail: north-around. Mirror of south: above every lever row is
        # empty margin (lanes/lever rows live north but nothing lives north
        # OF them). Same stagger, negative z is legal ground (lanes run
        # negative; astar clips at 0 but lwire corridors do not).
        try:
            _minz = _minz0 - 12 - 4 * _stitchnets.index(n)
            _na = (drv[0], _minz)
            _nb = (stub[0], _minz)
            if os.environ.get("REDSTONE_HIER_TRACE"):
                print(f"hier north {n} {drv}->{_na}->{_nb}->{stub}", flush=True)
            return _try(lambda: _legs([drv, _na, _nb, stub], "north"))
        except RuntimeError as e:
            _err = e
        _xs = sorted({drv[0] + (stub[0] - drv[0]) * _q // 4 for _q in (2,)})
        for _mx in _xs:
            for _za, _zb in ((drv[1], stub[1]),):
                try:
                    return _try(lambda: _legs([drv, (_mx, _za), (_mx, _zb), stub]))
                except RuntimeError as e:
                    _err = e
        _lo, _hi = sorted((drv[0], stub[0]))
        for _z in range(max(0, min(drv[1], stub[1]) - 1), -1, -1):
            if any(wires.get((x, 1, _z)) is not None
                   or solid.get((x, _z)) is not None
                   for x in range(_lo, _hi + 1)):
                continue
            for _px in (offs[b] - _HIER_GAP // 2, _lo + 2, _hi - 2):
                if solid.get((_px, _z)) is not None or wires.get((_px, 1, _z)) is not None:
                    continue
                try:
                    return _try(lambda: _legs([drv, (_px, _z), stub]))
                except RuntimeError as e:
                    _err = e
        hz0 = max(1, levermin.get(b, 2) - 1)
        px = offs[b] - _HIER_GAP // 2
        # ponytail: several hop rows, not one. A hop row that a small
        # consumer field walls off is still open two rows north (measured:
        # C2's band-3 micro-band walled the row above its lever bank but not
        # the one above that). Rows are empty margin by construction, so
        # trying more costs a stamp each and saves a whole merge.
        for _d in (0, 4, 8, 14, 22):
            hz = max(1, hz0 - _d)
            try:
                return _try(lambda: _legs([drv, (px, hz), stub]))
            except RuntimeError as e:
                _err = e
        raise _err
    # ponytail: flow starts EMPTY (reverted undirected seeding). Seeding
    # flow from partition wires marked every straight cell 2-dir
    # (forward+back), so _plant_repeaters (needs exactly 1 dir) planted
    # NOTHING on any stitch — measured: max-unboosted == full length on all
    # 9 stitch paths (170-471 cells, zero boosters), boundary nets arriving
    # dark (Y1 mismatches via dark A0B0). The back-feed it was meant to stop
    # was never measured; the under-boosting was. Fresh stitch dirs only.
    flow = {}
    stitched = {}
    # ponytail: stitch order (REDSTONE_HIER_ORDER=asc tries shortest-first;
    # default longest-first claims the hardest corridors on the empty field).
    # Two stitches sharing one consumer-edge pocket conflict whichever goes
    # second (measured: AL_C2's driver walled by AL_AB0's landed stitch);
    # order decides who claims it. Env-gated experiment, default unchanged.
    _rev = os.environ.get("REDSTONE_HIER_ORDER") == "asc"
    _freshc = set()
    for n in sorted(_stitchnets, key=_span, reverse=_rev):
        pb = prod[n]
        if os.environ.get("REDSTONE_HIER_TRACE"):
            print(f"hier stitch {n} drv={drv_of.get(n)} offs={offs}", flush=True)
        if n not in drv_of:
            raise RuntimeError(f"hier: cross net {n} has no driver")
        _fail = []
        # ponytail: chain fan-out stitches through the consumer stubs in
        # west-to-east band order, continuing from the PREVIOUS stub instead
        # of re-running from the driver every time. A long fan-out (C2
        # consumed by bands 2 AND 3) otherwise asks one run to cross two
        # whole fields: measured, driver->band3 (465 cells past band 1) died
        # on every strategy, while driver->band2 succeeds and band2->band3
        # is a short hop. Same net, so chaining is the same wire.
        _cons = []
        for (b, sub, out, pctx, sh) in built:
            # banked inputs chain through every other band's stub (the bank
            # band's own stub is the driver); everything else keeps the
            # boundary-only rule.
            if n not in sub["inputs"]:
                continue
            if n in recipe["inputs"] and n not in _banknets:
                continue
            _cons.append((b, pctx.pos[n][0] + offs[b], pctx.pos[n][1]))
        _cons.sort(key=lambda t: t[1])
        _cur = drv_of[n]
        for (b, sx, sz) in _cons:
            stub = (sx, sz)
            if os.environ.get("REDSTONE_HIER_TRACE"):
                print(f"hier leg {n} band {b} {drv_of[n]}->{stub}", flush=True)
            _prew = set(wires) | set(repeaters)
            _prews[0] = _prew
            _ss = _snap()
            from layout import _loop_rep as _lr
            _du0 = set(wires) - set(repeaters)
            _cb0 = {bb[:3] for bb in blocks
                    if bb[3].split("[")[0] == "minecraft:cobblestone"}
            _lp0 = _lr(wires, repeaters, _du0, _cb0)
            try:
                full = _stitch(_cur, stub, n, b,
                                40 if n in _banknets else 350)
            except RuntimeError as e:
                _fail.append(f"band {b} stub {stub}: {str(e)[:60]}")
                continue
            # ponytail: a banked input does NOT chain stub->stub. Its driver
            # sits in the empty margin west of the whole merge, so every
            # band's stub is reachable from it through open ground: up to the
            # north margin, east along it, down into the band. Chaining forced
            # one leg to cross every intervening field (measured: OP1
            # band2->band4, 642 cells straight through band 3, died on every
            # strategy: "path re-enters (1341,1,2)"). Same net, so the legs
            # share the corridor harmlessly. Gate nets keep the chain.
            if n not in _banknets:
                _cur = stub
            if not _planted[0]:
                for u, v in zip(full, full[1:]):
                    d = (v[0] - u[0], v[2] - u[2])
                    flow.setdefault((u[0], u[1], u[2]), set()).add(d)
                    flow.setdefault((v[0], v[1], v[2]), set()).add(d)
                _plant_repeaters(mctx, full, n, flow, end_boost=True,
                                 fresh={c for c in full if c not in _prew})
            _planted[0] = False
            # ponytail: the ring gate has to run AFTER boosting. _stitch's own
            # check fires before _plant_repeaters, so a booster that lands
            # where the path re-enters itself closes the ring unobserved
            # (measured: R1Q3's leg ends ...(2849,25),(2848,25),(2847,25)
            # then turns north past its own (2848,26),(2849,26), and the
            # west-facing diode at (2848,25) joins its own back — the merge
            # died in finish_assembly, thousands of blocks later). Roll the
            # leg back and let the net's next consumer try.
            _du = set(wires) - set(repeaters)
            _cb = {bb[:3] for bb in blocks
                   if bb[3].split("[")[0] == "minecraft:cobblestone"}
            _lp = _lr(wires, repeaters, _du, _cb)
            if _lp is not None and _lp != _lp0:
                _restore(_ss)
                _cur = drv_of[n]
                _fail.append(f"band {b} stub {stub}: rings at {_lp[0]}")
                continue
            stitched[n] = stitched.get(n, []) + [full]
            # ponytail: per-stitch dump (HIERDUMP_EACH=prefix): post-stitch
            # field snapshots so a later stitch's corridor can be debugged
            # against the exact dust it faced (not pristine). Env-gated.
            _de = os.environ.get("REDSTONE_HIERDUMP_EACH")
            if _de:
                import pickle as _p4
                with open(f"{_de}_{n}.pkl", "wb") as _f:
                    _p4.dump({"blocks": blocks, "solid": solid,
                              "rings": rings, "wires": wires,
                              "junctions": junctions,
                              "repeaters": repeaters, "pos": pos,
                              "sup": sup}, _f)
        if _fail:
            # ponytail: dump on a STITCH failure too. The opens/finish dumps
            # cover everything downstream of a landed stitch, but a stitch that
            # never lands has no dump at all -- and a banked input's fan-out is
            # the first thing that can fail there (measured: "hier stitch A3B3:
            # band 4 stub (1566,63): no ground for A3B3: (1834,50) ->
            # (1341,1)" with no field to inspect). Same env gate as the others.
            _df = os.environ.get("REDSTONE_HIERDUMP_FAIL")
            if _df:
                import pickle as _p5
                with open(_df, "wb") as _f:
                    _p5.dump({"blocks": blocks, "solid": solid,
                              "rings": rings, "wires": wires,
                              "junctions": junctions,
                              "repeaters": repeaters, "pos": pos, "sup": sup,
                              "stitched": stitched}, _f)
                print(f"hier dump-fail {_df}", flush=True)
            raise RuntimeError(f"hier stitch {n}: " + " | ".join(_fail))
    # ponytail: merge-wide slope-link lids. Partitions route (and 3D-fly)
    # assuming open surroundings; after the merge a foreign y=1 run can sit
    # diagonally below supported y>=2 dust, and the sim couples them while
    # check_shorts stays silent (measured: 273 elevated cells over band
    # fields, churn with no torch loop, all in a stitch corridor). Same rule
    # as _walk's per-walk lids, applied to EVERY elevated cell regardless of
    # which walk minted it: support below + foreign diagonal-below + no lid
    # over it -> drop one cobble above the lower wire. Blocks over ground
    # wire are inert, so electrics never move; only the coupling dies.
    # ponytail: default ON again (REDSTONE_MERGE_LIDS=0 opts out): the
    # churn it was written to fix is real (measured: R1Q*~qb legs ring
    # forever against the R1_R* repeater output beside them).
    # REDSTONE_MERGE_LIDS=0 opts out (A/B only); the pass is on because
    # the coupling it prevents is measured, not theoretical.
    # Added for a churn misdiagnosed as slope coupling (it was slow
    # convergence under tight caps: empty loop list, huge max_gap, settled
    # with headroom) — but a lid over a live slope breaks it into an OPEN
    # (measured: C3's hop, lid with no foreign pair needing it, merge dead).
    # _walk's per-walk hop lids (proven, pre-existing) still run; this pass
    # stays available for a coupling with a measured foreign pair.
    _elev = [(x, y, z) for (x, y, z), _nw in wires.items() if y >= 2]
    if _elev and os.environ.get("REDSTONE_MERGE_LIDS") != "0":
        _cob = {(bx, by, bz) for bx, by, bz, bid in blocks
                if bid.split("[")[0] == "minecraft:cobblestone"}
        for (x, y, z) in _elev:
            _un = wires[(x, y, z)]
            if (x, y - 1, z) not in _cob:
                continue
            for dx, dz in DIRS:
                lx, ly, lz = x + dx, y - 1, z + dz
                fw = wires.get((lx, ly, lz))
                if fw is None or fw == _un or (lx, y, lz) in _cob:
                    continue
                if (wires.get((lx, y, lz)) is not None
                        or (lx, ly, lz) in repeaters):
                    continue
                # ponytail: never lid airspace a same-net slope needs. The
                # lid cell may sit beside the lower wire's own elevated dust
                # (a hop mid-span or a flight leg passing through); lidding it
                # breaks that slope into an OPEN (measured: C3's hop killed
                # by a lid over its own lower, for a foreign pair that shares
                # the airspace). Coupling risk stays with the sim (it judges
                # values); a broken slope fails the whole merge now.
                if any(wires.get((lx + _ex, y, lz + _ez)) == fw
                       for _ex, _ez in DIRS):
                    continue
                _cob.add((lx, y, lz))
                blocks.append((lx, y, lz, "minecraft:cobblestone"))

    # ponytail: slope-clearing (runs AFTER the lid pass above, on purpose).
    # A lid the pass just added over a live same-net slope breaks that slope
    # into an OPEN (measured: C3 hop at (2847,2,155)). Reversing the order
    # was the whole bug. Stale lids from (partition _walk, or an earlier merge
    # pass) sitting over a stitch hop's lower cell breaks a legitimate slope
    # into an OPEN (measured: C3's hop, lid with no foreign pair needing it).
    # Instead of lidding the world, clear exactly the slope airspace each
    # stitch needs: for every elevated stitch cell with support below, drop
    # cobble found directly above its same-net diagonal-below neighbour —
    # but only when nothing sits above the lid cell itself (a structural
    # pillar carrying dust stays, always). Protective lids elsewhere (over
    # genuinely foreign pairs) are untouched.
    # ponytail: hoisted (a rebuild per cell hung the merge: 34k blocks ×
    # thousands of path cells). Removals discard manually; nothing here adds
    # cobble, so the set only shrinks and stays exact.
    _cob_all = {(bx, by, bz) for bx, by, bz, bid in blocks
                if bid.split("[")[0] == "minecraft:cobblestone"}

    for _n, _paths in stitched.items():
        for _full in _paths:
            for (_x, _y, _z) in _full:
                if _y < 2 or (_x, _y - 1, _z) not in _cob_all:
                    continue
                for _dx, _dz in DIRS:
                    _lx, _ly, _lz = _x + _dx, _y - 1, _z + _dz
                    if wires.get((_lx, _ly, _lz)) != _n:
                        continue
                    _lid = (_lx, _y, _lz)
                    if _lid not in _cob_all:
                        continue
                    # ponytail: directly-above only. Pillars carry dust
                    # straight up; the earlier version kept any lid with dust
                    # anywhere in the 3x3 above, which protects nothing real
                    # and blocked the exact slope it was written to clear
                    # (measured: R1Q3 dust at (2847,3,154) vetoed clearing).
                    if wires.get((_lid[0], _lid[1] + 1, _lid[2])) is not None:
                        continue
                    blocks[:] = [bb for bb in blocks
                                 if not (bb[0] == _lid[0] and bb[1] == _lid[1] and bb[2] == _lid[2]
                                         and bb[3].split("[")[0] == "minecraft:cobblestone")]
                    _cob_all.discard(_lid)
    # ponytail: connect producer stubs. A cross net with no in-band loads
    # leaves placement stub dust around its tile ports (never routed — there
    # was nothing to route to); after the merge that dust is OPEN (nothing
    # drives it) and check_opens fails the whole build for it (measured:
    # AL_C2/AL_t23 orphans hugging their driver tiles). BFS the net from its
    # driver over the merged field; every same-net cell in the producer band
    # that is NOT reached is a stub — route a short driver leg to each.
    # Stubs sit beside their tile, so these legs are single-digit cells;
    # anything farther is a real wall and fails loud, honestly.
    from collections import deque as _dq

    def _stub_band(_n, _bb, _anchor):
        # One band's stub pass (called for the producer's driver anchor and
        # each consumer's stub anchor — extracted as a helper so every seed
        # actually runs; an earlier inline version stranded the flood outside
        # its loop and only the last seed ever executed).
        _lo = offs[_bb]
        _his = [offs[bb] for bb in offs if offs[bb] > _lo]
        _hi = min(_his) if _his else 10 ** 9
        _seen, _qq = set(), _dq()
        # ponytail: check_opens-exact flood. A wire-only BFS fragments every
        # boosted lane (repeaters split dust runs) and every hop span (y=2/3
        # dust bridges a y=1 gap) into "unreached" stubs, then dies loud
        # connecting healthy legs (measured false walls on AL_AB2 twice).
        # Mirror check_opens cell-for-cell — same-net dust, same-net
        # repeaters, slope links with support below and no lid above, OR
        # junctions carrying the net — so anything this flood cannot reach is
        # exactly what check_opens will flag. No radius cap: hop artifacts
        # traverse correctly now, and a far true orphan fails loud honestly.
        # (Support split mirrors check_opens: _sup/_src from layout; lids
        # stay cobblestone-only. Parity is load-bearing here by construction.)
        _cob = {(bx, by, bz) for bx, by, bz, bid in blocks
                if bid.split("[")[0] == "minecraft:cobblestone"}
        _sup = _layout_sup3(blocks)
        _src = _layout_src3(blocks)

        # ponytail: seed AND traverse EXACTLY like check_opens (same
        # function, both halves). Two divergences were measured: (1) bare
        # junction cells (no wire) were traversed here but check_opens needs
        # wire there; (2) a repeater on a foreign-wire cell was traversed here
        # but check_opens' elif skips repeaters wherever wire sits. Both made
        # this flood call cells reached that check_opens flags, so orphans
        # survived every leg. Seeds mirror check_opens too (pos cell holding
        # the net, lever-adjacent cells, torch-adjacent cells) plus the local
        # anchor, so unreached here == dead there, by construction.
        def _push(_c, _nn):
            if (_c, _nn) not in _seen:
                _seen.add((_c, _nn))
                _qq.append((_c, _nn))

        _d3 = (_anchor[0], 1, _anchor[1])
        if wires.get(_d3) == _n:
            _push(_d3, _n)
        _pp = pos.get(_n)
        if _pp is not None:
            _p3 = (_pp[0], 1, _pp[1])
            if wires.get(_p3) == _n:
                _push(_p3, _n)
        for (_lx, _lz), (_kind, _ln) in solid.items():
            if _ln != _n:
                continue
            if _kind == "lever":
                for _ax, _az in DIRS:
                    _lc = (_lx + _ax, 1, _lz + _az)
                    if wires.get(_lc) == _n:
                        _push(_lc, _n)
            elif _kind == "torch":
                pass  # torch-adjacent dust seeds below (needs torch map)
        for _bx, _by, _bz, _bid in blocks:
            if "wall_torch" not in _bid:
                continue
            for _ax, _az in DIRS:
                _tc = (_bx + _ax, 1, _bz + _az)
                if wires.get(_tc) == _n:
                    _push(_tc, _n)
        while _qq:
            _c, _nn = _qq.popleft()
            for _ax, _az in DIRS:
                _m = (_c[0] + _ax, _c[1], _c[2] + _az)
                if _m in wires:
                    _nm = wires[_m]
                    if _nm == _nn or ((_m[0], _m[2]) in junctions
                                      and _nm in junctions[(_m[0], _m[2])]) or \
                       (((_c[0], _c[2]) in junctions
                         and _nn in junctions[(_c[0], _c[2])])):
                        _push(_m, _nm if _nm == _nn or (_m[0], _m[2]) not in junctions else _nn)
                elif (repeaters.get(_m) is not None
                      and repeaters[_m][0] == _nn):
                    _push(_m, _nn)
                elif (solid.get((_m[0], _m[2]), (None,))[0] == "repeater"
                      and solid[(_m[0], _m[2])][1] == _nn):
                    _push(_m, _nn)
                _up = (_c[0] + _ax, _c[1] + 1, _c[2] + _az)
                if (wires.get(_up) == _nn and (_c[0] + _ax, _c[1], _c[2] + _az) in _src
                        and (_c[0], _c[1] + 1, _c[2]) not in _cob):
                    _push(_up, _nn)
                _dn = (_c[0] + _ax, _c[1] - 1, _c[2] + _az)
                if (wires.get(_dn) == _nn and (_c[0], _c[1] - 1, _c[2]) in _sup
                        and (_c[0] + _ax, _c[1], _c[2] + _az) not in _cob):
                    _push(_dn, _nn)
        # ponytail: _seen holds (cell, net) states like check_opens (a cell
        # reached as another net through a junction does not count), so the
        # orphan test pairs the cell back up — else every cell reads unreached
        # and the pass sprays legs at healthy runs.
        _orph = [(_x, _y, _z) for (_x, _y, _z), _wn in list(wires.items())
                   if _wn == _n and ((_x, _y, _z), _n) not in _seen
                   and _lo <= _x < _hi and _y == 1]
        if os.environ.get("REDSTONE_HIER_TRACE"):
            _d3 = (_anchor[0], 1, _anchor[1])
            print(f"hier stubs {_n} band {_bb}: {len(_orph)} orphans "
                  f"anchor={_anchor} wire={wires.get(_d3)} "
                  f"first={(_orph[0] if _orph else None)}", flush=True)
        # ponytail: cap legs per net. A tile's stubs are a handful of cells;
        # dozens of "orphans" means a disconnected region (or a latch bank),
        # and each leg burns corridors+astar — measured >100s wall with no
        # output. Attempt the first few (covers real stubs); the rest stay
        # for check_opens to report loudly instead of hanging here.
        for (_x, _y, _z) in _orph[:6]:
            _ss = _snap()
            from layout import _loop_rep as _lr
            _du0 = set(mctx.wires) - set(mctx.repeaters)
            _cb0 = _layout_flood3(blocks)
            _lp0 = _lr(mctx.wires, mctx.repeaters, _du0, _cb0)
            try:
                _full = lwire(mctx, sup, guard, _anchor, (_x, _z), _n)
                # same gate as _stitch: a leg's own booster can close a
                # front-joins-back ring, and finish_assembly kills the WHOLE
                # merge on one. This path is outside _try, so it had none
                # (measured: R1Q3 at (2850,1,43) came from a stub leg).
                for _u, _v in zip(_full, _full[1:]):
                    _dd = (_v[0] - _u[0], _v[2] - _u[2])
                    flow.setdefault((_u[0], _u[1], _u[2]), set()).add(_dd)
                    flow.setdefault((_v[0], _v[1], _v[2]), set()).add(_dd)
                _plant_repeaters(mctx, _full, _n, flow)
                _du = set(mctx.wires) - set(mctx.repeaters)
                _cb = _layout_flood3(blocks)
                _lp = _lr(mctx.wires, mctx.repeaters, _du, _cb)
                if _lp is not None and _lp != _lp0:
                    raise RuntimeError(f"hier stub {_n}: rings at {_lp[0]}")
            except RuntimeError as _e:
                _restore(_ss)
                raise RuntimeError(f"hier stub {_n}: {_e}") from None
            stitched[_n] = stitched.get(_n, []) + [_full]
            # ponytail: the new leg is wired and live by construction — mark
            # its whole path reached, or the next orphan on the same run
            # burns another leg for cells this one already joined (measured:
            # one 6-cell run ate all 6 budgeted legs and still reported).
            # States, not cells: _seen holds (cell, net) pairs.
            for _c in _full:
                _seen.add((_c, _n))

    for _n in _stitchnets:
        _pb = prod[_n]
        _drv = drv_of.get(_n)
        if _drv is None:
            continue
        # ponytail: banked input nets seed EVERY consuming band, not just the
        # driver. A partition lever sat INSIDE its band and powered every
        # adjacent cell at 15, so a band's input net could have islands the
        # stub never reached. With the lever gone those islands are orphaned
        # (measured: check_opens OPEN on band 4's OP1 dust at (1467..1515,1,
        # 65..67)), and this per-band flood + leg pass is what reconnects them.
        _seedlist = [(_pb, _drv)]
        for (b, sub, out, pctx, sh) in built:
            if _n in sub["inputs"] and (_n not in recipe["inputs"]
                                       or _n in _banknets):
                _seedlist.append((b, (pctx.pos[_n][0] + offs[b],
                                      pctx.pos[_n][1])))
        for (_bb, _anchor) in _seedlist:
            _stub_band(_n, _bb, _anchor)
    check_shorts(wires, junctions, blocks)
    try:
        check_opens(wires, junctions, repeaters, solid, pos, blocks)
    except RuntimeError:
        # ponytail: exact-state dump on opens failure (HIERDUMP_FAIL): the
        # merged field + stitch paths at the moment of failure, so orphan
        # forensics runs on the real field instead of a reimplementation.
        # Env-gated, never fires otherwise.
        _df = os.environ.get("REDSTONE_HIERDUMP_FAIL")
        if _df:
            import pickle as _p3
            with open(_df, "wb") as _f:
                _p3.dump({"blocks": blocks, "solid": solid, "rings": rings,
                          "wires": wires, "junctions": junctions,
                          "repeaters": repeaters, "pos": pos, "sup": sup,
                          "stitched": stitched}, _f)
            print(f"hier dump-fail {_df}", flush=True)
        raise
    try:
        _out = finish_assembly(blocks, solid, wires, rings, junctions, repeaters, pos)
    except RuntimeError:
        # ponytail: same exact-state dump for finish_assembly failures
        # (repeater loops): the loop involves merge-added dust+repeaters, so
        # only the merged field diagnoses it. Same env gate as opens dumps.
        _df = os.environ.get("REDSTONE_HIERDUMP_FAIL")
        if _df:
            import pickle as _p3
            with open(_df, "wb") as _f:
                _p3.dump({"blocks": blocks, "solid": solid, "rings": rings,
                          "wires": wires, "junctions": junctions,
                          "repeaters": repeaters, "pos": pos, "sup": sup,
                          "stitched": stitched}, _f)
            print(f"hier dump-fail {_df}", flush=True)
        raise
    # ponytail: post-merge dump (REDSTONE_HIERDUMP2) for oscillator forensics:
    # the exact merged field + io + stitch paths, so coupling scans and
    # bisection sims iterate offline in seconds.
    _dump2 = os.environ.get("REDSTONE_HIERDUMP2")
    if _dump2:
        import pickle as _p2
        # ponytail: ship the shrink-wrap shift WITH the dump. solid / wires /
        # repeaters / rings / stitched are MERGE space; blocks and io are
        # BLOCK space, and finish_assembly moves them by (3 - min(OCC)) per
        # axis. Re-deriving that by hand has cost two sessions of forensics
        # (a phantom "3388 cobble deleted", then a phantom "230 missing
        # torches"). One key, no more arithmetic.
        # finish_assembly's OCC is solid AND wires, not solid alone (wires
        # run to z=-83 where tiles stop at -15, so using solid alone gave
        # (2,18) instead of (2,86) and matched 0/230 torches).
        _occ = [(x, 1, z) for (x, z) in solid] + list(wires)
        with open(_dump2, "wb") as _f:
            _p2.dump({"blocks": _out[0], "size": _out[1], "io": _out[2],
                      "solid": solid, "rings": rings, "wires": wires,
                      "junctions": junctions,
                      "repeaters": repeaters,
                      "pos": pos, "sup": sup, "stitched": stitched,
                      "shift": (3 - min(c[0] for c in _occ),
                                3 - min(c[2] for c in _occ))}, _f)
        print(f"hier dump2 {_dump2}", flush=True)
    return _out


def hier_dump(path, merged, metas, cross, prod, inputs):
    # stitch-iteration harness: pickle the post-lever-removal merged field
    # so stitch strategies iterate in seconds without re-composing bands
    # (30 min per full run). Harness rebuilds mctx + guard + levermin and
    # calls _stitch variants directly.
    import pickle as _p
    rec = {"merged": merged, "metas": metas, "cross": cross, "prod": prod,
           "inputs": inputs}
    with open(path, "wb") as f:
        _p.dump(rec, f)
    print(f"hier dump {path} ({len(metas)} bands)", flush=True)


# Placement spread factor (module-global so _compose_once's spacing reads
# it). 1 = the tight layout every green build was verified on.
_SPREAD = 1

# Routing order: gates-first is proven; inputs-first gives inputs clean
# ground (measured: alu1's OP1/OP0 input collision vanishes, micro1 stays
# green). compose() tries gates-first at every spread, then inputs-first.
_ORDER = "gates_first"

# Territorial placement + band-ordered routing (hierarchical-lite for 70+
# gate fields). 0 = off (every green build). compose() escalates here only
# after the whole standard ladder fails on a big banded recipe, so greens
# never see it; REDSTONE_TERR=1 forces it for probes. Bands become x
# territories (wide streets between them stay open for cross-band trunks);
# intra-band nets route before cross-band nets.
_TERR = 0
_TERR_W = 120
_TERR_MIN_GATES = 40

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

# Live deadline for the current compose() ladder, checked inside
# _compose_once's restart loop (rule 7). None when unset or outside compose().
_DEADLINE = None

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
    global _SPREAD, _ORDER, _JOGS, _DEADLINE, _TERR
    last = None
    deadline = time.monotonic() + _COMPOSE_SECS if _COMPOSE_SECS else None
    _DEADLINE = deadline
    # REDSTONE_FORCE="spread,order,jog" pins one rung (diagnostics: bisect a
    # single config instead of climbing the whole ladder).
    force = os.environ.get("REDSTONE_FORCE", "").strip()
    # ponytail: territorial fallback. Standard ladder first (every green lands
    # rung 1, bit-identical — the fallback never runs for them); only a big
    # banded recipe that exhausts all 44 rungs escalates to territories.
    # REDSTONE_TERR=1 skips straight to territories (probes).
    terr_only = os.environ.get("REDSTONE_TERR") == "1"
    terr_attempts = [("short", s, o, 1)
                     for s in (2, 4) for o in ("gates_first", "inputs_first")]
    # ponytail: split-and-stitch macros first for big banded recipes (their
    # partitions route at 15-gate scale in seconds; the monolith cannot).
    # Greens are never big (<40 gates), so this branch never runs for them.
    # REDSTONE_HIER=1 jumps straight to macros (probes).
    hier_only = os.environ.get("REDSTONE_HIER") == "1"
    big_banded = (len(recipe["gates"]) >= _TERR_MIN_GATES
                  and any(g.get("band") is not None for g in recipe["gates"]))
    if force:
        f_spread, _, rest = force.partition(",")
        f_order, _, f_jog = rest.partition(",")
        attempts = [(f_jog or "short", int(f_spread), f_order or "gates_first", 0)]
    elif terr_only:
        attempts = terr_attempts
    else:
        attempts = [(j, s, o, 0)
                    for j in ("short", "long")
                    for s in (1, 2, 3, 4, 5, 6, 8, 10)
                    for o in ("gates_first", "inputs_first")]
    try:
        if hier_only:
            _SPREAD, _ORDER, _TERR = 1, "gates_first", 0
            return compose_hier(recipe)
        if not force and not terr_only and big_banded:
            _hier_dl = deadline
            try:
                return compose_hier(recipe)
            except RuntimeError as e:
                last = e
                # sub ladders re-arm the global clock; restore the outer one
                # so the remaining ladder keeps its own budget. Same for the
                # stitch-only NO3D env (flat+hops do not leak into standard
                # rungs that need their overflights).
                _DEADLINE = deadline
                # compose_hier_parts is the only setter (callers never set
                # it), so pop restores the pre-hier state exactly.
                os.environ.pop("REDSTONE_NO3D", None)
                if ((deadline and time.monotonic() > deadline)
                        or not any(k in str(e) for k in _RETRYABLE)):
                    raise
                print(f"compose hier failed ({str(e)[:60]}); retrying",
                      flush=True)
        # ponytail: sim-gated ladder (REDSTONE_SIM_GATE=1, set by layout_retry
        # when verify=True). A rung that routes but miscomputes used to ship
        # (measured: mux4 rung-1 routes, Y3 wrong on 32 vectors under correct
        # lever physics) because the ladder stops at the first ROUTE. With the
        # gate, a routed-but-red rung retries instead — every current green
        # lands rung 1 sim-green bit-identical, so the gate is a no-op for
        # them. Big banded recipes skip it (their hier path sim-gates its own
        # partitions; a 1024-vector sim per rung would 50x the ladder).
        # Default OFF (previews stay fast); all sim failures retry (rung
        # geometry, not logic — a later rung can be clean).
        _simgate = (os.environ.get("REDSTONE_SIM_GATE") == "1"
                    and not big_banded)
        if _simgate:
            from sim import sim_verify as _simv
        for i, (jog, spread, order, terr) in enumerate(attempts):
            _SPREAD, _ORDER, _TERR = spread, order, terr
            _JOGS = _JOGS_SHORT if jog == "short" else _JOGS_LONG
            try:
                _res = _compose_once(recipe)
            except RuntimeError as e:
                last = e
                if (i == len(attempts) - 1
                        or (deadline and time.monotonic() > deadline)
                        or not any(k in str(e) for k in _RETRYABLE)):
                    raise
                print(f"compose {jog} spread {spread} {order}"
                      f"{' terr' if terr else ''} failed "
                      f"({str(e)[:60]}); retrying", flush=True)
                continue
            if not _simgate:
                return _res
            if deadline and time.monotonic() > deadline:
                return _res  # budget spent: ship the route ungated (old
                # behavior); the caller still sims it when verifying.
            try:
                _simv(recipe, _res[0], _res[2], quiet=True)
            except RuntimeError as e:
                last = e
                if (i == len(attempts) - 1
                        or (deadline and time.monotonic() > deadline)):
                    raise
                print(f"compose {jog} spread {spread} {order} sim-red "
                      f"({str(e)[:60]}); retrying", flush=True)
                continue
            return _res
        # standard ladder exhausted: escalate big banded recipes to territories
        if (not force and not terr_only
                and len(recipe["gates"]) >= _TERR_MIN_GATES
                and any(g.get("band") is not None for g in recipe["gates"])
                and any(k in str(last) for k in _RETRYABLE)
                and not (deadline and time.monotonic() > deadline)):
            for (jog, spread, order, terr) in terr_attempts:
                _SPREAD, _ORDER, _TERR = spread, order, terr
                _JOGS = _JOGS_SHORT
                try:
                    return _compose_once(recipe)
                except RuntimeError as e:
                    last = e
                    if ((deadline and time.monotonic() > deadline)
                            or not any(k in str(e) for k in _RETRYABLE)):
                        raise
                    print(f"compose {jog} spread {spread} {order} terr failed "
                          f"({str(e)[:60]}); retrying", flush=True)
        # ponytail: last is None only if attempts was empty (no rung ran).
        # Raising None is a TypeError; name the real wall instead.
        if last is None:
            raise RuntimeError("compose: empty ladder (no rungs attempted)")
        raise last
    finally:
        _DEADLINE = None
        _TERR = 0


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
