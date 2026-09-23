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
    for lit in ("0", "1"):  # tie-offs for constants, visual stub only
        blocks.append((0, 1, 2, "minecraft:redstone_wire"))
        pos[lit] = (0, 2)
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
# ponytail: textures stream from the upstream asset pack at runtime, no PNGs in this repo. Flat color stays as offline fallback.
TEXBASE = "https://raw.githubusercontent.com/PrismarineJS/minecraft-assets/master/data/1.21.8/blocks/"
TEXMAP = {"minecraft:stone": "stone.png", "minecraft:redstone_wire": "redstone_dust_dot.png",
          "minecraft:iron_block": "iron_block.png", "minecraft:gold_block": "gold_block.png",
          "minecraft:diamond_block": "diamond_block.png", "minecraft:redstone_block": "redstone_block.png",
          "minecraft:lever": "lever.png", "minecraft:redstone_lamp": "redstone_lamp_on.png"}

def export_mcfunction(blocks, path, oy=64):
    with open(path, "w") as f:
        f.write("# paste each line in chat, or /function. Built on flat world at y=%d\n" % oy)
        for x, y, z, bid in blocks:
            if bid == "minecraft:stone" and y == 0:
                continue  # flat world already stone, skip spam
            f.write(f"setblock {x} {oy + y} {z} {bid}\n")

def export_html(blocks, size, path):
    W, D = size
    # ponytail: floor renders as one plane, not W*D cubes. Keeps 8-bit previews fast.
    data = [{"p": [x, y, z], "c": COLORS.get(b, 0xffffff), "b": b,
             "t": TEXBASE + TEXMAP.get(b, "stone.png")}
            for x, y, z, b in blocks if not (b == "minecraft:stone" and y == 0)]
    html = """<!doctype html><html><head><meta charset=utf-8><title>redstone build</title>
<style>body{margin:0;font-family:sans-serif}#t{position:fixed;top:8px;left:8px;background:#111;color:#fff;padding:8px 12px;border-radius:8px}</style>
<script type="importmap">{"imports":{"three":"https://unpkg.com/three@0.160.0/build/three.module.js","three/addons/":"https://unpkg.com/three@0.160.0/examples/jsm/"}}</script>
</head><body><div id=t>drag to orbit, scroll to zoom — textures from upstream minecraft-assets</div>
<script type="module">import * as T from 'three';import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
const B=DATA;const s=new T.Scene();s.background=new T.Color(0x1a2028);
const cam=new T.PerspectiveCamera(50,innerWidth/innerHeight,.1,1000);cam.position.set(12,12,16);
const r=new T.WebGLRenderer({antialias:true});r.setSize(innerWidth,innerHeight);document.body.appendChild(r.domElement);
const c=new OrbitControls(cam,r.domElement);c.target.set(CX,0,CZ);
s.add(new T.AmbientLight(0xffffff,.9));const d=new T.DirectionalLight(0xffffff,.8);d.position.set(10,20,10);s.add(d);
const g=new T.BoxGeometry(.92,.92,.92);
const loader=new T.TextureLoader();loader.setCrossOrigin('anonymous');
const matCache={};
function matFor(b){if(matCache[b.b])return matCache[b.b];
 const tex=loader.load(b.t,(t)=>{t.magFilter=T.NearestFilter;t.colorSpace=T.SRGBColorSpace;});
 tex.magFilter=T.NearestFilter;tex.colorSpace=T.SRGBColorSpace;
 const m=new T.MeshLambertMaterial({color:0xffffff,map:tex});
 matCache[b.b]=m;return m;}
const stoneTex=loader.load(TEXSTONE,(t)=>{t.wrapS=t.wrapT=T.RepeatWrapping;t.repeat.set(FW,FD);t.magFilter=T.NearestFilter;t.colorSpace=T.SRGBColorSpace;});
stoneTex.wrapS=stoneTex.wrapT=T.RepeatWrapping;stoneTex.repeat.set(FW,FD);
const floor=new T.Mesh(new T.PlaneGeometry(FW,FD),new T.MeshLambertMaterial({map:stoneTex}));
floor.rotation.x=-Math.PI/2;floor.position.set(FW/2-0.5,-0.5,FD/2-0.5);s.add(floor);
const flatG=new T.BoxGeometry(.92,.18,.92);
for(const b of B){const isWire=b.b==='minecraft:redstone_wire';
 const m=new T.Mesh(isWire?flatG:g,matFor(b));m.position.set(b.p[0],b.p[1]+(isWire?-0.37:0),b.p[2]);s.add(m);}
(function a(){requestAnimationFrame(a);c.update();r.render(s,cam);})();</script></body></html>"""
    html = (html.replace("DATA", json.dumps(data)).replace("CX", str(W / 2)).replace("CZ", str(D / 2))
            .replace("TEXSTONE", json.dumps(TEXBASE + "stone.png"))
            .replace("FW", str(W)).replace("FD", str(D)))
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

def demo_alu8():
    r = build_adder8()
    for a, b in ((13, 29), (200, 100), (255, 1), (0, 0)):
        v = {f"A{i}": (a >> i) & 1 for i in range(8)}
        v.update({f"B{i}": (b >> i) & 1 for i in range(8)})
        got = eval_net(r, v)
        s = sum(got[f"S{i}"] << i for i in range(8))
        assert (s, got["C8"]) == ((a + b) & 255, (a + b) >> 8), (a, b, s)
    blocks, size = layout(r)
    export_mcfunction(blocks, "build_alu8.mcfunction")
    export_html(blocks, size, "build_alu8.html")
    print(f"alu8 ok: {len(blocks)} blocks, {len(r['gates'])} gates -> build_alu8.html + build_alu8.mcfunction")

if __name__ == "__main__":
    demo()
    if "--alu8" in sys.argv:
        demo_alu8()
    elif len(sys.argv) > 1:  # custom recipe file
        text = open(sys.argv[1]).read()
        r = parse_recipe(text)
        blocks, size = layout(r)
        export_mcfunction(blocks, "build.mcfunction")
        export_html(blocks, size, "build.html")
        print(f"custom ok: {len(blocks)} blocks -> build.html + build.mcfunction")
