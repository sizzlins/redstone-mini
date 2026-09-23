"""Export: mcfunction, schem, textured HTML preview."""

import json

from core import base


COLORS = {"minecraft:stone": 0x8a8a8a, "minecraft:redstone_wire": 0xe02020,
          "minecraft:cobblestone": 0x7a7a7a, "minecraft:redstone_wall_torch": 0xd83a00,
          "minecraft:lever": 0x7a5a2e, "minecraft:redstone_lamp": 0xffa726,
          "minecraft:redstone_block": 0xb01010, "minecraft:repeater": 0xc7a17a}
# ponytail: textures stream from the upstream asset pack at runtime, no PNGs in this repo.


TEXBASE = "https://raw.githubusercontent.com/PrismarineJS/minecraft-assets/master/data/1.21.8/blocks/"


TEXMAP = {"minecraft:stone": "stone.png", "minecraft:cobblestone": "cobblestone.png",
          "minecraft:redstone_lamp": "redstone_lamp_on.png",
          "minecraft:redstone_block": "redstone_block.png", "minecraft:repeater": "repeater.png"}



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
        schem.setBlock((x, oy + y, z), bid)
    folder, name = os.path.split(path)
    schem.save(folder or ".", name.replace(".schem", ""), mcschematic.Version.JE_1_21)
    print(f"schem ok: {path}")



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



def export_html(blocks, size, path, label="build", extra=None):
    W, D = size
    # ponytail: floor renders as one plane, not W*D cubes. Keeps big previews fast.
    solidxy = {(x, z) for x, y, z, b in blocks if y == 1}
    def arms(x, z):
        m = 0
        for k, (dx, dz) in enumerate(((1, 0), (-1, 0), (0, 1), (0, -1))):
            if (x + dx, z + dz) in solidxy:
                m |= 1 << k
        return m
    data = [{"p": [x, y, z], "c": COLORS.get(base(b), 0xffffff), "b": base(b),
             "t": TEXBASE + TEXMAP.get(base(b), "stone.png"),
             "a": arms(x, z) if base(b) == "minecraft:redstone_wire" else 0}
            for x, y, z, b in blocks if not (b == "minecraft:stone" and y == 0)]
    fdir = {"east": (1, 0), "west": (-1, 0), "south": (0, 1), "north": (0, -1)}
    mountxy = {(x, z) for x, y, z, b in blocks if y == 1 and base(b) in ("minecraft:cobblestone", "minecraft:stone")}
    torchinfo = {}
    for x, y, z, bid in blocks:
        if y == 1 and base(bid) == "minecraft:redstone_wall_torch":
            f = bid.split("facing=")[1].rstrip("]") if "facing=" in bid else "east"
            d = fdir[f]
            torchinfo[(x, z)] = {"f": list(d), "m": 1 if (x - d[0], z - d[1]) in mountxy else 0}
    for d in data:
        if d["b"] == "minecraft:redstone_wall_torch":
            t = torchinfo[(d["p"][0], d["p"][2])]
            d["f"], d["m"] = t["f"], t["m"]
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
for(const b of B){const k=b.b;if(k==='minecraft:lever'||k==='minecraft:redstone_wall_torch')continue;((groups[k] ??= []).push(b));}
const dummy=new T.Object3D();
for(const k in groups){const arr=groups[k];const b0=arr[0];
 let geo, mat;
 if(k==='minecraft:redstone_wire')continue; // traces below, from arms mask
 else if(k==='minecraft:repeater'){geo=flatG;mat=flatMat(b0);}
 else{geo=cubeG;mat=texMat(b0);}
 const im=new T.InstancedMesh(geo,mat,arr.length);
 arr.forEach((b,idx)=>{let y=b.p[1];
  if(k==='minecraft:repeater')y-=0.3;
  dummy.position.set(b.p[0],y,b.p[2]);dummy.updateMatrix();im.setMatrixAt(idx,dummy.matrix);});
 if(k==='minecraft:redstone_lamp'){lampMesh.mesh=im;lampMesh.order=arr.map(b=>b.p[0]+','+b.p[2]);}
 s.add(im);}
