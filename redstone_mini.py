"""Mini redstone recipe compiler: tiny DSL -> working redstone + 3D preview + Minecraft commands.
Recipe example:
    IN a, b, c
    OUT y
    t = a AND b
    y = t OR c
Gates are wiki-textbook torch designs (minecraft.wiki Logic circuits):
NOT/NOR = dust into block + torch, AND = inverted inputs into NOR, OR = joined wires.
Outputs: build.html (3D preview) + build.mcfunction (datapack /function or chat paste).
# ponytail: torch delay + signal length fixed by auto-repeaters; gamerule maxCommandChainLength bump for 8-bit functions.
"""
import heapq
import json
import random
import sys

OPS = ("AND", "OR", "XOR", "NOT")

def parse_recipe(text):
    inputs, outputs, gates = [], [], []
    for raw in text.strip().splitlines():
        line = raw.split("#")[0].strip()
        if not line:
            continue
        up = line.upper()
        if up.startswith("IN "):
            inputs = [s.strip() for s in line[3:].split(",") if s.strip()]
        elif up.startswith("OUT "):
            outputs = [s.strip() for s in line[4:].split(",") if s.strip()]
        else:
            out, _, expr = line.partition("=")
            out = out.strip()
            parts = expr.strip().split()
            if len(parts) == 3 and parts[1].upper() in ("AND", "OR", "XOR"):
                gates.append({"out": out, "op": parts[1].upper(), "args": [parts[0], parts[2]]})
            elif len(parts) == 2 and parts[0].upper() == "NOT":
                gates.append({"out": out, "op": "NOT", "args": [parts[1]]})
            else:
                raise ValueError(f"can't parse: {raw!r} (use: t = a AND b)")
    if not inputs or not gates:
        raise ValueError("need at least IN ... and one gate line")
    return {"inputs": inputs, "outputs": outputs, "gates": gates}

def eval_net(recipe, values):
    def val(x):
        if x == "0":
            return False
        if x == "1":
            return True
        return bool(sig[x])
    sig = dict(values)
    for g in recipe["gates"]:
        a = [val(x) for x in g["args"]]
        if g["op"] == "AND":
            sig[g["out"]] = a[0] and a[1]
        elif g["op"] == "OR":
            sig[g["out"]] = a[0] or a[1]
        elif g["op"] == "XOR":
            sig[g["out"]] = a[0] != a[1]
        elif g["op"] == "NOT":
            sig[g["out"]] = not a[0]
    return sig

def expand_gates(gates):
    """XOR->OR,AND,NOT,AND. AND stays a compound, OR a junction, NOT a tile."""
    gates = [dict(g, args=list(g["args"])) for g in gates]
    c = [0]
    def T(p):
        c[0] += 1
        return f"_{p}{c[0]}"
    changed = True
    while changed:
        changed = False
        nxt = []
        for g in gates:
            op, o, a = g["op"], g["out"], g["args"]
            if op == "XOR":
                t1, t2, t3 = T("xo"), T("xa"), T("xn")
                bd = g.get("band")
                nxt += [{"out": t1, "op": "OR", "args": [a[0], a[1]], "band": bd},
                        {"out": t2, "op": "AND", "args": [a[0], a[1]], "band": bd},
                        {"out": t3, "op": "NOT", "args": [t2], "band": bd},
                        {"out": o, "op": "AND", "args": [t1, t3], "band": bd}]
                changed = True
            else:
                nxt.append(g)
        gates = nxt
    return gates

DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))

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

