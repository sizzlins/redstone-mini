import pickle
import sys
import time

sys.path.insert(0, r'D:\redstone-mini\scratch')
sys.path.insert(0, r'D:\redstone-mini')
from rcon import Rcon
from sim import _parse_build, _run_vec

PW = open('D:/put gitrepos here/mc-server-1.21/rcon_pass.txt').read().strip()
OY, ZO = 64, 300


def cmd(c, to=180):
    try:
        r = Rcon('127.0.0.1', 25576, PW, timeout=to)
        return str(r._roundtrip(2, c)[0][1])[:140]
    except Exception as e:
        return 'ERR ' + str(e)[:60]


def live_is_zero(c):
    return 'passed' in cmd('execute if block %d %d %d '
                           'minecraft:redstone_wire[power=0]' % c).lower()


def live_power(c):
    for l in range(15, 0, -1):
        if 'passed' in cmd('execute if block %d %d %d '
                            'minecraft:redstone_wire[power=%d]' % (c[0], c[1], c[2], l)).lower():
            return l
    return -1


m = pickle.load(open(r'D:\redstone-mini\scratch\add8p2ind.pkl', 'rb'))
nets = m['io'].get('nets') or {}

OFF = 'minecraft:lever[face=floor,facing=north,powered=false]'
for (x, z), name in m['io']['levers'].items():
    cmd('setblock %d %d %d %s' % (x, OY + 1, ZO + z, OFF))
time.sleep(8)

P = _parse_build([tuple(b) for b in m['blocks']], m['io'])
vec = {k: 0 for k in m['io']['levers'].values()}
_, live, _, _, _, _ = _run_vec(vec, None, P)

# Walk every wire cell in the build, ordered by x, and find the first place
# vanilla disagrees with sim on the all-zero vector.
cells = sorted({(x, y, z) for x, y, z, b in m['blocks']
                if 'redstone_wire' in str(b)})
print('scanning %d wire cells ordered by x ...' % len(cells))
bad = []
for x, y, z in cells:
    c = (x, OY + y, ZO + z)
    sp = live.get((x, y, z), 0)
    if live_is_zero(c):
        if sp != 0:
            bad.append((x, y, z, 0, sp))
            print('  first mismatch at x=%d: game=0 sim=%d %s' % (x, sp, (x, y, z)))
            break
    else:
        gp = live_power(c)
        if gp != sp:
            bad.append((x, y, z, gp, sp))
            print('  mismatch x=%d %s: game=%s sim=%s' % (x, (x, y, z), gp, sp))
print('total mismatches found before stop:', len(bad))