// ponytail: dust renders as center dot + arms toward connections (like the
// game), from the arms bitmask computed trackside. No custom models.
const wireBs=B.filter(b=>b.b==='minecraft:redstone_wire');
let dotI=null,armEIM=null,armNIM=null;const armE=[],armN=[];
if(wireBs.length){dotI=new T.InstancedMesh(dotG,redM,wireBs.length);
wireBs.forEach((b,idx)=>{dummy.position.set(b.p[0],b.p[1]-0.41,b.p[2]);dummy.updateMatrix();dotI.setMatrixAt(idx,dummy.matrix);if(b.a&1)armE.push([b,1,0]);if(b.a&2)armE.push([b,-1,0]);if(b.a&4)armN.push([b,0,1]);if(b.a&8)armN.push([b,0,-1]);});
s.add(dotI);
for(const [lst,geo,isE] of [[armE,armEG,true],[armN,armNG,false]]){if(!lst.length)continue;const im=new T.InstancedMesh(geo,redM,lst.length);lst.forEach(([b,dx,dz],idx)=>{dummy.position.set(b.p[0]+dx*0.31,b.p[1]-0.41,b.p[2]+dz*0.31);dummy.updateMatrix();im.setMatrixAt(idx,dummy.matrix);});s.add(im);if(isE)armEIM=im;else armNIM=im;}
}
// ponytail: levers/torches are 2 boxes each (base+stick, stick+head),
// not cubes. All our wall torches face east, hence the +x offset.
const leverMeshes={},torchHeads={};
for(const b of B){
 if(b.b==='minecraft:lever'){
  const m1=new T.Mesh(leverBaseG,brownM);m1.position.set(b.p[0],b.p[1]-0.35,b.p[2]);s.add(m1);
  const m2=new T.Mesh(leverStickG,darkM);m2.position.set(b.p[0],b.p[1]+0.02,b.p[2]);s.add(m2);
  const key=b.p[0]+','+b.p[2];leverMeshes[key]={base:m1,stick:m2};
  m1.userData.lever=key;m2.userData.lever=key;
  }else if(b.b==='minecraft:redstone_wall_torch'){
   const f=b.f||[1,0],wall=b.m===1;
   const px=b.p[0]+(wall?f[0]*0.30:0),pz=b.p[2]+(wall?f[1]*0.30:0);
   const m1=new T.Mesh(torchStickG,redDarkM);m1.position.set(px,b.p[1]-0.15,pz);
   if(wall){m1.rotation.z=-f[0]*0.2;m1.rotation.x=f[1]*0.2;}s.add(m1);
   const hm=new T.MeshLambertMaterial({color:0xff2a1a});
   const m2=new T.Mesh(torchHeadG,hm);m2.position.set(px+(wall?f[0]*0.08:0),b.p[1]+0.22,pz+(wall?f[1]*0.08:0));s.add(m2);
   torchHeads[b.p[0]+','+b.p[2]]=m2;
  }
}
// ponytail: interactivity is state-switching, not physics. Python simulated
// every combo; the page just flips lever meshes and recolors. No timing.
const STATES=STATESJSON,INPUTS=INPUTJSON,LEVERNET=LEVERJSON,LAMPNET=LAMPJSON;
const dotIdx={},armEIdx={},armNIdx={};
wireBs.forEach((b,idx)=>{dotIdx[b.p[0]+','+b.p[2]]=idx;});
let _ai=0;for(const [b,dx,dz] of armE){armEIdx[b.p[0]+','+b.p[2]+','+dx+','+dz]=_ai++;}
_ai=0;for(const [b,dx,dz] of armN){armNIdx[b.p[0]+','+b.p[2]+','+dx+','+dz]=_ai++;}
const wireCol=l=>new T.Color().setHSL(0.0,0.85,0.06+0.5*l/15);
const leverState={};for(const k in LEVERNET)leverState[LEVERNET[k]]=0;
function readout(extra){
 const ins=INPUTS.map(n=>n+'='+(leverState[n]?'1':'0')).join(' ');
 const outs=Object.entries(LAMPNET).map(([c,n])=>n+'='+(extra&&extra.lamps&&extra.lamps[c]?'1':'0')).join(' ');
 document.getElementById('t').textContent='click a lever! '+ins+(outs?' -> '+outs:'');
}
function applyState(key){
 const v=STATES?STATES.vectors[key]:null;
 const paint=(mesh,idx,lvl)=>{mesh.setColorAt(idx,wireCol(lvl));mesh.instanceColor.needsUpdate=true;};
 for(const k in dotIdx){const lvl=v&&v.w[k]?v.w[k]:0;paint(dotI,dotIdx[k],lvl);}
 armE.forEach(([b,dx,dz],i)=>{const k=b.p[0]+','+b.p[2];const lvl=v&&v.w[k]?v.w[k]:0;paint(armEIM,i,lvl);});
 armN.forEach(([b,dx,dz],i)=>{const k=b.p[0]+','+b.p[2];const lvl=v&&v.w[k]?v.w[k]:0;paint(armNIM,i,lvl);});
 for(const k in torchHeads){torchHeads[k].material.color.set(v&&v.t[k]?0xff2a1a:0x4a1408);}
 if(lampMesh.mesh){const arr=lampMesh.order;arr.forEach((k,i)=>{lampMesh.mesh.setColorAt(i,new T.Color(v&&v.lamps&&v.lamps[k]?0xffffff:0x353535));});lampMesh.mesh.instanceColor.needsUpdate=true;}
 for(const k in leverMeshes){const n=LEVERNET[k];leverMeshes[k].stick.rotation.x=leverState[n]?-0.5:0.25;}
 readout(v);
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
 if(hits.length){const k=hits[0].object.userData.lever;leverState[LEVERNET[k]]^=1;click(leverState[LEVERNET[k]]);
  applyState(INPUTS.map(n=>leverState[n]?'1':'0').join(''));}});
(function a(){requestAnimationFrame(a);c.update();r.render(s,cam);})();</script></body></html>"""
    st = extra or None
    html = (html.replace("STATESJSON", json.dumps(st))
            .replace("INPUTJSON", json.dumps(st["inputs"] if st else []))
            .replace("LEVERJSON", json.dumps(st["levers"] if st else {}))
            .replace("LAMPJSON", json.dumps(st["lamps"] if st else {}))
            .replace("DATA", json.dumps(data)).replace("CX", str(W / 2)).replace("CZ", str(D / 2))
            .replace("TEXSTONE", json.dumps(TEXBASE + "stone.png"))
            .replace("STAMP", build_stamp(label, len(blocks)))
            .replace("MAXD", str(max(W, D))).replace("FW", str(W)).replace("FD", str(D)))
    open(path, "w").write(html)