def layout(recipe, seed=None):
    gates = expand_gates(recipe["gates"])
    banded = any(g.get("band") is not None for g in gates)
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

    # levers batch 1: inputs whose first load is an OR junction. Unbanded sit
    # top-left; banded sit by their band (short hops, no marathons). The
    # junction taps their feed in place. Others get levers by their load
    # ports after placement (zero-wire taps, no maze).
    firstuse = {}
    for g in gates:
        for k, a in enumerate(g["args"]):
            if a not in firstuse:
                firstuse[a] = (g["op"], k, g.get("band"))
    pos = {}
    for idx, name in enumerate(recipe["inputs"]):
        if name not in firstuse:
            continue  # unused input: no lever
        op, role, band = firstuse[name]
        if op != "OR":
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
    bandnext = {}
    firstport = {}  # input -> port cell of its first AND/NOT load
    for i, g in enumerate(gates):
        b = g.get("band")
        if b is None:
            gz, ox = 12 + i * 14, cx
        else:
            gz = bandnext.get(b, 12)
            bandnext[b] = gz + 14
            ox = 6 + b * 24
        op, o, a = g["op"], g["out"], g["args"]
        if op == "OR":
            # repeater-isolated OR (wiki): diodes sit on their drivers' side,
            # facing the junction, so entries stay short instead of marathoning.
            j = (ox, gz)
            if j in solid or j in wires:
                raise RuntimeError(f"OR cell blocked at {j}")
            reps = []
            seen = {j}
            for sig in a:
                sx, sz = pos[sig]
                if abs(sx - ox) >= abs(sz - gz):
                    order = [(1 if sx >= ox else -1, 0)]
                else:
                    order = [(0, 1 if sz >= gz else -1)]
                order += [(1, 0), (-1, 0), (0, 1), (0, -1)]
                done = False
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
                        done = True
                        break
                    if done:
                        break
                if not done:
                    raise RuntimeError(f"OR cell blocked around {j} for {sig}")
            wires[j] = o
            junctions[j] = {o}
            pos[o] = j
            recs.append((op, o, a, (j, reps)))
            continue
        if op == "AND":
            pa, pb, po = stamp_and(ox, gz, a[0], a[1], o)
            pos[o] = po
            for sig, port in ((a[0], pa), (a[1], pb)):
                firstport.setdefault(sig, port)
            recs.append((op, o, a, (pa, pb, po)))
            continue
        if op != "NOT":
            raise ValueError(f"bad primitive {op}")
        nets = own(o, *a)
        bx, bz = ox, gz
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
        fx, lx = ox_ + 1, ox_ + 2
        if (lx, oz) in solid or (lx, oz) in wires or (fx, oz) in solid or (fx, oz) in wires:
            raise RuntimeError(f"lamp spot taken for {name} at {(lx, oz)}")
        stamp_wire([(fx, oz)], name)  # touches out stub: zero-wire tap
        blocks.append((lx, 1, oz, "minecraft:redstone_lamp"))
        solid[(lx, oz)] = ("lamp", name)
        for dx, dz in DIRS:
            ring(lx + dx, oz + dz, own(name))
        recs.append(("OUT", name, [name], (fx, oz)))

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
    out = list(blocks)
    for (x, z), net in wires.items():
        out.append((x, 1, z, "minecraft:redstone_wire"))
    for (x, z), (net, facing) in repeaters.items():
        out.append((x, 1, z, f"minecraft:repeater[facing={facing},delay=1]"))
    for x in range(W):
        for z in range(D):
            out.append((x, 0, z, "minecraft:stone"))
    io = {"levers": {c: n for c, (k, n) in solid.items() if k == "lever"},
          "lamps": {c: n for c, (k, n) in solid.items() if k == "lamp"},
          "nets": dict(wires)}
    return sorted(out), (W, D), io

COLORS = {"minecraft:stone": 0x8a8a8a, "minecraft:redstone_wire": 0xe02020,
          "minecraft:cobblestone": 0x7a7a7a, "minecraft:redstone_wall_torch": 0xd83a00,
          "minecraft:lever": 0x7a5a2e, "minecraft:redstone_lamp": 0xffa726,
          "minecraft:redstone_block": 0xb01010, "minecraft:repeater": 0xc7a17a}
# ponytail: textures stream from the upstream asset pack at runtime, no PNGs in this repo.
TEXBASE = "https://raw.githubusercontent.com/PrismarineJS/minecraft-assets/master/data/1.21.8/blocks/"
TEXMAP = {"minecraft:stone": "stone.png", "minecraft:cobblestone": "cobblestone.png",
          "minecraft:redstone_lamp": "redstone_lamp_on.png",
          "minecraft:redstone_block": "redstone_block.png", "minecraft:repeater": "repeater.png"}

