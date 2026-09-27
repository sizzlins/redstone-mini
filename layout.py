"""Layout: A* maze router plus block placer (torch tiles, compounds)."""

import heapq
import os as _os
import random

from core import DIRS, TORCH_BACK
from recipe import expand_gates

# ponytail: pop cap bounds worst-case search per astar call (a sealed field
# is W*D pops of thrash; trip -> None -> loud RuntimeError -> next seed).
# Raise via REDSTONE_ASTAR_CAP if a verified build ever trips it.
_ASTAR_CAP = int(_os.environ.get("REDSTONE_ASTAR_CAP", "100000"))

# ponytail: 3D wires Attempt 1 (tiles stay flat). y=1 ground, y=2 ramp,
# y=3 flyover. Level-change moves cost _STEPCOST vs flat 1 (priced, ground
# preferred; seals pay for height). Ceiling: H=3, raise if a dump names a
# sealer needing a higher deck.
_H = 3
_STEPCOST = 4
# ponytail: 2 = ground-first passes (a net may only fly after every net has had
# its flat attempt). 1 = fly as soon as a net is stuck. Env-switched because the
# two orderings trade off against each other (see PONYTAIL-DEBT).
_PASSES = int(_os.environ.get("REDSTONE_3D_PASSES", "2"))

_OPP = {(1, 0): (-1, 0), (-1, 0): (1, 0), (0, 1): (0, -1), (0, -1): (0, 1)}


def dust_points(cell, dust):
    """The directions a dust cell points, i.e. where it can power a SIDE block.

    Vanilla (minecraft.wiki, Redstone Dust -> Placement / Behavior): powered
    dust weakly powers a conductive block only when it is ON TOP of it or
    POINTING at it. Pointing is a per-direction property of the cell's
    connection shape, which the game stores in its block states
    (east/north/south/west in {none, side, up}, "side can also mean down"):

      cross  (no dust neighbour) -> all four ways
      end    (one link)          -> "a line pointing both at the neighbor and
                                     away from it" = that axis, both ways
      line   (two opposite links)-> its own axis
      corner / T (2 adjacent / 3)-> the links it has
      dot    (right-clicked cross)-> nothing sideways (layouts never stamp one)

    A block is therefore powered by dust sitting on it, or by dust whose
    `dust_points` contains the direction from the dust to the block. Nothing
    else — notably a wire merely running PAST a block does not power it.

    ponytail: this lives here because layout owns the net map that defines the
    shape, and sim.py already imports from here, so the sim's block-power test
    and the exporter's blockstate writer share one table and cannot drift.
    Not yet consumed by either: wiring it into the sim changes verdicts, and
    that waits on the in-game end-cell test (see handoff).
    """
    live = [d for d in DIRS
            if (cell[0] + d[0], cell[1], cell[2] + d[1]) in dust]
    if not live:
        return frozenset(DIRS)                             # cross
    if len(live) == 1:
        return frozenset((live[0], _OPP[live[0]]))         # end: its own axis
    return frozenset(live)                                 # line / corner / T


_DIRNAME = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}


def wire_bid(cell, dust):
    """Full wire block id: base id plus pointing states from dust_points().

    The game stores a wire's connection shape per cell, so the FILE must
    carry it — a bare id pastes as a dot that powers nothing sideways.
    ponytail: flat dirs only (an elevated slope link bakes as none until the
    game updates it — needs a shared slope predicate if 3D ever ships);
    power is dynamic and game-owned, never baked.
    """
    pts = dust_points(cell, dust)
    return "minecraft:redstone_wire[" + ",".join(
        f"{_DIRNAME[d]}={'side' if d in pts else 'none'}" for d in DIRS) + "]"


def _support(cell, net, solid, wires, sup, reps, guard):
    """Support under a y>=2 wire cell: None=reuse, (x,y,z)=stamp once,
    False=infeasible. Never share foreign pillars (no refcounting), never
    reuse torch-attached cobble (dust powers it, flips the tile torch),
    never bury dust/diodes, never pillar directly under foreign dust
    (that would create a link the search never assumed)."""
    x, y, z = cell
    if y <= 1:
        return None
    b = (x, y - 1, z)
    if b in sup:
        return None if sup[b] == net else False
    if b in wires or b in reps:
        return False
    if b[1] == 1:
        k = solid.get((b[0], b[2]))
        if k is not None:
            if k[0] != "cobble" or (b[0], b[2]) in guard:
                return False
            return None
    w = wires.get((b[0], b[1] + 1, b[2]))
    if w is not None and w != net:
        return False
    return b


def _coupling_forb(wires, net, starts, goal, junctions, cob, air, window=None):
    """Cells that would couple to a foreign net: a same-level side touch, or a
    true slope link (support under the upper + no lid over the lower, sim's
    rule). Built from the FOREIGN side, so each foreign wire visits 4
    same-level neighbours (+8 slope partners when elevated dust exists)
    instead of every candidate probing 12 neighbours.

    Depends only on the net, the wires, the junctions and the support set, so
    one build serves a whole search.

    `window` (x0, x1, z0, z1) restricts the BUILD to foreign cells one step
    outside it: a candidate inside the window can only couple to a neighbour
    one step out, and `ok` already rejects candidates outside it, so the
    result is identical for every cell the search can ask about. The margin
    windows cover a fraction of a 20k-cell field, and the build was 12% of
    layout time. `fwire` stays FULL so the blame set is unaffected.
    """
    airstrip = set()
    for ax, ay, az in air:
        airstrip.update(((ax + 1, az), (ax - 1, az), (ax, az + 1), (ax, az - 1)))
    fwire = {c for c, n in wires.items() if n != net}
    if window is None:
        near = fwire
    else:
        wx0, wx1, wz0, wz1 = window
        wx0 -= 1
        wx1 += 1
        wz0 -= 1
        wz1 += 1
        near = {c for c in fwire if wx0 <= c[0] <= wx1 and wz0 <= c[2] <= wz1}
    forb = set()
    addforb = forb.add
    jget = junctions.get
    for c in near:
        cx, cy, cz = c
        # every exemption in the per-candidate form is stated about the
        # FOREIGN cell (it can never be `prev`, but it CAN be a foreign-held
        # port that sits in `starts`, and the goal may be foreign-owned).
        x_exempt = c in starts
        for dx, dz in DIRS:
            nx, nz = cx + dx, cz + dz
            if not x_exempt:
                j = jget((cx, cz))       # OR junction: wired-OR is the gate
                if not (j and net in j):
                    addforb((nx, cy, nz))
            if x_exempt or c == goal:
                continue
            # foreign c is the LOWER cell, candidate the upper one (own
            # support comes from move legality, so only the lid over the
            # foreign is tested).
            if (cx, cy + 1, cz) not in cob:
                addforb((nx, cy + 1, nz))
            # foreign c is the UPPER cell, candidate the lower one. Support
            # belongs UNDER the upper, the lid sits OVER the lower. A y=1
            # candidate can only couple if it is in the elevated-dust strip.
            if (cx, cy - 1, cz) in cob and (nx, cy, nz) not in cob:
                if cy > 2 or (air and (nx, nz) in airstrip):
                    addforb((nx, cy - 1, nz))
    return forb, fwire


def _straight3(a, b, c):
    """Three collinear cells at one level (booster/repeater sites). Ground and
    pillars alike: a repeater on a pillar is legal physics (the route already
    stamped the support) and sim's repeater/cobble rules are y-generic."""
    return a[1] == b[1] == c[1] and (a[0] == b[0] == c[0] or a[2] == b[2] == c[2])


def _cover_gap(path, i):
    """Backward booster cover: cheapest straight triple within 14 of path[i],
    or False. Dust dies after 15, so a run with no straight triple inside that
    window is unboostable (long pure-elevated flight) and the route is refused.
    Total order by (len, path) so builds compare across processes."""
    cands = [j for j in range(max(1, i - 14), min(i - 1, len(path) - 1) + 1)
             if _straight3(path[j - 1], path[j], path[j + 1])]
    return min(cands) if cands else False


def _loop_rep(wires, repeaters, dust):
    """First repeater whose front joins its back via same-net dust (a
    non-inverting loop: bistable in sim AND vanilla, the first transient
    latches it forever — micro1-s2 S at (80,1,19)). None when clean. Cost is
    one O(1) label check per repeater; BFS runs only on same-net pairs and
    exits on the first loop. Flat adjacency only: a slope-closed loop misses.
    """
    _V = {"east": (1, 0), "west": (-1, 0), "south": (0, 1), "north": (0, -1)}
    for (x, y, z), (net, facing) in repeaters.items():
        dx, dz = _V[facing]
        front, back = (x + dx, y, z + dz), (x - dx, y, z - dz)
        nf = wires.get(front)
        if front not in dust or back not in dust or nf is None \
                or wires.get(back) != nf:
            continue
        seen = {front}
        stack = [front]
        while stack:
            u = stack.pop()
            if u == back:
                return (x, y, z), nf
            for ox, oz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                m = (u[0] + ox, u[1], u[2] + oz)
                if m in dust and wires.get(m) == net and m not in seen:
                    seen.add(m)
                    stack.append(m)
    return None


def _has_support(cell, sup, solid):
    """Can a repeater stand at `cell`? y=1 rides the ground/stone floor; y>=2
    needs a solid block directly under it (route pillar or tile cobble).
    Loud False, never a floating repeater."""
    if cell[1] <= 1:
        return True
    b = (cell[0], cell[1] - 1, cell[2])
    if b in sup:
        return True
    return solid.get((b[0], b[2]), (None,))[0] == "cobble"


