"""Vertical deck stacking, v1: true 3D tile stacking without migrating the maps.

The 2D maps (solid/rings/junctions/pos keyed (x,z), ~140 y==1 sites) stay
untouched. Instead each deck composes FLAT through the proven pipeline
(layout_retry verify=True), then decks merge VERTICALLY as a post-pass:

  deck0 (inputs/levers/ground)  -> y = 1..4, as composed
  glass floor plate (inert)     -> y = 5 (transparent: never conducts, never
                                   cuts a slope, needs no support itself)
  deck1 (translated +5y)        -> y = 6.., same (x,z) footprint as deck0
  shaft+leg vias join boundary nets deck-to-deck; sim_verify gates the
  whole merged build.

Why translation, not mirror: translation preserves torch/repeater facings
and dust connection shapes exactly; a mirror would flip E<->W bids.
Why glass plate, not translated y=0 pads: translated stone pads are opaque
lids that cut lower-deck slopes; glass lids never cut (sim + vanilla).
Why deck pitch 5: lower decks top at y<=4 (tall bridge), sim couples dy<=1
only, so dy>=2 between decks is parasitic-free by construction.
Why glass pillars, not cobble: the engine verifies glass-supported wire
(sim models it, alu4glass7 proved it in game 6/6) but the router never
stamps glass (compose.py:2337, glass-free by design). A cobble pillar
beside foreign dust is a parasitic feed and needs clearance proof; a
glass pillar is inert, so vias add zero powerable mass. First glass
emitter in the repo: the plate, now the via shafts/feet too.

Via shape (provably stack-free): two single-level BFS legs joined by a
fixed diagonal shaft (x+i,1+i,z), i=0..5. Legs never move vertically
(dust-on-dust impossible); the shaft is a strict diagonal (a support
cell can never coincide with a path cell: i==1+j and i==j contradict).
Staircase slopes are the shape lwire flights already stamp.

ASSUMPTION (logged): reference HDL repos skipped after a listing peek --
all are flat compilers with no stacking pass; the in-repo hier pipeline
plus this post-pass is the mechanism. Revisit if v1 hits a wall.
"""

import os
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import DIRS, base
from recipe import parse_recipe, eval_net
from layout import wire_bid
from sim import layout_retry, sim_verify, _parse_build, _run_vec
from sim import _latch_hold_seed
from export import export_mcfunction, export_schem, export_html

DY = 5          # deck pitch (plate at PLATE_Y, deck1 comps at 1+DY)
PLATE_Y = 5     # deck1 floor plate level (deck0 comps live at y=1..4)
CORRIDORS = (0, 14, -14)   # x-bias retries for the via box
GLASS = "minecraft:glass"
NB6 = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
SHAFT_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
# ponytail: support-valid bids (mirrors sim._check_supports: dust/rep/comp
# may only rest on these; anything else below (torch, wire, lamp) both
# pops in vanilla and conducts wrong).
SUPPORT_OK = {"minecraft:cobblestone", "minecraft:stone", GLASS,
              "minecraft:stone_slab", "minecraft:smooth_stone_slab",
              "minecraft:cobblestone_slab", "minecraft:redstone_block"}

SUB_A = """IN a, b, c
OUT t, c2
t = a AND b
c2 = c OR c
"""

SUB_B = """IN t, c2
OUT y
y = t OR c2
"""

FULL = """IN a, b, c
OUT t, c2, y
t = a AND b
c2 = c OR c
y = t OR c2
"""


def _bbox(cells):
    xs = [c[0] for c in cells]
    zs = [c[2] for c in cells]
    return min(xs), max(xs), min(zs), max(zs)


def _strip_deck(blocks, io):
    """Keep everything except y=1 lever blocks and y=0 pads.

    Pads would translate into opaque slope-cutting lids; the glass plate
    replaces them. Lever blocks are re-driven from deck0 via shafts.
    """
    levcells = set()
    for (x, z) in io["levers"]:
        levcells.add((x, 1, z))
    keep = []
    for (x, y, z, bid) in blocks:
        if (x, y, z) in levcells and "lever" in bid:
            continue
        if y == 0:
            continue
        keep.append((x, y, z, bid))
    return keep


def _translate(blocks, dx, dy, dz):
    return [(x + dx, y + dy, z + dz, bid) for (x, y, z, bid) in blocks]


def _comp_types(blocks):
    """Cells holding a redstone component (wire/rep/comp/torch/lever/lamp)."""
    out = {}
    for (x, y, z, bid) in blocks:
        b = base(bid)
        if b in ("minecraft:redstone_wire", "minecraft:repeater",
                 "minecraft:comparator", "minecraft:redstone_wall_torch",
                 "minecraft:redstone_torch", "minecraft:lever",
                 "minecraft:redstone_lamp", "minecraft:redstone_block"):
            out[(x, y, z)] = b
    return out