def layout_retry(recipe, tries=12, verify=False):
    """Randomized-restart maze routing: reshuffle net order until the field fits.
    With verify, keep going until the placed build also passes redstone sim
    (generate-and-test: the sim is the selector, not just the guard)."""
    last = None
    for t in range(tries):
        try:
            out = layout(recipe, seed=None if t == 0 else t)
        except RuntimeError as e:
            last = e
            continue
        if not verify:
            return out
        try:
            sim_verify(recipe, out[0], out[2], quiet=True)
            return out
        except RuntimeError as e:
            e.blocks, e.size, e.io = out
            last = e
    raise last

def base(bid):
    return bid.split("[")[0]

def build_stamp(label, nblocks):
    import datetime
    import subprocess
    try:
        rev = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                      cwd="D:\\redstone-mini",
                                      stderr=subprocess.DEVNULL,
                                      timeout=10).decode().strip()
    except Exception:
        rev = "nogit"
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"{label} @ {rev} {ts} ({nblocks} blocks)"

def export_mcfunction(blocks, path, oy=64):
    order = {"minecraft:cobblestone": 0, "minecraft:stone": 0, "minecraft:redstone_block": 1,
             "minecraft:lever": 2, "minecraft:redstone_lamp": 2}
    def key(b):
        return (order.get(base(b[3]), 3), b[1], b[0], b[2])
    with open(path, "w") as f:
        f.write("# datapack /function or chat paste. Includes stone floor so dust/torches are supported.\n")
        f.write("# big builds: raise gamerule maxCommandChainLength (e.g. 200000) first.\n")
        for x, y, z, bid in sorted(blocks, key=key):
            f.write(f"setblock {x} {oy + y} {z} {bid}\n")