def astar(starts, goal, net, W, D, solid, rings, wires, junctions, margin=None, blocked=None, congest=None, guard=None, sup=None, reps=None, cob3=None, flat_only=False, aircells=frozenset()):
    """6-dir maze route for one wire (multi-source: fanout taps nearest own wire).
    None if blocked (loud fail, never silent wrong). Cells are (x, y, z),
    y in 1.._H; starts/goal are y=1 tile ports. Guards are per-level: y=1
    keeps solid/ring/torch-hug rules, y>=2 ignores tile columns (overflight)
    and couples only via true slope links (support + no lid, sim's rule).
    Supports are feasibility-checked here, stamped once by route()."""
    if sup is None:
        sup = {}
    if reps is None:
        reps = {}
    if guard is None:
        guard = set()
    if isinstance(starts, tuple):
        starts = [starts]
    starts = list(dict.fromkeys(starts))
    if margin is None:
        x0, x1, z0, z1 = 0, W - 1, 0, D - 1
    else:
        x0 = max(0, min(min(s[0] for s in starts), goal[0]) - margin)
        x1 = min(W - 1, max(max(s[0] for s in starts), goal[0]) + margin)
        z0 = max(0, min(min(s[2] for s in starts), goal[2]) - margin)
        z1 = min(D - 1, max(max(s[2] for s in starts), goal[2]) + margin)
    # every conductive block (tile cobble, bridge support, stamped pillar) —
    # passed in pre-joined by route() so this is O(1) per call, not a rebuild
    cob = cob3 if cob3 is not None else set(sup)
    # O(1) replacements for the per-candidate distance test: `near` is every
    # cell within Chebyshev 2 of the goal or a start (the port exemption),
    # `gexp` is the torch-hug guard grown by one cell, `air` is maintained by
    # the layout (a y=1 cell can only couple upward if some elevated dust
    # exists at all). Was: a generator + abs/max per candidate, plus an
    # O(len(wires)) scan per call.
    near = set()
    for cx, cz in [(goal[0], goal[2])] + [(s[0], s[2]) for s in starts]:
        for ax in range(cx - 2, cx + 3):
            for az in range(cz - 2, cz + 3):
                near.add((ax, az))
    gexp = set(guard)
    for gx0, gz0 in list(guard):
        gexp.update(((gx0 + 1, gz0), (gx0 - 1, gz0), (gx0, gz0 + 1), (gx0, gz0 - 1)))
    air = aircells
    # Elevated dust is rare (a handful of flights per build) but every flat
    # candidate used to pay 8 vertical-coupling lookups for it. `airstrip` is
    # those cells dilated by one in x/z: a y=1 cell can only couple upward if
    # it is IN the strip, so 1 lookup replaces 8 for everyone else.
    airstrip = set()
    for ax, ay, az in air:
        airstrip.update(((ax + 1, az), (ax - 1, az), (ax, az + 1), (ax, az - 1)))
    # ponytail: hoist the coupling predicate from per-candidate to per-search.
    # `forb` = every cell that side-touches a foreign net, or slope-couples to
    # one. Built from the FOREIGN cell outwards, so each foreign wire visits 4
    # same-level neighbours (+8 slope partners when elevated dust exists)
    # instead of every candidate probing 12 neighbours. Per search: ~1.3k
    # cheap ops instead of 12.8k x ~6 dict.gets (was 63M gets on alu1).
    _XCHECK = _os.environ.get("REDSTONE_XCHECK") == "1"
    forb, fwire = _coupling_forb(wires, net, starts, goal, junctions, cob, air,
                                 (x0, x1, z0, z1))
    def lid(cell):
        return cell in cob  # any pillar: tile, bridge, or stamped
    # Same hoist for the static obstacles: solid, rings-without-net and the
    # stamped ground pillars are fixed for the search, and all three lead to
    # the same `return False`, so they merge into ONE membership test. The
    # junction allow-check stays a lookup because it can override them.
    hard = {(x, 1, z) for (x, z) in solid}
    for (x, z), v in rings.items():
        if net not in v:
            hard.add((x, 1, z))
    for (sx, sy, sz) in sup:
        if sy == 1:
            hard.add((sx, 1, sz))
    # ponytail: a repeater cell is not dust. The search treated the LATCH
    # S-row repeater as free space and routed straight through it (D-latch
    # seed 1 crossed an east-facing repeater north-south; the load behind it
    # never fed). One guard here covers flat/3D/bridge: all funnel through
    # ok(). Ceiling: y==1 only; no y>=2 repeater exists before the cover pass.
    for (rx, ry, rz) in reps:
        if ry == 1:
            hard.add((rx, 1, rz))
    jget2 = junctions.get
    wg2 = wires.get
    def ok(cell):
        x, y, z = cell
        if not (x0 <= x <= x1 and z0 <= z <= z1 and 1 <= y <= _H):
            return False
        if cell == goal:
            return True
        if wg2(cell) not in (None, net):
            return False
        if y == 1:
            j = jget2((x, z))
            if j is not None and net in j:
                return True
            if cell in hard:
                return False
        elif cell in cob:
            return False  # inside a pillar (tile/bridge/stamped): no dust here
        return True

    def _unused_ok_reference(cell):
        x, y, z = cell
        if not (x0 <= x <= x1 and z0 <= z <= z1 and 1 <= y <= _H):
            return False
        if cell == goal:
            return True
        if cell in wires and wires[cell] != net:
            return False
        if y == 1:
            if (x, z) in junctions and net in junctions[(x, z)]:
                return True
            if (x, z) in solid:
                return False
            if (x, z) in rings and net not in rings[(x, z)]:
                return False
            if (x, 1, z) in sup:
                return False
            if cell in reps:
                return False
        elif cell in cob:
            return False
        return True
    def _unused_touches_foreign_reference(cell, prev):
        # same-y side touch couples; diagonal +-1 couples only via a true
        # slope link (support under upper + no lid over lower). Stacked or
        # unsupported y-adjacency never links, so overflight stays legal.
        # Hot path (millions of calls): local refs, no generators.
        x, y, z = cell
        wg = wires.get
        jn = junctions
        up = y > 1 or (air and (x, z) in airstrip)   # any vertical coupling left?
        for dx, dz in DIRS:
            m = (x + dx, y, z + dz)
            if m != prev and m not in starts:
                w = wg(m)          # cheap first: no foreign dust, no junction work
                if w is not None and w != net:
                    j = jn.get((m[0], m[2]))
                    if not (j and net in j):   # OR junction: wired-OR is the gate
                        if blocked is not None:
                            if y == 1:
                                # blame the ring, exactly as the 2D code did:
                                # a closed loop far from the goal seals just as
                                # dead as a wall on the goal itself.
                                for dx2, dz2 in DIRS:
                                    k = (m[0] + dx2, 1, m[2] + dz2)
                                    if k != cell and k in wires and wires[k] != net:
                                        blocked.add(k)
                            else:
                                blocked.add(m)
                        return True
            if not up:
                continue
            for dy in (1, -1):
                f = (x + dx, y + dy, z + dz)
                if f == prev or f in starts or f == goal:
                    continue
                w = wg(f)
                if w is None or w == net:
                    continue
                if dy == 1:
                    if (f[0], f[1] - 1, f[2]) in cob and (x, y + 1, z) not in cob:
                        if blocked is not None:
                            blocked.add(f)
                        return True
                elif y > 1 and (f[0], y, f[2]) not in cob:
                    # support below own cell is guaranteed by move legality
                    if blocked is not None:
                        blocked.add(f)
                    return True
        return False
    open_h = [(abs(s[0] - goal[0]) + abs(s[2] - goal[2]), 0, s, s, None) for s in starts]
    heapq.heapify(open_h)
    came, cost = {s: None for s in starts}, {s: 0 for s in starts}
    n = 0
    while open_h:
        _, g, _, cell, prev = heapq.heappop(open_h)
        n += 1
        if n > _ASTAR_CAP:
            return None  # anti-freeze: sealed pocket, fail fast, try next seed
        if cell == goal:
            path, c = [cell], cell
            while came[c] is not None:
                c = came[c]
                path.append(c)
            return path[::-1]
        x, y, z = cell
        for dx, dz in DIRS:
            ups = () if (flat_only or y >= _H) else (((x + dx, y + 1, z + dz), _STEPCOST),)
            dns = () if (flat_only or y <= 1) else (((x + dx, y - 1, z + dz), _STEPCOST),)
            for m, step in (((x + dx, y, z + dz), 1),) + ups + dns:
                if not ok(m):
                    if _XCHECK and ok(m) is not _unused_ok_reference(m):
                        raise AssertionError(f"hard-set merge differs at {m}")
                    continue
                mx, my, mz = m
                if my != y:
                    # level change: support under the upper endpoint (stamped
                    # once by route(), never during search) + lid over the
                    # lower endpoint clear, else the slope never conducts.
                    if my >= 2 and _support(m, net, solid, wires, sup, reps, guard) is False:
                        continue
                    lo = cell if my > y else m
                    if lid((lo[0], lo[1] + 1, lo[2])):
                        continue
                elif my >= 2 and _support(m, net, solid, wires, sup, reps, guard) is False:
                    continue
                if m == goal and (m[0], m[2]) in junctions and net in junctions[(m[0], m[2])]:
                    pass  # OR junction: wired-OR is the gate
                else:
                    _tf = m in forb
                    if _XCHECK and _tf is not _unused_touches_foreign_reference(m, cell):
                        # Set REDSTONE_XCHECK=1 to run the old predicate beside
                        # the hoisted one on every candidate (it caught three
                        # inversion bugs: the support cell, the candidate's y,
                        # and that the junction gate reads the FOREIGN column).
                        # Keep it green when touching `forb` or this test.
                        raise AssertionError(f"forb inversion differs at {m}")
                    if _tf:
                        if blocked is not None:
                            for dx, dz in DIRS:
                                fm = (mx + dx, my, mz + dz)
                                if fm == cell or fm not in fwire:
                                    continue
                                if my == 1:
                                    for dx2, dz2 in DIRS:
                                        k = (fm[0] + dx2, 1, fm[2] + dz2)
                                        if k != m and k in wires and wires[k] != net:
                                            blocked.add(k)
                                else:
                                    blocked.add(fm)
                        continue
                ng = g + step
                if congest:
                    # ponytail: negotiated congestion (lite). Ripped corridors
                    # stay expensive, so retries explore new lanes instead of
                    # cycling the same blame pair. Zero when nothing failed.
                    ng += congest.get(m, 0)
                if gexp and my == 1 and m != goal and (mx, mz) not in near and (mx, mz) in gexp:
                    # ponytail: no hugging solids mid-run. A wire beside a
                    # torch block powers it (wrong values); beside a lit torch
                    # it gets back-powered into a ring oscillator. Ports live
                    # within 2 of goal/start (the `near` exemption), so only
                    # drive-bys are refused. (y>=2 is immune: sim couples
                    # torches same-y only.)
                    continue
                if ng < cost.get(m, 1e9):
                    cost[m], came[m] = ng, cell
                    # (f, g, (x,z), cell, prev): the 2D projection first keeps
                    # the flat tie-break exactly as the 2D code had it, the 3D
                    # cell then makes the order total (no hash-order anywhere).
                    heapq.heappush(open_h, (ng + abs(mx - goal[0]) + abs(mz - goal[2]), ng, (mx, mz), m, cell))
    return None



def bridge_plan(fx, fz, axis):
    """One pre-proven crossover footprint (coordinates match sim.py's
    crossover vectors exactly). ns = travel along z over victim (fx,1,fz).
    Returns (feet, supports, dusts) as full (x,y,z) cells."""
    if axis == "ns":
        feet = [(fx, 1, fz - 2), (fx, 1, fz + 2)]
        supports = [(fx, 1, fz - 1), (fx, 1, fz + 1), (fx, 2, fz)]
        dusts = [(fx, 2, fz - 1), (fx, 3, fz), (fx, 2, fz + 1)]
    else:
        feet = [(fx - 2, 1, fz), (fx + 2, 1, fz)]
        supports = [(fx - 1, 1, fz), (fx + 1, 1, fz), (fx, 2, fz)]
        dusts = [(fx - 1, 2, fz), (fx, 3, fz), (fx + 1, 2, fz)]
    return feet, supports, dusts


def bridge_free(wires, solid, repeaters, guard, W, D, fx, fz, axis, net, cond=()):
    # ponytail: single bridge shape; any footprint collision -> no bridge,
    # the router detours instead. Full 3D search if hops ever dominate.
    if wires.get((fx, 1, fz)) in (None, net):
        return False  # nothing foreign to hop
    feet, supports, dusts = bridge_plan(fx, fz, axis)
    for x, y, z in supports + dusts:
        if not (0 <= x < W and 0 <= z < D):
            return False
        if (x, z) in guard:
            return False
        if wires.get((x, y, z)) not in (None, net):
            return False
        if wires.get((x, y + 1, z)) not in (None, net):
            return False  # 3D: no pillaring under / dust over foreign wire
    # 3D slope guard: bridge dust is elevated, so it can slope-link a foreign
    # wire diagonally beside it (sim couples exactly this way: support under
    # the upper cell, no lid over the lower). The bridge's own supports count
    # as that support, so a hop over one neighbour shorts the next. Caught
    # live as `SHORT3D: W slope-links S` — the search never saw it because a
    # bridge is stamped without consulting the coupling rules.
    cond2 = set(cond) | set(supports)
    for x, y, z in dusts:
        for dx, dz in DIRS:
            for dy in (1, -1):
                w = wires.get((x + dx, y + dy, z + dz))
                if w is None or w == net:
                    continue
                if dy == 1:      # foreign dust above ours: support under it,
                    if ((x + dx, y, z + dz) in cond2     # no lid over ours
                            and (x, y + 1, z) not in cond2):
                        return False
                else:            # foreign dust below ours: support under ours,
                    if ((x, y - 1, z) in cond2           # no lid over theirs
                            and (x + dx, y, z + dz) not in cond2):
                        return False
    for x, y, z in supports:
        if y == 1 and (x, z) in solid:
            return False
        if (x, y, z) in repeaters:
            return False
    if solid.get((fx, fz)) is not None or (fx, 1, fz) in repeaters:
        return False  # center column must hold only victim dust
    if wires.get((fx, 4, fz)) is not None:
        return False  # air above the hop
    for x, y, z in feet:
        if not (0 <= x < W and 0 <= z < D):
            return False
        if wires.get((x, y, z)) not in (None, net):
            return False
        if (x, z) in solid or (x, 1, z) in repeaters:
            return False
    return True


def bridge_stamp(blocks, solid, wires, rings, placed, net, fx, fz, axis):
    """Stamp a free-checked bridge; returns ground feet for 2D routing."""
    CB = "minecraft:cobblestone"
    feet, supports, dusts = bridge_plan(fx, fz, axis)
    for x, y, z in supports:
        blocks.append((x, y, z, CB))
        solid[(x, z)] = ("cobble", net)
    for x, y, z in dusts:
        wires[(x, y, z)] = net
        placed.add((x, y, z))
    for x, y, z in supports + [(fx, 1, fz)]:
        for dx, dz in DIRS:
            rings.setdefault((x + dx, z + dz), set()).add(net)
    return feet



