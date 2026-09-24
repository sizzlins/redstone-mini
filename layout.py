"""Layout: A* maze router plus block placer (torch tiles, compounds)."""

import heapq
import random

from core import DIRS
from recipe import expand_gates


def astar(starts, goal, net, W, D, solid, rings, wires, junctions, margin=None):
    """Maze route for one wire (multi-source: fanout taps nearest own wire).
    None if blocked (loud fail, never silent wrong)."""
    if isinstance(starts, tuple):
        starts = [starts]
    starts = list(dict.fromkeys(starts))
    if margin is None:
        x0, x1, z0, z1 = 0, W - 1, 0, D - 1
    else:
        x0 = max(0, min(min(s[0] for s in starts), goal[0]) - margin)
        x1 = min(W - 1, max(max(s[0] for s in starts), goal[0]) + margin)
        z0 = max(0, min(min(s[1] for s in starts), goal[1]) - margin)
        z1 = min(D - 1, max(max(s[1] for s in starts), goal[1]) + margin)
    def ok(cell):
        x, z = cell
        if not (x0 <= x <= x1 and z0 <= z <= z1):
            return False
        if cell == goal:
            return True
        if cell in junctions and net in junctions[cell]:
            return True
        if cell in solid:
            return False
        if cell in rings and net not in rings[cell]:
            return False
        if cell in wires and wires[cell] != net:
            return False
        return True
    def touches_foreign(cell, prev):
        for dx, dz in DIRS:
            m = (cell[0] + dx, cell[1] + dz)
            if m == prev or m in starts:
                continue
            if m == goal and m in junctions and net in junctions[m]:
                continue  # OR junction: wired-OR is the gate
            if m in wires and wires[m] != net and not (m in junctions and net in junctions[m]):
                return True
        return False
    open_h = [(abs(s[0] - goal[0]) + abs(s[1] - goal[1]), 0, s, None) for s in starts]
    heapq.heapify(open_h)
    came, cost = {s: None for s in starts}, {s: 0 for s in starts}
    while open_h:
        _, g, cell, prev = heapq.heappop(open_h)
        if cell == goal:
            path, c = [cell], cell
            while came[c] is not None:
                c = came[c]
                path.append(c)
            return path[::-1]
        for dx, dz in DIRS:
            m = (cell[0] + dx, cell[1] + dz)
            if not ok(m):
                continue
            if m == goal and m in junctions and net in junctions[m]:
                pass  # OR junction: wired-OR is the gate
            elif touches_foreign(m, cell):
                continue
            ng = g + 1
            if ng < cost.get(m, 1e9):
                cost[m], came[m] = ng, cell
                heapq.heappush(open_h, (ng + abs(m[0] - goal[0]) + abs(m[1] - goal[1]), ng, m, cell))
    return None



