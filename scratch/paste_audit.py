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


m = pickle.load(open(r'D:\redstone-mini\scratch\add8p2ind.pkl', 'rb'))
want = {(x, y, z): b for x, y, z, b in m['blocks']}
have = {(x, OY + y, ZO + z) for x, y, z, b in m['blocks']}

# Every world cell the build claims, inside a box around the sum lamps.
SX, SZ = 40, 120
box = [(x, OY + 1, ZO + z) for x in range(0, SX) for z in range(SZ, SZ + 40)]
missing = [c for c in box if c not in have and c[1] == 65]
print('cells in scan window that the build never claimed:', len(missing))

# Which claimed cells are actually AIR in the world? A claimed cell that is
# air is a paste that did not land -- that is the whole question.
import random
random.seed(7)
samp = random.sample(sorted(have), 300)
air = []
for c in samp:
    if 'passed' in cmd('execute if block %d %d %d minecraft:air' % c).lower():
        air.append(c)
print('sampled 300 claimed cells, AIR in world: %d' % len(air))
if air:
    print('  first 8:', air[:8])