"""Export: mcfunction, schem, textured HTML preview."""

import base64
import functools
import json

from core import base


COLORS = {"minecraft:stone": 0x8a8a8a, "minecraft:redstone_wire": 0xe02020,
          "minecraft:cobblestone": 0x7a7a7a, "minecraft:redstone_wall_torch": 0xd83a00,
          "minecraft:lever": 0x7a5a2e, "minecraft:redstone_lamp": 0xffa726,
          "minecraft:redstone_block": 0xb01010, "minecraft:repeater": 0xc7a17a,
          "minecraft:comparator": 0x9a8a7a, "minecraft:glass": 0xd8f0f0,
          "minecraft:target": 0xfffcf5, "minecraft:stone_slab": 0x9a9a9a,
          "minecraft:smooth_stone_slab": 0x9a9a9a,
          "minecraft:cobblestone_slab": 0x7a7a7a,
          "minecraft:white_wool": 0xe9ecec, "minecraft:orange_wool": 0xf07613,
          "minecraft:magenta_wool": 0xbd44b3, "minecraft:light_blue_wool": 0x3aafd9,
          "minecraft:yellow_wool": 0xf1af15, "minecraft:lime_wool": 0x70b919,
          "minecraft:pink_wool": 0xed8dac, "minecraft:gray_wool": 0x3e4447,
          "minecraft:light_gray_wool": 0x8e8e86, "minecraft:cyan_wool": 0x158991,
          "minecraft:purple_wool": 0x792aac, "minecraft:blue_wool": 0x35399d,
          "minecraft:brown_wool": 0x724728, "minecraft:green_wool": 0x546d1b,
          "minecraft:red_wool": 0xa02722, "minecraft:black_wool": 0x181414}
# ponytail: textures stream from the upstream asset pack at runtime, no PNGs in this repo.


TEXBASE = "https://raw.githubusercontent.com/PrismarineJS/minecraft-assets/master/data/1.21.8/blocks/"


TEXMAP = {"minecraft:stone": "stone.png", "minecraft:cobblestone": "cobblestone.png",
          "minecraft:redstone_lamp": "redstone_lamp_on.png",
          "minecraft:redstone_block": "redstone_block.png", "minecraft:repeater": "repeater.png",
          "minecraft:comparator": "comparator.png",
          "minecraft:glass": "glass.png"}
# ponytail: slabs ride the stone.png fallback (asset names vary by variant;
# a wrong guess 404s every preview, the fallback never does).



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



# ponytail: missing props := vanilla defaults (the resting state of a fresh
# block). The .schem palette holds no defaults: a strict loader (WorldEdit)
# replaces a partial state with air. /setblock is lenient, so this is a
# no-op there. Levers are fully stamped at their sites; not listed here.
# Slabs always carry explicit type+waterlogged: a bare slab id is ambiguous
# (we never emit slabs; hand bids should state type, default assumed bottom
# here so a bare bid pastes instead of vanishing).
_DEFAULT_PROPS = {
    "minecraft:redstone_wire": (("power", "0"),),
    "minecraft:repeater": (("powered", "false"), ("locked", "false")),
    "minecraft:comparator": (("powered", "false"),),
    "minecraft:redstone_wall_torch": (("lit", "true"),),
    "minecraft:redstone_torch": (("lit", "true"),),
    "minecraft:redstone_lamp": (("lit", "false"),),
    "minecraft:target": (("power", "0"),),
    "minecraft:stone_slab": (("type", "bottom"), ("waterlogged", "false")),
    "minecraft:smooth_stone_slab": (("type", "bottom"), ("waterlogged", "false")),
    "minecraft:cobblestone_slab": (("type", "bottom"), ("waterlogged", "false")),
}


# ponytail: bids repeat massively across blocks (palette of dozens);
# completing the same partial state 70k times per export is pure waste.
# Same pattern as core.base/footprint caches. Pure function: safe.
@functools.lru_cache(maxsize=None)
def full_state(bid):
    """Complete a partial blockstate with vanilla defaults (see above)."""
    base_, sep, rest = bid.partition("[")
    if not sep:
        extra = _DEFAULT_PROPS.get(bid)
        return f"{bid}[{','.join(f'{k}={v}' for k, v in extra)}]" if extra else bid
    have = {p.split("=", 1)[0] for p in rest.rstrip("]").split(",") if "=" in p}
    missing = [f"{k}={v}" for k, v in _DEFAULT_PROPS.get(base_, ()) if k not in have]
    if not missing:
        return bid
    return f"{bid.rstrip(']')},{','.join(missing)}]"


