"""Full vanilla-vs-sim power map for a bbox. Prints net, sim, vanilla per cell.
Usage: python scratch/mapdump.py OX OY OZ x0 x1 z0 z1 > scratch/mapdump.txt
Covers y=0..4, all pkl dust/dev cells in the local bbox.
"""
import os
import pickle
import shutil
import struct
import sys
import zlib

import nbtlib

sys.path.insert(0, 'D:/redstone-mini')
import sim

OX, OY, OZ = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
X0, X1, Z0, Z1 = (int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]),
                 int(sys.argv[7]))
SAVES = (r'C:\Users\LOQ\AppData\Roaming\FreesmLauncher\instances\26.3'
         r'\minecraft\saves\New World (1)\dimensions\minecraft\overworld\region')
TMP = r'C:\Users\LOQ\AppData\Local\Temp\opencode\alu4regions'
os.makedirs(TMP, exist_ok=True)

import io as _io


def entry_name_props(entry):
    name = str(entry.get('id', entry.get('', '')))
    return name, {str(k): str(v) for k, v in entry.get('properties', {}).items()}


def read_chunk(rf, cx, cz):
    rf.seek(4 * ((cx & 31) + (cz & 31) * 32))
    off, _ = struct.unpack('>IB', b'\x00' + rf.read(3) + rf.read(1))
    if off == 0:
        return None
    rf.seek(off * 4096)
    (ln,) = struct.unpack('>I', rf.read(4))
    assert rf.read(1) == b'\x02'
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
        fn = os.path.join(TMP, 'r.%d.%d.mca' % (rx, rz))
        if not os.path.exists(fn):
            shutil.copyfile(os.path.join(SAVES, 'r.%d.%d.mca' % (rx, rz)), fn)
        rfiles[(rx, rz)] = open(fn, 'rb')
        cache[(cx, cz)] = read_chunk(rfiles[(rx, rz)], cx, cz)
    ch = cache[(cx, cz)]
    if ch is None:
        return None
    st = sec_states(ch, y >> 4)
    if st is None:
        return None
    pal = st['palette']
    if 'data' not in st:
        return entry_name_props(pal[0])
    data = [int(v) & ((1 << 64) - 1) for v in st['data']]
    bpe = max(4, (len(pal) - 1).bit_length())
    idx = ((y & 15) * 16 + (z & 15)) * 16 + (x & 15)
    per = 64 // bpe
    return entry_name_props(pal[(data[idx // per] >> ((idx % per) * bpe)) & ((1 << bpe) - 1)])


def base(bid):
    return bid.split('[')[0]


m = pickle.load(open('scratch/alu4bank.pkl', 'rb'))
blocks, io = m['blocks'], m['io']
nets = io['nets']
P = sim._parse_build(blocks, io)
vec = {'A0': 0, 'A1': 0, 'A2': 0, 'A3': 0, 'B0': 0, 'B1': 0,
       'B2': 0, 'B3': 0, 'OP1': 0, 'OP0': 0}
got, live, tlive, ticks, rlive, conc = sim._run_vec(
    vec, sim._latch_hold_seed(blocks, io), P)

rfiles, cache = {}, {}
n = 0
for x, y, z, bid in blocks:
    if not (X0 <= x <= X1 and Z0 <= z <= Z1 and 0 <= y <= 4):
        continue
    b = base(bid)
    if b not in ('minecraft:redstone_wire', 'minecraft:redstone_wall_torch',
                 'minecraft:repeater', 'minecraft:comparator',
                 'minecraft:redstone_lamp', 'minecraft:lever'):
        continue
    w = (x + OX, y + OY, z + OZ)
    gotb = get_block(rfiles, cache, *w)
    if gotb is None:
        continue
    name, props = gotb
    if b == 'minecraft:redstone_wire':
        if 'redstone_wire' not in name:
            print(w, nets.get((x, y, z), '?'), 'GONE', name)
            continue
        vp, sp = int(props.get('power', -1)), live.get((x, y, z), 0)
        flag = '' if (vp >= 1) == bool(sp) else '  <<<DIV'
        print(w, nets.get((x, y, z), '?'), 'sim=%d' % sp, 'van=%d' % vp + flag)
    elif b == 'minecraft:redstone_wall_torch':
        vl, sl = props.get('lit', '?'), tlive.get((x, y, z), None)
        flag = '' if sl is None or (vl == 'true') == bool(sl) else '  <<<DIV'
        print(w, 'TORCH', 'sim=%s' % sl, 'van=%s' % vl + flag)
    elif b == 'minecraft:repeater':
        vp, sr = props.get('powered', '?'), rlive.get((x, y, z), None)
        flag = '' if sr is None or (vp == 'true') == bool(sr) else '  <<<DIV'
        print(w, 'REP', props.get('facing', '?'), 'sim=%s' % sr,
              'van=%s' % vp, 'lock=' + props.get('locked', '?') + flag)
    n += 1
print('cells:', n, file=sys.stderr)
for rf in rfiles.values():
    rf.close()
