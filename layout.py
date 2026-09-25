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

    # bus: one lever per input at its lane head (planned after tiles).
    # Batch-1/load-port levers and the feeds set are gone with the maze.
    pos = {}
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
    firstport = {}  # input -> port cell of its first AND/NOT load
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
                dict(pos), dict(junctions), len(recs), dict(firstport),
                set(bridges))

    def _restore(s):
        nb, w, so, ri, p, jn, nr, fp, br = s
        del blocks[nb:]
        wires.clear(); wires.update(w)
        solid.clear(); solid.update(so)
        rings.clear(); rings.update(ri)
        pos.clear(); pos.update(p)
        junctions.clear(); junctions.update(jn)
        del recs[nr:]
        for k in [k for k in firstport if k not in fp]:
            del firstport[k]
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
                        for sig, port in ((a[0], pa), (a[1], pb)):
                            firstport.setdefault(sig, port)
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
        if op == "NOR":
            # torch NOR (wiki): inputs into block sides. West chained, north mazed.
            dv = pos.get(a[0])
            cands = []
            if dv is not None and dv not in junctions and not g.get("rep"):
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
                        firstport.setdefault(a[0], (bx - 1, bz))
                        recs.append((op, o, a, (bx, bz)))
                        placed = True
                        break
                    except RuntimeError:
                        _restore(s)
                    if placed:
                        break
            if not placed:
                raise RuntimeError(f"NOR blocked for {o}")
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
                    firstport.setdefault(a[0], pa)
                    firstport.setdefault(a[1], pb)
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
                    firstport.setdefault(a[0], pa)
                    firstport.setdefault(a[1], pb)
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
                    firstport.setdefault(a[0], (bx - 1, bz))
                    recs.append((op, o, a, (bx, bz)))
                    placed = True
                    break
                except RuntimeError:
                    _restore(s)
            if placed:
                break
        if not placed:
            raise RuntimeError(f"NOT blocked for {o}")

    # bus: net spec from tile ports (same mapping the maze tasks used),
    # one trunk/star per net, one lever per input at its chain head.
    # (XOR tile-stamped side levers stay: tile geometry, and same-net
    # duplicates are wired-OR harmless.)
    netspec = {}
    outband = {}
    for g in gates:
        outband.setdefault(g["out"], g.get("band"))
    def _load(net, cell, band):
        if net == "0":
            return  # dark stubs read 0; nothing is stamped
        e = netspec.setdefault(net, {'drv': None, 'loads': [], 'db': None, 'lbs': []})
        e['loads'].append(cell)
        e['lbs'].append(band)
    for op, o, a, cell in recs:
        ob = outband.get(o)
        if op == "AND":
            pa, pb, po = cell
            netspec.setdefault(o, {'drv': po, 'loads': [], 'db': ob, 'lbs': []})
            _load(a[0], pa, ob); _load(a[1], pb, ob)
        elif op == "NOT":
            bx, bz = cell
            netspec.setdefault(o, {'drv': (bx + 2, bz), 'loads': [], 'db': ob, 'lbs': []})
            _load(a[0], (bx - 1, bz), ob)
        elif op in ("LATCH", "XOR"):
            pa, pb, po = cell
            netspec.setdefault(o, {'drv': po, 'loads': [], 'db': ob, 'lbs': []})
            _load(a[0], pa, ob); _load(a[1], pb, ob)
        elif op == "OR":
            j, reps = cell
            netspec.setdefault(o, {'drv': j, 'loads': [], 'db': ob, 'lbs': []})
            for sig, (rr, bb) in zip(a, reps):
                _load(sig, bb, ob)
        elif op == "OUT":
            pass  # lamp sits at the trunk end; no stub
        else:
            raise RuntimeError(f"bus: unsupported {op}")
    for name in recipe["inputs"]:
        netspec.setdefault(name, {'drv': None, 'loads': []})
    if "1" in netspec:
        netspec["1"]['drv'] = pos["1"]
    for net in [n for n, s in netspec.items()
                if not s['loads'] and n not in recipe["outputs"]]:
        del netspec[net]
    busplan = None
    try:
        busplan = plan_bus(netspec, solid, wires, rings, W, D, seed)
    finally:
        # ponytail: permanent debug tap (debug.py reads it). Costs one env
        # check per layout; replaces every ad-hoc Temp probe.
        if _os.environ.get("REDSTONE_DEBUG"):
            from debug import dump_state
            dump_state(_os.environ["REDSTONE_DEBUG"], gates, netspec, busplan,
                       solid, wires, rings, W, D)
    for name in recipe["inputs"]:
        spec = netspec.get(name)
        if not spec:
            continue  # unused input: no lever
        for (lx, lz) in spec['loads']:
            stamp_wire([(lx, lz)], name)  # port dust (tile input); lever touch powers it
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

    # phase 2: bus stamp. Lamps stay after it so their collision check
    # dodges trunks automatically.
    for name in recipe["outputs"]:
        p = busplan[name]  # KeyError if output is undriven: loud, as before
        pos[name] = (p['trunks'][0][0], p['trunks'][0][3]) if p['trunks'] else p['hub']
    for net, p in busplan.items():
        for (T, z0, z1, feed, stations) in p['trunks']:
            rep_at = set(stations)
            for z in range(z0, z1 + 1):
                if z in rep_at:
                    if (T, z) in solid or (T, 1, z) in wires:
                        raise RuntimeError(f"bus station blocked for {net} at {(T, z)}")
                    facing = "south" if z > feed else "north"
                    blocks.append((T, 1, z, f"minecraft:repeater[facing={facing},delay=1]"))
                    solid[(T, z)] = ("repeater", net)
                else:
                    stamp_wire([(T, z)], net)
        for jog in p['jogs']:
            stamp_wire([(x, z) for x, z in dict.fromkeys(jog)], net)
        for path in p['stubs']:
            stamp_wire([(x, z) for x, z in dict.fromkeys(path)], net)

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
                stack.append((m, n))  # bus stations + OR diodes stamp solid-only
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
    bus = {n: {'trunks': [(T - minx, z0 - minz, z1 - minz, feed - minz,
                            [s - minz for s in stations])
                           for (T, z0, z1, feed, stations) in p['trunks']],
               'taps': [(x - minx, z - minz) for x, z in p['taps']],
               'jogs': [[(x - minx, z - minz) for x, z in j] for j in p['jogs']],
               'hub': ((p['hub'][0] - minx, p['hub'][1] - minz)
                       if p['hub'] is not None else None),
               'lever': ((p['lever'][0] - minx, p['lever'][1] - minz)
                         if p['lever'] is not None else None)}
           for n, p in busplan.items()}
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
          "nets": dict(wires),
          "bus": bus}
    return sorted(out), (W, D), io


