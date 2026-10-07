"""Fresh-copy regions, print powered= for given world cells.
Usage: python scratch/levercheck.py x1 y1 z1 [x2 y2 z2 ...]
"""
import os
import shutil
import struct
import sys
import zlib

import io as _io

import nbtlib


def entry_name_props(entry):
    if not hasattr(entry, 'get'):
        return str(entry), {}
    name = str(entry.get('id', entry.get('', '')))
    props = entry.get('properties', {})
    return name, {str(k): str(v) for k, v in props.items()}


def read_chunk(rf, cx, cz):
    rf.seek(4 * ((cx & 31) + (cz & 31) * 32))
    off, sectors = struct.unpack('>IB', b'\x00' + rf.read(3) + rf.read(1))
    if off == 0:
        return None
    rf.seek(off * 4096)
    (ln,) = struct.unpack('>I', rf.read(4))
    assert rf.read(1) == b'\x02', 'expected zlib'
    return nbtlib.File.from_fileobj(
        _io.BytesIO(zlib.decompress(rf.read(ln - 1))))


def sec_states(chunk, sy):
    secs = chunk.get('sections', chunk.get('Sections', []))
    for s in secs:
        if int(s['Y']) == sy:
            return s.get('block_states')
    return None

SAVES = (r'C:\Users\LOQ\AppData\Roaming\FreesmLauncher\instances\26.3'
         r'\minecraft\saves\New World (1)\dimensions\minecraft\overworld\region')
TMP = r'C:\Users\LOQ\AppData\Local\Temp\opencode\alu4regions'
os.makedirs(TMP, exist_ok=True)

want = set()
cells = []
args = [int(a) for a in sys.argv[1:]]
for i in range(0, len(args), 3):
    cells.append((args[i], args[i + 1], args[i + 2]))
    want.add(((args[i] >> 4) >> 5, (args[i + 2] >> 4) >> 5))
for rn in ['r.%d.%d.mca' % k for k in want]:
    shutil.copyfile(os.path.join(SAVES, rn), os.path.join(TMP, rn))
print('fresh copy done')

rpaths = {}
for k in want:
    rpaths[k] = open(os.path.join(TMP, 'r.%d.%d.mca' % k), 'rb')
cache = {}


def get_block(x, y, z):
    cx, cz = x >> 4, z >> 4
    if (cx, cz) not in cache:
        cache[(cx, cz)] = read_chunk(rpaths[((cx >> 5), (cz >> 5))], cx, cz)
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
    val = (data[idx // per] >> ((idx % per) * bpe)) & ((1 << bpe) - 1)
    return entry_name_props(pal[val])


for c in cells:
    print(c, get_block(*c))
for rf in rpaths.values():
    rf.close()
