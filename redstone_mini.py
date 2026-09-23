"""Mini redstone recipe compiler: tiny DSL -> 3D model + Minecraft commands.
Recipe example:
    IN a, b, c
    OUT y
    t = a AND b
    y = t OR c
Outputs: build.html (3D preview) + build.mcfunction (paste into flat world).
# ponytail: visual model only, not tick-accurate redstone. Swap tiles for tested blueprints when needed.
# ponytail: O(n^2) L-wire scan, fine for <100 gates. Real router if it ever matters.
"""
import json
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
    sig = dict(values)
    for g in recipe["gates"]:
        a = [bool(sig[x]) for x in g["args"]]
        if g["op"] == "AND":
            sig[g["out"]] = a[0] and a[1]
        elif g["op"] == "OR":
            sig[g["out"]] = a[0] or a[1]
        elif g["op"] == "XOR":
            sig[g["out"]] = a[0] != a[1]
        elif g["op"] == "NOT":
            sig[g["out"]] = not a[0]
    return sig

GATE_BLOCK = {"AND": "minecraft:iron_block", "OR": "minecraft:gold_block",
              "XOR": "minecraft:diamond_block", "NOT": "minecraft:redstone_block"}

def layout(recipe):
    blocks = []  # (x, y, z, id)
    W = max(11, len(recipe["inputs"]) * 3 + 4)
    D = 5 + len(recipe["gates"]) * 4 + 2
    cx = W // 2
    for x in range(W):
        for z in range(D):
            blocks.append((x, 0, z, "minecraft:stone"))
    pos = {}
    for i, name in enumerate(recipe["inputs"]):
        x = 2 + i * 3
        blocks.append((x, 1, 1, "minecraft:lever"))
        blocks.append((x, 1, 2, "minecraft:redstone_wire"))
        pos[name] = (x, 2)
    def wire(x0, z0, x1, z1):
        for x in range(min(x0, x1), max(x0, x1) + 1):
            if not any(b[0] == x and b[2] == z0 and b[3] != "minecraft:stone" and b[1] == 1 for b in blocks if b[3] in GATE_BLOCK.values()):
                blocks.append((x, 1, z0, "minecraft:redstone_wire"))
        for z in range(min(z0, z1), max(z0, z1) + 1):
            blocks.append((x1, 1, z, "minecraft:redstone_wire"))
    for i, g in enumerate(recipe["gates"]):
        gz = 4 + i * 4
        blocks.append((cx, 1, gz, GATE_BLOCK[g["op"]]))
        for k, arg in enumerate(g["args"]):
            sx, sz = pos[arg]
            wire(sx, sz, cx - 1 + k, gz)
        pos[g["out"]] = (cx, gz + 1)
        blocks.append((cx, 1, gz + 1, "minecraft:redstone_wire"))
    for j, name in enumerate(recipe["outputs"]):
        sx, sz = pos[name]
        oz = D - 1
        wire(sx, sz, sx, oz)
        blocks.append((sx, 1, oz, "minecraft:redstone_lamp"))
    # dedupe, gate bodies win over wire
    seen, out = {}, []
    for b in blocks:
        k = (b[0], b[1], b[2])
        if k in seen and seen[k] in GATE_BLOCK.values() and b[3] == "minecraft:redstone_wire":
            continue
        seen[k] = b[3]
    for (x, y, z), bid in seen.items():
        out.append((x, y, z, bid))
    return sorted(out), (W, D)

COLORS = {"minecraft:stone": 0x8a8a8a, "minecraft:redstone_wire": 0xe02020,
          "minecraft:iron_block": 0xd8dee6, "minecraft:gold_block": 0xf5c542,
          "minecraft:diamond_block": 0x4de3e3, "minecraft:redstone_block": 0xb01010,
          "minecraft:lever": 0x7a5a2e, "minecraft:redstone_lamp": 0xffa726}

def export_mcfunction(blocks, path, oy=64):
    with open(path, "w") as f:
        f.write("# paste each line in chat, or /function. Built on flat world at y=%d\n" % oy)
        for x, y, z, bid in blocks:
            if bid == "minecraft:stone" and y == 0:
                continue  # flat world already stone, skip spam
            f.write(f"setblock {x} {oy + y} {z} {bid}\n")

def export_html(blocks, size, path):
    W, D = size
    data = [{"p": [x, y, z], "c": COLORS.get(b, 0xffffff), "b": b} for x, y, z, b in blocks]
    html = """<!doctype html><html><head><meta charset=utf-8><title>redstone build</title>
<style>body{margin:0;font-family:sans-serif}#t{position:fixed;top:8px;left:8px;background:#111;color:#fff;padding:8px 12px;border-radius:8px}</style>
<script type="importmap">{"imports":{"three":"https://unpkg.com/three@0.160.0/build/three.module.js","three/addons/":"https://unpkg.com/three@0.160.0/examples/jsm/"}}</script>
</head><body><div id=t>drag to orbit, scroll to zoom — red tall = wire, metal = gates</div>
<script type="module">import * as T from 'three';import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
const B=DATA;const s=new T.Scene();s.background=new T.Color(0x1a2028);
const cam=new T.PerspectiveCamera(50,innerWidth/innerHeight,.1,1000);cam.position.set(12,12,16);
const r=new T.WebGLRenderer({antialias:true});r.setSize(innerWidth,innerHeight);document.body.appendChild(r.domElement);
const c=new OrbitControls(cam,r.domElement);c.target.set(CX,0,CZ);
s.add(new T.AmbientLight(0xffffff,.9));const d=new T.DirectionalLight(0xffffff,.8);d.position.set(10,20,10);s.add(d);
const g=new T.BoxGeometry(.92,.92,.92);
for(const b of B){const m=new T.Mesh(g,new T.MeshLambertMaterial({color:b.c}));m.position.set(b.p[0],b.p[1],b.p[2]);s.add(m);}
(function a(){requestAnimationFrame(a);c.update();r.render(s,cam);})();</script></body></html>"""
    html = html.replace("DATA", json.dumps(data)).replace("CX", str(W / 2)).replace("CZ", str(D / 2))
    open(path, "w").write(html)

DEMO = """IN a, b, c
OUT y
t = a AND b
y = t OR c
"""

def demo():
    r = parse_recipe(DEMO)
    for a in (0, 1):
        for b in (0, 1):
            for c in (0, 1):
                got = eval_net(r, {"a": a, "b": b, "c": c})["y"]
                assert got == ((a and b) or c), (a, b, c, got)
    blocks, size = layout(r)
    assert any(b == "minecraft:iron_block" for *_, b in blocks), "AND gate missing"
    assert any(b == "minecraft:gold_block" for *_, b in blocks), "OR gate missing"
    export_mcfunction(blocks, "build.mcfunction")
    export_html(blocks, size, "build.html")
    print(f"ok: {len(blocks)} blocks, {len(r['gates'])} gates -> build.html + build.mcfunction")

if __name__ == "__main__":
    demo()
    if len(sys.argv) > 1:  # custom recipe file
        text = open(sys.argv[1]).read()
        r = parse_recipe(text)
        blocks, size = layout(r)
        export_mcfunction(blocks, "build.mcfunction")
        export_html(blocks, size, "build.html")
        print(f"custom ok: {len(blocks)} blocks -> build.html + build.mcfunction")
