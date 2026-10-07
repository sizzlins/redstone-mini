"""Diff on-disk (vanilla) block states vs sim T1 state + pkl bids.
Usage: python scratch/regiondiff.py OX OY OZ
Copies r.1.0/r.2.0/r.3.0 to temp first (live world: avoid torn reads).
Prints every vanilla-hot/sim-dark cell and every shape mismatch.
"""
import os
import pickle
import shutil
import struct
import sys
import zlib

import io as _io

import nbtlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OX, OY, OZ = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
SAVES = (r'C:\Users\LOQ\AppData\Roaming\FreesmLauncher\instances\26.3'
         r'\minecraft\saves\New World (1)\dimensions\minecraft\overworld\region')
TMP = r'C:\Users\LOQ\AppData\Local\Temp\opencode\alu4regions'
os.makedirs(TMP, exist_ok=True)
for rn in ('r.1.0.mca', 'r.2.0.mca', 'r.3.0.mca'):
    shutil.copyfile(os.path.join(SAVES, rn), os.path.join(TMP, rn))
print('regions copied')

m = pickle.load(open('scratch/alu4bank.pkl', 'rb'))
blocks, io = m['blocks'], m['io']
nets = io['nets']


def _prop(bid, side):
    if side + '=' not in bid:
        return ''
    return bid.split(side + '=')[1].split(',')[0].rstrip(']')


PKLBIDS = {(x, y, z): bid for x, y, z, bid in blocks}


def W(c):
    return (c[0] + OX, c[1] + OY, c[2] + OZ)


WANT_NETS = None  # None = every net
cells = {}  # world cell -> ('dust', net)
for c, n in nets.items():
    if WANT_NETS is None or n in WANT_NETS:
        cells[W(c)] = ('dust', n)


def base(bid):
    return bid.split('[')[0]


for x, y, z, bid in blocks:
    w = (x + OX, y + OY, z + OZ)
    b = base(bid)
    if b in ('minecraft:redstone_wall_torch', 'minecraft:repeater',
             'minecraft:comparator', 'minecraft:redstone_lamp'):
        cells[w] = ('dev', b)


def read_chunk(rf, cx, cz):
    rf.seek(4 * ((cx & 31) + (cz & 31) * 32))
    off, sectors = struct.unpack('>IB', b'\x00' + rf.read(3) + rf.read(1))
    if off == 0:
        return None
    rf.seek(off * 4096)
    (ln,) = struct.unpack('>I', rf.read(4))
    assert rf.read(1) == b'\x02', 'expected zlib'
    return nbtlib.File.from_fileobj(_io.BytesIO(zlib.decompress(rf.read(ln - 1))))


def sec_states(chunk, sy):
    secs = chunk.get('sections', chunk.get('Sections', []))
    for s in secs:
        if int(s['Y']) == sy:
            return s.get('block_states')
    return None


