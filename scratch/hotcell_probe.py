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


def what(x, y, z):
    for bid, tag in (('minecraft:redstone_wire[power=15]', 'dust15'),
                     ('minecraft:redstone_wire', 'dust'),
                     ('minecraft:repeater', 'repeater'),
                     ('minecraft:redstone_wall_torch', 'torch'),
                     ('minecraft:cobblestone', 'cobble'),
                     ('minecraft:stone', 'stone'),
                     ('minecraft:air', 'AIR')):
        if 'passed' in cmd('execute if block %d %d %d %s' % (x, y, z, bid)).lower():
            return tag
    return '?'


CX, CY, CZ = 543, OY + 1, 300 + 141
print('centre', (CX, CY, CZ), '=', what(CX, CY, CZ))
for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
    c = (CX + dx, CY, CZ + dz)
    print('  same level %-20s %s' % (str(c), what(*c)))
print('  above  %-24s %s' % (str((CX, CY + 1, CZ)), what(CX, CY + 1, CZ)))
print('  below  %-24s %s' % (str((CX, CY - 1, CZ)), what(CX, CY - 1, CZ)))
# is the power steady or a one-off? read twice
time.sleep(4)
print('re-read centre:', cmd('execute if block %d %d %d minecraft:redstone_wire[power=15]' % (CX, CY, CZ)))
print('lamp S2 (build 545,141 -> world):',
      cmd('execute if block 545 65 441 minecraft:redstone_lamp[lit=true]'))