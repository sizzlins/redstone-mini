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


def pwr(c):
    for l in range(15, 0, -1):
        if 'passed' in cmd('execute if block %d %d %d '
                            'minecraft:redstone_wire[power=%d]' % (c[0], c[1], c[2], l)).lower():
            return l
    return 0


# all levers OFF
OFF = 'minecraft:lever[face=floor,facing=north,powered=false]'
import pickle
m = pickle.load(open(r'D:\redstone-mini\scratch\add8p2ind.pkl', 'rb'))
for (x, z), name in m['io']['levers'].items():
    cmd('setblock %d %d %d %s' % (x, OY + 1, ZO + z, OFF))
time.sleep(8)

for bz in (138, 140, 143):
    c = (543, OY + 1, ZO + bz)
    print('repeater z=%d powered=%s   dust z=%d pwr=%2d  dust z=%d pwr=%2d'
          % (bz,
             cmd('execute if block %d %d %d minecraft:repeater[powered=true]' % c),
             bz - 1, pwr((543, OY + 1, ZO + bz - 1)),
             bz + 1, pwr((543, OY + 1, ZO + bz + 1))))
print()
print('S2 lamp :', cmd('execute if block 545 65 441 minecraft:redstone_lamp[lit=true]'))
print('S0 lamp :', cmd('execute if block 49 65 436 minecraft:redstone_lamp[lit=true]'))
print('all-zero expectation: every S lamp dark')