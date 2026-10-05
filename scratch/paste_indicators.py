import sys
import time

sys.path.insert(0, r'D:\redstone-mini\scratch')
from rcon import Rcon

PW = open('D:/put gitrepos here/mc-server-1.21/rcon_pass.txt').read().strip()


def cmd(c, to=180):
    try:
        r = Rcon('127.0.0.1', 25576, PW, timeout=to)
        return str(r._roundtrip(2, c)[0][1])[:160]
    except Exception as e:
        return 'ERR ' + str(e)[:70]


# 16 indicator lamps: world (2, 65, z) for each lever at (3, 65, z)
LAMPS = [('B0', 2, 3), ('A0', 2, 13), ('B1', 2, 23), ('A1', 2, 33),
         ('B2', 2, 43), ('A2', 2, 53), ('B3', 2, 63), ('A3', 2, 73),
         ('B4', 2, 83), ('A4', 2, 93), ('B5', 2, 103), ('A5', 2, 113),
         ('B6', 2, 123), ('A6', 2, 133), ('B7', 2, 143), ('A7', 2, 153)]

print('--- place 16 indicator lamps at x=2 (west of each lever) ---')
for name, x, z in LAMPS:
    print('  %-3s %s' % (name, cmd('setblock %d 65 %d minecraft:redstone_lamp' % (x, z))))

time.sleep(3)
print()
print('--- read them with A0=1 only (B0=0 A0=1 -> only A0L should be lit) ---')
L = 'minecraft:lever[face=floor,facing=north,powered=true]'
OFF = 'minecraft:lever[face=floor,facing=north,powered=false]'
print('  set A0 on :', cmd('setblock 3 65 13 ' + L))
time.sleep(4)
lit = []
for name, x, z in LAMPS:
    if 'passed' in cmd('execute if block %d 65 %d minecraft:redstone_lamp[lit=true]'
                       % (x, z)).lower():
        lit.append(name)
print('  lit:', lit, '(want only A0)')

print()
print('--- all 16 on ---')
for _, x, z in LAMPS:
    cmd('setblock 3 65 %d ' % z + L)
time.sleep(6)
lit = [n for n, x, z in LAMPS
       if 'passed' in cmd('execute if block %d 65 %d minecraft:redstone_lamp[lit=true]'
                          % (x, z)).lower()]
print('  lit: %d/16 %s' % (len(lit), lit))

print()
print('--- all off ---')
for _, x, z in LAMPS:
    cmd('setblock 3 65 %d ' % z + OFF)
time.sleep(6)
lit = [n for n, x, z in LAMPS
       if 'passed' in cmd('execute if block %d 65 %d minecraft:redstone_lamp[lit=true]'
                          % (x, z)).lower()]
print('  lit: %d/16 %s (want 0)' % (len(lit), lit))