def _bfs2d(occ, comps, wires, net, starts, goals, y, box, sup_ok=None,
           allow=(), ban=(), lamps=(), cap=60000):
    """Single-level BFS (no vertical moves: self-stacking impossible by
    construction). sup_ok(c) optionally gates the support cell below.
    allow: cells passing all gates (pre-validated shaft joints). ban:
    never stepped on. lamps: lamp blocks (vias keep one cell away, even
    own-net: dust hugging a lamp corner-blocks its arm). Same clearance
    as clear(): orthogonal foreign, slope foreign wires, lamp proximity.
    Returns path or None (bounded, quiet: the caller picks the next
    shaft/corridor)."""
    x0, x1, z0, z1 = box
    NB4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
    own = {c for c, v in wires.items() if v == net}

    def ok(c):
        if c in allow:
            return True  # pre-validated shaft joint (base/front)
        if c in ban:
            return False
        if not (x0 <= c[0] <= x1 and z0 <= c[2] <= z1) or c[1] != y:
            return False
        # ponytail: air-only paths (no stepping on any wire, own or
        # foreign). A diode planted on a pre-existing net cell faces
        # walk-direction and severs every load behind it (measured:
        # deck0 t lamp dark with driver lit on 110/111). Joins happen
        # by adjacency at the endpoints, never underfoot.
        if c in wires:
            return False
        if c in occ:
            return False
        if sup_ok is not None and not sup_ok(c):
            return False
        for dx, dy, dz in NB6:
            n = (c[0] + dx, c[1] + dy, c[2] + dz)
            if n in own:
                if n in lamps:
                    return False
                continue
            if n in comps or n in lamps:
                return False
        for dx, dz in DIRS:
            for dy in (-1, 1):
                n = (c[0] + dx, c[1] + dy, c[2] + dz)
                if n in wires and n not in own:
                    return False
        n = (c[0], c[1] + 1, c[2])
        if n in wires and n not in own:
            return False
        return True

    prev = {}
    seen = set()
    q = deque()
    for c in sorted(starts):
        if ok(c) and c not in seen:
            seen.add(c)
            prev[c] = None
            q.append(c)
    pops = 0
    found = None
    while q:
        pops += 1
        if pops > cap:
            return None
        c = q.popleft()
        if c in goals:
            found = c
            break
        for dx, dz in NB4:
            n = (c[0] + dx, c[1], c[2] + dz)
            if n in seen or not ok(n):
                continue
            seen.add(n)
            prev[n] = c
            q.append(n)
    if found is None:
        return None
    path = [found]
    while prev[path[-1]] is not None:
        path.append(prev[path[-1]])
    path.reverse()
    return path