def get_block(rfiles, cache, x, y, z):
    cx, cz = x >> 4, z >> 4
    if (cx, cz) not in cache:
        rx, rz = cx >> 5, cz >> 5
        key = (rx, rz)
        if key not in rfiles:
            cache[(cx, cz)] = None
        else:
            cache[(cx, cz)] = read_chunk(rfiles[key], cx, cz)
    ch = cache[(cx, cz)]
    if ch is None:
        return None
    st = sec_states(ch, y >> 4)
    # sections indexed by absolute Y offset; find by matching instead
    if st is None:
        for s in ch['Sections']:
            pass
        return None
    pal = st['palette']
    if 'data' not in st:
        return entry_name_props(pal[0])
    data = [int(v) & ((1 << 64) - 1) for v in st['data']]
    bpe = max(4, (len(pal) - 1).bit_length())
    lx, lz, ly = x & 15, z & 15, y & 15
    idx = (ly * 16 + lz) * 16 + lx
    per = 64 // bpe
    val = (data[idx // per] >> ((idx % per) * bpe)) & ((1 << bpe) - 1)
    entry = pal[val]
    return entry_name_props(entry)


def entry_name_props(entry):
    name = str(entry.get('id', entry.get('', '')))
    props = entry.get('properties', {})
    return name, {str(k): str(v) for k, v in props.items()}


rpaths = {k: open(os.path.join(TMP, f'r.{k[0]}.{k[1]}.mca'), 'rb')
          for k in [(1, 0), (2, 0), (3, 0)]}

import sim as simmod
P = simmod._parse_build(blocks, io)
vec = {'A0': 0, 'A1': 0, 'A2': 0, 'A3': 0, 'B0': 0, 'B1': 0,
       'B2': 0, 'B3': 0, 'OP1': 0, 'OP0': 0}
got, live, tlive, ticks, rlive, conc = simmod._run_vec(
    vec, simmod._latch_hold_seed(blocks, io), P)
liveL = {(x + OX, y + OY, z + OZ): v for (x, y, z), v in live.items()}
tliveW = {(x + OX, y + OY, z + OZ): v for (x, y, z), v in tlive.items()}
ronW = {(x + OX, y + OY, z + OZ): v for (x, y, z), v in rlive.items()}
conW = {(x + OX, y + OY, z + OZ): v for (x, y, z), v in conc.items()}
print('sim ticks', ticks, 'cells to check:', len(cells))

miss = 0
divs = []
cache = {}
VPOW = {}
VLIT = {}
VREP = {}
for w, (typ, info) in sorted(cells.items()):
    gotb = get_block(rpaths, cache, *w)
    if gotb is None:
        continue
    name, props = str(gotb[0]), {str(k): str(v) for k, v in gotb[1].items()}
    if typ == 'dust':
        if 'redstone_wire' not in name:
            divs.append((w, info, 'NOT-DUST-ON-DISK', name))
            continue
        vp = int(props.get('power', -1))
        VPOW[w] = vp
        sp = 1 if liveL.get(w, 0) else 0
        if (vp >= 1) != bool(sp):
            divs.append((w, info, 'sim=%d' % sp, 'vanilla=%d' % vp))
        pb = PKLBIDS.get((w[0] - OX, w[1] - OY, w[2] - OZ), '')
        for side in ('east', 'west', 'north', 'south'):
            a = _prop(pb, side)
            b = props.get(side, '?')
            if a and a != b:
                divs.append((w, info, 'shape-%s' % side, 'pkl=%s' % a,
                             'disk=%s' % b))
                break
        vl = props.get('lit', '?')
        sl = 1 if liveL.get(w, 0) else 0
        if (vl == 'true') != bool(sl):
            divs.append((w, 'LAMP', 'sim=%d' % sl, 'vanilla=%s' % vl))
    elif info == 'minecraft:redstone_wall_torch':
        vl = props.get('lit', '?')
        VLIT[w] = (vl == 'true')
        sl = tliveW.get(w, None)
        if sl is not None and (vl == 'true') != bool(sl):
            divs.append((w, 'TORCH', 'sim=%s' % sl, 'vanilla=%s' % vl))
    elif info == 'minecraft:repeater':
        vp = props.get('powered', '?')
        VREP[w] = (vp == 'true', props.get('facing', '?'))
        sr = ronW.get(w, None)
        if sr is not None and (vp == 'true') != bool(sr):
            divs.append((w, 'REP', 'sim=%s' % sr, 'vanilla=%s' % vp,
                         props.get('locked', '?'), props.get('facing', '?')))
    elif info == 'minecraft:comparator':
        vo = None
        sc = conW.get(w, None)
        divs.append((w, 'COMP-check', 'sim=%s' % sc, props))
for d in divs:
    print(*d)
print('divergences:', len(divs))

D6 = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
VV = {'east': (1, 0), 'west': (-1, 0), 'south': (0, 1), 'north': (0, -1)}
print('--- first causes (vanilla-hot, sim-dark, no hot/feeding neighbor):')
fc = 0
for w, (typ, info) in sorted(cells.items()):
    if typ != 'dust':
        continue
    if VPOW.get(w, 0) < 1:
        continue
    lc = (w[0] - OX, w[1] - OY, w[2] - OZ)
    if live.get(lc, 0):
        continue
    fed = []
    for dx, dy, dz in D6:
        n = (w[0] + dx, w[1] + dy, w[2] + dz)
        if VPOW.get(n, 0) >= 1:
            fed.append(('dust', n, VPOW[n]))
        if VLIT.get(n, False):
            fed.append(('torch', n))
        if n in VREP and VREP[n][0]:
            fed.append(('rep', n, VREP[n][1]))
    if not fed:
        print(w, info, 'vp=%d' % VPOW[w])
        fc += 1
print('first causes:', fc)
for rf in rpaths.values():
    rf.close()