def plan_bus(netspec, solid, wires, rings, W, D, seed=None):
    """Bus trunk geometry (pure: same (netspec, seed) → same plan).
    Greedy trunk choice deadlocks on ordering (whoever claims a
    corridor walls the rest), so seeded calls search: several
    shuffles of net order × trunk-x order, first complete plan wins.
    Unseeded call does one deterministic pass (driverless nets first).
    '0' nets never appear here (dark stubs read 0 — caller drops
    them). Loud RuntimeError when nothing fits (grow backstop)."""
    tries = 1 if seed is None else 25
    last = None
    for t in range(tries):
        try:
            return _plan_once(netspec, solid, wires, rings, W, D,
                              None if seed is None else f"{seed}/{t}")
        except RuntimeError as e:
            last = e
    raise last


def _plan_once(netspec, solid, wires, rings, W, D, seed=None):
    """One greedy pass (see plan_bus). Post-relay every hop spans <=1 band
    gap: single-band nets star direct from a hub cell; a net reaching one
    further band serves it from one N-S trunk in the gap west of that band
    (nets reaching two further bands break the relay contract — loud).
    Trunk geometry is new; the v1 core is verbatim: legality incl. SHORT
    adjacency and pitch-2 taken, both-L stubs with decay caps, taps only at
    full-strength cells, seeded order search."""
    plan = {}  # no taken: lever halos stamp with their levers; wires see ghost
    ghost, gsolid = dict(wires), dict(solid)  # planned nets' wires/solids: mutual visibility
    if seed is None:
        order = list(netspec)
    else:
        order = list(netspec)
        random.Random(seed).shuffle(order)
    for net in order:
        spec = netspec[net]
        drv, loads, db, lbs = spec['drv'], spec['loads'], spec.get('db'), spec.get('lbs', [])
        blocked = set()  # own lever + committed station cells (future solids)
        def _bad(x, z):
            if (x, z) in blocked:
                return True
            if (x, z) in gsolid:
                return True
            if (x, 1, z) in ghost and ghost[(x, 1, z)] != net:
                return True
            if (x, z) in rings and net not in rings[(x, z)]:
                return True
            if any((x + dx, 1, z + dz) in ghost and ghost[(x + dx, 1, z + dz)] != net
                   for dx, dz in DIRS):
                return True
            return False
        def _shapes(fx, fz, tx, tz, cap=14):
            vfirst = [(fx, z) for z in range(min(fz, tz), max(fz, tz) + 1)] + \
                     [(x, tz) for x in range(min(fx, tx), max(fx, tx) + 1)]
            hfirst = [(x, fz) for x in range(min(fx, tx), max(fx, tx) + 1)] + \
                     [(tx, z) for z in range(min(fz, tz), max(fz, tz) + 1)]
            return [s for s in (vfirst, hfirst)
                    if len(dict.fromkeys(s)) - 1 <= cap
                    and all(0 <= x < W and 0 <= z < D for x, z in s)
                    and not any(_bad(x, z) for x, z in s)]
        def _star(hubcell, cells):
            """Direct stubs hub->each cell; None if any misses decay."""
            paths = []
            for cell in cells:
                if cell == hubcell:
                    continue
                shapes = _shapes(hubcell[0], hubcell[1], cell[0], cell[1])
                if not shapes:
                    return None
                paths.append(shapes[0])
            return paths
        def _via_trunk(cands, hubcell, gleloads, tag):
            """One N-S trunk serving gleloads; None if no x fits."""
            # ponytail: toward the hub→loads interval first (a trunk parked
            # mid-corridor walls the jogs behind it); nearest-hub walled nD.
            lox = min([hubcell[0]] + [x for x, _ in gleloads])
            hix = max([hubcell[0]] + [x for x, _ in gleloads])
            c0 = sorted(cands, key=lambda x: (0 if lox <= x <= hix else
                                              min(abs(x - lox), abs(x - hix)), x))
            first, rest = c0[:1], c0[1:]
            if seed is not None:
                random.Random(f"{seed}:{net}:{tag}").shuffle(rest)
            why = []
            why0 = None
            for T in first + rest:
                # ponytail: feed rows near the hub row first (a hub facing one
                # way jogs out sideways, travels, and re-enters — _rl3's fix).
                feeds = [hubcell[1]] + [hubcell[1] + d for k in range(1, 6)
                                         for d in (2 * k, -2 * k)
                                         if 0 <= hubcell[1] + d < D]
                for feed in feeds:
                    jogs = _shapes(hubcell[0], hubcell[1], T, feed)
                    if not jogs:
                        why.append(f"no jog")
                        why0 = why0 or f"T={T}/f={feed}: no jog"
                        continue
                    jog = jogs[0]
                    jog_len = len(dict.fromkeys(jog)) - 1
                    rows = sorted(z for _, z in gleloads)
                    z0req, z1req = min(feed, rows[0]), max(feed, rows[-1])
                    # ponytail: first station 14 signal-travel from the driver
                    # (jog eats part of the budget), then every 14 — v1's rule,
                    # both directions since loads sit north and south of feed.
                    d0 = 14 - jog_len if jog_len < 14 else 14
                    stations = sorted(s for k in range(0, 99)
                                      for s in (feed + d0 + 14 * k, feed - d0 - 14 * k)
                                      if z0req - 28 <= s <= z1req + 28)
                    if any(_bad(x, z) for x, z in
                           [(T, z) for z in range(z0req, z1req + 1) if z not in stations]):
                        why.append("cells blocked")
                        why0 = why0 or f"T={T}/f={feed}: cells blocked"
                        continue
                    if any(_bad(T, s) for s in stations):
                        why.append("station blocked")
                        why0 = why0 or f"T={T}/f={feed}: station blocked"
                        continue
                    blocked.update(added := [(T, s) for s in stations])  # taps dodge them
                    taps, lstubs = [], []
                    for lx, lz in gleloads:
                        tcands = sorted([(feed, 14 - jog_len)] +
                                        [(s + (1 if s > feed else -1), 14) for s in stations],
                                        key=lambda c: (abs(c[0] - lz), c[0]))
                        for tz, budget in tcands:
                            if budget < 0:
                                continue
                            shapes = _shapes(T, tz, lx, lz, cap=budget)
                            if shapes:
                                break
                        else:
                            break
                        taps.append((T, tz))
                        lstubs.append(shapes[0])
                    if len(taps) != len(gleloads):
                        blocked.difference_update(added)
                        why.append("taps fail")
                        why0 = why0 or f"T={T}/f={feed}: taps fail"
                        continue  # a load found no tap: try next trunk x
                    needed = sorted({s for s in stations for (_, tz) in taps
                                     if min(feed, tz) <= s <= max(feed, tz)})
                    z0 = min([z0req] + needed)
                    z1 = max([z1req] + needed)
                    stations = needed
                    if any(_bad(x, z) for x, z in
                           [(T, z) for z in range(z0, z1 + 1) if z not in stations]):
                        blocked.difference_update(added)
                        why.append("ext blocked")
                        why0 = why0 or f"T={T}/f={feed}: ext blocked"
                        continue  # extension hit something: try next trunk x
                    return (T, z0, z1, feed, stations, taps, jog, lstubs)
            counts = {s: why.count(s) for s in dict.fromkeys(why)}
            raise RuntimeError(f"bus: no trunk for {net} {tag} hub={hubcell} loads={gleloads}: "
                               + ", ".join(f"{s}x{n}" for s, n in counts.items())
                               + f" (e.g. {why0})")
        def _commit(trunklist, taplist, joglist, stublist, hubcell, levercell):
            # own stations stamp solid after planning: no stub/jog may cross
            # one (order search retries other seeds on collision).
            own = {(T, s) for (T, z0, z1, feed, stations) in trunklist for s in stations}
            for path in stublist + joglist:
                if any((x, z) in own for x, z in dict.fromkeys(path)):
                    raise RuntimeError(f"bus: own station collision for {net}")
            for (T, z0, z1, feed, stations) in trunklist:
                for z in range(z0, z1 + 1):
                    if z in stations:
                        gsolid[(T, z)] = ("repeater", net)
                    else:
                        ghost.setdefault((T, 1, z), net)
            for path in stublist + joglist:
                for (x, z) in dict.fromkeys(path):
                    ghost.setdefault((x, 1, z), net)
            plan[net] = {'trunks': trunklist, 'taps': taplist, 'jogs': joglist,
                         'stubs': stublist, 'hub': hubcell, 'lever': levercell}
        groups = {}
        for cell, lb in zip(loads, lbs):
            groups.setdefault(lb, []).append(cell)
        trunks, taps, jogs, stubs = [], [], [], []
        if drv is None:
            # inputs fan out via one lever per load at stamp time: nothing
            # to route (multi-band loads are fine — each gets its own lever).
            plan[net] = {'trunks': [], 'taps': [], 'jogs': [], 'stubs': [],
                         'hub': None, 'lever': None}
            continue
        cross = sorted(lb for lb in groups if lb != db)
        if len(cross) > 1:
            raise RuntimeError(f"bus: net {net} spans {cross} (relay contract broken)")
        hub = drv
        paths = _star(hub, groups.get(db, []))
        if paths is None:
            # same-band hop past decay (stacked tiles sit a full pitch
            # apart): serve it from a local trunk like a gap hop.
            T, z0, z1, feed, stations, ftaps, jog, lstubs = _via_trunk(
                [x for x in range(hub[0] - 10, hub[0] + 11)
                 if 0 <= x < W], hub, groups[db], "loc")
            trunks.append((T, z0, z1, feed, stations))
            taps.extend(ftaps)
            jogs.append(jog)
            stubs = [[hub]] + lstubs
        else:
            stubs = [[hub]] + paths
        if cross:
            lb = cross[0]
            if lb is None or lb <= 0:
                raise RuntimeError(f"bus: no gap west of band {lb} for {net}")
            lo, hi = 6 + 24 * (lb - 1) + 9, 6 + 24 * lb - 3
            T, z0, z1, feed, stations, ftaps, jog, lstubs = _via_trunk(
                range(lo, hi + 1), hub, groups[lb], f"g{lb}")
            trunks.append((T, z0, z1, feed, stations))
            taps.extend(ftaps)
            jogs.append(jog)
            stubs.extend(lstubs)
        _commit(trunks, taps, jogs, stubs, hub, None)
    return plan


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