def export_html(blocks, size, path, label="build"):
    W, D = size
    # ponytail: floor renders as one plane, not W*D cubes. Keeps big previews fast.
    data = [{"p": [x, y, z], "c": COLORS.get(base(b), 0xffffff), "b": base(b),
             "t": TEXBASE + TEXMAP.get(base(b), "stone.png")}
            for x, y, z, b in blocks if not (b == "minecraft:stone" and y == 0)]
    html = """<!doctype html><html><head><meta charset=utf-8><title>redstone build</title>
<style>body{margin:0;font-family:sans-serif}#t{position:fixed;top:8px;left:8px;background:#111;color:#fff;padding:8px 12px;border-radius:8px}</style>
<script type="importmap">{"imports":{"three":"https://unpkg.com/three@0.160.0/build/three.module.js","three/addons/":"https://unpkg.com/three@0.160.0/examples/jsm/"}}</script>
</head><body><div id=t>STAMP — drag to orbit, scroll to zoom. Real torch gates.</div>
<script type="module">import * as T from 'three';import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
const B=DATA;const s=new T.Scene();s.background=new T.Color(0x1a2028);
const SZ=MAXD;const cam=new T.PerspectiveCamera(50,innerWidth/innerHeight,.1,5000);cam.position.set(SZ*.7,SZ*.7,SZ*.9);
const r=new T.WebGLRenderer({antialias:true});r.setSize(innerWidth,innerHeight);document.body.appendChild(r.domElement);
const c=new OrbitControls(cam,r.domElement);c.target.set(CX,0,CZ);
s.add(new T.AmbientLight(0xffffff,.9));const d=new T.DirectionalLight(0xffffff,.8);d.position.set(10,20,10);s.add(d);
const loader=new T.TextureLoader();loader.setCrossOrigin('anonymous');
const matCache={};
function texMat(b){const k='t'+b.b;if(matCache[k])return matCache[k];
 const tex=loader.load(b.t,(t)=>{t.magFilter=T.NearestFilter;t.colorSpace=T.SRGBColorSpace;});
 tex.magFilter=T.NearestFilter;tex.colorSpace=T.SRGBColorSpace;
 const m=new T.MeshLambertMaterial({color:0xffffff,map:tex});matCache[k]=m;return m;}
function flatMat(b){const k='f'+b.c;if(matCache[k])return matCache[k];
 const m=new T.MeshLambertMaterial({color:b.c});matCache[k]=m;return m;}
const stoneTex=loader.load(TEXSTONE,(t)=>{t.wrapS=t.wrapT=T.RepeatWrapping;t.repeat.set(FW,FD);t.magFilter=T.NearestFilter;t.colorSpace=T.SRGBColorSpace;});
stoneTex.wrapS=stoneTex.wrapT=T.RepeatWrapping;stoneTex.repeat.set(FW,FD);
const floor=new T.Mesh(new T.PlaneGeometry(FW,FD),new T.MeshLambertMaterial({map:stoneTex}));
floor.rotation.x=-Math.PI/2;floor.position.set(FW/2-0.5,-0.5,FD/2-0.5);s.add(floor);
const cubeG=new T.BoxGeometry(.92,.92,.92);
const flatG=new T.BoxGeometry(.92,.18,.92);
const smallG=new T.BoxGeometry(.45,.7,.45);
const groups={};
for(const b of B){const k=b.b;((groups[k] ??= []).push(b));}
const dummy=new T.Object3D();
for(const k in groups){const arr=groups[k];const b0=arr[0];
 let geo, mat;
 if(k==='minecraft:redstone_wire'){geo=flatG;mat=flatMat(b0);}
 else if(k==='minecraft:lever'||k==='minecraft:redstone_wall_torch'){geo=smallG;mat=flatMat(b0);}
 else if(k==='minecraft:repeater'){geo=flatG;mat=flatMat(b0);}
 else{geo=cubeG;mat=texMat(b0);}
 const im=new T.InstancedMesh(geo,mat,arr.length);
 arr.forEach((b,idx)=>{let y=b.p[1];
  if(k==='minecraft:redstone_wire')y-=0.37;
  if(k==='minecraft:lever'||k==='minecraft:redstone_wall_torch')y-=0.1;
  if(k==='minecraft:repeater')y-=0.3;
  dummy.position.set(b.p[0],y,b.p[2]);dummy.updateMatrix();im.setMatrixAt(idx,dummy.matrix);});
 s.add(im);}
(function a(){requestAnimationFrame(a);c.update();r.render(s,cam);})();</script></body></html>"""
    html = (html.replace("DATA", json.dumps(data)).replace("CX", str(W / 2)).replace("CZ", str(D / 2))
            .replace("TEXSTONE", json.dumps(TEXBASE + "stone.png"))
            .replace("STAMP", build_stamp(label, len(blocks)))
            .replace("MAXD", str(max(W, D))).replace("FW", str(W)).replace("FD", str(D)))
    open(path, "w").write(html)

DEMO = """IN a, b, c
OUT y
t = a AND b
y = t OR c
"""

def build_adder8():
    """8-bit ripple-carry adder. Bit i lives in band i (datapath columns)."""
    ins = [f"A{i}" for i in range(8)] + [f"B{i}" for i in range(8)]
    gates = []
    for i in range(8):
        a, b, cin, cout = f"A{i}", f"B{i}", f"C{i}", f"C{i+1}"
        if i == 0:
            cin = "0"
        gates += [{"out": f"X{i}", "op": "XOR", "args": [a, b], "band": i},
                  {"out": f"S{i}", "op": "XOR", "args": [f"X{i}", cin], "band": i},
                  {"out": f"T{i}", "op": "AND", "args": [a, b], "band": i},
                  {"out": f"U{i}", "op": "AND", "args": [f"X{i}", cin], "band": i},
                  {"out": cout, "op": "OR", "args": [f"T{i}", f"U{i}"], "band": i}]
    return {"inputs": ins, "outputs": [f"S{i}" for i in range(8)] + ["C8"], "gates": gates}