def route_via(occ, solid, comps, sources, targets, wires, net, plate_span,
              src_levels, bset, lampcells, avoid=(), xbias=0):
    """Two y=1/y=6 legs joined by a fixed diagonal glass-pillared shaft,
    plus a top booster (fresh 15 for leg2: the shaft arrives decayed).

    sources: own-net cells in deck0 (y==1 used). targets: own-net cells
    in deck1 (y==1+DY used: the translated lever-adjacent stubs).
    solid: cells holding support-valid bids (dust/rep/comp may rest on
    these; a torch/lamp/wire below both pops in vanilla and conducts
    wrong, so only these reuse). src_levels: {cell: driven level} from
    the partition sim (driver region taps first). Returns (dust_cells,
    glass_cells, repeaters). Raises RuntimeError (loud: the caller tries
    the next shaft/corridor instead of shipping a coupling).
    """
    S1 = sorted((c for c in sources if c[1] == 1),
                key=lambda c: (-src_levels.get(c, 0), c))
    T6 = sorted(c for c in targets if c[1] == 1 + DY)
    if not S1:
        raise RuntimeError("via: no y=1 source cells")
    if not T6:
        raise RuntimeError("via: no deck-level target cells")
    top_lvl = max(src_levels.get(c, 0) for c in S1)
    tapcells = [c for c in S1 if src_levels.get(c, 0) >= top_lvl - 2]
    own = {c for c, v in wires.items() if v == net}
    mnx, mxx, mnz, mxz = plate_span
    xs = [c[0] for c in S1 + T6]
    zs = [c[2] for c in S1 + T6]
    box = (min(xs) - 12 + min(xbias, 0), max(xs) + 12 + max(xbias, 0),
           min(zs) - 12, max(zs) + 12)

    def clear(c):
        # orthogonal foreign components short (wired-or by touch); the 8
        # vertical-diagonal + directly-above foreign wires couple through
        # sim's slope terms (cup/cdn read diagonally regardless of lids
        # when the support is transparent). Same-y diagonals never
        # connect, so they stay legal (keeps routes possible).
        # Lamps (any net, even own) read arms: dust hugging a lamp
        # corner-blocks its arm and darkens it with the net lit
        # (measured: deck0 t lamp dark at 13 on the arm). Vias keep one
        # cell from every lamp block.
        for dx, dy, dz in NB6:
            n = (c[0] + dx, c[1] + dy, c[2] + dz)
            if n in own:
                if n in lampcells:
                    return False
                continue
            if n in comps or n in lampcells:
                return False
        for dx, dz in DIRS:
            for dy in (-1, 1):
                n = (c[0] + dx, c[1] + dy, c[2] + dz)
                if n in wires and n not in own:
                    return False
        n = (c[0], c[1] + 1, c[2])
        if n in wires and n not in own:
            return False
        return True

    def shaft_at(bx, bz, dx, dz):
        """Validate a climb; return (dust, glass) or None (quiet)."""
        dust = [(bx + i * dx, 1 + i, bz + i * dz) for i in range(DY + 1)]
        sup = [(bx + i * dx, i, bz + i * dz) for i in range(DY + 1)]
        glass = []
        for d in dust:
            if d in occ or d in bset or d in wires or d in avoid:
                return None
            if not clear(d):
                return None
        for s in sup:
            if s in wires:
                return None  # support on a wire = dust-on-dust upstairs
            if s in solid:
                continue  # reusable support (pad, pillar, plate rock)
            if s[1] == PLATE_Y and mnx <= s[0] <= mxx and mnz <= s[2] <= mxz:
                continue  # the plate lands here
            glass.append(s)
        return dust, glass

    # ponytail: shafts hunt near the TAP, not the S-T midpoint. The tap
    # is the only place with level to spend (driver region ~15); a
    # shaft across the field starts decayed and dies mid-climb
    # (measured: tops dark, y dark on every vector at center
    # alignment). Starts likewise leave from tap-adjacent cells only.
    midx = sum(c[0] for c in tapcells) // len(tapcells)
    midz = sum(c[2] for c in tapcells) // len(tapcells)

    def _sup2(x, y, z):
        # leg2 (y=6) support: reusable valid solid, else stampable air.
        # A torch/lamp/wire below both pops in vanilla and conducts
        # wrong (measured: t dark on 110 with a dust-on-torch support
        # the occ-only rule reused). Plate rock counts as reusable.
        s = (x, y, z)
        if s in wires:
            return False
        if s in solid:
            return True
        if s in occ:
            return False
        return True

    # ponytail: the path ends IN an ex-lever cell (dust), which feeds
    # B's leg exactly as the lever did (same topology, same shapes).
    # Goals widen to the feed's air neighbors (adjacent dust conducts
    # identically; a single walled feed cell starved the second via
    # every order -- measured 200+ shafts x leg2 always 0). The forced
    # end diode below re-15s wherever the path lands.
    goals6 = set(T6)
    for (x, y, z) in T6:
        for dx, dz in DIRS:
            goals6.add((x + dx, y, z + dz))
    # ponytail: avoid = other feeds' 3x3 columns (all y). Feeds sit
    # adjacent (banked levers); the first via's halo otherwise covers
    # the second feed's approaches and leg2 fails every order
    # (measured 200+ shafts x leg2 always 0, both orders). A 3x3 column
    # blocks every coupling geometry (orthogonal + slope need dx,dz<=1)
    # while costing detours nothing (shafts live in margin anyway).
    # Own feed is 4+ away: disjoint by construction (asserted below).
    avoid = set(avoid)
    for (fx, fy, fz) in goals6:
        assert all(abs(fx - ax) > 1 or abs(fz - az) > 1 for (ax, ay, az)
                   in avoid), f"via {net}: feeds overlap (no room)"
    cands = []
    for x in range(box[0], box[1] + 1):
        for z in range(box[2], box[3] + 1):
            c = (x, 1, z)
            if c in occ or c in wires or c in avoid or not clear(c):
                continue
            s = (x, 0, z)
            if s in occ or s in wires:
                continue
            cands.append((abs(x - midx) + abs(z - midz), x, z))
    cands.sort()
    dbg = os.environ.get("STACKDBG")
    # valid leg1 starts diagnose landlock (pads/torch halos/c2's wall).
    _st = [c for c in _adj(S1, 1)
           if c not in occ and not (c in wires and c not in own)
           and (c[0], 0, c[2]) not in occ]
    if dbg:
        print(f"via {net}: {len(cands)} shaft bases, "
              f"{len(_st)} raw leg1 starts", flush=True)
    nshaft = nleg1 = 0
    for _d, bx, bz in cands[:64]:
        for dx, dz in SHAFT_DIRS:
            r = shaft_at(bx, bz, dx, dz)
            if r is None:
                continue
            nshaft += 1
            dust_s, glass_s = r
            base_c, top_c = dust_s[0], dust_s[-1]
            # ponytail: booster must dodge the shaft itself. Shaft dust
            # is unwired air to these checks (caller stamps it later): a
            # flat directly ABOVE shaft dust reads as free air, the
            # plate skips the cell, and the flat lands on wire
            # (measured: flat (30,6,21) on shaft (30,5,21)). Shaft
            # glass supports are reusable; shaft dust is never built on.
            shd0 = set(dust_s)
            gls0 = set(glass_s)
            # ponytail: top booster (fresh 15 for leg2). The shaft
            # arrives decayed (6 climbs + leg1 walk off a ~15 tap), so
            # leg2 would die the same way without it. Flat + diode
            # right after the top, facing travel; supports reuse
            # solid/plate or stamp glass (never a wire).
            bopt = None
            for fdx, fdz in ((dx, dz),) + tuple(
                    d for d in SHAFT_DIRS if d != (dx, dz)):
                flat = (top_c[0] + fdx, 1 + DY, top_c[2] + fdz)
                rep = (top_c[0] + 2 * fdx, 1 + DY, top_c[2] + 2 * fdz)
                front = (top_c[0] + 3 * fdx, 1 + DY, top_c[2] + 3 * fdz)
                # ponytail: leg2 must leave through the diode's front
                # (repeaters are directional: a sideways-departing leg2
                # reads nothing from it -- measured, booster ron=1 with
                # the leg dark behind it). front is validated now, leg2
                # starts there.
                okb = True
                bsup = []
                for cell in (flat, rep, front):
                    if cell in occ or cell in bset or cell in wires or cell in avoid:
                        okb = False
                        break
                    if not clear(cell):
                        okb = False
                        break
                if not okb:
                    continue
                for cell in (flat, rep):
                    s = (cell[0], cell[1] - 1, cell[2])
                    if s in wires or s in shd0:
                        okb = False
                        break
                    if s in solid or s in gls0:
                        continue
                    if (s[1] == PLATE_Y and mnx <= s[0] <= mxx
                            and mnz <= s[2] <= mxz):
                        continue
                    if s in occ:
                        okb = False  # unsupportable solid: next dir
                        break
                    bsup.append(s)
                if okb:
                    bopt = (flat, rep, front, TRAVEL_FACING[(fdx, fdz)],
                            bsup, (fdx, fdz))
                    break
            if bopt is None:
                continue
            flat_c, rep_c, front_c, rep_f, rep_sup, rep_dir = bopt
            if dbg:
                print(f"via {net}: bopt flat={flat_c} rep={rep_c} "
                      f"front={front_c} fdir={rep_dir}", flush=True)
            # ponytail: legs must not use shaft/booster cells. Shaft dust
            # is unwired air to the search (caller stamps it later): a
            # leg stepping onto shaft dust joins fine, but a leg ABOVE
            # shaft dust stacks dust-on-dust (measured: leg2 (32,6,14)
            # on shaft (32,5,14)). Reserve them out of the legs; the
            # joints bypass via allow. Supports below legs reuse shaft
            # glass (it will exist) but never shaft dust.
            shdust = set(dust_s)
            reserved = ((set(dust_s) | set(glass_s) | {flat_c, rep_c}
                         | set(rep_sup)) - {base_c, rep_c})
            occ_leg = occ | reserved
            leg1 = _bfs2d(occ_leg, comps, wires, net, _adj(tapcells, 1),
                          {base_c}, 1, box,
                          sup_ok=lambda c: (c[0], 0, c[2]) not in occ,
                          allow={base_c}, ban=bset | avoid, lamps=lampcells)
            if leg1 is None:
                continue
            nleg1 += 1
            leg2 = _bfs2d(occ_leg, comps, wires, net, {front_c},
                          goals6, 1 + DY, box,
                          sup_ok=lambda c: _sup2(c[0], c[1] - 1, c[2])
                          and (c[0], c[1] - 1, c[2]) not in shdust,
                          allow={front_c}, ban=bset | avoid, lamps=lampcells)
            if leg2 is None:
                continue
            dust = leg1 + dust_s[1:] + [flat_c] + leg2
            if dbg:
                print(f"via {net}: leg1={leg1[:3]}..{leg1[-1:]} "
                      f"shaft={dust_s[0]}..{dust_s[-1]} "
                      f"flat={flat_c} rep={rep_c}{rep_f} front={front_c} "
                      f"leg2={leg2[:3]}..{leg2[-2:]}", flush=True)
            if len(set(dust)) != len(dust):
                continue  # legs reuse a shaft cell: degenerate loop
            if set(leg2) & {flat_c, rep_c}:
                continue  # leg2 doubles back over the booster: hairpin
            # ponytail: periodic diodes (fresh 15 every <=7 flats). Dust
            # decays ~1/cell and the entry tap is ~15: an unboosted
            # 20-cell leg2 arrives dark (measured). Diodes replace dust
            # in place (same footprint, strictly less coupling surface;
            # supports already validated). Shaft cells never host (not
            # level), flat_c keeps its dedicated rep.
            reps = [(rep_c, rep_f)]
            counter = 14  # entry level at the tap-adjacent start
            ordered = list(dust)
            for i, cell in enumerate(ordered):
                counter -= 1
                # ponytail: never diode the booster front (it is fed at
                # 15 by the top booster by design; a walk diode there
                # faces onward and severs the handoff -- measured: whole
                # leg2 dark behind a ron=0 diode reading air).
                # ponytail: straight runs only. A diode AT a corner
                # faces one branch and reads the other (dark): it must
                # sit mid-straight with prev/cell/next collinear
                # (measured: corner diode reading dark side branch
                # while 15 waited around the corner).
                if cell in shdust or cell == flat_c or cell == front_c:
                    continue  # slope, booster-fed, or handoff: no diode
                if counter > 7 or i + 1 >= len(ordered) or i == 0:
                    continue
                prv, nxt = ordered[i - 1], ordered[i + 1]
                d = (nxt[0] - cell[0], nxt[2] - cell[2])
                e = (cell[0] - prv[0], cell[2] - prv[2])
                if nxt[1] != cell[1] or d not in TRAVEL_FACING:
                    continue  # non-flat step: diode can't sit here
                if d != e or prv[1] != cell[1]:
                    continue  # corner: signal turns here, diode can't
                reps.append((cell, TRAVEL_FACING[d]))
                counter = 15
            # ponytail: forced end diode (fresh 15 IN the feed cell).
            # B's leg was built for lever-15 at exactly this cell; the
            # periodic walk may leave the tail decayed. Second-to-last
            # dust facing the feed, flat by construction (leg2 level).
            have = {rc for rc, _rf in reps}
            if len(dust) >= 2:
                pen, last = dust[-2], dust[-1]
                d = (last[0] - pen[0], last[2] - pen[2])
                if (pen not in have and last[1] == pen[1]
                        and d in TRAVEL_FACING
                        and len(dust) >= 3
                        and (pen[0] - dust[-3][0],
                             pen[2] - dust[-3][2]) == d
                        and dust[-3][1] == pen[1]):
                    reps.append((pen, TRAVEL_FACING[d]))
                    print(f"via {net}: end diode at {pen} facing {last}",
                          flush=True)
            glass = [g for g in glass_s] + list(rep_sup)
            seeng = set(glass_s) | set(rep_sup)
            bad = False
            for c in leg1 + leg2:
                s = (c[0], c[1] - 1, c[2])
                if s in solid or s in seeng:
                    continue  # reusable support or shaft/booster glass
                if (s[1] == PLATE_Y and mnx <= s[0] <= mxx
                        and mnz <= s[2] <= mxz):
                    continue  # the plate lands here
                if s in occ or s in wires or s in shdust:
                    bad = True  # torch/lamp/wire below, or stacking:
                    break  # next shaft, don't ship floating dust
                glass.append(s)
                seeng.add(s)
            if bad:
                continue
            # legs/shaft are disjoint by the loop check above; every
            # support below a path cell is plate, reusable solid, or own
            # glass stamped here -- nothing lands on path dust.
            if len(set(glass)) != len(glass):
                continue
            if set(glass) & set(dust):
                continue
            if dbg:
                print(f"via {net}: shafts ok={nshaft} leg1 ok={nleg1}",
                      flush=True)
            return dust, glass, reps
    if dbg:
        print(f"via {net}: shafts ok={nshaft} leg1 ok={nleg1} leg2 always 0",
              flush=True)
    raise RuntimeError("via: no shaft+legs in box (try another corridor)")


