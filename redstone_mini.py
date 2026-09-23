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
                nxt += [{"out": t1, "op": "OR", "args": [a[0], a[1]]},
                        {"out": t2, "op": "AND", "args": [a[0], a[1]]},
                        {"out": t3, "op": "NOT", "args": [t2]},
                        {"out": o, "op": "AND", "args": [t1, t3]}]
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
    W = max(30, len(recipe["inputs"]) * 3 + 10)
    cx = W // 2
    rows = len(gates)
    D = 12 + rows * 14 + 12
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
        starts = [a] + [c for c, n in wires.items() if n == net and c != a]
        for margin in (12, 40, None):
            path = astar(starts, b, net, W, D, solid, rings, wires, junctions, margin)
            if path:
                break
        if not path:
            raise RuntimeError(f"no route for {net}: {a} -> {b} (grid full, widen W)")
        stamp_wire(path, net)
        paths.append((path, net))
        return path

    # compact: each lever sits on its first load's row, each lamp on its
    # driver's row. Feed rows are globally distinct (pitch 14 > offsets 0..5),
    # so feeds never share a row and marathons disappear.
    rows = [12 + i * 14 for i in range(len(gates))]
    firstload = {}
    for i, g in enumerate(gates):
        if g["op"] == "AND":
            for a, off in zip(g["args"], (0, 3)):
                firstload[a] = min(firstload.get(a, 1e9), rows[i] + off)
        else:
            for a in g["args"]:
                firstload[a] = min(firstload.get(a, 1e9), rows[i])
    pos = {}
    for idx, name in enumerate(recipe["inputs"]):
        if name not in firstload:
            continue  # unused input: no lever
        x, rz = 2 + idx * 3, firstload[name]
        blocks.append((x, 1, rz, "minecraft:lever"))
        solid[(x, rz)] = ("lever", name)
        for dx, dz in DIRS:
            ring(x + dx, rz + dz, own(name))
        wires[(x + 1, rz)] = name
        pos[name] = (x + 1, rz)
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
        stamp_wire([(ox + 2, gz + 3), (ox + 3, gz + 3), (ox + 4, gz + 3),
                    (ox + 4, gz + 2), (ox + 3, gz + 2)], nb)
        stamp_wire([(ox + 5, gz + 1), (ox + 6, gz + 1)], O)
        return (ox - 2, gz), (ox - 2, gz + 3), (ox + 6, gz + 1)

    recs = []
    outrow = {}
    for i, g in enumerate(gates):
        gz = rows[i]
        ox = cx
        op, o, a = g["op"], g["out"], g["args"]
        if op == "OR":
            # junction taps driver-A in place (zero wire); only driver-B routes.
            ax, az = pos[a[0]]
            j = None
            for dx, dz in ((1, 0), (0, 1), (0, -1), (-1, 0)):
                c = (ax + dx, az + dz)
                if c in solid or c in wires or c in rings:
                    continue
                j = c
                break
            if j is None:
                j = (ox, gz)
                route(pos[a[0]], j, a[0])
            else:
                wires[j] = a[0]
            junctions[j] = {a[0], a[1], o}
            pos[o] = j
            outrow[o] = gz
            recs.append((op, o, a, (j, j != (ox, gz))))
            continue
        if op == "AND":
            pa, pb, po = stamp_and(ox, gz, a[0], a[1], o)
            pos[o] = po
            outrow[o] = gz + 1
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
        outrow[o] = gz
        recs.append((op, o, a, (bx, bz)))

    for name in recipe["outputs"]:
        dr = outrow[name]
        blocks.append((W - 2, 1, dr, "minecraft:redstone_lamp"))
        solid[(W - 2, dr)] = ("lamp", name)
        for dx, dz in DIRS:
            ring(W - 2 + dx, dr + dz, own(name))
        recs.append(("OUT", name, [name], (W - 3, dr)))

    # phase 2: route every net through the finished field, shortest hops first
    # so long runs maze around settled locals instead of fencing them in.
    tasks = []
    for op, o, a, cell in recs:
        if op == "OR":
            j, tapped = cell
            if not tapped:
                tasks.append((pos[a[0]], j, a[0]))
            tasks.append((pos[a[1]], j, a[1]))
        elif op == "AND":
            pa, pb, po = cell
            tasks += [(pos[a[0]], pa, a[0]), (pos[a[1]], pb, a[1])]
        elif op == "NOT":
            bx, bz = cell
            tasks.append((pos[a[0]], (bx - 1, bz), a[0]))
        elif op == "OUT":
            tasks.append((pos[a[0]], cell, a[0]))
    tasks.sort(key=lambda t: abs(t[0][0] - t[1][0]) + abs(t[0][1] - t[1][1]))
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

    # repeaters: dust dies after 15 blocks; boost straight runs in-line (sides stay isolated).
    for path, net in paths:
        last = 0
        for i in range(1, len(path) - 1):
            (x0, z0), (x1, z1), (x2, z2) = path[i - 1], path[i], path[i + 1]
            straight = (x0 == x1 == x2) or (z0 == z1 == z2)
            if i - last >= 14 and straight and i < len(path) - 2:
                dx, dz = x1 - x0, z1 - z0
                facing = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}[(dx, dz)]
                for f in ((x1 + dx, z1 + dz), (x1 - dx, z1 - dz)):
                    w = wires.get(f)
                    if w is not None and w != net:
                        raise RuntimeError(f"repeater guard {net} vs {w} at {f}")
                del wires[(x1, z1)]
                repeaters[(x1, z1)] = (net, facing)
                last = i

    # checker: no two nets may share/side-touch dust, except at OR junctions.
    for (x, z), net in wires.items():
        for dx, dz in DIRS:
            m = (x + dx, z + dz)
            if m in wires and wires[m] != net:
                ok = (m in junctions and net in junctions[m] and wires[m] in junctions[m])
                ok = ok or ((x, z) in junctions and wires[m] in junctions[(x, z)])
                if not ok:
                    raise RuntimeError(f"SHORT: {net} touches {wires[m]} at {(x, z)}->{m}")
    out = list(blocks)
    for (x, z), net in wires.items():
        out.append((x, 1, z, "minecraft:redstone_wire"))
    for (x, z), (net, facing) in repeaters.items():
        out.append((x, 1, z, f"minecraft:repeater[facing={facing},delay=1]"))
    for x in range(W):
        for z in range(D):
            out.append((x, 0, z, "minecraft:stone"))
    return sorted(out), (W, D)