def layout(recipe, seed=None, grow=0):
    gates = expand_gates(recipe["gates"])
    banded = any(g.get("band") is not None for g in gates)
    if not banded:
        # ALAP: latest-first, each gate just before its earliest consumer,
        # so producer runs are short hops, not full-stack marathons.
        # Pop+insert keeps producers earlier and consumers later.
        for i in range(len(gates) - 1, -1, -1):
            outs = [j for j, h in enumerate(gates)
                    if j > i and gates[i]["out"] in h["args"]]
            if outs:
                gates.insert(min(outs) - 1, gates.pop(i))
    if banded:
        maxband = max(g.get("band", -1) for g in gates)
        W = 6 + (maxband + 1) * 24 + 10
        counts = {}
        for g in gates:
            b = g.get("band", -1)
            counts[b] = counts.get(b, 0) + 1
        D = 12 + max(counts.values()) * 14 + 12
    else:
        W = max(30, len(recipe["inputs"]) * 3 + 10)
        D = 12 + len(gates) * 14 + 12
    # ponytail: infinite room = grow on demand. Each grow doubles the field;
    # placement is deterministic so extra space only ever helps detours.
    W = min(int(W * (1.5 ** grow)), 2000)
    D = min(int(D * (1.5 ** grow)), 2000)
    cx = W // 2
    blocks = []  # (x, y, z, block-id [+state])
    solid, rings, wires, junctions, repeaters, paths = {}, {}, {}, {}, {}, []
    FLOOR = "minecraft:stone"

    def own(*nets):
        return set(nets)

    def ring(x, z, nets):
        rings.setdefault((x, z), set()).update(nets)

    def stamp_wire(path, net):
        for cell in path:
            if cell in solid:
                raise RuntimeError(f"wire {net} hits solid at {cell}")
            if cell in wires and wires[cell] != net:
                if cell in junctions and net in junctions[cell]:
                    continue  # OR junction: wired-OR is the gate
                raise RuntimeError(f"wire {net} bridges {wires[cell]} at {cell}")
            if cell in rings and net not in rings[cell]:
                if cell in junctions and net in junctions[cell]:
                    pass
                else:
                    raise RuntimeError(f"wire {net} hits guarded {cell}")
            wires.setdefault(cell, net)

    def route(a, b, net):
        # single source: every branch traces full-length to its driver.
        # (Tapping live-looking mid-wire cells caused decayed weak taps.)
        for margin in (12, 40, None):
            path = astar([a], b, net, W, D, solid, rings, wires, junctions, margin)
            if path:
                break
        if not path:
            raise RuntimeError(f"no route for {net}: {a} -> {b} (grid full, widen W)")
        stamp_wire(path, net)
        paths.append((path, net))
        return path

    # levers batch 1: inputs feeding an OR junction (its placement reads
    # their feed up front). Unbanded sit top-left; banded sit by their band
    # (short hops, no marathons). The junction taps their feed in place.
    # Others get levers by their load ports after placement (zero-wire taps).
    firstuse = {}
    for g in gates:
        for k, a in enumerate(g["args"]):
            if a not in firstuse:
                firstuse[a] = (g["op"], k, g.get("band"))
    orfeed = {a for g in gates if g["op"] == "OR" for a in g["args"]}
    pos = {}
    for idx, name in enumerate(recipe["inputs"]):
        if name not in firstuse:
            continue  # unused input: no lever
        op, role, band = firstuse[name]
        if op != "OR" and (banded or name not in orfeed):
            continue  # placed by load port later
        x = 16 * band + (2 if role == 0 else 5) if band is not None else 2 + idx * 3
        if (x, 6) in solid or (x, 6) in wires or (x + 1, 6) in solid or (x + 1, 6) in wires:
            raise RuntimeError(f"lever spot taken for {name} at {(x, 6)}")
        blocks.append((x, 1, 6, "minecraft:lever"))
        solid[(x, 6)] = ("lever", name)
        for dx, dz in DIRS:
            ring(x + dx, 6 + dz, own(name))
        wires[(x + 1, 6)] = name
        pos[name] = (x + 1, 6)
    if any(a in ("0", "1") for g in gates for a in g["args"]):
        wires[(0, 3)] = "0"
        pos["0"] = (0, 3)
        blocks.append((W - 1, 1, 3, "minecraft:redstone_block"))
        solid[(W - 1, 3)] = ("block", "1")
        for dx, dz in DIRS:
            ring(W - 1 + dx, 3 + dz, own("1"))
        wires[(W - 2, 3)] = "1"
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
        if b is None:
            gridpos.append((cx, 12 + i * 14))
        else:
            gz = bandrows.get(b, 12)
            bandrows[b] = gz + 14
            gridpos.append((6 + b * 24, gz))
    def footprint(op, ox, gz):
        if op == "AND":
            return {(x, z) for x in range(ox - 2, ox + 9) for z in range(gz - 1, gz + 8)}
        if op in ("NOT", "NOR"):
            return {(x, z) for x in range(ox - 3, ox + 4) for z in range(gz - 1, gz + 2)}
        return {(x, z) for x in range(ox - 3, ox + 4) for z in range(gz - 3, gz + 4)}

    reserved = [footprint(g["op"], *gridpos[i]) for i, g in enumerate(gates)]
    others_reserved = []
    for i in range(len(gates)):
        u = set()
        for j, box in enumerate(reserved):
            if j != i:
                u |= box
        others_reserved.append(u)

    def _snap():
        return (len(blocks), dict(wires), dict(solid),
                {k: set(v) for k, v in rings.items()},
                dict(pos), dict(junctions), len(recs), dict(firstport))

    def _restore(s):
        nb, w, so, ri, p, jn, nr, fp = s
        del blocks[nb:]
        wires.clear(); wires.update(w)
        solid.clear(); solid.update(so)
        rings.clear(); rings.update(ri)
        pos.clear(); pos.update(p)
        junctions.clear(); junctions.update(jn)
        del recs[nr:]
        for k in [k for k in firstport if k not in fp]:
            del firstport[k]
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
                raise RuntimeError(f"OR out of bounds for {o}")
            s = _snap()
            try:
                    j = (jx, jz)
                    if j in solid or j in wires:
                        raise RuntimeError(f"OR cell blocked at {j}")
                    reps = []
                    seen = {j}
                    for sig in a:
                        sx, sz = pos[sig]
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
                    wires[j] = o
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
            if dv is not None and dv not in junctions:
                cands.append((dv[0] + 3, dv[1]))
            cands.append((ox, gz))
            placed = False
            for ox2, gz2 in cands:
                if not (0 <= ox2 - 2 and ox2 + 6 < W and 0 <= gz2 and gz2 + 6 < D):
                    continue
                if abs(ox2 - ox) > 16 or abs(gz2 - gz) > 7:
                    continue
                if not footprint("AND", ox2, gz2).isdisjoint(others_reserved[i]):
                    continue
                s = _snap()
                try:
                    pa, pb, po = stamp_and(ox2, gz2, a[0], a[1], o)
                    pos[o] = po
                    for sig, port in ((a[0], pa), (a[1], pb)):
                        firstport.setdefault(sig, port)
                    recs.append((op, o, a, (pa, pb, po)))
                    placed = True
                    break
                except RuntimeError:
                    _restore(s)
            if not placed:
                raise RuntimeError(f"AND blocked for {o}")
            continue
        if op == "NOR":
            # torch NOR (wiki): inputs into block sides. West chained, north mazed.
            dv = pos.get(a[0])
            cands = []
            if dv is not None and dv not in junctions:
                cands.append((dv[0] + 3, dv[1]))
            cands.append((ox, gz))
            placed = False
            for bx, bz in cands:
                if not (0 <= bx - 2 and bx + 2 < W and 0 <= bz - 1 and bz + 1 < D):
                    continue
                if abs(bx - ox) > 16 or abs(bz - gz) > 7:
                    continue
                if not footprint("NOT", bx, bz).isdisjoint(others_reserved[i]):
                    continue
                s = _snap()
                try:
                    nets = own(o, *a)
                    stamp_cobble(bx, bz, o)
                    stamp_torch(bx + 1, bz, o)
                    for rx, rz in ((bx - 1, bz), (bx + 1, bz), (bx, bz - 1), (bx, bz + 1),
                                   (bx + 2, bz), (bx + 1, bz - 1), (bx + 1, bz + 1)):
                        ring(rx, rz, nets)
                    if (bx + 2, bz) in wires:
                        raise RuntimeError(f"out cell blocked at {(bx + 2, bz)}")
                    wires[(bx + 2, bz)] = o
                    pos[o] = (bx + 2, bz)
                    firstport.setdefault(a[0], (bx - 1, bz))
                    recs.append((op, o, a, (bx, bz)))
                    placed = True
                    break
                except RuntimeError:
                    _restore(s)
            if not placed:
                raise RuntimeError(f"NOR blocked for {o}")
            continue
        if op != "NOT":
            raise ValueError(f"bad primitive {op}")
        dv = pos.get(a[0])
        cands = []
        if dv is not None and dv not in junctions:
            cands.append((dv[0] + 3, dv[1]))
        cands.append((ox, gz))
        placed = False
        for bx, bz in cands:
            if not (0 <= bx - 2 and bx + 2 < W and 0 <= bz - 1 and bz + 1 < D):
                continue
            if abs(bx - ox) > 16 or abs(bz - gz) > 7:
                continue
            if not footprint("NOT", bx, bz).isdisjoint(others_reserved[i]):
                continue
            s = _snap()
            try:
                nets = own(o, *a)
                stamp_cobble(bx, bz, o)
                stamp_torch(bx + 1, bz, o)
                for rx, rz in ((bx - 1, bz), (bx + 1, bz), (bx, bz - 1), (bx, bz + 1),
                               (bx + 2, bz), (bx + 1, bz - 1), (bx + 1, bz + 1)):
                    ring(rx, rz, nets)
                if (bx + 2, bz) in wires:
                    raise RuntimeError(f"out cell blocked at {(bx + 2, bz)}")
                wires[(bx + 2, bz)] = o
                pos[o] = (bx + 2, bz)
                firstport.setdefault(a[0], (bx - 1, bz))
                recs.append((op, o, a, (bx, bz)))
                placed = True
                break
            except RuntimeError:
                _restore(s)
        if not placed:
            raise RuntimeError(f"NOT blocked for {o}")

    for idx, name in enumerate(recipe["inputs"]):
        if name not in firstport or name in pos:
            continue  # unused, or OR-first (already placed)
        px, pz = firstport[name]
        lx, fx = px - 2, px - 1
        if (lx, pz) in solid or (lx, pz) in wires or (fx, pz) in solid or (fx, pz) in wires:
            raise RuntimeError(f"lever spot taken for {name} at {(lx, pz)}")
        blocks.append((lx, 1, pz, "minecraft:lever"))
        solid[(lx, pz)] = ("lever", name)
        for dx, dz in DIRS:
            ring(lx + dx, pz + dz, own(name))
        stamp_wire([(fx, pz)], name)  # touches port stub: zero-wire tap
        pos[name] = (fx, pz)

    for name in recipe["outputs"]:
        ox_, oz = pos[name]
        done = False
        for dx, dz in ((1, 0), (0, 1), (-1, 0), (0, -1)):
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

    # phase 2: route every net through the finished field, shortest hops first
    # so long runs maze around settled locals instead of fencing them in.
    tasks = []
    for op, o, a, cell in recs:
        if op == "OR":
            j, reps = cell
            tasks += [(pos[sig], b, sig) for sig, (r, b) in zip(a, reps)]
        elif op == "AND":
            pa, pb, po = cell
            tasks += [(pos[a[0]], pa, a[0]), (pos[a[1]], pb, a[1])]
        elif op == "NOT":
            bx, bz = cell
            tasks.append((pos[a[0]], (bx - 1, bz), a[0]))
        elif op == "NOR":
            bx, bz = cell
            tasks += [(pos[a[0]], (bx - 1, bz), a[0]), (pos[a[1]], (bx, bz - 1), a[1])]
        elif op == "OUT":
            tasks.append((pos[a[0]], cell, a[0]))
    tasks.sort(key=lambda t: -(abs(t[0][0] - t[1][0]) + abs(t[0][1] - t[1][1])))
    if seed is not None:
        random.Random(seed).shuffle(tasks)
    placed = set(wires)  # feeds/outs/ties stay; routed paths may be ripped up
    pending = tasks[:]
    fails = {}
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
            A = (t[0] + dx, t[1] + dz)
            for c in [A] + [(A[0] + ex, A[1] + ez) for ex, ez in DIRS]:
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
                paths.remove((p, m))
        pending = [(s, t, net)] + block_tasks + pending

    # repeaters: dust dies after 15 blocks. Backward cover from each goal:
    # every path cell ends within 14 of a booster-or-source behind it.
    def is_straight(path, i):
        if i <= 0 or i >= len(path) - 1:
            return False
        (x0, z0), (x1, z1), (x2, z2) = path[i - 1], path[i], path[i + 1]
        return (x0 == x1 == x2) or (z0 == z1 == z2)

    def place_rep(path, net, j):
        (x0, z0), (x1, z1) = path[j - 1], path[j]
        dx, dz = x1 - x0, z1 - z0
        facing = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}[(dx, dz)]
        for f in ((x1 + dx, z1 + dz), (x1 - dx, z1 - dz)):
            w = wires.get(f)
            if w is not None and w != net:
                raise RuntimeError(f"repeater guard {net} vs {w} at {f}")
        if wires.get((x1, z1)) != net:
            raise RuntimeError(
                f"repeater spot {net} at {(x1, z1)} holds {wires.get((x1, z1), 'EMPTY')} "
                f"(solid {solid.get((x1, z1), '-')})")
        del wires[(x1, z1)]
        repeaters[(x1, z1)] = (net, facing)

    for path, net in paths:
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

    # checker: no two nets may share/side-touch dust, except at OR junctions.
    for (x, z), net in wires.items():
        for dx, dz in DIRS:
            m = (x + dx, z + dz)
            if m in wires and wires[m] != net:
                ok = (m in junctions and net in junctions[m] and wires[m] in junctions[m])
                ok = ok or ((x, z) in junctions and wires[m] in junctions[(x, z)])
                if not ok:
                    raise RuntimeError(f"SHORT: {net} touches {wires[m]} at {(x, z)}->{m}")
    # checker 2 (opens): every wire must trace to a driver (lever feed, tie,
    # or torch-adjacent dust). Same-net steps, junctions merge, repeaters pass.
    # A routed-looking but unconnected net fails loudly instead of building dead.
    seed_states = []
    for name, p in pos.items():
        if p in wires and wires[p] == name:
            seed_states.append((p, name))
    for (x, z), net in wires.items():
        for dx, dz in DIRS:
            if solid.get((x + dx, z + dz), (None,))[0] == "torch":
                seed_states.append(((x, z), net))
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
            m = (c[0] + dx, c[1] + dz)
            if m in wires:
                nm = wires[m]
                if nm == n or (c in junctions and nm in junctions[c]) or \
                   (m in junctions and n in junctions[m]):
                    stack.append((m, nm if nm == n or m not in junctions else n))
            elif m in repeaters and repeaters[m][0] == n:
                stack.append((m, n))
    dead = [(x, z) for (x, z) in wires if (x, z) not in reached]
    if dead:
        raise RuntimeError(f"OPEN (unconnected dust, nothing drives it): {dead[:6]}")
    # ponytail: shrink-wrap grid to content (+3 margin). A 13x4 gate on a
    # 30x38 pad photographs as sprawl even when every wire is minimal.
    OCC = [c for c in list(solid) + list(wires)]
    minx = min(c[0] for c in OCC) - 3
    minz = min(c[1] for c in OCC) - 3
    maxx = max(c[0] for c in OCC) + 3
    maxz = max(c[1] for c in OCC) + 3
    blocks = [(x - minx, y, z - minz, b) for x, y, z, b in blocks]
    solid = {(x - minx, z - minz): v for (x, z), v in solid.items()}
    wires = {(x - minx, z - minz): v for (x, z), v in wires.items()}
    rings = {(x - minx, z - minz): v for (x, z), v in rings.items()}
    junctions = {(x - minx, z - minz): v for (x, z), v in junctions.items()}
    pos = {n: (x - minx, z - minz) for n, (x, z) in pos.items()}
    repeaters = {(x - minx, z - minz): v for (x, z), v in repeaters.items()}
    W, D = maxx - minx + 1, maxz - minz + 1
    out = list(blocks)
    for (x, z), net in wires.items():
        out.append((x, 1, z, "minecraft:redstone_wire"))
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