def export_schem(blocks, path, oy=64):
    """Real .schem via mcschematic (pip install mcschematic). Skips politely
    without the dep; mcfunction export always works."""
    try:
        import mcschematic
        import os
    except ImportError:
        print("mcschematic missing: pip install mcschematic (skipping .schem)")
        return
    schem = mcschematic.MCSchematic()
    for x, y, z, bid in blocks:
        schem.setBlock((x, oy + y, z), full_state(bid))
    folder, name = os.path.split(path)
    schem.save(folder or ".", name.replace(".schem", ""), mcschematic.Version.JE_1_21)
    print(f"schem ok: {path}")



def sign_snbt(text, kind="minecraft:oak_sign", facing=None):
    """1.21 sign NBT, verified live on 1.21.11 (see LOG.md 2026-10-05).

    Four facts that each cost a probe:
      * `rotation` was REMOVED in 1.21 -- wall signs take `facing`, and
        `oak_sign` takes no facing at all.
      * BOTH front_text and back_text must be present or the setblock is
        refused outright ("Could not set the block").
      * `messages` must carry FOUR slots. A one-slot list is accepted and then
        silently dropped, which reads as "the text did not save".
      * `TextComponent:'...'` is accepted and ignored. front_text.messages is
        the real key.
    """
    q = '"%s"' % str(text).replace('"', "'")
    e = '""'
    msgs = "[%s,%s,%s,%s]" % (q, e, e, e)
    blk = '"black"'
    side = "[facing=%s]" % facing if facing else ""
    return ("minecraft:%s%s{front_text:{messages:%s,color:%s,"
            "has_glowing_text:0b},back_text:{messages:%s,color:%s,"
            "has_glowing_text:0b}}" % (kind.split(":")[1], side, msgs, blk,
                                      msgs, blk))


def label_lines(io, oy=64, lever_off=(-2, 0), lamp_off=(0, 2), blocks=None):
    """(stone pad, sign) setblock lines labelling every lever and lamp.

    Signs, not lamps: a label must not cost redstone. One stone pad + one
    standing sign per pin, both outside the circuit, so labelling a build
    changes no power path -- sim and cmc see the same circuit before and
    after. Positions are offsets in the BUILD frame, so the caller gets them
    for free from io.

    ponytail: a sign must never land on another pin. With 2-pitch lamps the
    default offset puts each sign exactly on the next lamp (measured: S1's
    sign sat on S0's lamp and B0's on A0's, burying both -- the lamps read
    dark forever). Fall back through neighbour offsets to the first cell
    that holds no lever or lamp, loudly. Sparse layouts take the default
    and come out byte-identical.

    With blocks= (the caller's block list) the avoid set extends to every
    y==1 cell and anything above it: a sign replacing a wire/repeater kills
    the net, and pulling floor stone from under a pillar pops the pillar.
    Pads are skipped where y==0 is already occupied (support exists).
    blocks=None keeps the old pins-only behaviour.
    """
    def pin_cell(key):
        k = tuple(key) if isinstance(key, (list, tuple)) else (key,)
        return (int(k[0]), int(k[1]) if len(k) == 2 else int(k[2]))

    pins = ([(pin_cell(k), lever_off, n)
             for k, n in sorted((io.get("levers") or {}).items(), key=str)]
            + [(pin_cell(k), lamp_off, n)
               for k, n in sorted((io.get("lamps") or {}).items(), key=str)])
    taken = {(x, z) for (x, z), _, _ in pins}
    y0occ = set()
    if blocks is not None:
        for x, y, z, _b in blocks:
            if y == 1 or y == 2:
                taken.add((x, z))
            if y == 0:
                y0occ.add((x, z))
    lines = []
    for (x, z), off, name in pins:
        spot = None
        for dx, dz in (off, (0, -2), (2, 0), (-2, 0), (0, 1), (0, -1),
                       (1, 0), (-1, 0), (0, 3), (0, -3)):
            if (x + dx, z + dz) not in taken:
                spot = (x + dx, z + dz)
                break
        if spot is None:
            print('label_lines: NO FREE CELL for %s near (%d,%d)' % (name, x, z))
            continue
        taken.add(spot)
        px, pz = spot
        if (px, pz) not in y0occ:
            lines.append("setblock %d %d %d minecraft:stone" % (px, oy, pz))
        lines.append("setblock %d %d %d %s" % (px, oy + 1, pz,
                                               sign_snbt(name)))
    return lines