def _adj(cells, y):
    """Free orthogonal neighbor cells of `cells` at level y (pre-filter;
    _bfs2d ok() applies the full gate)."""
    out = set()
    for (x, _y, z) in cells:
        for dx, dz in DIRS:
            out.add((x + dx, y, z + dz))
    out.update((x, y, z) for (x, _y, z) in cells if _y == y)
    return out


# ponytail: repeater bids face the DRIVER (output->input), i.e. opposite
# the travel direction (tiles.py place_or convention; sim negates back).
# A via climbing +x gets facing=west: it reads the shaft, drives onward.
TRAVEL_FACING = {(1, 0): "west", (-1, 0): "east",
                 (0, 1): "north", (0, -1): "south"}


def _tap_levels(blocks, io, recipe, net):
    """Driven levels of `net`'s cells, desc (driver region first).

    Dust decays ~1/cell, so a via tapping 10 cells from the driver
    starts at ~5 and dies mid-climb (measured: shaft top dark, y dark
    on every vector). Tapping the level-15 driver region plus a top
    booster keeps every hop inside budget. Loud if the net never
    drives (miswired boundary, not a routing problem).
    """
    ins = recipe["inputs"]
    act = None
    for k in range(2 ** len(ins)):
        vec = {ins[j]: (k >> j) & 1 for j in range(len(ins))}
        if eval_net(recipe, vec).get(net):
            act = vec
            break
    if act is None:
        raise RuntimeError(f"tap: net {net} never drives")
    P = _parse_build(blocks, io)
    _got, live, _tl, _tk, _ron, _con = _run_vec(
        act, _latch_hold_seed(blocks, io), P)
    lv = sorted(((live.get(c, 0), c)
                 for c, v in io["nets"].items() if v == net),
                key=lambda t: (-t[0], t[1]))
    if not lv or lv[0][0] < 13:
        raise RuntimeError(f"tap: net {net} peaks at "
                           f"{lv[0][0] if lv else None} (want >=13)")
    return lv