def layout(recipe, seed=None, grow=0):
    gates = expand_gates(recipe["gates"], recipe["inputs"])
    banded = any(g.get("band") is not None for g in gates)
    if not banded:
        # topo-sort + one gate per column: every producer sits strictly west
        # of its consumers, so wires flow east and never cross on the layer.
        # (Sharing a column forced crossings: whoever detoured sealed another
        # stub into a pocket, or hugged a torch block into an oscillator.)
        by_out = {}
        for i, g in enumerate(gates):
            by_out.setdefault(g["out"], i)
        deps = {i: {by_out[a] for a in g["args"] if a in by_out and by_out[a] != i}
                for i, g in enumerate(gates)}
        ready = sorted(i for i, d in deps.items() if not d)
        order = []
        while ready:
            i = ready.pop(0)
            order.append(i)
            for j, d in deps.items():
                if i in d:
                    d.discard(i)
                    if not d and j not in order and j not in ready:
                        ready.append(j)
            ready.sort()
        if len(order) == len(gates):
            gates = [gates[i] for i in order]
        for i, g in enumerate(gates):
            g["band"] = i
        banded = True
    if banded:
        maxband = max(g.get("band", -1) for g in gates)
        W = 6 + (maxband + 1) * 24 + 10
        counts = {}
        for g in gates:
            b = g.get("band", -1)
            counts[b] = counts.get(b, 0) + 1
        D = 12 + max(counts.values()) * 14 + 12
    # ponytail: infinite room = grow on demand. Each grow doubles the field;
    # placement is deterministic so extra space only ever helps detours.
    # (W cap fits ~830 bands; cpu4 needs 247.)
    W = min(int(W * (1.5 ** grow)), 20000)
    D = min(int(D * (1.5 ** grow)), 4000)
    blocks = []  # (x, y, z, block-id [+state])
    solid, rings, wires, junctions, repeaters, paths, sup = {}, {}, {}, {}, {}, [], {}
    # sup: (x,y,z) -> net stamped 3D support pillars (cobble). Tile cobbles
    # stay in 2D solid; sup holds only route-stamped pillars (all levels).
    FLOOR = "minecraft:stone"

    def own(*nets):
        return set(nets)

    def ring(x, z, nets):
        rings.setdefault((x, z), set()).update(nets)

    def stamp_wire(path, net, ends=()):
        for cell in path:
            if len(cell) == 2:
                cell = (cell[0], 1, cell[1])  # placement stubs are y=1
            flat = (cell[0], cell[2])
            if cell[1] == 1:
                if flat in solid:
                    raise RuntimeError(f"wire {net} hits solid at {cell}")
            elif cell in sup:
                raise RuntimeError(f"wire {net} hits pillar at {cell}")
            # (tile columns never block y>=2 overflight: correction 1)
            if cell in wires and wires[cell] != net:
                if cell[1] == 1 and flat in junctions and net in junctions[flat]:
                    continue  # OR junction: wired-OR is the gate
                raise RuntimeError(f"wire {net} bridges {wires[cell]} at {cell}")
            if cell[1] == 1 and flat in rings and net not in rings[flat]:
                # astar exempts the ports (a tile port sits inside rings by
                # construction and the router MUST start and end there), so
                # stamping must agree — otherwise a legal route dies at its own
                # endpoint. The ring overlap is a tile-placement artefact
                # either way; sim is the selector for whether it miscomputes.
                if cell[1] == 1 and flat in junctions and net in junctions[flat]:
                    pass
                elif flat in ends:
                    pass
                else:
                    raise RuntimeError(f"wire {net} hits guarded {cell}")
            # ponytail: same-level adjacency guard. A* guarantees a routed path
            # never side-touches a foreign net (touches_foreign), but every
            # OTHER stamp goes through here with no search at all: output taps,
            # bank stubs, tile port rows, XOR side wires, the cover tail. Those
            # were checked only for "a foreign wire sits ON this cell", never
            # "one sits next to it" — so a routed net could end up touching an
            # output tap. Measured: `SHORT: m0 touches Y at (223,1,13)
            # ->(222,1,13)`, Y's cell in no routed path at all.
            for dx, dz in DIRS:
                nb = wires.get((cell[0] + dx, cell[1], cell[2] + dz))
                if nb is not None and nb != net and not (
                        (cell[0] + dx, cell[2] + dz) in junctions
                        and net in junctions[(cell[0] + dx, cell[2] + dz)]):
                    raise RuntimeError(f"wire {net} touches {nb} beside {cell}")
            wires.setdefault(cell, net)

    def route(a, b, net, use3d=True):
        # single source: every branch traces full-length to its driver.
        # (Tapping live-looking mid-wire cells caused decayed weak taps;
        #  connected-tap + shortest-first retries in 2026-09 also broke xor.)
        # 3D Attempt 1 is an ESCAPE, not an optimizer: pass 1 is today's flat
        # search verbatim (same cost, same routes, same failures) and is tried
        # first, so green builds never touch the 3D search. Height is searched
        # only when flat has NO route — the seal case 3D exists to dissolve.
        # The 3D winner is re-checked against the FINAL pillar set (a flyover
        # pillar can lid the path's own later slope: self-lid, invisible to
        # the search) and against booster cover (dust dies after 15, so a run
        # with no straight triple in the window — twisty or climbing — is dead
        # and is refused; cover may sit on a pillar). Ceiling: one 3D pass, no
        # research loop — the caller's rip-up/bridge/next-seed already retries.
        CB = "minecraft:cobblestone"
        seen = set()
        # O(1): the conductive sets are maintained by the layout, so a route
        # hands them straight through instead of re-joining them per search.
        # Margin ladder: windows are nested (None ⊇ 40 ⊇ 12), so a narrower one
        # finds a SHORTER path when it finds one — 12 won 16/17 and 40/None
        # never beat it — but it can also find nothing. A retry (post-rip) needs
        # room to escape the congestion it just caused, so it takes the single
        # middle window instead of three: measured 17/17 on micro1, and it turns
        # 94% of all searches (flat/post-rip) from 3 passes into 1.
        margins = (40,) if congest else (12, 40, None)

        def _search(flat, margins):
            # Candidates, shortest first. Stop as soon as a route hits the
            # Manhattan lower bound: nothing can be shorter, so the wider
            # windows would burn two more full-field A* passes for nothing.
            out = []
            lb = abs(a[0] - b[0]) + abs(a[1] - b[1])
            for margin in margins:
                cand = astar([(a[0], 1, a[1])], (b[0], 1, b[1]), net, W, D, solid,
                             rings, wires, junctions, margin, blocked=seen,
                             congest=congest, guard=guard, sup=sup, reps=repeaters,
                             cob3=condg if flat else cond, flat_only=flat,
                             aircells=aircells)
                if cand:
                    out.append(cand)
                    if len(cand) == lb:
                        break
            # shortest wins; on a tie the earlier margin wins (stable sort over
            # a fixed margin order) — same pick as the pre-3D code, and the
            # order is fully specified (no set/dict iteration anywhere).
            return [(i, p) for i, p in sorted(enumerate(out), key=lambda ip: (len(ip[1]), ip[0]))]

        cands = _search(True, margins)
        path = cands[0][1] if cands else None
        needs = []
        if path is None and use3d:
            # 3D: take the shortest candidate that survives support, self-lid
            # and cover. One pass, no research loop.
            why = None
            for _i, cand in _search(False, margins):
                needs = []
                try:
                    for cell in cand:
                        if cell[1] < 2:
                            continue
                        r = _support(cell, net, solid, wires, sup, repeaters, guard)
                        if r is False:
                            raise RuntimeError("support sealed")
                        if r is not None and r not in sup and r not in needs:
                            needs.append(r)
                    cobf = cond | set(needs)
                    for u, v in zip(cand, cand[1:]):
                        if u[1] == v[1]:
                            continue
                        lo, hi = (u, v) if u[1] < v[1] else (v, u)
                        if (hi[0], hi[1] - 1, hi[2]) not in cobf or (lo[0], lo[1] + 1, lo[2]) in cobf:
                            raise RuntimeError("self-lid")
                    i = len(cand) - 1
                    while i > 14:
                        j = _cover_gap(cand, i)
                        if j is False:
                            raise RuntimeError("unboostable 3D")
                        i = j
                except RuntimeError as e:
                    why = str(e)
                    continue
                path = cand
                break
            if path is None and why:
                last_blocked[net] = seen
                raise RuntimeError(f"no route for {net}: {a} -> {b} (3D: {why})")
        if not path:
            last_blocked[net] = seen
            raise RuntimeError(f"no route for {net}: {a} -> {b} (grid full, widen W)")
        # Pillars go into the maintained sets now and into `blocks` once, after
        # all routing (a rip-up used to rebuild the whole block list per rip).
        for s_ in needs:
            sup[s_] = net
            cond.add(s_)
            if s_[1] == 1:
                condg.add(s_)
        stamp_wire(path, net, (a, b))
        for c in path:
            if c[1] >= 2:
                aircells.add(c)
        paths.append((path, net, tuple(needs)))
        return path

    # maze: every used input gets one bank lever on the south edge; fanout
    # below rides the router (zero-wire taps deleted — see bus section).
    pos = {}
    used = {a for g in gates for a in g["args"]} & set(recipe["inputs"])
    bz = D - 2
    # ponytail: levers park below their loads' median band, not huddled
    # west. West-corner levers force every input marathon east across all
    # gate columns (micro1 OP ran 160 east and sealed the field: 2s->>290s);
    # north runs cross free middle field instead. Ceiling: colliding medians
    # run east and may go out of bounds (loud); upgrade is input fanout
    # chaining (recipe.py still excludes inputs from relay chains).
    _ax = {}
    for name in recipe["inputs"]:
        if name in used:
            _bands = sorted(g.get("band", 0) for g in gates if name in g["args"])
            _ax[name] = 6 + _bands[len(_bands) // 2] * 24
    _ord = {n: i for i, n in enumerate(recipe["inputs"])}
    _prev = 2
    for name in sorted(_ax, key=lambda n: (_ax[n], _ord[n])):
        x = max(min(_ax[name], W - 2), _prev)
        if not (x + 1 < W and bz - 1 >= 0):
            raise RuntimeError(f"bank lever out of bounds for {name}")
        if (x, bz) in solid or (x, 1, bz) in wires or (x + 1, bz) in solid or (x + 1, 1, bz) in wires:
            raise RuntimeError(f"bank lever spot taken for {name} at {(x, bz)}")
        blocks.append((x, 1, bz, "minecraft:lever"))
        solid[(x, bz)] = ("lever", name)
        for dx, dz in DIRS:
            ring(x + dx, bz + dz, own(name))
        stamp_wire([(x + 1, bz)], name)
        pos[name] = (x + 1, bz)
        _prev = x + 3
    if any(a in ("0", "1") for g in gates for a in g["args"]):
        stamp_wire([(0, 3)], "0")
        pos["0"] = (0, 3)
        blocks.append((W - 1, 1, 3, "minecraft:redstone_block"))
        solid[(W - 1, 3)] = ("block", "1")
        for dx, dz in DIRS:
            ring(W - 1 + dx, 3 + dz, own("1"))
        stamp_wire([(W - 2, 3)], "1")
        pos["1"] = (W - 2, 3)

    # ponytail: bus lanes pre-claim (spec 2026-09-26-dense-panel-green).
    # Straight E-W claims south of tiles; tiles dodge via spot_free.
    # Lanes saturate -> maze detours (no new search).
    used_ins = {a for g in gates for a in g["args"]} & set(recipe["inputs"])
    lanes = {}
    for idx, name in enumerate(recipe["inputs"]):
        if name not in used_ins:
            continue
        lz = (D - 4) - idx * 2
        lanes[name] = {(x, lz) for x in range(1, W - 1)}
    # phase 1: place all tiles (solids+rings+outs) so routes see the full obstacle field.
    # AND = fixed torch compound (hand-verified layout, checker-guarded):
    #   two NOTs feed a NOR; internal wires fixed, only ports route globally.
    def stamp_cobble(x, z, o):
        blocks.append((x, 1, z, "minecraft:cobblestone"))
        solid[(x, z)] = ("cobble", o)

    def stamp_torch(x, z, o):
        blocks.append((x, 1, z, "minecraft:redstone_wall_torch[facing=east]"))
        solid[(x, z)] = ("torch", o)

    def stamp_and(ox, gz, A, B, O):
        # compact torch AND (textbook): NOT-A top, NOT-B bottom, NOR middle-right.
        na, nb = f"{O}~a", f"{O}~b"
        fam = own(A, B, O, na, nb)
        stamp_cobble(ox, gz, O)
        stamp_torch(ox + 1, gz, O)
        stamp_cobble(ox, gz + 3, O)
        stamp_torch(ox + 1, gz + 3, O)
        stamp_cobble(ox + 3, gz + 1, O)
        stamp_torch(ox + 4, gz + 1, O)
        for rx, rz in ((ox - 1, gz), (ox + 1, gz), (ox, gz - 1), (ox, gz + 1),
                       (ox + 2, gz), (ox + 1, gz - 1), (ox + 1, gz + 1),
                       (ox - 1, gz + 3), (ox + 1, gz + 3), (ox, gz + 2), (ox, gz + 4),
                       (ox + 2, gz + 3), (ox + 1, gz + 2), (ox + 1, gz + 4),
                       (ox + 2, gz + 1), (ox + 4, gz + 1), (ox + 3, gz),
                       (ox + 5, gz + 1), (ox + 4, gz), (ox + 4, gz + 2)):
            ring(rx, rz, fam)
        stamp_wire([(ox - 2, gz), (ox - 1, gz)], A)
        stamp_wire([(ox - 2, gz + 3), (ox - 1, gz + 3)], B)
        # ponytail: ~A must APPROACH the NOR host along the axis it points at.
        # Vanilla: powered dust powers a block only when it is on top of it or
        # POINTING at it, and pointing comes from the connection shape
        # (dust_points). The old N-S stub ((ox+2,gz),(ox+2,gz+1)) left its end
        # cell pointing north and south, so it never powered the host at
        # (ox+3,gz+1) -- the AND tile's NOR input was dead in vanilla and only
        # appeared to work because the sim assumed every cell is a cross. This
        # E-W stub ends at (ox+2,gz+1), which points east into the host. Both
        # cells were already in the ring list above, so no ring edit is needed.
        stamp_wire([(ox + 1, gz + 1), (ox + 2, gz + 1)], na)
        # ponytail: ~B hugs the west side on purpose. It must never touch the
        # NOR torch (ox+4,gz+1): torch->wire->block->torch is a ring oscillator
        # that blinks instead of computing whenever both NOTs are off.
        stamp_wire([(ox + 2, gz + 3), (ox + 3, gz + 3), (ox + 3, gz + 2)], nb)
        stamp_wire([(ox + 5, gz + 1), (ox + 6, gz + 1)], O)
        return (ox - 2, gz), (ox - 2, gz + 3), (ox + 6, gz + 1)

    recs = []
    bandrows = {}
    # grid slot per gate (fallback positions) + reservation boxes so chained
    # tiles never steal a future grid slot (grid stays provably placeable).
    gridpos = []
    for i, g in enumerate(gates):
        b = g.get("band")
        gz = bandrows.get(b, 12)
        bandrows[b] = gz + 14
        gridpos.append((6 + b * 24, gz))
    def footprint(op, ox, gz):
        if op == "AND":
            return {(x, z) for x in range(ox - 2, ox + 9) for z in range(gz - 1, gz + 8)}
        if op in ("NOT", "NOR"):
            return {(x, z) for x in range(ox - 3, ox + 4) for z in range(gz - 1, gz + 2)}
        if op == "LATCH":
            return {(x, z) for x in range(ox - 6, ox + 8) for z in range(gz - 5, gz + 6)}
        if op == "XOR":
            return {(x, z) for x in range(ox - 3, ox + 8) for z in range(gz - 2, gz + 8)}
        return {(x, z) for x in range(ox - 3, ox + 4) for z in range(gz - 3, gz + 4)}

    reserved = [footprint(g["op"], *gridpos[i]) for i, g in enumerate(gates)]
    others_reserved = []
    for i in range(len(gates)):
        u = set()
        for j, box in enumerate(reserved):
            if j != i:
                u |= box
        others_reserved.append(u)

    def spot_free(op, ox, gz, i):
        # one guard for all placers: bounds per tile, disjoint from every
        # other grid slot, and actually empty (lever cells now dot the
        # field, so grid slots aren't provably free anymore).
        if op == "AND":
            if not (0 <= ox - 2 and ox + 6 < W and 0 <= gz and gz + 6 < D):
                return False
        elif op in ("NOT", "NOR"):
            if not (0 <= ox - 2 and ox + 2 < W and 0 <= gz - 1 and gz + 1 < D):
                return False
        elif op == "LATCH":
            if not (0 <= ox - 6 and ox + 7 < W and 0 <= gz - 5 and gz + 6 < D):
                return False
        elif op == "XOR":
            if not (0 <= ox - 3 and ox + 7 < W and 0 <= gz - 2 and gz + 7 < D):
                return False
        else:
            if not (0 <= ox - 3 and ox + 3 < W and 0 <= gz - 3 and gz + 3 < D):
                return False
        fp = footprint(op, ox, gz)
        if not fp.isdisjoint(others_reserved[i]):
            return False
        for cells in lanes.values():
            if not fp.isdisjoint(cells):
                return False
        return all((x, z) not in solid and (x, 1, z) not in wires for x, z in fp)

    def gridrows(ox, gz):
        # fallback rows when the grid slot is taken: 14 apart, footprints
        # top out at 11 tall, so rows never overlap each other.
        while gz <= D + 5:
            yield ox, gz
            gz += 14

    def _snap():
        return (len(blocks), dict(wires), dict(solid),
                {k: set(v) for k, v in rings.items()},
                dict(pos), dict(junctions), len(recs))

    def _restore(s):
        nb, w, so, ri, p, jn, nr = s
        del blocks[nb:]
        wires.clear(); wires.update(w)
        solid.clear(); solid.update(so)
        rings.clear(); rings.update(ri)
        pos.clear(); pos.update(p)
        junctions.clear(); junctions.update(jn)
        del recs[nr:]

    for i, g in enumerate(gates):
        ox, gz = gridpos[i]
        op, o, a = g["op"], g["out"], g["args"]
        if op == "OR":
            # repeater-isolated OR (wiki). Junction stays on-grid (merging by
            # touch would short); diodes face drivers. Grid fallback inside.
            jx, jz = ox, gz
            if not (0 <= jx - 3 and jx + 3 < W and 0 <= jz - 3 and jz + 3 < D):
                raise RuntimeError(f"OR out of bounds for {o} at {(jx, jz)} field {W}x{D}")
            s = _snap()
            try:
                    j = (jx, jz)
                    if j in solid or (j[0], 1, j[1]) in wires:
                        raise RuntimeError(f"OR cell blocked at {j}")
                    reps = []
                    seen = {j}
                    for sig in a:
                        sx, sz = pos.get(sig, (jx - 4, jz))
                        if abs(sx - jx) >= abs(sz - jz):
                            order = [(1 if sx >= jx else -1, 0)]
                        else:
                            order = [(0, 1 if sz >= jz else -1)]
                        order += [(1, 0), (-1, 0), (0, 1), (0, -1)]
                        ok = False
                        for dx, dz in order:
                            for step in (1, 2, 3):
                                r = (j[0] + dx * step, j[1] + dz * step)
                                b = (j[0] + dx * (step + 1), j[1] + dz * (step + 1))
                                if r in solid or (r[0], 1, r[1]) in wires or b in solid or (b[0], 1, b[1]) in wires \
                                   or r in seen or b in seen:
                                    continue
                                facing = {(1, 0): "west", (-1, 0): "east",
                                          (0, 1): "north", (0, -1): "south"}[(dx, dz)]
                                blocks.append((r[0], 1, r[1], f"minecraft:repeater[facing={facing},delay=1]"))
                                solid[r] = ("repeater", o)
                                reps.append((r, b))
                                seen.add(r)
                                seen.add(b)
                                ok = True
                                break
                            if ok:
                                break
                        if not ok:
                            raise RuntimeError(f"OR cell blocked around {j} for {sig}")
                    stamp_wire([j], o)
                    junctions[j] = {o}
                    pos[o] = j
                    recs.append((op, o, a, (j, reps)))
            except RuntimeError:
                _restore(s)
                raise
            continue
        if op == "AND":
            # in-A port lands touching its driver (zero-wire tap). Chained
            # stays local (else grid): marches cause top-edge stranding.
            # (in-B chaining marches north; dropped for that reason.)
            dv = pos.get(a[0])
            cands = []
            if dv is not None and dv not in junctions and not g.get("rep"):
                cands.append((dv[0] + 3, dv[1], True))
            cands.append((ox, gz, False))
            placed = False
            for ox2, gz2, local in cands:
                rows = [(ox2, gz2)] if local else gridrows(ox2, gz2)
                for ox3, gz3 in rows:
                    if local and (abs(ox3 - ox) > 16 or abs(gz3 - gz) > 7):
                        break
                    if not spot_free("AND", ox3, gz3, i):
                        continue
                    s = _snap()
                    try:
                        pa, pb, po = stamp_and(ox3, gz3, a[0], a[1], o)
                        pos[o] = po
                        recs.append((op, o, a, (pa, pb, po)))
                        placed = True
                        break
                    except RuntimeError:
                        _restore(s)
                if placed:
                    break
            if not placed:
                raise RuntimeError(f"AND blocked for {o}")
            continue
        if op == "LATCH":
            # flat SR latch (textbook NOR latch, adjacent blocks): A-block
            # reads R+Qb, B-block reads S+Q-west; Q exits west at z+2.
            # Hand-placed: cross-coupling is delay-critical, the router must
            # never thread repeaters through it (they sustain power-on race).
            qb = f"{o}~qb"
            fam = own(a[0], a[1], o, qb)
            placed = False
            for ox2, gz2 in gridrows(ox, gz):
                if not spot_free("LATCH", ox2, gz2, i):
                    continue
                ox, gz = ox2, gz2
                Sdust = [(ox - 1 + k, gz + 4) for k in range(6)] + \
                    [(ox + 4, gz + 3), (ox + 4, gz + 2), (ox + 4, gz + 1)]
                Rdust = [(ox - 2, gz), (ox - 1, gz)]
                Qdust = [(ox + 2, gz), (ox + 3, gz), (ox + 2, gz + 1)] + \
                    [(ox + 2 - k, gz + 2) for k in range(8)]
                Qbdust = [(ox + 4, gz - 2), (ox + 4, gz - 3), (ox + 4, gz - 4)] + \
                    [(ox + 4 - k, gz - 4) for k in range(5)] + \
                    [(ox, gz - 3), (ox, gz - 2), (ox, gz - 1)]
                s = _snap()
                try:
                    stamp_cobble(ox, gz, o)
                    blocks.append((ox + 1, 1, gz, "minecraft:redstone_wall_torch[facing=east]"))
                    solid[(ox + 1, gz)] = ("torch", o)
                    stamp_cobble(ox + 4, gz, o)
                    blocks.append((ox + 4, 1, gz - 1, "minecraft:redstone_wall_torch[facing=north]"))
                    solid[(ox + 4, gz - 1)] = ("torch", o)
                    for cells, net in ((Sdust, a[0]), (Rdust, a[1]),
                                       (Qdust, o), (Qbdust, qb)):
                        stamp_wire(cells, net)
                    # ponytail: the S row is 9 cells of the tile's OWN dust from
                    # the block it must power, so it needs level ~10 at the port
                    # and no bus budget can supply that -- the load is the port,
                    # the row is past it. A repeater in the row fixes it, and
                    # (ox+1) is the only cell that still sees power at the
                    # guaranteed minimum. Measured: at level 2 the row died 4
                    # cells short and the latch could NEVER set. A repeater on
                    # the set input is the textbook shape and costs no race:
                    # only set is delayed, reset is not, and the cross-coupled
                    # Q/Qb loop itself is untouched.
                    del wires[(ox + 1, 1, gz + 4)]
                    repeaters[(ox + 1, 1, gz + 4)] = (a[0], "east")
                    for cx_, cz_ in set([(ox, gz), (ox + 1, gz), (ox + 4, gz),
                                         (ox + 4, gz - 1)] + Sdust + Rdust + Qdust + Qbdust):
                        for dx, dz in DIRS:
                            ring(cx_ + dx, cz_ + dz, fam)
                    pa, pb, po = (ox - 1, gz + 4), (ox - 2, gz), (ox - 5, gz + 2)
                    pos[o] = po
                    recs.append((op, o, a, (pa, pb, po)))
                    placed = True
                except RuntimeError:
                    _restore(s)
                if placed:
                    break
            if not placed:
                raise RuntimeError(f"LATCH blocked for {o}")
            continue
        if op == "XOR":
            # comparator XOR (dual subtract, sim-verified): C1 = A-B,
            # C2 = B-A, outputs merged west. Side inputs are tile-stamped
            # repeaters fed by the input nets (wiki: sides need STRONG power,
            # dust never counts, so routed wire can't feed them — and neither
            # can a panel lever beside the comparator, which is why the old
            # tile levers cost a second lever per input).
            fam = own(a[0], a[1], o)
            placed = False
            for ox2, gz2 in gridrows(ox, gz):
                if not spot_free("XOR", ox2, gz2, i):
                    continue
                ox, gz = ox2, gz2
                Adust = [(ox + 2, gz), (ox + 1, gz), (ox + 3, gz)]
                Bdust = [(ox + 2, gz + 4), (ox + 1, gz + 4), (ox + 3, gz + 4)]
                Odust = [(ox - 1, gz), (ox - 2, gz), (ox - 2, gz + 1),
                         (ox - 2, gz + 2), (ox - 2, gz + 3), (ox - 2, gz + 4),
                         (ox - 1, gz + 4), (ox - 2, gz + 5), (ox - 2, gz + 6)]
                s = _snap()
                try:
                    blocks.append((ox, 1, gz, "minecraft:comparator[facing=east,mode=subtract]"))
                    solid[(ox, gz)] = ("comp", o)
                    blocks.append((ox, 1, gz + 4, "minecraft:comparator[facing=east,mode=subtract]"))
                    solid[(ox, gz + 4)] = ("comp", o)
                    for cells, net in ((Adust, a[0]), (Bdust, a[1]), (Odust, o)):
                        stamp_wire(cells, net)
                    # ponytail: merge-tail diodes (example_xor SIM-dark root).
                    # Subtract outs start at whatever decayed level the routed
                    # rear delivers (~4, not 15); the 9-cell Odust merge eats
                    # it before y-drv. Diodes facing flow restore 15; the
                    # second also carries C2's entry south of the first.
                    # Ceiling: two fixed diodes; revisit if the merge grows.
                    for _jx, _jz in ((ox - 2, gz + 3), (ox - 2, gz + 5)):
                        for _fx, _fz in ((_jx, _jz - 1), (_jx, _jz + 1)):
                            _w = wires.get((_fx, 1, _fz))
                            if _w is not None and _w != o:
                                raise RuntimeError(f"XOR diode guard {o} vs {_w} at {(_fx, _fz)}")
                        if wires.get((_jx, 1, _jz)) != o:
                            raise RuntimeError(f"XOR diode spot holds {wires.get((_jx, 1, _jz), 'EMPTY')}")
                        del wires[(_jx, 1, _jz)]
                        repeaters[(_jx, 1, _jz)] = (o, "south")
                    # ponytail: side feeds are repeaters, not levers. Wiki:
                    # comparator sides need STRONG power and dust never counts,
                    # so the old tile levers ringed their neighbours shut and
                    # every XOR input cost a second lever. REP2 (a -> C2 north
                    # side) rides a 3-cell tile stub off Adust; REP1 (b -> C1
                    # north side) takes a routed load at (ox,gz-2), kept clear
                    # of the output/lamp row down south. Both face south into
                    # their comparator; backs read dust, outputs are 15 exactly
                    # like the levers were (subtract takes max of sides, so the
                    # north/south swap on C1 is equivalent).
                    stamp_wire([(ox + 1, gz + 1), (ox + 1, gz + 2), (ox, gz + 2)], a[0])
                    for _rx, _rz in ((ox, gz - 1), (ox, gz + 3),
                                     (ox + 1, gz + 1), (ox + 1, gz + 2), (ox, gz + 2)):
                        ring(_rx, _rz, fam)
                    repeaters[(ox, 1, gz - 1)] = (a[1], "south")
                    repeaters[(ox, 1, gz + 3)] = (a[0], "south")
                    for cx_, cz_ in set([(ox, gz), (ox, gz + 4)] + Adust + Bdust + Odust):
                        for dx, dz in DIRS:
                            ring(cx_ + dx, cz_ + dz, fam)
                    pa, pb, po = (ox + 3, gz), (ox + 3, gz + 4), (ox - 2, gz + 6)
                    pos[o] = po
                    recs.append((op, o, a, (pa, pb, po)))
                    placed = True
                except RuntimeError:
                    _restore(s)
                if placed:
                    break
            if not placed:
                raise RuntimeError(f"XOR blocked for {o}")
            continue
        if op != "NOT":
            raise ValueError(f"bad primitive {op}")
        dv = pos.get(a[0])
        cands = []
        if dv is not None and dv not in junctions:
            cands.append((dv[0] + 3, dv[1], True))
        cands.append((ox, gz, False))
        placed = False
        for bx, bz, local in cands:
            rows = [(bx, bz)] if local else gridrows(bx, bz)
            for bx3, bz3 in rows:
                if local and (abs(bx3 - ox) > 16 or abs(bz3 - gz) > 7):
                    break
                if not spot_free("NOT", bx3, bz3, i):
                    continue
                s = _snap()
                try:
                    bx, bz = bx3, bz3
                    nets = own(o, *a)
                    stamp_cobble(bx, bz, o)
                    stamp_torch(bx + 1, bz, o)
                    for rx, rz in ((bx - 1, bz), (bx + 1, bz), (bx, bz - 1), (bx, bz + 1),
                                   (bx + 2, bz), (bx + 1, bz - 1), (bx + 1, bz + 1)):
                        ring(rx, rz, nets)
                    # ponytail: input stub must APPROACH the host along the axis
                    # it points at (dust_points) — same reshape as the AND ~a stub
                    # (67987b0). The old bare port (bx-1,bz) let the router arrive
                    # from any side; from the north it left an end cell pointing
                    # N/S that never powered the host. This E-W stub ends at
                    # (bx-1,bz), which points east into the host no matter where
                    # the router reaches the open load (bx-2,bz) from.
                    stamp_wire([(bx - 2, bz), (bx - 1, bz)], a[0])
                    if (bx + 2, 1, bz) in wires:
                        raise RuntimeError(f"out cell blocked at {(bx + 2, bz)}")
                    stamp_wire([(bx + 2, bz)], o)
                    pos[o] = (bx + 2, bz)
                    recs.append((op, o, a, (bx, bz)))
                    placed = True
                    break
                except RuntimeError:
                    _restore(s)
            if placed:
                break
        if not placed:
            raise RuntimeError(f"NOT blocked for {o}")

    # bus: net spec from tile ports (same mapping the maze tasks used).
    # Inputs fan out via one lever per load below (zero-wire); every other
    # net routes driver -> each load with astar (relays made hops short, so
    # local margins hit fast), then boosters bridge residual decay.
    # (XOR tile-stamped side levers stay: tile geometry, and same-net
    # duplicates are wired-OR harmless.)
    netspec = {}
    def _load(net, cell):
        if net == "0":
            return  # dark stubs read 0; nothing is stamped
        e = netspec.setdefault(net, {'drv': None, 'loads': []})
        e['loads'].append(cell)
    for op, o, a, cell in recs:
        if op == "AND":
            pa, pb, po = cell
            netspec.setdefault(o, {'drv': po, 'loads': []})
            _load(a[0], pa); _load(a[1], pb)
        elif op == "NOT":
            bx, bz = cell
            netspec.setdefault(o, {'drv': (bx + 2, bz), 'loads': []})
            _load(a[0], (bx - 2, bz))
        elif op in ("LATCH", "XOR"):
            pa, pb, po = cell
            netspec.setdefault(o, {'drv': po, 'loads': []})
            _load(a[0], pa); _load(a[1], pb)
            if op == "XOR":
                # REP1 back (ox,gz-2) is a routed load: pa = (ox+3,gz).
                _load(a[1], (pa[0] - 3, pa[1] - 2))
        elif op == "OR":
            j, reps = cell
            netspec.setdefault(o, {'drv': j, 'loads': []})
            for sig, (rr, bb) in zip(a, reps):
                _load(sig, bb)
        elif op == "OUT":
            pass  # lamp taps the driver wire; no stub
        else:
            raise RuntimeError(f"bus: unsupported {op}")
    for name in recipe["inputs"]:
        netspec.setdefault(name, {'drv': None, 'loads': []})
    if "1" in netspec:
        netspec["1"]['drv'] = pos["1"]
    for net in [n for n, s in netspec.items()
                if not s['loads'] and n not in recipe["outputs"]]:
        del netspec[net]
    # ponytail: inputs ride the router like gate nets (single-lever panel);
    # fanout cost is real routing now. Loud fail if a dense input seals.
    tasks = []
    for net, spec in netspec.items():
        if net == "0":
            continue  # dark stubs read 0
        drv = spec['drv'] if spec['drv'] is not None else pos.get(net)
        for cell in spec['loads']:
            tasks.append((drv, cell, net))
    tasks.sort(key=lambda t: -(abs(t[0][0] - t[1][0]) + abs(t[0][1] - t[1][1])))
    if seed is not None:
        random.Random(seed).shuffle(tasks)
    # ponytail: spine-first per input (spec 2026-09-26-spine-fed-input-
    # distribution-design). Bank->farthest load routes once (the spine);
    # remaining loads tap it nearest-first. Input groups shuffle per seed
    # on a separate stream so the gate shuffle above is byte-identical.
    # Gates share key (1,0,0,0): stable sort keeps today's relative order.
    _ins = set(recipe["inputs"])
    _dist = lambda t: abs(t[0][0] - t[1][0]) + abs(t[0][1] - t[1][1])
    _far = {}
    for _t in tasks:
        if _t[2] in _ins and (_t[2] not in _far or _dist(_t) > _dist(_far[_t[2]])):
            _far[_t[2]] = _t
    _names = [n for n in recipe["inputs"] if n in _ins]
    if seed is not None:
        random.Random(seed + 1).shuffle(_names)
    _oi = {n: i for i, n in enumerate(_names)}
    tasks.sort(key=lambda t: (0, _oi[t[2]], 0 if t == _far[t[2]] else 1, _dist(t)) if t[2] in _ins else (1, 0, 0, 0))
    placed = set(wires)  # stubs/outs/ties stay; routed paths may be ripped up
    last_blocked = {}  # net -> wire cells whose touch sealed its last failure
    congest = {}  # wire cell -> extra cost after a rip (lanes stay shared)
    guard = set()  # torch cells + their attach blocks: the only solids a
    for x, y, z, bid in blocks:  # routed wire must never hug (oscillators).
        if "wall_torch" in bid:  # lever/lamp coupling settles merely wrong
            guard.add((x, z))  # (no loop possible); sim catches it instead.
            face = bid.split("facing=")[1].rstrip("]")
            dx, dz = TORCH_BACK[face]
            guard.add((x + dx, z + dz))
    pending = tasks[:]
    # conductive blocks, maintained as tiles/bridges/pillars land: the search
    # reads this instead of rebuilding it per astar call.
    tilecob = {(x, 1, z) for (x, z), (k, _) in solid.items() if k == "cobble"}
    coball = {(x, y, z) for x, y, z, bid in blocks
              if bid.split("[")[0] == "minecraft:cobblestone"}
    # Conductive sets are maintained, never rebuilt: a route only ever needs
    # "is there a block here", and rebuilding per route/rip was O(routes x
    # pillars). condg = ground level (what the flat search may stand on),
    # cond = every level (what the 3D search may slope onto).
    condg = set(tilecob)
    cond = set(coball)
    aircells = set()          # elevated wire cells: a y=1 cell can only

    def _rip(sups, net):
        """Drop a ripped path's own pillars: a stale cobble would roof a later
        slope and a stale sup entry would block the ground column. Pillars are
        NOT in `blocks` during routing, so this is O(pillars of the path) —
        no O(blocks) rebuild per rip-up."""
        gone = {c for c in sups if sup.get(c) == net}
        for c in gone:
            del sup[c]
            cond.discard(c)
            if c[1] == 1:
                condg.discard(c)
        return gone
    fails = {}
    bridged = set()  # (fx, fz, axis) already hopped; never retry
    def try_bridge(s, t, net):
        # ponytail: last-resort hop over sealing dust with one pre-proven
        # bridge, then two 2D segments (no 3D search). Green builds never
        # reach here, so their routes are unchanged. Cap 24 hops per build.
        if len(bridged) >= 24 or s is None or t is None:
            return False
        cands = []
        for c in last_blocked.get(net, ()):
            if c[1] == 1 and c not in placed:
                w = wires.get(c)
                if w is not None and w != net:
                    cands.append((c[0], c[2]))
        for dx, dz in DIRS:
            A = (t[0] + dx, 1, t[1] + dz)
            for c in [A] + [(A[0] + ex, 1, A[2] + ez) for ex, ez in DIRS]:
                if c not in placed:
                    w = wires.get(c)
                    if w is not None and w != net:
                        cands.append((c[0], c[2]))
        cands = list(dict.fromkeys(cands))
        # total order (p last): bridge-candidate ties were hash-seed dependent,
        # which made cross-process build diffs guesswork (handoff repro bug).
        cands.sort(key=lambda p: ((p[0], 1, p[1]) not in placed,
                                  abs(p[0] - s[0]) + abs(p[1] - s[1]) + abs(p[0] - t[0]) + abs(p[1] - t[1]), p))
        prefer = ("ew", "ns") if abs(s[0] - t[0]) >= abs(s[1] - t[1]) else ("ns", "ew")
        for fx, fz in cands[:8]:
            for axis in prefer:
                if (fx, fz, axis) in bridged:
                    continue
                if not bridge_free(wires, solid, repeaters, guard, W, D, fx, fz, axis, net, cond=cond):
                    continue
                feet = bridge_stamp(blocks, solid, wires, rings, placed, net, fx, fz, axis)
                _sup, _dst = bridge_plan(fx, fz, axis)[1:]
                cond.update(_sup)
                condg.update(c for c in _sup if c[1] == 1)
                fa, fb = sorted(feet, key=lambda f: abs(f[0] - s[0]) + abs(f[2] - s[1]))
                _npath = len(paths)
                try:
                    pa = route(s, (fa[0], fa[2]), net)
                    pb = route((fb[0], fb[2]), t, net)
                    # ponytail: splice the hop into ONE path. The bridge's dust
                    # belonged to neither route, so the cover pass never counted
                    # it and never boosted it: the electrical run across the hop
                    # was longer than anything _cover_gap had promised, and a
                    # load past the bridge got whatever level was left over.
                    # Measured: a tile input load at level 0 -- a gate input
                    # simply dark -- so the R AND tile computed R=0 forever and
                    # the D-latch could never reset. Ordering by distance from
                    # the near foot is exact: a hop is straight and monotonic
                    # along its axis. Free: the same cells, re-partitioned.
                    _mid = sorted(_dst, key=lambda c: (c[0] - fa[0]) ** 2 + (c[2] - fa[2]) ** 2)
                    _m = list(pa) + list(_mid) + list(pb)
                    # ponytail: the cover assumes a CHAIN -- place_rep derives a
                    # repeater's facing from the step into its cell, so a
                    # non-adjacent pair here would face a repeater the wrong way
                    # and feed the hop instead of the tile. Cheap to assert, and
                    # a wrong order would otherwise be a silently wrong circuit.
                    for _u, _v in zip(_m, _m[1:]):
                        if max(abs(_u[0] - _v[0]), abs(_u[1] - _v[1]),
                               abs(_u[2] - _v[2])) != 1:
                            raise RuntimeError(
                                f"bridge splice not a chain on {net}: {_u} -> {_v}")
                    paths[-2] = (_m, net, ())
                    paths.pop()
                except RuntimeError:
                    # ponytail: all-or-nothing hop. pa stamps inline, so a
                    # failed pb left the approach path behind as litter that
                    # seals later retries (micro1 S feet orphaned at (51,17),
                    # (43,16), (55,17)). Unwind pa's entry while the hop is
                    # reverted; no congest (its corridor is fine, pb failed).
                    if len(paths) > _npath:
                        _pp, _, _ps = paths.pop()
                        for _c in _pp:
                            if wires.get(_c) == net and _c not in placed:
                                del wires[_c]
                        _rip(_ps, net)
                    # ponytail: undo the hop. This used to rely on the caller
                    # raising (which discards the whole layout), but the
                    # two-pass loop keeps going after a failed task — so a
                    # half-placed arch survived as orphaned elevated dust and
                    # the next pass died on `OPEN`. Un-stamp here instead.
                    for c in _dst:
                        wires.pop(c, None)
                        placed.discard(c)
                        aircells.discard(c)
                    for c in _sup:
                        solid.pop((c[0], c[2]), None)
                        cond.discard(c)
                        if c[1] == 1:
                            condg.discard(c)
                        blocks[:] = [b for b in blocks if (b[0], b[1], b[2]) != c]
                    for c in _sup + [(fx, 1, fz)]:
                        for dx, dz in DIRS:
                            _r = rings.get((c[0] + dx, c[2] + dz))
                            if _r is not None:
                                _r.discard(net)
                                if not _r:
                                    del rings[(c[0] + dx, c[2] + dz)]
                    return False
                bridged.add((fx, fz, axis))
                try:
                    tasks.remove((s, t, net))
                except ValueError:
                    pass
                tasks.extend([(s, (fa[0], fa[2]), net), ((fb[0], fb[2]), t, net)])
                return True
        return False
    # ponytail: two passes over the same task list. Pass 1 is flat-only, so
    # every net that CAN route on the ground keeps today's exact route; only
    # what pass 1 could not place at all reaches pass 2, where 3D is allowed.
    # Interleaving instead (3D whenever a net is stuck) lets one long flight's
    # pillars eat the ground columns a later flat net needed — the flight
    # solved net A and killed net R (measured, latch_sr).
    stuck = None
    deferred = []
    # ponytail: total search budget for one layout. Measured post-deferral:
    # alu1 spends 98.6% of its searches re-searching flat after a rip (3D is
    # 0.6%), and 3842 searches is >300s on a 20k-cell field — so bounding the
    # *3D escalation* (the obvious suspect) would buy ~1%. Bound the effort
    # instead, and raise the NORMAL error so the debug dump still lands (a
    # census reads the dump, so an exotic exception would throw it away).
    # Default 0 = unlimited, i.e. no behaviour change; set it to bound a
    # runaway dense attempt.
    _scap = int(_os.environ.get("REDSTONE_SEARCH_CAP", "0"))
    _scount = [0]
    try:
        for use3d in ((False, True) if _PASSES == 2 else (True,)):
            if not pending:
                break
            while pending:
                if _scap and _scount[0] >= _scap:
                    raise RuntimeError(
                        f"search budget exceeded ({_scap} A* calls) with "
                        f"{len(pending)} task(s) unrouted — raise "
                        f"REDSTONE_SEARCH_CAP or narrow the build")
                _scount[0] += 1
                s, t, net = pending.pop(0)
                try:
                    route(s, t, net, use3d)
                    continue
                except RuntimeError as e:
                    why = str(e)
                # targeted ripup: nets physically sealing this wire get re-routed
                # after us. Goal-side first (cheap, master-identical); driver-side
                # only when goal rips are exhausted (drivers get entombed too).
                def seal_nets(cell):
                    found = set()
                    for dx, dz in DIRS:
                        # flat pass blames the two levels the 2D code blamed;
                        # only the 3D pass counts elevated dust as a sealer
                        for yy in ((1, 2, 3) if use3d else (1, 2)):
                            A = (cell[0] + dx, yy, cell[1] + dz)
                            for c in [A] + [(A[0] + qx, A[1], A[2] + qz) for qx, qz in DIRS]:
                                w = wires.get(c)
                                if w is not None and w != net and c not in placed:
                                    found.add(w)
                    return found
                blockers = seal_nets(t)
                for c in last_blocked.get(net, ()):
                    w = wires.get(c)
                    if w is not None and w != net and c not in placed:
                        blockers.add(w)
                block_tasks = [tk for tk in tasks if tk[2] in blockers]
                key = (net, tuple(sorted(blockers)))
                fails[key] = fails.get(key, 0) + 1
                if not block_tasks or fails[key] > 2:
                    extra = (seal_nets(s) - blockers) if s is not None else set()
                    extra_tasks = [tk for tk in tasks if tk[2] in extra]
                    xkey = (net, tuple(sorted(blockers | extra)), "drv")
                    if extra_tasks and fails.get(xkey, 0) < 2:
                        fails[xkey] = fails.get(xkey, 0) + 1
                        for p, m, s_ in paths[:]:
                            if m in extra:
                                for c in p:
                                    if wires.get(c) == m and c not in placed:
                                        del wires[c]
                                        congest[c] = congest.get(c, 0) + 5
                                _rip(s_, m)
                                paths.remove((p, m, s_))
                        pending = [(s, t, net)] + extra_tasks + pending
                        continue
                    if try_bridge(s, t, net):
                        continue
                    # ponytail: defer, do not abandon. `break` here ended the
                    # WHOLE pass, so exactly one task per layout ever reached
                    # the 3D pass — measured on alu1: 7 route attempts over 2
                    # nets, 1 three-D search, the other ~25 nets in the spec
                    # never attempted at all. Collect and keep going; the next
                    # pass (or the raise) decides.
                    deferred.append((s, t, net, why))
                    continue
                for p, m, s_ in paths[:]:
                    if m in blockers:
                        for c in p:
                            if wires.get(c) == m and c not in placed:
                                del wires[c]
                                congest[c] = congest.get(c, 0) + 5
                        _rip(s_, m)
                        paths.remove((p, m, s_))
                pending = [(s, t, net)] + block_tasks + pending
            if not deferred:
                break                       # pass drained: nothing left to fly
            if use3d:
                stuck = deferred[0]          # last chance: keep it so it raises
                break
            pending = [d[:3] for d in deferred] + pending   # pass 2: height allowed
            deferred = []
        if stuck is not None:
            raise RuntimeError(f"no route for {stuck[2]}: {stuck[0]} -> {stuck[1]} "
                               f"(grid full, widen W; last: {stuck[3]}; "
                               f"{len(deferred) + 1} task(s) unroutable)")
    finally:
        # ponytail: permanent debug tap (debug.py reads it). Costs one env
        # check per layout; replaces every ad-hoc Temp probe.
        if _os.environ.get("REDSTONE_DEBUG"):
            from debug import dump_state
            dump_state(_os.environ["REDSTONE_DEBUG"], gates, netspec,
                       solid, wires, rings, W, D)
    for name in recipe["outputs"]:
        pos[name]  # KeyError if output is undriven: loud, as before

    # pillars into the block list, once: routing kept them in `sup`/`cond` only
    for s_, n in sup.items():
        blocks.append((s_[0], s_[1], s_[2], "minecraft:cobblestone"))

    # phase 2: maze stamp is done above (route stamps inline); lamps stay
    # after routing so their collision check dodges wires automatically.

    # repeaters: dust dies after 15 blocks. Backward cover from each goal:
    # every path cell ends within 14 of a booster-or-source behind it.
    def place_rep(path, net, j):
        (x0, y0, z0), (x1, y1, z1) = path[j - 1], path[j]
        dx, dz = x1 - x0, z1 - z0
        facing = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}[(dx, dz)]
        if not _has_support((x1, y1, z1), sup, solid):
            raise RuntimeError(f"repeater {net} at {(x1, y1, z1)} has no support under it")
        for f in ((x1 + dx, y1, z1 + dz), (x1 - dx, y1, z1 - dz)):
            w = wires.get(f)
            if w is not None and w != net:
                raise RuntimeError(f"repeater guard {net} vs {w} at {f}")
        if wires.get((x1, y1, z1)) != net:
            if (x1, y1, z1) in repeaters and repeaters[(x1, y1, z1)][0] == net:
                return  # shared fanout trunk: a sibling branch already boosted here
            raise RuntimeError(
                f"repeater spot {net} at {(x1, y1, z1)} holds {wires.get((x1, y1, z1), 'EMPTY')} "
                f"(solid {solid.get((x1, z1), '-')})")
        del wires[(x1, y1, z1)]
        repeaters[(x1, y1, z1)] = (net, facing)

    for path, net, _sups in paths:
        # cover the tile-stub tail past the goal too: same-net dust stamped
        # in phase 1 (ports, latch rows) decays exactly like routed wire, and
        # a latch S-row needs level 9 at the port to reach its block, while
        # the endpoint alone is only guaranteed level 1.
        #
        # ponytail: walk ONE chain, not a tree. The tree version appended in
        # discovery order, so consecutive entries could be two cells apart
        # (`(114,1,13) -> (114,1,11)`); _straight3 still calls that triple
        # "collinear, same y" and hands the index to place_rep, which died on
        # `KeyError: (0,-2)`. A chain is always adjacent (which is all cover
        # and place_rep assume) and is less code. Bounded so a shared trunk
        # never drags in a far sibling branch.
        cells = list(path)
        seen = set(cells)
        g = c = cells[-1]
        while True:
            nxt = None
            for dx, dz in DIRS:
                m = (c[0] + dx, 1, c[2] + dz)
                if m in seen or wires.get(m) != net:
                    continue
                if abs(m[0] - g[0]) + abs(m[2] - g[2]) > 12:
                    continue
                nxt = m
                break
            if nxt is None:
                break
            seen.add(nxt)
            cells.append(nxt)
            c = nxt
        path = cells
        n = len(path)
        i = n - 1
        while i > 14:
            j = _cover_gap(path, i)
            if j is False:
                raise RuntimeError(f"unboostable gap on {net} near index {i} (twisty path)")
            place_rep(path, net, j)
            i = j

    for name in recipe["outputs"]:
        ox_, oz = pos[name]
        done = False
        for dx, dz in ((1, 0), (0, 1), (0, -1), (-1, 0)):
            fx, lx = (ox_ + dx, oz + dz), (ox_ + dx * 2, oz + dz * 2)
            if not (0 <= lx[0] < W and 0 <= lx[1] < D):
                continue
            if lx in solid or (lx[0], 1, lx[1]) in wires or fx in solid or (fx[0], 1, fx[1]) in wires:
                continue
            # The tap is stamped after routing, so no route could avoid it —
            # it has to dodge instead, and "occupied" now means a foreign wire
            # BESIDE the tap as well as on it (stamp_wire's adjacency guard).
            if any(wires.get((fx[0] + ax, 1, fx[1] + az)) not in (None, name)
                   for ax, az in DIRS):
                continue
            stamp_wire([fx], name)  # touches out stub: zero-wire tap
            blocks.append((lx[0], 1, lx[1], "minecraft:redstone_lamp"))
            solid[lx] = ("lamp", name)
            for ddx, ddz in DIRS:
                ring(lx[0] + ddx, lx[1] + ddz, own(name))
            recs.append(("OUT", name, [name], fx))
            done = True
            break
        if not done:
            raise RuntimeError(f"lamp spot taken for {name} at {(ox_, oz)}")

    # checker: no two nets may share/side-touch dust, except at OR junctions.
    # Diagonal +-1 adjacency counts only via a true slope link (support +
    # no lid, sim's rule): stacked/unsupported y-adjacency never couples,
    # so legal overflight passes and real 3D shorts still fail loudly.
    cob3 = {(x, y, z) for x, y, z, bid in blocks if bid.split("[")[0] == "minecraft:cobblestone"}
    for (x, y, z), net in wires.items():
        for dx, dz in DIRS:
            m = (x + dx, y, z + dz)
            if m in wires and wires[m] != net:
                ok = ((m[0], m[2]) in junctions and net in junctions[(m[0], m[2])] and wires[m] in junctions[(m[0], m[2])])
                ok = ok or ((x, z) in junctions and wires[m] in junctions[(x, z)])
                if not ok:
                    raise RuntimeError(f"SHORT: {net} touches {wires[m]} at {(x, y, z)}->{m}")
            for dy in (1, -1):
                f = (x + dx, y + dy, z + dz)
                w = wires.get(f)
                if w is None or w == net:
                    continue
                if dy == 1:
                    if (f[0], f[1] - 1, f[2]) in cob3 and (x, y + 1, z) not in cob3:
                        raise RuntimeError(f"SHORT3D: {net} slope-links {w} at {(x, y, z)}->{f}")
                elif y >= 2 and (x, y - 1, z) in cob3 and (f[0], y, f[2]) not in cob3:
                    raise RuntimeError(f"SHORT3D: {net} slope-links {w} at {(x, y, z)}->{f}")
    # checker 2 (opens): every wire must trace to a driver (lever feed, tie,
    # or torch-adjacent dust). Same-net steps, junctions merge, repeaters pass.
    # A routed-looking but unconnected net fails loudly instead of building dead.
    seed_states = []
    for name, p in pos.items():
        p3 = (p[0], 1, p[1])
        if p3 in wires and wires[p3] == name:
            seed_states.append((p3, name))
    for (x, z), (kind, name) in solid.items():
        # ponytail: every lever island seeds (multi-lever inputs drive
        # several disconnected dust cells; pos[] only knows the first).
        if kind != "lever":
            continue
        for dx, dz in DIRS:
            c = (x + dx, 1, z + dz)
            if c in wires and wires[c] == name:
                seed_states.append((c, name))
    for (x, y, z), net in wires.items():
        for dx, dz in DIRS:
            if solid.get((x + dx, z + dz), (None,))[0] == "torch":
                seed_states.append(((x, y, z), net))
                break
    reached, seen_states = set(), set()
    stack = seed_states
    cob = {(x, y, z) for x, y, z, bid in blocks if bid.split("[")[0] == "minecraft:cobblestone"}
    while stack:
        c, n = stack.pop()
        if (c, n) in seen_states:
            continue
        seen_states.add((c, n))
        reached.add(c)
        for dx, dz in DIRS:
            m = (c[0] + dx, c[1], c[2] + dz)
            if m in wires:
                nm = wires[m]
                if nm == n or ((c[0], c[2]) in junctions and nm in junctions[(c[0], c[2])]) or \
                   ((m[0], m[2]) in junctions and n in junctions[(m[0], m[2])]):
                    stack.append((m, nm if nm == n or (m[0], m[2]) not in junctions else n))
            elif m in repeaters and repeaters[m][0] == n:
                stack.append((m, n))
            elif solid.get((m[0], m[2]), (None,))[0] == "repeater" and solid[(m[0], m[2])][1] == n:
                stack.append((m, n))  # OR diodes stamp solid-only
            # ponytail: slope links use sim's rule (support below, no lid
            # above); without this every bridge reads as unconnected dust.
            up = (c[0] + dx, c[1] + 1, c[2] + dz)
            if wires.get(up) == n and (c[0] + dx, c[1], c[2] + dz) in cob \
                    and (c[0], c[1] + 1, c[2]) not in cob:
                stack.append((up, n))
            dn = (c[0] + dx, c[1] - 1, c[2] + dz)
            if wires.get(dn) == n and (c[0], c[1] - 1, c[2]) in cob \
                    and (c[0] + dx, c[1], c[2] + dz) not in cob:
                stack.append((dn, n))
    dead = [(x, y, z) for (x, y, z) in wires if (x, y, z) not in reached
            and wires[(x, y, z)] != "0"]  # undriven "0" stubs read 0 unconnected
    if dead:
        raise RuntimeError(f"OPEN (unconnected dust, nothing drives it): {dead[:6]}")
    # ponytail: shrink-wrap grid to content (+3 margin). A 13x4 gate on a
    # 30x38 pad photographs as sprawl even when every wire is minimal.
    OCC = [(x, 1, z) for (x, z) in solid] + list(wires)
    minx = min(c[0] for c in OCC) - 3
    minz = min(c[2] for c in OCC) - 3
    maxx = max(c[0] for c in OCC) + 3
    maxz = max(c[2] for c in OCC) + 3
    blocks = [(x - minx, y, z - minz, b) for x, y, z, b in blocks]
    solid = {(x - minx, z - minz): v for (x, z), v in solid.items()}
    wires = {(x - minx, y, z - minz): v for (x, y, z), v in wires.items()}
    rings = {(x - minx, z - minz): v for (x, z), v in rings.items()}
    junctions = {(x - minx, z - minz): v for (x, z), v in junctions.items()}
    pos = {n: (x - minx, z - minz) for n, (x, z) in pos.items()}
    repeaters = {(x - minx, y, z - minz): v for (x, y, z), v in repeaters.items()}
    W, D = maxx - minx + 1, maxz - minz + 1
    out = list(blocks)
    # ponytail: one component per cell; a repeater wins over dust. The router
    # can re-stamp a wire label onto a tile repeater cell (tile dels it, route
    # re-adds it), which modelled dust+repeater at once -- a phantom loop that
    # holds itself lit across phases (D-latch seeds 4/5). The world gets one
    # block, so the sim must see one.
    dust = set(wires) - set(repeaters)
    _loop = _loop_rep(wires, repeaters, dust)
    if _loop is not None:
        raise RuntimeError(f"repeater loop on {_loop[1]} at {_loop[0]}: front "
                           f"joins back via dust (bistable; first transient latches it)")
    for (x, y, z), net in wires.items():
        if (x, y, z) in repeaters:
            continue
        out.append((x, y, z, wire_bid((x, y, z), dust)))
    for (x, y, z), (net, facing) in repeaters.items():
        out.append((x, y, z, f"minecraft:repeater[facing={facing},delay=1]"))
    # ponytail: stone only where a ground component sits (flat worlds have
    # ground already); a full pad was 98% of the file. y>=2 rides pillars.
    for x, z in sorted({(x, z) for x, y, z, bid in out if y == 1}):
        out.append((x, 0, z, "minecraft:stone"))
    io = {"levers": {c: n for c, (k, n) in solid.items() if k == "lever"},
          "lamps": {c: n for c, (k, n) in solid.items() if k == "lamp"},
          "nets": dict(wires)}
    return sorted(out), (W, D), io