def export_mcfunction(blocks, path, oy=64, io=None):
    order = {"minecraft:cobblestone": 0, "minecraft:stone": 0, "minecraft:redstone_block": 1,
             "minecraft:lever": 2, "minecraft:redstone_lamp": 2}
    def key(b):
        return (order.get(base(b[3]), 3), b[1], b[0], b[2])
    with open(path, "w") as f:
        f.write("# datapack /function or chat paste. Includes stone floor so dust/torches are supported.\n")
        f.write("# big builds: raise gamerule maxCommandChainLength (e.g. 200000) first.\n")
        for x, y, z, bid in sorted(blocks, key=key):
            f.write(f"setblock {x} {oy + y} {z} {full_state(bid)}\n")
        if io:
            f.write("# --- labels: stone pad + sign per pin, no redstone ---\n")
            for line in label_lines(io, oy, blocks=blocks):
                f.write(line + "\n")



def _pack_states(st, data):
    """Pack STATES["vectors"] into base64 rows the page indexes by input key.

    1024 vectors x 14634 dust cells as JSON is ~1.6GB of page. One nibble of
    power per dust cell (4 bits), one bit per repeater/torch/comparator, one
    byte of lamp bits per vector: ~10MB, exact. Row order matches the page's
    InstancedMesh build order (wireBs/repBs/torchHeads/cmpBs), so the page
    indexes by instance number and never builds a coordinate map.
    """
    v = st["vectors"]
    keys = sorted(v)
    order = {tag: ["%d,%d,%d" % tuple(d["p"]) for d in data if d["b"] == bid]
             for tag, bid in (("w", "minecraft:redstone_wire"),
                              ("r", "minecraft:repeater"),
                              ("t", "minecraft:redstone_wall_torch"),
                              ("c", "minecraft:comparator"))}
    order["l"] = list(st["lamps"])

    def nibbles(ps, src):
        """One 4-bit power level per dust cell, two cells to a byte."""
        nb = (len(ps) + 1) // 2
        out = bytearray()
        for r in src:
            b = bytearray(nb)
            for i, p in enumerate(ps):
                b[i >> 1] |= r.get(p, 0) << ((i & 1) * 4)
            out += b
        return nb, base64.b64encode(bytes(out)).decode()

    def bits(ps, src):
        """One flag per cell, eight cells to a byte."""
        nb = (len(ps) + 7) // 8
        out = bytearray()
        for r in src:
            b = bytearray(nb)
            for i, p in enumerate(ps):
                if r.get(p):
                    b[i >> 3] |= 1 << (i & 7)
            out += b
        return nb, base64.b64encode(bytes(out)).decode()

    pk = {"keys": keys}
    for tag, field in (("w", "w"), ("r", "r"), ("t", "t"), ("c", "o"), ("l", "lamps")):
        nb, blob = (nibbles if tag == "w" else bits)(order[tag],
                                                      [v[k][field] for k in keys])
        pk[tag + "s"], pk[tag] = nb, blob
    return pk


