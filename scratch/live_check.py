import json
import pickle
import sys
import time

sys.path.insert(0, r'D:\redstone-mini\scratch')
from rcon import Rcon

PW = open('D:/put gitrepos here/mc-server-1.21/rcon_pass.txt').read().strip()
OY, ZO, SETTLE = 64, 800, 20


def cmd(c, to=180):
    try:
        r = Rcon('127.0.0.1', 25576, PW, timeout=to)
        return str(r._roundtrip(2, c)[0][1])[:140]
    except Exception as e:
        return 'ERR ' + str(e)[:60]


def passed(c):
    return 'passed' in cmd(c).lower()


d = json.load(open(r'D:\redstone-mini\scratch\add8p2ind.v2doc.json'))
lev = {}
for c, n in d['levers']:
    p = [int(v) for v in c.split(',')]
    lev[(p[0], p[-1])] = n
lam = {}
# doc 2-part lamp coords are (x,z) at build y=1; 3-part are literal (x,y,z)
for coord, name in d['lamps']:
    p = [int(v) for v in coord.split(',')]
    if len(p) == 2:
        lam[name] = (p[0], OY + 1, p[1] + ZO)
    else:
        lam[name] = (p[0], OY + p[1], p[2] + ZO)

S = ['S%d' % i for i in range(8)] + ['COUT']
# carry-heavy set: nibble boundaries, the alternating patterns, and full
# overflow (0xFF must light COUT), plus the powers of two.
PATTERNS = [0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80,
            0x0F, 0xF0, 0x55, 0xAA, 0xFF, 0x1F, 0x7F, 0x8F, 0xFE]
vecs = [{}] + [{'A%d' % i: 1 for i in range(8) if p & (1 << i)} for p in PATTERNS]
ok_n = 0
for vec in vecs:
    for (x, z), name in lev.items():
        want = 'true' if name in vec else 'false'
        cmd('setblock %d %d %d minecraft:lever[face=floor,facing=north,powered=%s]'
            % (x, OY + 1, z + ZO, want))
    time.sleep(3)
    # read the levers BACK: if any did not take, the vector is not the one we asked for
    stuck = [n for (x, z), n in lev.items()
             if passed('execute if block %d %d %d minecraft:lever[powered=%s]'
                       % (x, OY + 1, z + ZO, 'true' if n in vec else 'false')) is False]
    time.sleep(SETTLE)
    got = {n: passed('execute if block %d %d %d minecraft:redstone_lamp[lit=true]' % c)
           for n, c in lam.items()}
    val = sum((1 << i) for i in range(8) if got['S%d' % i])
    val += 256 if got['COUT'] else 0
    exp = sum((1 << i) for i, n in enumerate(['A%d' % i for i in range(8)]) if n in vec)
    ind = all(got[n + 'L'] == (n in vec) for n in ['A%d' % i for i in range(8)])
    good = (val == exp) and ind and not stuck
    ok_n += good
    print('A-on=%-14s sum=%3d expected=%3d  indicators_ok=%-5s levers_stuck=%-14s %s'
          % (','.join(sorted(vec)) or '-', val, exp, ind, stuck or 'none',
             'GREEN' if good else 'RED'))

print()
print('LIVE VERDICT: %d/%d vectors green' % (ok_n, len(vecs)))