def stack_demo():
    """Compose two flat decks, stack, stitch, verify, export."""
    rA = parse_recipe(SUB_A)
    rB = parse_recipe(SUB_B)
    rF = parse_recipe(FULL)
    print("compose deck0 ...", flush=True)
    bA, sizeA, ioA, _stA = layout_retry(rA, verify=True)
    print(f"deck0 ok: {len(bA)} blocks", flush=True)
    print("compose deck1 ...", flush=True)
    bB, sizeB, ioB, _stB = layout_retry(rB, verify=True)
    print(f"deck1 ok: {len(bB)} blocks", flush=True)

    keepB = _strip_deck(bB, ioB)
    # ponytail: port alignment, not center alignment. Vias are decay
    # budgets (dust ~1/cell, 6 to climb): centering B over A spans the
    # field (measured 35-49 dust, dead on arrival). Landing each tile
    # input over its driver keeps every via inside budget. Drivers come
    # from the sim (level-15 region on an activating vector); B-side
    # anchors are the tile input diode backs (repeater input = cell +
    # facing vec, tiles.py convention), NOT lever-adjacent stubs: a
    # lever-adjacent island need not connect to the tile path at all
    # (measured: via landed at island (31,6,21)=8 while B's leg stayed
    # dark and y dark on every vector).
    tapA = {n: _tap_levels(bA, ioA, rA, n) for n in ("t", "c2")}
    # ponytail: feed points are B's removed lever cells (translated),
    # NOT diode backs. Backs proved ambiguous (lever-adjacent islands,
    # severed legs, multi-back tiles: three attempts, y dark every
    # time). Dust IN the ex-lever cell reproduces standalone exactly:
    # same leg topology, same shapes (lever absence never armed dust),
    # one cell per boundary input, known from io. The forced end diode
    # (route_via) re-15s it; B's leg downstream is untouched.
    feedB = {}
    for (x, z), nm in ioB["levers"].items():
        if nm in ("t", "c2"):
            feedB.setdefault(nm, []).append((x, 1, z))
    for n in ("t", "c2"):
        assert feedB.get(n), f"B has no lever for boundary {n}"
        feedB[n] = sorted(feedB[n])
    ddx, ddz = [], []
    for n in ("t", "c2"):
        (dl, (tx, _ty, tz)) = tapA[n][0]
        sx = sum(c[0] for c in feedB[n]) // len(feedB[n])
        sz = sum(c[2] for c in feedB[n]) // len(feedB[n])
        ddx.append(tx - sx)
        ddz.append(tz - sz)
        print(f"port {n}: driver tap {(tx, _ty, tz)}@{dl}", flush=True)
    dx = sum(ddx) // len(ddx)
    dz = sum(ddz) // len(ddz)
    tB = _translate(keepB, dx, DY, dz)
    feedT = {n: sorted((x + dx, y + DY, z + dz) for (x, y, z) in cells)
             for n, cells in feedB.items()}
    # ponytail: diode backs locate the tile side (input diodes read
    # boundary dust; their backs + fronts seed the tile flood below).
    # Input faces the driver (tiles.py convention): back = cell + vec.
    _FV = {"east": (1, 0), "west": (-1, 0),
           "south": (0, 1), "north": (0, -1)}
    anchorB = {}
    for (x, y, z, bid) in keepB:
        if base(bid) != "minecraft:repeater":
            continue
        f = bid.split("facing=")[1].split(",")[0] if "facing=" in bid \
            else "east"
        d = _FV[f]
        back = (x + d[0], y, z + d[1])
        n = ioB["nets"].get(back)
        if n in ("t", "c2"):
            anchorB.setdefault(n, []).append(back)
    for n in ("t", "c2"):
        anchorB[n] = sorted(set(anchorB.get(n, [])))
    dead = set()  # no strip: levers+pads only (see _strip_deck)
    # ponytail: strip lever-ONLY tails (keep tile-reachable + anchors).
    # Lever-side legs left whole are dark dead-ends the via must tell
    # apart from tile paths (two wasted iterations: islands, severs).
    # Rule: flood tile-side from diode fronts+backs, flood lever-side
    # from lever-adjacent cells (both through boundary wires, diodes
    # break continuity naturally); strip lever-only minus anchors.
    # Snake cells (both sides) are genuinely tile-connected: keep.
    _bset_all = {(x, y, z) for (x, y, z), v in ioB["nets"].items()
                 if v in ("t", "c2")}
    _levcells = {(x, 1, z) for (x, z) in ioB["levers"]}
    _anchset0 = {c for cells in anchorB.values() for c in cells}

    def _flood(seeds):
        seen, q = set(), list(seeds)
        while q:
            u = q.pop()
            if u in seen or u not in _bset_all:
                continue
            seen.add(u)
            for dx, dy, dz in NB6:
                m = (u[0] + dx, u[1] + dy, u[2] + dz)
                if m not in seen and m in _bset_all:
                    q.append(m)
        return seen

    _FV2 = {"east": (1, 0), "west": (-1, 0),
            "south": (0, 1), "north": (0, -1)}
    _fronts = set()
    for (x, y, z, bid) in keepB:
        if base(bid) != "minecraft:repeater":
            continue
        f = bid.split("facing=")[1].split(",")[0] if "facing=" in bid \
            else "east"
        d = _FV2[f]
        _fronts.add((x - d[0], y, z - d[1]))
    _tile = _flood(set(anchorB.get("t", [])) | set(anchorB.get("c2", []))
                   | {c for c in _fronts if c in _bset_all})
    _leveradj = {c for c in _bset_all
                 if any((c[0] + dx, c[1] + dy, c[2] + dz) in _levcells
                        for dx, dy, dz in NB6)}
    _leverreach = _flood(_leveradj)
    dead = set(_leverreach - _tile - _anchset0)
    print(f"strip: {len(dead)} lever-only boundary cells removed",
          flush=True)
    keepB = [b for b in keepB
             if (b[0], b[1], b[2]) not in dead
             or base(b[3]) != "minecraft:redstone_wire"]  # no strip: levers+pads only (see _strip_deck)

    # net-name collision is a wiring fault: shared names must be EXACTLY
    # the boundary vias (driven below, consumed above), nothing else.
    # ponytail: t/c2 live in both decks by design (that is the via); any
    # other shared name would short two signals into one.
    via_nets = ["t", "c2"]
    netsA = {n for n in ioA["nets"].values()}
    netsB = {n for n in ioB["nets"].values()}
    overlap = (netsA | set(ioA["levers"].values())) & netsB - set(via_nets)
    assert not overlap, f"net collision across decks: {sorted(overlap)}"

    wires0 = dict(ioA["nets"])
    for (x, y, z), n in ioB["nets"].items():
        if (x, y, z) in dead:
            continue  # stripped lever-side leg (anchors + tile-side stay)
        wires0[(x + dx, y + DY, z + dz)] = n
    base_blocks = list(bA) + tB
    if os.environ.get("STACKDBG"):
        _bb = {(x, y, z): bid for (x, y, z, bid) in base_blocks}
        for n in via_nets:
            for (fx, fy, fz) in feedT[n]:
                print(f"feed {n} at {(fx, fy, fz)} neighborhood:",
                      flush=True)
                for _x in range(fx - 3, fx + 4):
                    row = ""
                    for _z in range(fz - 3, fz + 4):
                        _b = _bb.get((_x, 6, _z))
                        if _b is None:
                            row += "."
                        else:
                            _bbase = base(_b)
                            row += {"minecraft:redstone_wire": "w",
                                    "minecraft:repeater": "r",
                                    "minecraft:cobblestone": "c",
                                    "minecraft:redstone_wall_torch": "t",
                                    "minecraft:glass": "g",
                                    "minecraft:lever": "L",
                                    "minecraft:redstone_lamp": "Y",
                                    "minecraft:comparator": "k"}.get(
                                        _bbase, "?")
                    print(f"  x={_x}: {row}", flush=True)
    lampcells0 = {(x, y, z) for (x, y, z, bid) in base_blocks
                  if base(bid) == "minecraft:redstone_lamp"}
    # ponytail: via step-ban (see _bfs2d ban): kept tile-side boundary
    # runs + anchors. Vias end adjacent and conduct in; stepping on
    # them risks a walk-direction diode severing the tile feed.
    bset0 = {(x + dx, y + DY, z + dz) for (x, y, z), v in ioB["nets"].items()
             if v in via_nets and (x, y, z) not in dead}
    # ponytail: B-deck legs are gone (stripped above), so no ban set:
    # translated B wire cells are tile outputs (foreign, refused),
    # re-added backs (own, joinable), or via cells. The plain
    # foreign-wire/comps gates suffice.
    solid0 = {(x, y, z) for (x, y, z, bid) in base_blocks
              if base(bid) in SUPPORT_OK}

    # ponytail: order retries. The first via's wall can landlock the
    # second net's landlocked sources (measured: c2's 41-dust wall left
    # t with 6 starts reaching 0 of 166 shafts). Longest-first is the
    # hier convention; shortest-first is the bounded fallback. State is
    # rebuilt per attempt so a failed order leaves no trace.
    spans = {}
    for n in via_nets:
        S = sorted(c for c, v in ioA["nets"].items() if v == n)
        T = feedT[n]
        assert S, f"no source cells for {n}"
        assert T, f"no target cells for {n}"
        spans[n] = max(abs(s[0] - t[0]) + abs(s[1] - t[1]) + abs(s[2] - t[2])
                       for s in S for t in T)
    orders = [sorted(via_nets, key=lambda n: -spans[n]),
              sorted(via_nets, key=lambda n: spans[n])]
    err = None
    _vias = []
    for attempt in orders:
        _vias = []
        blocks = list(base_blocks)
        wires = dict(wires0)
        occ = {(x, y, z) for (x, y, z, _b) in blocks}
        solid = set(solid0)
        comps = _comp_types(blocks)
        partid = "+".join(attempt)
        try:
            for n in attempt:
                S = sorted(c for c, v in ioA["nets"].items() if v == n)
                T = feedT[n]
                verr = None
                lvmap = {c: lv for lv, c in tapA[n]}
                # ponytail: keep this via out of the other feed's 3x3
                # column (see route_via avoid): adjacent feeds, first
                # halo starves second leg2 otherwise.
                avoid = set()
                for m, cells in feedT.items():
                    if m == n:
                        continue
                    for (fx, fy, fz) in cells:
                        for ax in (-1, 0, 1):
                            for az in (-1, 0, 1):
                                for ay in range(0, 11):
                                    avoid.add((fx + ax, ay, fz + az))
                for xb in CORRIDORS:
                    try:
                        ux0, ux1, uz0, uz1 = _bbox(
                            [(x, y, z) for (x, y, z, _b) in blocks])
                        dust, glass, reps = route_via(
                            occ, solid, comps, S, T, wires, n,
                            (ux0 - 2, ux1 + 2, uz0 - 2, uz1 + 2),
                            lvmap, bset0, lampcells0, avoid, xbias=xb)
                    except RuntimeError as e:
                        verr = e
                        continue
                    for (x, y, z) in glass:
                        blocks.append((x, y, z, GLASS))
                        occ.add((x, y, z))
                        solid.add((x, y, z))
                    for (x, y, z) in dust:
                        blocks.append((x, y, z, "minecraft:redstone_wire"))
                        wires[(x, y, z)] = n
                        occ.add((x, y, z))
                    for (rc, rf) in reps:
                        # ponytail: diode replaces dust (finish_assembly
                        # convention: repeater wins over dust, one cell
                        # one block). Pop any own-dust under it so io
                        # nets never claim a repeater cell as wire.
                        wires.pop(rc, None)
                        blocks.append(
                            (rc[0], rc[1], rc[2],
                             f"minecraft:repeater[facing={rf},delay=1]"))
                        occ.add(rc)
                    comps = _comp_types(blocks)
                    print(f"via {n}: {len(dust)} dust + {len(glass)} glass "
                          f"+ {len(reps)} rep", flush=True)
                    _vias.append((n, list(dust), list(reps)))
                    break
                else:
                    raise RuntimeError(f"via {n} failed all corridors: {verr}")
        except RuntimeError as e:
            err = f"order {partid}: {e}"
            print(f"order {partid} failed, retrying", flush=True)
            continue
        print(f"order {partid} green", flush=True)
        break
    else:
        raise RuntimeError(f"all via orders failed: {err}")

    # glass floor plate under deck1 (transparent: conducts nothing, cuts
    # nothing, floats legally). Skips via cells.
    ux0, ux1, uz0, uz1 = _bbox([(x, y, z) for (x, y, z, _b) in blocks])
    for x in range(ux0 - 2, ux1 + 3):
        for z in range(uz0 - 2, uz1 + 3):
            if (x, PLATE_Y, z) in occ:
                continue
            blocks.append((x, PLATE_Y, z, GLASS))
            occ.add((x, PLATE_Y, z))
            solid.add((x, PLATE_Y, z))

    # y=0 stone pads under ground comps (finish_assembly convention).
    # Via feet already carry glass (in have), so pads skip them.
    have = {(x, y, z) for (x, y, z, _b) in blocks}
    for (x, y, z, bid) in list(blocks):
        if y == 1 and (x, 0, z) not in have:
            blocks.append((x, 0, z, "minecraft:stone"))
            have.add((x, 0, z))

    # wire bids from connection shapes (layout's own renderer of record).
    dust = {c for c, v in wires.items()}
    rep_cells = {(x, y, z) for (x, y, z, bid) in blocks
                 if base(bid) == "minecraft:repeater"}
    cmp_cells = {(x, y, z) for (x, y, z, bid) in blocks
                 if base(bid) == "minecraft:comparator"}
    dust_shapes = (dust - rep_cells) - cmp_cells
    out = [b for b in blocks if base(b[3]) != "minecraft:redstone_wire"]
    for (x, y, z), n in sorted(wires.items()):
        if (x, y, z) in rep_cells or (x, y, z) in cmp_cells:
            continue  # tile diode keeps its own bid (finish convention)
        out.append((x, y, z, wire_bid((x, y, z), dust_shapes)))

    # ponytail: one cell one block, checked last on the finished list
    # (mirrors finish_assembly: duplicates + dust-on-dust both pop in
    # vanilla while the sim would read both).
    cell = {}
    for b in out:
        k = (b[0], b[1], b[2])
        if k in cell and cell[k] != base(b[3]):
            col = sorted([(b_[1], base(b_[3])) for b_ in out
                          if b_[0] == k[0] and b_[2] == k[2]])
            raise RuntimeError(
                f"duplicate block at {k}: {cell[k]} vs {b[3]} "
                f"(wire net here: {wires.get(k)}); column x,z: {col}")
        cell[k] = base(b[3])
    wirecells = {k for k, b in cell.items() if b == "minecraft:redstone_wire"}
    for k, b in sorted(cell.items()):
        if b in ("minecraft:redstone_wire", "minecraft:repeater",
                 "minecraft:comparator") and k[1] != 1:
            below = (k[0], k[1] - 1, k[2])
            if below in wirecells:
                raise RuntimeError(
                    f"component at {k} rests on wire at {below}: dust "
                    f"cannot support dust (upper net {wires.get(k)}, "
                    f"lower net {wires.get(below)})")

    lamps = {(x, z): n for (x, z), n in ioA["lamps"].items()}
    for (x, z), n in ioB["lamps"].items():
        lamps[(x + dx, 1 + DY, z + dz)] = n
    io = {"levers": dict(ioA["levers"]), "lamps": lamps, "nets": dict(wires)}

    # structural proof the decks overlap (stacking, not side-by-side).
    ax = {x for (x, _y, _z) in occ if _y <= 4}
    assert ax, "deck0 empty"
    up = {(x, z) for (x, y, z) in occ if y >= 1 + DY}
    shared = {(x, z) for (x, z) in up if x in ax}
    assert shared, "decks do not share footprint (not stacking)"
    glassn = sum(1 for b in out if base(b[3]) == GLASS)
    assert glassn > 0, "plate missing"

    print(f"stacked: {len(out)} blocks, {len(shared)} shared columns, "
          f"{glassn} glass", flush=True)
    try:
        sim_verify(rF, out, io)
    except RuntimeError:
        if os.environ.get("STACKDUMP"):
            import pickle as _pk
            _pk.dump({"blocks": out, "io": io,
                      "gates": rF["gates"], "inputs": rF["inputs"],
                      "outputs": rF["outputs"], "vias": _vias},
                     open("scratch/stackfail.pkl", "wb"))
            print("dumped scratch/stackfail.pkl", flush=True)
        raise
    W = max(x for (x, _y, _z) in occ) + 4
    D = max(z for (_x, _y, z) in occ) + 4
    export_mcfunction(out, "build_stack3d.mcfunction")
    export_schem(out, "build_stack3d.schem")
    export_html(out, (W, D), "build_stack3d.html", "stack3d 2-deck demo")
    print("stack3d ok: 8/8 vectors, outputs staged", flush=True)
    return out, io


if __name__ == "__main__":
    stack_demo()