def export_html(blocks, size, path, label="build", extra=None):
    W, D = size
    # ponytail: floor renders as one plane, not W*D cubes. Keeps big previews fast.
    solidxyz = {(x, y, z) for x, y, z, b in blocks}
    def arms(x, y, z):
        m = 0
        for k, (dx, dz) in enumerate(((1, 0), (-1, 0), (0, 1), (0, -1))):
            if (x + dx, y, z + dz) in solidxyz:
                m |= 1 << k
        return m
    data = [{"p": [x, y, z], "c": COLORS.get(base(b), 0xffffff), "b": base(b),
             "t": TEXBASE + TEXMAP.get(base(b), "stone.png"),
              "a": arms(x, y, z) if base(b) == "minecraft:redstone_wire" else 0}
            for x, y, z, b in blocks if not (b == "minecraft:stone" and y == 0)]
    fdir = {"east": (1, 0), "west": (-1, 0), "south": (0, 1), "north": (0, -1)}
    # ponytail: torch mounts include glass/slab/target (all wall-mountable).
    _MOUNT = ("minecraft:cobblestone", "minecraft:stone", "minecraft:glass",
              "minecraft:target", "minecraft:stone_slab", "minecraft:smooth_stone_slab",
              "minecraft:cobblestone_slab")
    mountxy = {(x, z) for x, y, z, b in blocks if y == 1 and base(b) in _MOUNT}
    torchinfo, repinfo, cmpinfo = {}, {}, {}
    for x, y, z, bid in blocks:
        b = base(bid)
        if y == 1 and b == "minecraft:redstone_wall_torch":
            f = bid.split("facing=")[1].rstrip("]") if "facing=" in bid else "east"
            d = fdir[f]
            torchinfo[(x, z)] = {"f": list(d), "m": 1 if (x - d[0], z - d[1]) in mountxy else 0}
        elif b == "minecraft:repeater":
            f = bid.split("facing=")[1].split(",")[0] if "facing=" in bid else "east"
            dl = bid.split("delay=")[1].split(",")[0].rstrip("]") if "delay=" in bid else "1"
            # render arrow points output-ward = negative of facing (which points output->input)
            _v = fdir[f]
            repinfo[(x, y, z)] = {"f": [-_v[0], -_v[1]], "dl": max(1, min(4, int(dl)))}
        if b == "minecraft:comparator":
            f = bid.split("facing=")[1].split(",")[0] if "facing=" in bid else "east"
            v = fdir[f]
            # render arrow points output-ward = negative of facing (which points output->input)
            cmpinfo[(x, y, z)] = {"f": [-v[0], -v[1]]}
    for d in data:
        if d["b"] == "minecraft:redstone_wall_torch":
            t = torchinfo[(d["p"][0], d["p"][2])]
            d["f"], d["m"] = t["f"], t["m"]
        elif d["b"] == "minecraft:repeater":
            # 3D: repeaters may stand on a pillar, so key on (x,y,z)
            r = repinfo[(d["p"][0], d["p"][1], d["p"][2])]
            d["f"], d["dl"] = r["f"], r["dl"]
        elif d["b"] == "minecraft:comparator":
            d["f"] = cmpinfo[(d["p"][0], d["p"][1], d["p"][2])]["f"]
    html = """<!doctype html><html><head><meta charset=utf-8><title>redstone build</title>
<style>body{margin:0;font-family:sans-serif}#t{position:fixed;top:8px;left:8px;background:#111;color:#fff;padding:8px 12px;border-radius:8px}</style>
<script type="importmap">{"imports":{"three":"https://unpkg.com/three@0.160.0/build/three.module.js","three/addons/":"https://unpkg.com/three@0.160.0/examples/jsm/"}}</script>
</head><body><div id=t>STAMP — drag to orbit, scroll to zoom. Real torch gates.</div>
<div id=io style="position:fixed;left:8px;bottom:8px;background:#111;color:#eee;padding:8px 12px;border-radius:8px;font-family:ui-monospace,Consolas,monospace;font-size:14px"></div>
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
floor.rotation.x=-Math.PI/2;floor.position.set(FW/2-0.5,0.46,FD/2-0.5);s.add(floor);
const cubeG=new T.BoxGeometry(.92,.92,.92);
const flatG=new T.BoxGeometry(.92,.18,.92);
const dotG=new T.BoxGeometry(.3,.12,.3);
const armEG=new T.BoxGeometry(.62,.1,.3);
const armNG=new T.BoxGeometry(.3,.1,.62);
const leverBaseG=new T.BoxGeometry(.5,.22,.5);
const leverStickG=new T.BoxGeometry(.14,.55,.14);
const torchStickG=new T.BoxGeometry(.14,.6,.14);
const torchHeadG=new T.BoxGeometry(.26,.26,.26);
const brownM=new T.MeshLambertMaterial({color:0x7a5a2e});
const darkM=new T.MeshLambertMaterial({color:0x4a2f16});
const redM=new T.MeshLambertMaterial({color:0xc02020});
const redDarkM=new T.MeshLambertMaterial({color:0x6a1010});
const groups={};
const lampMesh={mesh:null,order:[]};
for(const b of B){const k=b.b;if(k==='minecraft:lever'||k==='minecraft:redstone_wall_torch'||k==='minecraft:repeater')continue;((groups[k] ??= []).push(b));}
const dummy=new T.Object3D();
for(const k in groups){const arr=groups[k];const b0=arr[0];
 let geo, mat;
  if(k==='minecraft:redstone_wire')continue; // traces below, from arms mask
  else{geo=cubeG;mat=texMat(b0);}
 const im=new T.InstancedMesh(geo,mat,arr.length);
  arr.forEach((b,idx)=>{dummy.position.set(b.p[0],b.p[1],b.p[2]);dummy.updateMatrix();im.setMatrixAt(idx,dummy.matrix);});
 if(k==='minecraft:redstone_lamp'){lampMesh.mesh=im;lampMesh.order=arr.map(b=>b.p[0]+','+b.p[1]+','+b.p[2]);}
 s.add(im);}
// ponytail: dust renders as center dot + arms toward connections (like the
// game), from the arms bitmask computed trackside. No custom models.
const wireBs=B.filter(b=>b.b==='minecraft:redstone_wire');
let dotI=null,armEIM=null,armNIM=null;const armE=[],armN=[];
if(wireBs.length){dotI=new T.InstancedMesh(dotG,redM,wireBs.length);
 wireBs.forEach((b,idx)=>{dummy.position.set(b.p[0],b.p[1]-0.41,b.p[2]);dummy.updateMatrix();dotI.setMatrixAt(idx,dummy.matrix);if(b.a&1)armE.push([b,1,0,idx]);if(b.a&2)armE.push([b,-1,0,idx]);if(b.a&4)armN.push([b,0,1,idx]);if(b.a&8)armN.push([b,0,-1,idx]);});
s.add(dotI);
for(const [lst,geo,isE] of [[armE,armEG,true],[armN,armNG,false]]){if(!lst.length)continue;const im=new T.InstancedMesh(geo,redM,lst.length);lst.forEach(([b,dx,dz],idx)=>{dummy.position.set(b.p[0]+dx*0.31,b.p[1]-0.41,b.p[2]+dz*0.31);dummy.updateMatrix();im.setMatrixAt(idx,dummy.matrix);});s.add(im);if(isE)armEIM=im;else armNIM=im;}
}
// ponytail: levers/torches are 2 boxes each (base+stick, stick+head), not cubes.
const leverMeshes={},torchHeads={};let torchN=0;
for(const b of B){
 if(b.b==='minecraft:lever'){
  const m1=new T.Mesh(leverBaseG,brownM);m1.position.set(b.p[0],b.p[1]-0.35,b.p[2]);s.add(m1);
  const m2=new T.Mesh(leverStickG,darkM);m2.position.set(b.p[0],b.p[1]+0.02,b.p[2]);s.add(m2);
  const key=b.p[0]+','+b.p[1]+','+b.p[2];leverMeshes[key]={base:m1,stick:m2};
  m1.userData.lever=key;m2.userData.lever=key;
  }else if(b.b==='minecraft:redstone_wall_torch'){
   const f=b.f||[1,0],wall=b.m===1;
   const px=b.p[0]+(wall?-f[0]*0.30:0),pz=b.p[2]+(wall?-f[1]*0.30:0);
   const m1=new T.Mesh(torchStickG,redDarkM);m1.position.set(px,b.p[1]-0.15,pz);
   if(wall){m1.rotation.z=-f[0]*0.2;m1.rotation.x=f[1]*0.2;}s.add(m1);
   const hm=new T.MeshLambertMaterial({color:0xff2a1a});
   const m2=new T.Mesh(torchHeadG,hm);m2.position.set(px+(wall?f[0]*0.08:0),b.p[1]+0.22,pz+(wall?f[1]*0.08:0));s.add(m2);
   torchHeads[b.p[0]+','+b.p[1]+','+b.p[2]]=[m2,torchN++];
 }
}
const repBs=B.filter(b=>b.b==='minecraft:repeater');
const repOrder=[];let repSlabIM=null,dotFIM=null,dotBIM=null,nubIM=null;
const dotG2=new T.BoxGeometry(.2,.14,.2);
const nubG=new T.BoxGeometry(.16,.16,.3);
if(repBs.length){repSlabIM=new T.InstancedMesh(flatG,flatMat({c:0xc7a17a}),repBs.length);
dotFIM=new T.InstancedMesh(dotG2,redM.clone(),repBs.length);
dotBIM=new T.InstancedMesh(dotG2,redM.clone(),repBs.length);
nubIM=new T.InstancedMesh(nubG,darkM,repBs.length);
repBs.forEach((b,idx)=>{const f=b.f||[1,0],ang=Math.atan2(-f[1],f[0]);
 dummy.rotation.set(0,ang,0);dummy.position.set(b.p[0],b.p[1]-0.3,b.p[2]);dummy.updateMatrix();repSlabIM.setMatrixAt(idx,dummy.matrix);
 const cs=Math.cos(ang),sn=Math.sin(ang),lx=0.22;
 [[dotFIM,lx],[dotBIM,-lx]].forEach(([im,ox])=>{dummy.position.set(b.p[0]+ox*cs,b.p[1]-0.12,b.p[2]-ox*sn);dummy.updateMatrix();im.setMatrixAt(idx,dummy.matrix);im.setColorAt(idx,new T.Color(0x4a1408));});
 const nx=(b.dl-2.5)*0.12;dummy.position.set(b.p[0]+nx*cs,b.p[1]-0.12,b.p[2]-nx*sn);dummy.updateMatrix();nubIM.setMatrixAt(idx,dummy.matrix);
 dummy.rotation.set(0,0,0);repOrder.push(b.p[0]+','+b.p[1]+','+b.p[2]);});
 s.add(repSlabIM);s.add(dotFIM);s.add(dotBIM);s.add(nubIM);}
const cmpBs=B.filter(b=>b.b==='minecraft:comparator');
const cmpOrder=[];
const cmpDotG=new T.BoxGeometry(.2,.14,.2);
if(cmpBs.length){
 const slab=new T.InstancedMesh(flatG,flatMat({c:0x9a8a7a}),cmpBs.length);
 const df=new T.InstancedMesh(cmpDotG,redM.clone(),cmpBs.length);
 const db=new T.InstancedMesh(cmpDotG,redM.clone(),cmpBs.length*2);
 cmpBs.forEach((b,idx)=>{const f=b.f||[1,0],ang=Math.atan2(-f[1],f[0]);
  dummy.rotation.set(0,ang,0);dummy.position.set(b.p[0],b.p[1]-0.3,b.p[2]);dummy.updateMatrix();slab.setMatrixAt(idx,dummy.matrix);
  const cs=Math.cos(ang),sn=Math.sin(ang);
  dummy.position.set(b.p[0]+0.22*cs,b.p[1]-0.12,b.p[2]-0.22*sn);dummy.updateMatrix();df.setMatrixAt(idx,dummy.matrix);
  [[0.22,0],[-0.22,0]].forEach(([ox,oz],k)=>{dummy.position.set(b.p[0]+ox*cs-oz*sn,b.p[1]-0.12,b.p[2]-ox*sn-oz*cs);dummy.updateMatrix();db.setMatrixAt(idx*2+k,dummy.matrix);});
  dummy.rotation.set(0,0,0);cmpOrder.push(b.p[0]+','+b.p[1]+','+b.p[2]);});
 s.add(slab);s.add(df);s.add(db);
 window.__cmp={slab,df,db};
}
// ponytail: interactivity is state-switching, not physics. Python simulated
// every combo; the page just flips lever meshes and recolors. No timing.
const STATES=STATESJSON,INPUTS=INPUTJSON,LEVERNET=LEVERJSON,LAMPNET=LAMPJSON;
function makeLabel(text){const cv=document.createElement('canvas');cv.width=256;cv.height=64;const g=cv.getContext('2d');g.fillStyle='rgba(10,10,12,0.78)';g.fillRect(0,0,256,64);g.font='bold 34px Consolas,monospace';g.textAlign='center';g.textBaseline='middle';g.fillStyle='#ffd75e';g.fillText(text,128,34);const tx=new T.CanvasTexture(cv);tx.colorSpace=T.SRGBColorSpace;const sp=new T.Sprite(new T.SpriteMaterial({map:tx,depthTest:false}));sp.scale.set(1.7,0.42,1);return sp;}
for(const b of B){if(b.b==='minecraft:lever'){const lb=makeLabel('in '+(LEVERNET[b.p[0]+','+b.p[1]+','+b.p[2]]||'?'));lb.position.set(b.p[0],b.p[1]+0.85,b.p[2]);s.add(lb);}else if(b.b==='minecraft:redstone_lamp'){const lb=makeLabel('out '+(LAMPNET[b.p[0]+','+b.p[1]+','+b.p[2]]||'?'));lb.position.set(b.p[0],b.p[1]+0.95,b.p[2]);s.add(lb);}}
const ioDiv=document.getElementById('io');
// ponytail: 1024 vectors x 14634 dust cells as JSON is ~1.6GB of page, so
// Python hands over base64 rows (nibble per dust cell, bit per torch/rep/cmp)
// and this unpacks one row per click. No physics here, just table lookup.
const PK=STATES&&STATES.vectors&&STATES.vectors.keys?STATES.vectors:{keys:[]};
const _u8=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
const WB=PK.w?_u8(PK.w):null,RB=PK.r?_u8(PK.r):null,TB=PK.t?_u8(PK.t):null,OB=PK.c?_u8(PK.c):null,LB=PK.l?_u8(PK.l):null;
const ridx={};PK.keys.forEach((k,i)=>ridx[k]=i);
const lampIdx={};Object.keys(LAMPNET).forEach((k,i)=>lampIdx[k]=i);
let lampOn=[];
function renderIO(){let h='IN ';for(const n of INPUTS)h+=`<button data-n="${n}" style="margin:0 2px;font:inherit;background:${leverState[n]?'#7a2a12':'#333'};color:#fff;border:1px solid #666;border-radius:4px;cursor:pointer">${n}=${leverState[n]?'1':'0'}</button>`;h+=' OUT ';Object.keys(LAMPNET).forEach((k,i)=>h+=`<span style="margin:0 4px;padding:1px 6px;background:#222;border:1px solid #666;border-radius:4px">${LAMPNET[k]}=${lampOn[i]?'1':'0'}</span>`);ioDiv.innerHTML=h;ioDiv.querySelectorAll('button').forEach(x=>x.onclick=()=>flip(x.dataset.n));}
function flip(n){leverState[n]^=1;click(leverState[n]);applyState(INPUTS.map(x=>leverState[x]?'1':'0').join(''));}
const dotIdx={};
wireBs.forEach((b,idx)=>{dotIdx[b.p[0]+','+b.p[1]+','+b.p[2]]=idx;});
const wireCol=l=>new T.Color().setHSL(0.0,0.85,0.06+0.5*l/15);
const leverState={};for(const k in LEVERNET)leverState[LEVERNET[k]]=0;
function readout(){
 const ins=INPUTS.map(n=>n+'='+(leverState[n]?'1':'0')).join(' ');
 const outs=Object.keys(LAMPNET).map((k,i)=>LAMPNET[k]+'='+(lampOn[i]?'1':'0')).join(' ');
 document.getElementById('t').textContent='click a lever! '+ins+(outs?' -> '+outs:'');
}
function applyState(key){
 const n=PK.keys.length&&ridx[key]!==undefined?ridx[key]:-1;
 const grey=n<0?new T.Color(0x555555):null;
 const lvl=i=>n<0?0:(WB[n*PK.ws+(i>>1)]>>((i&1)*4))&15;
 const bit=(buf,rs,i)=>n<0?0:(buf[n*rs+(i>>3)]>>(i&7))&1;
 const paint=(mesh,idx,l)=>{mesh.setColorAt(idx,grey||wireCol(l));mesh.instanceColor.needsUpdate=true;};
 for(const k in dotIdx){const i=dotIdx[k];paint(dotI,i,lvl(i));}
 armE.forEach((a,i)=>paint(armEIM,i,lvl(a[3])));
 armN.forEach((a,i)=>paint(armNIM,i,lvl(a[3])));
  for(const k in torchHeads){const[hh,i]=torchHeads[k];hh.material.color.set(bit(TB,PK.ts,i)?0xff2a1a:0x4a1408);}
   if(dotFIM){repOrder.forEach((k,i)=>{const col=bit(RB,PK.rs,i)?new T.Color(0xff2a1a):new T.Color(0x4a1408);dotFIM.setColorAt(i,col);dotBIM.setColorAt(i,col);});dotFIM.instanceColor.needsUpdate=true;dotBIM.instanceColor.needsUpdate=true;}
   if(window.__cmp){cmpOrder.forEach((k,i)=>{const col=bit(OB,PK.cs,i)?new T.Color(0xff2a1a):new T.Color(0x4a1408);window.__cmp.df.setColorAt(i,col);window.__cmp.db.setColorAt(i*2,col);window.__cmp.db.setColorAt(i*2+1,col);});window.__cmp.df.instanceColor.needsUpdate=true;window.__cmp.db.instanceColor.needsUpdate=true;}
 lampOn=Object.keys(LAMPNET).map((k,i)=>!!bit(LB,PK.ls,i));
 if(lampMesh.mesh){lampMesh.order.forEach((k,i)=>lampMesh.mesh.setColorAt(i,new T.Color(lampOn[lampIdx[k]]?0xffffff:0x353535)));lampMesh.mesh.instanceColor.needsUpdate=true;}
 for(const k in leverMeshes){const nm=LEVERNET[k];leverMeshes[k].stick.rotation.x=leverState[nm]?-0.5:0.25;}
  readout();
  renderIO();
  if(n<0)document.getElementById('t').textContent+=' — no data here (this input combo was not collected)';
}
const _ray=new T.Raycaster(),_ptr=new T.Vector2();let _down=null;
let AC=null;function click(on){try{AC=AC||new (window.AudioContext||window.webkitAudioContext)();const o=AC.createOscillator(),g=AC.createGain();o.type='square';o.frequency.value=on?2200:1400;g.gain.setValueAtTime(0.08,AC.currentTime);g.gain.exponentialRampToValueAtTime(0.001,AC.currentTime+0.06);o.connect(g);g.connect(AC.destination);o.start();o.stop(AC.currentTime+0.07);}catch(e){}}
r.domElement.addEventListener('pointerdown',e=>{_down=[e.clientX,e.clientY];});
r.domElement.addEventListener('pointerup',e=>{
 if(!STATES||!_down)return;
 const moved=Math.hypot(e.clientX-_down[0],e.clientY-_down[1]);_down=null;
 if(moved>5)return;
 _ptr.x=(e.clientX/innerWidth)*2-1;_ptr.y=-(e.clientY/innerHeight)*2+1;
 _ray.setFromCamera(_ptr,cam);
 const hits=_ray.intersectObjects(Object.values(leverMeshes).flatMap(o=>[o.base,o.stick]));
  if(hits.length){flip(LEVERNET[hits[0].object.userData.lever]);}});
applyState(INPUTS.map(n=>'0').join(''));
(function a(){requestAnimationFrame(a);c.update();r.render(s,cam);})();</script></body></html>"""
    st = extra or None
    # the page reads STATES.vectors as packed rows, not per-vector dicts
    packed = dict(st, vectors=_pack_states(st, data)) if st and st.get("vectors") else st
    # ponytail: template text FIRST, JSON payloads LAST. str.replace is global,
    # so an all-caps placeholder (DATA, STAMP, FW...) injected early gets
    # spell-checked against every base64 row afterwards -- it really happened,
    # 5910 bytes of silently mangled state. The JSON payloads are safe to go
    # last: base64 has no lowercase, and the block URLs are lowercase "data/".
    html = (html.replace("CX", str(W / 2)).replace("CZ", str(D / 2))
            .replace("TEXSTONE", json.dumps(TEXBASE + "stone.png"))
            .replace("STAMP", build_stamp(label, len(blocks)))
            .replace("MAXD", str(max(W, D))).replace("FW", str(W)).replace("FD", str(D))
            .replace("DATA", json.dumps(data))
            .replace("STATESJSON", json.dumps(packed))
            .replace("INPUTJSON", json.dumps(st["inputs"] if st else []))
            .replace("LEVERJSON", json.dumps(st["levers"] if st else {}))
            .replace("LAMPJSON", json.dumps(st["lamps"] if st else {})))
    # utf-8 explicitly: the page declares <meta charset=utf-8> and the hint
    # string carries an em dash, which the locale codec used to mangle.
    open(path, "w", encoding="utf-8").write(html)