def sim_verify(recipe, blocks, io, seed=7, quiet=False):
    """Independent redstone simulation of the PLACED build (ignores layout nets).
    Plays input vectors through torch/dust physics to a fixed point, compares
    lamps against eval_net. Catches opens/shorts the static guards can't see.
    # ponytail: flat single-level physics only (all our builds are); delay unmodeled.
    """
    import random as _r
    from collections import deque
    dust, torch, lampat, rep, rblk, cob = set(), {}, set(), {}, set(), set()
    for x, y, z, bid in blocks:
        if y != 1:
            continue
        b, c = base(bid), (x, z)
        if b == "minecraft:redstone_wire":
            dust.add(c)
        elif b == "minecraft:redstone_wall_torch":
            face = bid.split("facing=")[1].rstrip("]") if "facing=" in bid else "east"
            back = {"east": (-1, 0), "west": (1, 0), "south": (0, -1), "north": (0, 1)}[face]
            torch[c] = (c[0] + back[0], c[1] + back[1])
        elif b == "minecraft:redstone_lamp":
            lampat.add(c)
        elif b == "minecraft:repeater":
            face = bid.split("facing=")[1].split(",")[0] if "facing=" in bid else "east"
            rep[c] = {"east": (1, 0), "west": (-1, 0), "south": (0, 1), "north": (0, -1)}[face]
        elif b == "minecraft:redstone_block":
            rblk.add(c)
        elif b == "minecraft:cobblestone":
            cob.add(c)
    lever = dict(io["levers"])
    lampnet = dict(io["lamps"])
    attach_rev = {}
    for t, a in torch.items():
        attach_rev.setdefault(a, []).append(t)

    def run(vec):
        # signal levels 0-15 (dust loses 1 per block). Levels drain phantom
        # latches that boolean models can't: no source => decays to 0.
        pw, pb, pbs, tl, ron = {}, {}, {}, {}, {}
        for c in torch:
            tl[c] = False
        q = deque()
        q.extend(("d", c) for c in dust)
        q.extend(("c", c) for c in cob)
        q.extend(("t", c) for c in torch)
        q.extend(("r", c) for c in rep)

        def push_dependents(kind, c):
            for dx, dz in DIRS:
                m = (c[0] + dx, c[1] + dz)
                if m in dust:
                    q.append(("d", m))
                elif m in cob:
                    q.append(("c", m))
                elif m in rep:
                    d = rep[m]
                    if (m[0] - d[0], m[1] - d[1]) == c:
                        q.append(("r", m))

        def dust_lvl(c):
            lv = 0
            for dx, dz in DIRS:
                m = (c[0] + dx, c[1] + dz)
                if m in torch and tl.get(m, False):
                    return 15
                if m in lever and vec.get(lever[m], False):
                    return 15
                if m in rblk:
                    return 15
                if m in cob and pbs.get(m, False):
                    return 15
                if m in dust:
                    lv = max(lv, pw.get(m, 0) - 1)
                if m in rep:
                    d = rep[m]
                    if (m[0] + d[0], m[1] + d[1]) == c and ron.get(m, False):
                        return 15
            return max(lv, 0)

        def cob_state(c):
            pwrd, strong = False, False
            for dx, dz in DIRS:
                m = (c[0] + dx, c[1] + dz)
                if m in dust and pw.get(m, 0) >= 1:
                    pwrd = True
                if m in rblk:
                    pwrd, strong = True, True
                if m in rep:
                    d = rep[m]
                    if (m[0] + d[0], m[1] + d[1]) == c and ron.get(m, False):
                        pwrd, strong = True, True
            return pwrd, strong

        def rep_on(c):
            d = rep[c]
            b = (c[0] - d[0], c[1] - d[1])
            if b in dust and pw.get(b, 0) >= 1:
                return True
            if b in cob and pb.get(b, False):
                return True
            if b in lever and vec.get(lever[b], False):
                return True
            if b in rblk:
                return True
            # ponytail: repeaters chain back-to-back (standard); read upstream ron.
            if b in rep:
                d2 = rep[b]
                if (b[0] + d2[0], b[1] + d2[1]) == c and ron.get(b, False):
                    return True
            return False

        n = 0
        from collections import Counter as _Counter
        hot = _Counter()
        while q:
            n += 1
            if n > 20000:
                live = {c: v for c, v in pw.items() if v}
                raise RuntimeError(f"sim not settling on {vec}. live: {sorted(live.items())} torches: {tl} ron: {ron}")
            kind, c = q.popleft()
            hot[(kind, c)] += 1
            if kind == "d":
                v = dust_lvl(c)
                if pw.get(c, 0) != v:
                    pw[c] = v
                    push_dependents(kind, c)
            elif kind == "c":
                v, s = cob_state(c)
                if pb.get(c, False) != v or pbs.get(c, False) != s:
                    pb[c], pbs[c] = v, s
                    push_dependents(kind, c)
                    for t in attach_rev.get(c, []):
                        q.append(("t", t))
            elif kind == "t":
                v = not pb.get(torch[c], False)
                if tl.get(c, False) != v:
                    tl[c] = v
                    push_dependents(kind, c)
            elif kind == "r":
                v = rep_on(c)
                if ron.get(c, False) != v:
                    ron[c] = v
                    push_dependents(kind, c)
        return ({net: any(pw.get((cell[0] + dx, cell[1] + dz), 0) >= 1
                          for dx, dz in DIRS)
                 for cell, net in lampnet.items()},
                {c: v for c, v in pw.items() if v})

    ins = recipe["inputs"]
    if 2 ** len(ins) <= 4096:
        combos = [{ins[j]: (k >> j) & 1 for j in range(len(ins))} for k in range(2 ** len(ins))]
    else:
        rr = _r.Random(seed)
        combos = [{n: 0 for n in ins}, {n: 1 for n in ins},
                  {n: j % 2 for j, n in enumerate(ins)},
                  {n: (j + 1) % 2 for j, n in enumerate(ins)}]
        combos += [{n: rr.randint(0, 1) for n in ins} for _ in range(60)]
    bad = []
    lastlive = {}
    for vec in combos:
        got, live = run(vec)
        exp = eval_net(recipe, vec)
        for net in recipe["outputs"]:
            if bool(got.get(net, False)) != bool(exp[net]):
                bad.append((vec, net, got.get(net), bool(exp[net])))
                lastlive = live
    if bad:
        raise RuntimeError(f"SIM MISMATCH x{len(bad)}: {bad[:4]} live: {sorted(lastlive.items())}")
    if not quiet:
        print(f"sim ok: {len(combos)} vectors, lamps match logic")

