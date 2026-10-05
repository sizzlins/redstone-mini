import pickle
import sys
import time

sys.path.insert(0, r'D:\redstone-mini\scratch')
sys.path.insert(0, r'D:\redstone-mini')
from rcon import Rcon
from sim import _parse_build, _run_vec

PW = open('D:/put gitrepos here/mc-server-1.21/rcon_pass.txt').read().strip()
OY, ZO = 64, 800


def cmd(c, to=180):
    try:
        r = Rcon('127.0.0.1', 25576, PW, timeout=to)
        return str(r._roundtrip(2, c)[0][1])[:140]
    except Exception as e:
        return 'ERR ' + str(e)[:60]


def pwr(c):
    for l in range(15, 0, -1):
        if 'passed' in cmd('execute if block %d %d %d '
                            'minecraft:redstone_wire[power=%d]' % (c[0], c[1], c[2], l)).lower():
            return l
    return 0


m = pickle.load(open(r'D:\redstone-mini\scratch\add8p2ind.pkl', 'rb'))
d = {(x, y, z): str(b) for x, y, z, b in m['blocks']}
lev = m['io']['levers']

# A3 = 1  -> expected sum 8, so S3 must light
for (x, z), name in lev.items():
    cmd('setblock %d %d %d minecraft:lever[face=floor,facing=north,powered=%s]'
        % (x, OY + 1, ZO + z, 'true' if name == 'A3' else 'false'))
time.sleep(10)
print('A3 on:  S3 lamp lit =',
      cmd('execute if block 823 65 941 minecraft:redstone_lamp[lit=true]'))

P = _parse_build([tuple(b) for b in m['blocks']], m['io'])
vec = {k: (1 if k == 'A3' else 0) for k in lev.values()}
_, live, _, _, _, _ = _run_vec(vec, None, P)
print('sim says S3 lit =', bool(live.get((823, 1, 141), 0) > 0)
      or 'see verdict')

# the comparator that drives S3
cx, cz = 823, 139
print()
print('comparator block:', d.get((cx, 1, cz)))
print('  live powered  =', cmd('execute if block %d %d %d minecraft:comparator[powered=true]'
                               % (cx, OY + 1, ZO + cz)))
for side, (dx, dz) in (('back', (-1, 0)), ('left', (0, -1)), ('right', (0, 1))):
    c = (cx + dx, OY + 1, ZO + cz + dz)
    blk = d.get((cx + dx, 1, cz + dz))
    print('  %-5s %-16s game_pwr=%2d sim=%2d  build=%s'
          % (side, str(c), pwr(c), live.get((cx + dx, 1, cz + dz), 0),
             str(blk).split('[')[0].replace('minecraft:', '') if blk else '-'))
print()
print('output side of comparator, z=%d: game_pwr=%d'
      % (cz + 1, pwr((cx, OY + 1, ZO + cz + 1))))
print('sim  output side        : %d' % live.get((cx, 1, cz + 1), 0))