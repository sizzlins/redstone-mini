"""Layout: A* maze router plus block placer (torch tiles, compounds)."""

import heapq
import os as _os
import random

from core import DIRS, TORCH_BACK
from recipe import expand_gates


def astar(starts, goal, net, W, D, solid, rings, wires, junctions, margin=None, blocked=None, congest=None, guard=None):
    """Maze route for one wire (multi-source: fanout taps nearest own wire).
    None if blocked (loud fail, never silent wrong). Cells are (x, y, z);
    rings/junctions/solid stay 2D (rings guard whole columns)."""
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
    def ok(cell):
        x, y, z = cell
        if not (x0 <= x <= x1 and z0 <= z <= z1):
            return False
        if cell == goal:
            return True
        if y == 1 and (x, z) in junctions and net in junctions[(x, z)]:
            return True
        if y == 1 and (x, z) in solid:
            return False
        if (x, z) in rings and net not in rings[(x, z)]:
            return False
        if cell in wires and wires[cell] != net:
            return False
        return True
    def touches_foreign(cell, prev):
        for dx, dz in DIRS:
            m = (cell[0] + dx, cell[1], cell[2] + dz)
            if m == prev or m in starts:
                continue
            if m == goal and (m[0], m[2]) in junctions and net in junctions[(m[0], m[2])]:
                continue  # OR junction: wired-OR is the gate
            if m in wires and wires[m] != net and not ((m[0], m[2]) in junctions and net in junctions[(m[0], m[2])]):
                return True
        return False
    open_h = [(abs(s[0] - goal[0]) + abs(s[2] - goal[2]), 0, (s[0], s[2]), s, None) for s in starts]
    heapq.heapify(open_h)
    came, cost = {s: None for s in starts}, {s: 0 for s in starts}
    while open_h:
        _, g, _, cell, prev = heapq.heappop(open_h)
        if cell == goal:
            path, c = [cell], cell
            while came[c] is not None:
                c = came[c]
                path.append(c)
            return path[::-1]
        for dx, dz in DIRS:
            m = (cell[0] + dx, 1, cell[2] + dz)
            if not ok(m):
                continue
            if m == goal and (m[0], m[2]) in junctions and net in junctions[(m[0], m[2])]:
                pass  # OR junction: wired-OR is the gate
            elif touches_foreign(m, cell):
                if blocked is not None:
                    # sealed-pocket ripup: record the exact wire cells whose
                    # touch rejects this step (a closed loop far from the goal
                    # seals just as dead as a wall on the goal itself).
                    for dx2, dz2 in DIRS:
                        k = (m[0] + dx2, 1, m[2] + dz2)
                        if k != cell and k in wires and wires[k] != net:
                            blocked.add(k)
                continue
            ng = g + 1
            if congest:
                # ponytail: negotiated congestion (lite). Ripped corridors
                # stay expensive, so retries explore new lanes instead of
                # cycling the same blame pair. Zero when nothing failed.
                ng += congest.get(m, 0)
            if guard and m != goal:
                # ponytail: no hugging solids mid-run. A wire beside a
                # torch block powers it (wrong values); beside a lit torch
                # it gets back-powered into a ring oscillator. Ports live
                # within 2 of goal/start, so only drive-bys are refused.
                if max(abs(m[0] - goal[0]), abs(m[2] - goal[2])) > 2 and all(
                        max(abs(m[0] - s[0]), abs(m[2] - s[2])) > 2
                        for s in starts):
                    if any((m[0] + dx, m[2] + dz) in guard
                           for dx, dz in DIRS):
                        continue
            if ng < cost.get(m, 1e9):
                cost[m], came[m] = ng, cell
                heapq.heappush(open_h, (ng + abs(m[0] - goal[0]) + abs(m[2] - goal[2]), ng, (m[0], m[2]), m, cell))
    return None



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
    solid, rings, wires, junctions, repeaters, paths = {}, {}, {}, {}, {}, []
    bridges = set()  # (x, z) columns holding y=2 support cobble (Task 2 stamps)
    FLOOR = "minecraft:stone"

    def own(*nets):
        return set(nets)

    def ring(x, z, nets):
        rings.setdefault((x, z), set()).update(nets)

    def stamp_wire(path, net):
        for cell in path:
            if len(cell) == 2:
                cell = (cell[0], 1, cell[1])  # placement stubs are y=1
            flat = (cell[0], cell[2])
            if cell[1] == 1 and flat in solid:
                raise RuntimeError(f"wire {net} hits solid at {cell}")
            if cell in wires and wires[cell] != net:
                if cell[1] == 1 and flat in junctions and net in junctions[flat]:
                    continue  # OR junction: wired-OR is the gate
                raise RuntimeError(f"wire {net} bridges {wires[cell]} at {cell}")
            if flat in rings and net not in rings[flat]:
                if cell[1] == 1 and flat in junctions and net in junctions[flat]:
                    pass
                else:
                    raise RuntimeError(f"wire {net} hits guarded {cell}")
            wires.setdefault(cell, net)

    def route(a, b, net):
        # single source: every branch traces full-length to its driver.
        # (Tapping live-looking mid-wire cells caused decayed weak taps;
        #  connected-tap + shortest-first retries in 2026-09 also broke xor.)
        seen = set()
        best = None
        for margin in (12, 40, None):
            path = astar([(a[0], 1, a[1])], (b[0], 1, b[1]), net, W, D, solid, rings, wires, junctions, margin, blocked=seen, congest=congest, guard=guard)
            if path and (best is None or len(path) < len(best)):
                best = path
        path = best
        if not path:
            last_blocked[net] = seen
            raise RuntimeError(f"no route for {net}: {a} -> {b} (grid full, widen W)")
        stamp_wire(path, net)
        paths.append((path, net))
        return path

    # maze: inputs fan out via one lever per load below (zero-wire taps),
    # except OR-feeding inputs: the junction aims at a batch-1 lever, so
    # those keep a pre-placement lever (master pattern, verbatim).
    pos = {}
    feeds = set()  # lever-feed wire cells: loads touching one need no route
    firstuse, firstor = {}, {}
    for g in gates:
        for k, a in enumerate(g["args"]):
            if a not in firstuse:
                firstuse[a] = (g["op"], k, g.get("band"))
            if g["op"] == "OR" and a not in firstor:
                firstor[a] = (g["op"], k, g.get("band"))
    orfeed = {a for g in gates if g["op"] == "OR" for a in g["args"]}
    for idx, name in enumerate(recipe["inputs"]):
        if name not in firstuse:
            continue  # unused input: no lever
        op, role, band = firstor.get(name, firstuse[name])
        if op != "OR" and (banded or name not in orfeed):
            continue  # placed by load port later
        x = 16 * band + (2 if role == 0 else 5) if band is not None else 2 + idx * 3
        if (x, 6) in solid or (x, 6) in wires or (x + 1, 6) in solid or (x + 1, 1, 6) in wires:
            raise RuntimeError(f"lever spot taken for {name} at {(x, 6)}")
        blocks.append((x, 1, 6, "minecraft:lever"))
        solid[(x, 6)] = ("lever", name)
        for dx, dz in DIRS:
            ring(x + dx, 6 + dz, own(name))
        stamp_wire([(x + 1, 6)], name)
        feeds.add((x + 1, 1, 6))
        pos[name] = (x + 1, 6)
    if any(a in ("0", "1") for g in gates for a in g["args"]):
        stamp_wire([(0, 3)], "0")
        pos["0"] = (0, 3)
        blocks.append((W - 1, 1, 3, "minecraft:redstone_block"))
        solid[(W - 1, 3)] = ("block", "1")
        for dx, dz in DIRS:
            ring(W - 1 + dx, 3 + dz, own("1"))
        stamp_wire([(W - 2, 3)], "1")
        pos["1"] = (W - 2, 3)

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
        stamp_wire([(ox + 2, gz), (ox + 2, gz + 1)], na)
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
        # other grid slot, and actually empty (lever feeds now dot the
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
                dict(pos), dict(junctions), len(recs),
                set(bridges))

    def _restore(s):
        nb, w, so, ri, p, jn, nr, br = s
        del blocks[nb:]
        wires.clear(); wires.update(w)
        solid.clear(); solid.update(so)
        rings.clear(); rings.update(ri)
        pos.clear(); pos.update(p)
        junctions.clear(); junctions.update(jn)
        del recs[nr:]
        bridges.clear(); bridges.update(br)
    def _free(cells):
        return all(c not in solid and c not in wires for c in cells)

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
                    if j in solid or j in wires:
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
                                if r in solid or r in wires or b in solid or b in wires \
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
            # levers (dust side-feeds don't count as comparator input).
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
                         (ox - 1, gz + 4), (ox - 2, gz + 5)]
                s = _snap()
                try:
                    blocks.append((ox, 1, gz, "minecraft:comparator[facing=east,mode=subtract]"))
                    solid[(ox, gz)] = ("comp", o)
                    blocks.append((ox, 1, gz + 4, "minecraft:comparator[facing=east,mode=subtract]"))
                    solid[(ox, gz + 4)] = ("comp", o)
                    for cells, net in ((Adust, a[0]), (Bdust, a[1]), (Odust, o)):
                        stamp_wire(cells, net)
                    for lx, lz, ln in ((ox, gz + 3, a[0]), (ox, gz + 1, a[1])):
                        blocks.append((lx, 1, lz, "minecraft:lever"))
                        solid[(lx, lz)] = ("lever", ln)
                        for dx, dz in DIRS:
                            ring(lx + dx, lz + dz, own(ln))
                    for cx_, cz_ in set([(ox, gz), (ox, gz + 4)] + Adust + Bdust + Odust):
                        for dx, dz in DIRS:
                            ring(cx_ + dx, cz_ + dz, fam)
                    pa, pb, po = (ox + 3, gz), (ox + 3, gz + 4), (ox - 2, gz + 5)
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
    orbbs = set()  # OR diode-backs: input-fed ones read the batch-1 lever, never a tap
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
            _load(a[0], (bx - 1, bz))
        elif op in ("LATCH", "XOR"):
            pa, pb, po = cell
            netspec.setdefault(o, {'drv': po, 'loads': []})
            _load(a[0], pa); _load(a[1], pb)
        elif op == "OR":
            j, reps = cell
            netspec.setdefault(o, {'drv': j, 'loads': []})
            for sig, (rr, bb) in zip(a, reps):
                orbbs.add(bb)
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
    for name in recipe["inputs"]:
        spec = netspec.get(name)
        if not spec:
            continue  # unused input: no lever
        for (lx, lz) in spec['loads']:
            if (lx, lz) in orbbs:
                continue  # OR diode-back: batch-1 lever feeds it via the junction
            stamp_wire([(lx, lz)], name)  # port dust (tile input); lever touch powers it
            feeds.add((lx, 1, lz))
            for (px, pz) in ((lx - 1, lz), (lx + 1, lz), (lx, lz - 1), (lx, lz + 1)):
                if not (0 <= px < W and 0 <= pz < D):
                    continue
                if (px, pz) in solid or (px, 1, pz) in wires:
                    continue
                break
            else:
                raise RuntimeError(f"bus lever blocked for {name} at {(lx, lz)}")
            blocks.append((px, 1, pz, "minecraft:lever"))
            solid[(px, pz)] = ("lever", name)
            for dx, dz in DIRS:
                ring(px + dx, pz + dz, own(name))
        # (same-net duplicate levers are wired-OR, harmless — XOR precedent)
    # ponytail: input loads already touch their own lever feed need no
    # route; without this every fanout load spans the field (master filter).
    ins = set(recipe["inputs"])
    tasks = []
    for net, spec in netspec.items():
        if net == "0":
            continue  # dark stubs read 0
        drv = spec['drv'] if spec['drv'] is not None else pos.get(net)
        for cell in spec['loads']:
            if net in ins and ((cell[0], 1, cell[1]) in feeds or any(
                    ((cell[0] + dx, 1, cell[1] + dz) in feeds and
                     wires.get((cell[0] + dx, 1, cell[1] + dz)) == net)
                    for dx, dz in DIRS)):
                continue
            tasks.append((drv, cell, net))
    tasks.sort(key=lambda t: -(abs(t[0][0] - t[1][0]) + abs(t[0][1] - t[1][1])))
    if seed is not None:
        random.Random(seed).shuffle(tasks)
    placed = set(wires)  # feeds/outs/ties stay; routed paths may be ripped up
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
    fails = {}
    try:
        while pending:
            s, t, net = pending.pop(0)
            try:
                route(s, t, net)
                continue
            except RuntimeError:
                pass
            # targeted ripup: nets physically sealing this goal get re-routed after us.
            blockers = set()
            for dx, dz in DIRS:
                for yy in (1, 2):
                    A = (t[0] + dx, yy, t[1] + dz)
                    for c in [A] + [(A[0] + ex, A[1], A[2] + ez) for ex, ez in DIRS]:
                        w = wires.get(c)
                        if w is not None and w != net and c not in placed:
                            blockers.add(w)
            for c in last_blocked.get(net, ()):
                w = wires.get(c)
                if w is not None and w != net and c not in placed:
                    blockers.add(w)
            block_tasks = [tk for tk in tasks if tk[2] in blockers]
            key = (net, tuple(sorted(blockers)))
            fails[key] = fails.get(key, 0) + 1
            if not block_tasks or fails[key] > 2:
                raise RuntimeError(f"no route for {net}: {s} -> {t} (grid full, widen W)")
            for p, m in paths[:]:
                if m in blockers:
                    for c in p:
                        if wires.get(c) == m and c not in placed:
                            del wires[c]
                            congest[c] = congest.get(c, 0) + 5
                    paths.remove((p, m))
            pending = [(s, t, net)] + block_tasks + pending
    finally:
        # ponytail: permanent debug tap (debug.py reads it). Costs one env
        # check per layout; replaces every ad-hoc Temp probe.
        if _os.environ.get("REDSTONE_DEBUG"):
            from debug import dump_state
            dump_state(_os.environ["REDSTONE_DEBUG"], gates, netspec, None,
                       solid, wires, rings, W, D)
    for name in recipe["outputs"]:
        pos[name]  # KeyError if output is undriven: loud, as before

    # phase 2: maze stamp is done above (route stamps inline); lamps stay
    # after routing so their collision check dodges wires automatically.

    # repeaters: dust dies after 15 blocks. Backward cover from each goal:
    # every path cell ends within 14 of a booster-or-source behind it.
    def is_straight(path, i):
        if i <= 0 or i >= len(path) - 1:
            return False
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = path[i - 1], path[i], path[i + 1]
        if not (y0 == y1 == y2 == 1):
            return False
        return (x0 == x1 == x2) or (z0 == z1 == z2)

    def place_rep(path, net, j):
        (x0, _, z0), (x1, _, z1) = path[j - 1], path[j]
        dx, dz = x1 - x0, z1 - z0
        facing = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}[(dx, dz)]
        for f in ((x1 + dx, 1, z1 + dz), (x1 - dx, 1, z1 - dz)):
            w = wires.get(f)
            if w is not None and w != net:
                raise RuntimeError(f"repeater guard {net} vs {w} at {f}")
        if wires.get((x1, 1, z1)) != net:
            if (x1, z1) in repeaters and repeaters[(x1, z1)][0] == net:
                return  # shared fanout trunk: a sibling branch already boosted here
            raise RuntimeError(
                f"repeater spot {net} at {(x1, 1, z1)} holds {wires.get((x1, 1, z1), 'EMPTY')} "
                f"(solid {solid.get((x1, z1), '-')})")
        del wires[(x1, 1, z1)]
        repeaters[(x1, z1)] = (net, facing)

    for path, net in paths:
        # cover the tile-stub tail past the goal too: same-net dust stamped
        # in phase 1 (ports, latch rows) decays exactly like routed wire, and
        # a latch S-row needs level 9 at the port to reach its block, while
        # the endpoint alone is only guaranteed level 1. Bounded walk so a
        # shared trunk never drags in a far sibling branch.
        cells = list(path)
        seen = set(cells)
        g = cells[-1]
        stack = [g]
        while stack:
            c = stack.pop()
            for dx, dz in DIRS:
                m = (c[0] + dx, 1, c[2] + dz)
                if m in seen or wires.get(m) != net:
                    continue
                if abs(m[0] - g[0]) + abs(m[2] - g[2]) > 12:
                    continue
                seen.add(m)
                cells.append(m)
                stack.append(m)
        path = cells
        n = len(path)
        i = n - 1
        while i > 14:
            cands = [j for j in range(max(1, i - 14), min(i - 1, n - 1) + 1)
                     if is_straight(path, j)]
            if not cands:
                raise RuntimeError(f"unboostable gap on {net} near index {i} (twisty path)")
            j = min(cands)
            place_rep(path, net, j)
            i = j

    for name in recipe["outputs"]:
        ox_, oz = pos[name]
        done = False
        for dx, dz in ((1, 0), (0, 1), (0, -1), (-1, 0)):
            fx, lx = (ox_ + dx, oz + dz), (ox_ + dx * 2, oz + dz * 2)
            if not (0 <= lx[0] < W and 0 <= lx[1] < D):
                continue
            if lx in solid or lx in wires or fx in solid or fx in wires:
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
    for (x, y, z), net in wires.items():
        for dx, dz in DIRS:
            m = (x + dx, y, z + dz)
            if m in wires and wires[m] != net:
                ok = ((m[0], m[2]) in junctions and net in junctions[(m[0], m[2])] and wires[m] in junctions[(m[0], m[2])])
                ok = ok or ((x, z) in junctions and wires[m] in junctions[(x, z)])
                if not ok:
                    raise RuntimeError(f"SHORT: {net} touches {wires[m]} at {(x, y, z)}->{m}")
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
        # several disconnected feeds; pos[] only knows the first).
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
            elif (m[0], m[2]) in repeaters and repeaters[(m[0], m[2])][0] == n:
                stack.append((m, n))
            elif solid.get((m[0], m[2]), (None,))[0] == "repeater" and solid[(m[0], m[2])][1] == n:
                stack.append((m, n))  # boosters + OR diodes stamp solid-only
    dead = [(x, y, z) for (x, y, z) in wires if (x, y, z) not in reached
            and wires[(x, y, z)] != "0"]  # undriven "0" stubs read 0 unconnected
    if dead:
        raise RuntimeError(f"OPEN (unconnected dust, nothing drives it): {dead[:6]}")
    # ponytail: shrink-wrap grid to content (+3 margin). A 13x4 gate on a
    # 30x38 pad photographs as sprawl even when every wire is minimal.
    OCC = [(x, 1, z) for (x, z) in solid] + list(wires) + [(x, 1, z) for (x, z) in bridges]
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
    repeaters = {(x - minx, z - minz): v for (x, z), v in repeaters.items()}
    bridges = {(x - minx, z - minz) for (x, z) in bridges}
    W, D = maxx - minx + 1, maxz - minz + 1
    out = list(blocks)
    for x, z in sorted(bridges):
        out.append((x, 1, z, "minecraft:cobblestone"))
    for (x, y, z), net in wires.items():
        out.append((x, y, z, "minecraft:redstone_wire"))
    for (x, z), (net, facing) in repeaters.items():
        out.append((x, 1, z, f"minecraft:repeater[facing={facing},delay=1]"))
    # ponytail: stone only where a component sits on it (flat worlds have
    # ground already); a full pad was 98% of the file.
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
    print("or-lever ok: OR inputs on batch levers, verify green")