def demo():
    r = parse_recipe(DEMO)
    for a in (0, 1):
        for b in (0, 1):
            for c in (0, 1):
                got = eval_net(r, {"a": a, "b": b, "c": c})["y"]
                assert got == ((a and b) or c), (a, b, c, got)
    blocks, size, io = layout_retry(r, verify=True)
    assert any(base(b) == "minecraft:cobblestone" for *_, b in blocks), "gate block missing"
    assert any(base(b) == "minecraft:redstone_wall_torch" for *_, b in blocks), "torch missing"
    export_mcfunction(blocks, "build.mcfunction")
    export_html(blocks, size, "build.html", "2-gate demo")
    print(f"ok: {len(blocks)} blocks -> build.html + build.mcfunction")

def demo_alu8():
    r = build_adder8()
    for a, b in ((13, 29), (200, 100), (255, 1), (0, 0)):
        v = {f"A{i}": (a >> i) & 1 for i in range(8)}
        v.update({f"B{i}": (b >> i) & 1 for i in range(8)})
        got = eval_net(r, v)
        s = sum(got[f"S{i}"] << i for i in range(8))
        assert (s, got["C8"]) == ((a + b) & 255, (a + b) >> 8), (a, b, s)
    blocks, size, io = layout_retry(r, verify=True)
    export_mcfunction(blocks, "build_alu8.mcfunction")
    export_html(blocks, size, "build_alu8.html", "8-bit adder")
    print(f"alu8 ok: {len(blocks)} blocks -> build_alu8.html + build_alu8.mcfunction")

if __name__ == "__main__":
    demo()
    if "--alu8" in sys.argv:
        demo_alu8()
    elif len(sys.argv) > 1:  # custom recipe file
        text = open(sys.argv[1]).read()
        r = parse_recipe(text)
        blocks, size, io = layout_retry(r, verify=True)
        export_mcfunction(blocks, "build.mcfunction")
        export_html(blocks, size, "build.html", sys.argv[1])
        print(f"custom ok: {len(blocks)} blocks -> build.html + build.mcfunction")