if __name__ == "__main__":
    # ponytail: ONE runnable check — port grid spec (docs/phase1).
    # Single-tile builds keep the lamp due east (nothing else placed yet),
    # so lamp-anchored relative offsets prove the grid: absolute coords
    # shift per build (shrink-wrap), easternmost cells are downstream
    # routes — only tile-to-port vectors are invariant.
    # (NOR has no recipe syntax — covered indirectly by banded builds;
    # OR is a junction, exempt per spec.)
    from recipe import parse_recipe
    from sim import layout_retry
    _r = parse_recipe("IN a\nOUT n\nn = NOT a\n")
    _, _, _io, _ = layout_retry(_r, verify=True)
    _lamps = [c for c, v in _io["lamps"].items() if v == "n"]
    assert len(_lamps) == 1, _io["lamps"]
    _lx, _lz = _lamps[0]
    _nets = _io["nets"]
    assert _nets.get((_lx - 2, 1, _lz)) == "n", "NOT out drifted"
    assert _nets.get((_lx - 5, 1, _lz)) == "a", "NOT port drifted"
    _r = parse_recipe("IN a, b\nOUT t\nt = a AND b\n")
    _, _, _io, _ = layout_retry(_r, verify=True)
    _lamps = [c for c, v in _io["lamps"].items() if v == "t"]
    assert len(_lamps) == 1, _io["lamps"]
    _lx, _lz = _lamps[0]
    _nets = _io["nets"]
    assert _nets.get((_lx - 2, 1, _lz)) == "t", "AND out drifted"
    assert _nets.get((_lx - 10, 1, _lz - 1)) == "a", "AND A-port drifted"
    assert _nets.get((_lx - 10, 1, _lz + 2)) == "b", "AND B-port drifted"
    print("ports ok: AND/NOT grid matches spec")
    # ponytail: OR-feeding inputs keep batch levers (junction aims at them);
    # verify=True proves the diodes fire (serve-DEMO class: silent dark bb).
    _r = parse_recipe("IN a, b\nOUT y\ny = a OR b\n")
    _, _, _io, _ = layout_retry(_r, verify=True)
    assert set(_io["levers"].values()) >= {"a", "b"}, _io["levers"]
    print("or-lever ok: OR inputs on bank levers, verify green")
    # ponytail: ONE panel check — shared input builds green with exactly
    # one lever per input (verify=True proves the routed fanout fires).
    from collections import Counter as _Ctr
    _r = parse_recipe("IN a, b, c\nOUT y\ny1 = a AND b\ny2 = a AND c\ny = y1 OR y2\n")
    _xb, _, _io, _ = layout_retry(_r, verify=True)
    _c = _Ctr(_io["levers"].values())
    assert _c["a"] == 1 and len(_c) == 3, _c
    print("panel ok: shared input on one bank lever, verify green")
    # ponytail: the AND/OR check above is BLIND to XOR, so XOR gets its own:
    # side feeds are repeaters fed by the input nets (see placer), which is
    # what lets the panel bar hold here — one lever per input, no exemptions.
    _r = parse_recipe("IN a, b\nOUT y\ny = a XOR b\n")
    _xg, _, _gio, _ = layout_retry(_r, verify=True)
    _c = _Ctr(_gio["levers"].values())
    assert _c["a"] == 1 and _c["b"] == 1, dict(_c)
    print("xor-lever ok: one lever per input, verify green")
    # ponytail: both bars above count LABELS, so neither can see the two ways
    # the panel can actually be broken. (a) A lever beside wire of a SECOND net
    # is a short the label never reports: the sim powers ANY same-level cell next
    # to an ON lever (dust_lvl), so "one lever" and "one net" are different
    # claims. (b) The extra loads may not be reachable from that one lever at
    # all — the panel would be a label and not a wire. Check the real graph,
    # crossing repeaters (a connection: the back reads behind, the output feeds
    # front) and the sim's slope links at y+-1. Run on the AND fanout AND on
    # XOR, whose side feed runs ELEVATED — that shape is what caught a y=1-only
    # walk here, and a canary that skips it would let the bug back in.
    _AX = {"east": (1, 0), "west": (-1, 0), "south": (0, 1), "north": (0, -1)}

    def _panel_electrical(blocks, io, inputs):
        nets = io["nets"]
        reps = {}
        for x, y, z, bid in blocks:
            if bid.startswith("minecraft:repeater"):
                reps[(x, y, z)] = bid.split("facing=")[1].split(",")[0]
        for (lx, lz), lab in io["levers"].items():
            near = {nets[(lx + dx, 1, lz + dz)]
                    for dx, dz in DIRS if (lx + dx, 1, lz + dz) in nets}
            assert len(near) <= 1, \
                f"lever {lab} at {(lx, lz)} also reaches {sorted(near - {lab})}"
        for a in inputs:
            src = None
            for (lx, lz), lab in io["levers"].items():
                if lab == a:
                    for dx, dz in DIRS:
                        if nets.get((lx + dx, 1, lz + dz)) == a:
                            src = (lx + dx, 1, lz + dz)
                            break
                if src:
                    break
            assert src is not None, f"lever for {a} reaches no wire"
            seen, q = {src}, [src]
            while q:
                c = q.pop()
                nxt = [m for dx, dz in DIRS for dy in (0, 1, -1)
                       if nets.get(m := (c[0] + dx, c[1] + dy, c[2] + dz)) == a or m in reps]
                if c in reps:
                    dx, dz = _AX[reps[c]]
                    nxt += [(c[0] + dx, 1, c[2] + dz), (c[0] - dx, 1, c[2] + dz)]
                for m in nxt:
                    if m not in seen:
                        seen.add(m)
                        q.append(m)
            want = {c for c, n in nets.items() if n == a}
            assert not want - seen, \
                f"{a}: {len(want - seen)} of {len(want)} cells not reachable " \
                f"from its one lever, e.g. {sorted(want - seen)[:3]}"

    _panel_electrical(_xb, _io, ("a", "b", "c"))
    _panel_electrical(_xg, _gio, ("a", "b"))
    # ponytail: negative controls, because a canary never seen red is a print
    # statement -- 9980750 is the scar tissue (a lever bar that counted nothing
    # for a year). Two vacuity risks, both cheap to close: a lever shorting a
    # second net, and the per-input loop quietly testing nothing.
    import copy as _copy
    _bad = _copy.deepcopy(_io)
    _bl = next(iter(_bad["levers"]))
    _bad["nets"][(_bl[0], 1, _bl[1] - 1)] = "intruder"
    try:
        _panel_electrical(_xb, _bad, ("a", "b", "c"))
        raise SystemExit("panel-wire canary did NOT catch a lever shorting a 2nd net")
    except AssertionError as e:
        assert "also reaches" in str(e), e
    try:
        _panel_electrical(_xb, _io, ("nosuchinput",))
        raise SystemExit("panel-wire canary did NOT notice an input with no lever")
    except AssertionError as e:
        assert "reaches no wire" in str(e), e
    print("panel-wire ok: no lever shorts a 2nd net, every load fed by its one lever")
    print("panel-wire neg: short caught, missing lever caught")
    # ponytail: the POINTING table, asserted straight from
    # minecraft.wiki/Redstone_Dust. This is the only external oracle in the
    # project: everything else is the sim agreeing with the layout, which is
    # how a wrong model passes itself. Asserted here because the sim's
    # block-power test and the exporter's blockstate writer both consume
    # dust_points(), and the in-game end-cell test has not been run yet.
    _D = {(0, 1, 0), (0, 1, 1), (0, 1, 2), (0, 1, 3)}          # N-S line
    assert dust_points((5, 1, 5), {(5, 1, 5)}) == frozenset(DIRS), \
        "cross points all four"
    assert dust_points((0, 1, 3), _D) == frozenset({(0, 1), (0, -1)}), \
        "end cell points along its own axis, both ways"
    assert dust_points((0, 1, 1), _D) == frozenset({(0, 1), (0, -1)}), \
        "line points along its own axis"
    _E = {(0, 1, 0), (1, 1, 0), (2, 1, 0)}                     # E-W line
    assert dust_points((1, 1, 0), _E) == frozenset({(1, 0), (-1, 0)}), \
        "a wire running PAST a block does not point at it"
    _C = {(0, 1, 0), (1, 1, 0), (1, 1, 1)}                     # corner
    assert dust_points((1, 1, 0), _C) == frozenset({(-1, 0), (0, 1)}), \
        "corner points at its links only"
    _T = {(0, 1, 0), (1, 1, 0), (2, 1, 0), (1, 1, 1)}          # T
    assert dust_points((1, 1, 0), _T) == frozenset({(-1, 0), (1, 0), (0, 1)}), \
        "T points at its three links"
    print("pointing ok: cross/end/line/corner/T per wiki Redstone Dust")
    # ponytail: the export round-trip — the FILE is the shipping gate and the
    # sim never reads it, so a bare-id regression would go green everywhere
    # and ship dots. Export a real build, read the .schem back, assert every
    # wire's baked states equal wire_bid (the one shared encoding).
    try:
        import mcschematic as _ms
        from export import export_schem as _xs
        import tempfile as _tf
        import os as _oo
    except ImportError:
        print("export-rt skipped: mcschematic missing (export already skips)")
    else:
        _r = parse_recipe("IN a, b\nOUT y\ny = a AND b\n")
        _bb, _, _bio, _ = layout_retry(_r, verify=True)
        with _tf.TemporaryDirectory(prefix="rs_rt_") as _td:
            _rp = _oo.path.join(_td, "rt.schem")
            _xs(_bb, _rp, 0)
            _rs = _ms.MCSchematic(_rp)
            _dust = set(_bio["nets"])
            assert _dust, "no wires to round-trip"
            for _c in _dust:
                assert _rs.getBlockStateAt(_c) == wire_bid(_c, _dust), _c
        print(f"export-rt ok: {len(_dust)} wire states round-trip through .schem")
    # ponytail: ONE bridge check — template matches sim's proven crossover
    # vectors; live-fire two independent nets through it, sim green.
    _feet, _sup, _dst = bridge_plan(7, 5, "ns")
    assert _dst == [(7, 2, 4), (7, 3, 5), (7, 2, 6)], _dst
    assert _sup == [(7, 1, 4), (7, 1, 6), (7, 2, 5)], _sup
    assert bridge_free({(7, 1, 5): "A"}, {}, {}, set(), 40, 40, 7, 5, "ns", "B") is True
    assert bridge_free({}, {}, {}, set(), 40, 40, 7, 5, "ns", "B") is False
    _bl, _so, _wi, _ri, _pl = [], {}, {}, {}, set()
    _feet = bridge_stamp(_bl, _so, _wi, _ri, _pl, "B", 7, 5, "ns")
    assert _feet == [(7, 1, 3), (7, 1, 7)], _feet
    assert all(_wi[c] == "B" for c in [(7, 2, 4), (7, 3, 5), (7, 2, 6)]), _wi
    assert all(_so[k][0] == "cobble" for k in [(7, 4), (7, 6), (7, 5)]), _so
    assert _pl == {(7, 2, 4), (7, 3, 5), (7, 2, 6)}, _pl
    assert bridge_free(_wi, _so, {}, set(), 40, 40, 7, 5, "ns", "C") is False
    assert bridge_free(_wi, _so, {}, set(), 40, 40, 7, 5, "ew", "C") is False
    # 3D slope guard FIRES: the ns dust at (7,2,4) sits on support (7,1,4), so
    # foreign dust one step beside it at (8,1,4) is slope-linked (sim steps
    # one axis at a time) — that hop would be a short. Same footprint without
    # the neighbour is fine, and a lid over the neighbour decouples it again.
    assert bridge_free({(7, 1, 5): "A", (8, 1, 4): "C"}, {}, {}, set(), 40, 40, 7, 5, "ns", "B") is False
    assert bridge_free({(7, 1, 5): "A"}, {}, {}, set(), 40, 40, 7, 5, "ns", "B") is True
    assert bridge_free({(7, 1, 5): "A", (8, 1, 4): "C"}, {}, {}, set(), 40, 40, 7, 5, "ns", "B",
                       cond={(8, 2, 4)}) is True, "a lid over the lower wire decouples it"
    from sim import sim_verify as _sv
    _W, _CB = "minecraft:redstone_wire", "minecraft:cobblestone"
    _xb = [(2, 1, 5, "minecraft:lever")] + [(x, 1, 5, _W) for x in range(3, 10)] + [(10, 1, 5, "minecraft:redstone_lamp")]
    _xb += [(7, 1, 1, "minecraft:lever"), (7, 1, 2, _W), (7, 1, 3, _W)]
    for _c in _sup:
        _xb.append((_c[0], _c[1], _c[2], _CB))
    for _c in _dst:
        _xb.append((_c[0], _c[1], _c[2], _W))
    _xb += [(7, 1, 7, _W), (7, 1, 8, _W), (7, 1, 9, "minecraft:redstone_lamp")]
    _xio = {"levers": {(2, 5): "A", (7, 1): "B"}, "lamps": {(10, 5): "Aout", (7, 9): "Bout"}, "nets": {}}
    _xr = {"inputs": ["A", "B"], "outputs": ["Aout", "Bout"],
           "gates": [{"out": "Aout", "op": "AND", "args": ["A", "A"]},
                     {"out": "Bout", "op": "AND", "args": ["B", "B"]}]}
    _sv(_xr, _xb, _xio, quiet=True)
    print("bridge ok: ns hop crosses live wire, sim green both ways")
    # ponytail: 3D Attempt 1 rules — support assert FIRES on a bad case, cover
    # accepts a pillar run and refuses a long pure-elevated one. No fixture:
    # hand-built cells, the same helpers route() uses.
    assert _has_support((4, 1, 4), {}, {}) is True, "ground needs no block"
    assert _has_support((4, 2, 4), {}, {}) is False, "floating repeater allowed!"
    assert _has_support((4, 2, 4), {(4, 1, 4): "n"}, {}) is True
    assert _has_support((4, 2, 4), {}, {(4, 4): ("cobble", "n")}) is True
    assert _has_support((4, 3, 4), {(4, 1, 4): "n"}, {}) is False, "y=3 on a y=1 pillar"
    _p = [(x, 1, 0) for x in range(6)] + [(x, 2, 0) for x in range(6, 10)]
    assert _cover_gap(_p, len(_p) - 1) == 1, "cover should back off to the last straight run"
    _pillar = [(x, 2, 0) for x in range(20)]  # straight flight: cover sits on a pillar
    assert _cover_gap(_pillar, 19) == 5, "pillar cover not used"
    _fly = [(0, 1, 0)] + [(x, 3, 0) for x in range(1, 21)]  # 20 at y=3, no support
    assert _cover_gap(_fly, len(_fly) - 1) is not False, "straight run is boostable"
    _twist = [(x, 1, 0) if x % 2 else (x, 2, 0) for x in range(21)]  # no straight triple
    assert _cover_gap(_twist, 20) is False, "unboostable twisty run should be refused"
    print("3d ok: support assert fires, cover takes pillars, refuses dead flights")