COLORS = {"minecraft:stone": 0x8a8a8a, "minecraft:redstone_wire": 0xe02020,
          "minecraft:cobblestone": 0x7a7a7a, "minecraft:redstone_wall_torch": 0xd83a00,
          "minecraft:lever": 0x7a5a2e, "minecraft:redstone_lamp": 0xffa726,
          "minecraft:redstone_block": 0xb01010, "minecraft:repeater": 0xc7a17a}
# ponytail: textures stream from the upstream asset pack at runtime, no PNGs in this repo.
TEXBASE = "https://raw.githubusercontent.com/PrismarineJS/minecraft-assets/master/data/1.21.8/blocks/"
TEXMAP = {"minecraft:stone": "stone.png", "minecraft:cobblestone": "cobblestone.png",
          "minecraft:redstone_lamp": "redstone_lamp_on.png",
          "minecraft:redstone_block": "redstone_block.png", "minecraft:repeater": "repeater.png"}

def layout_retry(recipe, tries=12):
    """Randomized-restart maze routing: reshuffle net order until the field fits."""
    last = None
    for t in range(tries):
        try:
            return layout(recipe, seed=None if t == 0 else t)
        except RuntimeError as e:
            last = e
    raise last

def base(bid):
    return bid.split("[")[0]

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

