import pickle
import sys
import time

sys.path.insert(0, r'D:\redstone-mini\scratch')
from rcon import Rcon

PW = open('D:/put gitrepos here/mc-server-1.21/rcon_pass.txt').read().strip()
OY, ZO = 64, 300


def cmd(c, to=180):
    try:
        r = Rcon('127.0.0.1', 25576, PW, timeout=to)
        return str(r._roundtrip(2, c)[0][1])[:140]
    except Exception as e:
        return 'ERR ' + str(e)[:60]


def lit(x, y, z, lvl):
    return 'passed' in cmd('execute if block %d %d %d '
                            'minecraft:redstone_wire[power=%d]' % (x, y, z, lvl)).lower()


m = pickle.load(open(r'D:\redstone-mini\scratch\add8p2ind.pkl', 'rb'))
# every lever OFF first, so the honest expectation is all-dark
OFF = 'minecraft:lever[face=floor,facing=north,powered=false]'
for (x, z), name in m['io']['levers'].items():
    cmd('setblock %d %d %d %s' % (x, OY + 1, ZO + z, OFF))
time.sleep(6)

# S2's lamp and its tap, plus the S2 net's cells from the nets table
nets = m['io'].get('nets') or {}
s2 = [c for c, n in nets.items() if n == 'S2']
print('S2 net cells in build:', len(s2))
lamp = m['io']['lamps'].get('S2')
print('S2 lamp pin (build):', lamp)

# read the live power of a spread of S2 cells
probe = sorted(s2, key=lambda c: c[0])[:1] + \
    sorted(s2, key=lambda c: c[0])[len(s2) // 4::max(1, len(s2) // 4)][:6]
for c in probe:
    wx, wy, wz = c[0], OY + c[1], ZO + c[2]
    levels = [l for l in (15, 14, 13, 12, 11, 10, 9, 8, 1) if lit(wx, wy, wz, l)]
    print('  S2 cell %-18s live power: %s' % (str(c), levels or 'dark (0)'))

# and the lamp itself
lx, lz = lamp[0], lamp[1] if len(lamp) == 2 else lamp[2]
print('S2 lamp live:', cmd('execute if block %d %d %d minecraft:redstone_lamp[lit=true]'
                           % (lx, OY + 1, ZO + lz)))
# compare against sim on the same all-zero vector
from sim import _parse_build, _run_vec
P = _parse_build([tuple(b) for b in m['blocks']], m['io'])
vec = {k: 0 for k in m['io']['levers'].values()}
got, live, _, _, _, _ = _run_vec(vec, None, P)
sims2 = {k: int(p) for k, p in live.items() if k[0] == lx and k[2] == lz}
print('sim power at that lamp cell:', sims2 or 'dark (0)')
print('sim S2 lamp verdict:', bool(got.get('S2')))