if __name__ == "__main__":
    # The page unpacks with 3 lines of bit math; this is the same contract in
    # Python, so a layout slip fails here instead of as a dark cell in the page.
    _d = [{"p": [x, 1, 0], "b": "minecraft:redstone_wire"} for x in range(5)]
    _d += [{"p": [x, 1, 1], "b": "minecraft:repeater"} for x in range(3)]
    _d += [{"p": [x, 1, 2], "b": "minecraft:redstone_wall_torch"} for x in range(2)]
    _d += [{"p": [x, 1, 3], "b": "minecraft:comparator"} for x in range(2)]
    _d += [{"p": [x, 1, 4], "b": "minecraft:redstone_lamp"} for x in range(2)]
    _st = {"lamps": {"0,1,4": "y0", "1,1,4": "y1"},
           "vectors": {"000": {"w": {"0,1,0": 15, "1,1,0": 9, "4,1,0": 1},
                               "r": {"0,1,1": 1, "2,1,1": 1}, "t": {"1,1,2": 1},
                               "o": {"0,1,3": 1},
                               "lamps": {"0,1,4": 1, "1,1,4": 0}},
                       "111": {"w": {"2,1,0": 3}, "r": {"1,1,1": 1},
                               "t": {"0,1,2": 1}, "o": {"1,1,3": 1},
                               "lamps": {"0,1,4": 0, "1,1,4": 1}}}}
    _pk = _pack_states(_st, _d)
    _u = {t: base64.b64decode(_pk[t]) for t in "wrtcl"}

    def _lvl(n, i):
        return (_u["w"][n * _pk["ws"] + (i >> 1)] >> ((i & 1) * 4)) & 15

    def _bit(t, n, i):
        return (_u[t][n * _pk[t + "s"] + (i >> 3)] >> (i & 7)) & 1

    assert _pk["keys"] == ["000", "111"] and _pk["ws"] == 3, _pk["keys"]
    assert [_lvl(0, i) for i in range(5)] == [15, 9, 0, 0, 1]
    assert [_lvl(1, i) for i in range(5)] == [0, 0, 3, 0, 0]
    assert [_bit("r", 0, i) for i in range(3)] == [1, 0, 1]
    assert [_bit("r", 1, i) for i in range(3)] == [0, 1, 0]
    assert [_bit("t", 0, i) for i in range(2)] == [0, 1]
    assert [_bit("t", 1, i) for i in range(2)] == [1, 0]
    assert [_bit("c", 0, i) for i in range(2)] == [1, 0]
    assert [_bit("c", 1, i) for i in range(2)] == [0, 1]
    assert [_bit("l", 0, i) for i in range(2)] == [1, 0]
    assert [_bit("l", 1, i) for i in range(2)] == [0, 1]
    print("export ok: packed states round-trip through the page's bit math")