def export_html(blocks, size, path):
    W, D = size
    # ponytail: floor renders as one plane, not W*D cubes. Keeps big previews fast.
    data = [{"p": [x, y, z], "c": COLORS.get(base(b), 0xffffff), "b": base(b),
             "t": TEXBASE + TEXMAP.get(base(b), "stone.png")}
            for x, y, z, b in blocks if not (b == "minecraft:stone" and y == 0)]
    html = """<!doctype html><html><head><meta charset=utf-8><title>redstone build</title>
<style>body{margin:0;font-family:sans-serif}#t{position:fixed;top:8px;left:8px;background:#111;color:#fff;padding:8px 12px;border-radius:8px}</style>
<script type="importmap">{"imports":{"three":"https://unpkg.com/three@0.160.0/build/three.module.js","three/addons/":"https://unpkg.com/three@0.160.0/examples/jsm/"}}</script>
</head><body><div id=t>drag to orbit, scroll to zoom — real torch gates, textures from upstream minecraft-assets</div>
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
            .replace("MAXD", str(max(W, D))).replace("FW", str(W)).replace("FD", str(D)))
    open(path, "w").write(html)

DEMO = """IN a, b, c
OUT y
t = a AND b
y = t OR c
"""

def build_adder8():
    """8-bit ripple-carry adder. 5 two-input gates per bit, no new gate types."""
    ins = [f"A{i}" for i in range(8)] + [f"B{i}" for i in range(8)]
    gates = []
    for i in range(8):
        a, b, cin, cout = f"A{i}", f"B{i}", f"C{i}", f"C{i+1}"
        if i == 0:
            cin = "0"
        gates += [{"out": f"X{i}", "op": "XOR", "args": [a, b]},
                  {"out": f"S{i}", "op": "XOR", "args": [f"X{i}", cin]},
                  {"out": f"T{i}", "op": "AND", "args": [a, b]},
                  {"out": f"U{i}", "op": "AND", "args": [f"X{i}", cin]},
                  {"out": cout, "op": "OR", "args": [f"T{i}", f"U{i}"]}]
    return {"inputs": ins, "outputs": [f"S{i}" for i in range(8)] + ["C8"], "gates": gates}

def demo():
    r = parse_recipe(DEMO)
    for a in (0, 1):
        for b in (0, 1):
            for c in (0, 1):
                got = eval_net(r, {"a": a, "b": b, "c": c})["y"]
                assert got == ((a and b) or c), (a, b, c, got)
    blocks, size = layout_retry(r)
    assert any(base(b) == "minecraft:cobblestone" for *_, b in blocks), "gate block missing"
    assert any(base(b) == "minecraft:redstone_wall_torch" for *_, b in blocks), "torch missing"
    export_mcfunction(blocks, "build.mcfunction")
    export_html(blocks, size, "build.html")
    print(f"ok: {len(blocks)} blocks -> build.html + build.mcfunction")

def demo_alu8():
    r = build_adder8()
    for a, b in ((13, 29), (200, 100), (255, 1), (0, 0)):
        v = {f"A{i}": (a >> i) & 1 for i in range(8)}
        v.update({f"B{i}": (b >> i) & 1 for i in range(8)})
        got = eval_net(r, v)
        s = sum(got[f"S{i}"] << i for i in range(8))
        assert (s, got["C8"]) == ((a + b) & 255, (a + b) >> 8), (a, b, s)
    blocks, size = layout_retry(r)
    export_mcfunction(blocks, "build_alu8.mcfunction")
    export_html(blocks, size, "build_alu8.html")
    print(f"alu8 ok: {len(blocks)} blocks -> build_alu8.html + build_alu8.mcfunction")

if __name__ == "__main__":
    demo()
    if "--alu8" in sys.argv:
        demo_alu8()
    elif len(sys.argv) > 1:  # custom recipe file
        text = open(sys.argv[1]).read()
        r = parse_recipe(text)
        blocks, size = layout_retry(r)
        export_mcfunction(blocks, "build.mcfunction")
        export_html(blocks, size, "build.html")
        print(f"custom ok: {len(blocks)} blocks -> build.html + build.mcfunction")
