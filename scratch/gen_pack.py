"""Regenerate the alu4 datapack functions for a paste origin.
Usage: python scratch/gen_pack.py OX OY OZ
Writes into the New World (1) datapack. All tellraws use @a (works both
manual and scheduled). Probe/coords derive from scratch/alu4bank.pkl.
"""
import pickle
import os
import sys

OX, OY, OZ = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
ROOT = (r'C:\Users\LOQ\AppData\Roaming\FreesmLauncher\instances\26.3'
        r'\minecraft\saves\New World (1)\datapacks\alu4\data\alu4\function')


def W(c):
    return (c[0] + OX, c[1] + OY, c[2] + OZ)


def emit(name, lines):
    with open(os.path.join(ROOT, name + '.mcfunction'), 'w') as f:
        f.write('\n'.join(lines) + '\n')
    print('wrote', name, len(lines), 'lines')


m = pickle.load(open('scratch/alu4bank.pkl', 'rb'))
blocks, io = m['blocks'], m['io']

# --- levers: order left-to-right 1..10 ---
order = ['B0', 'A0', 'B1', 'A1', 'B2', 'A2', 'OP1', 'OP0', 'B3', 'A3']
lev = {v: k for k, v in io['levers'].items()}
lines = []
for i, nm in enumerate(order, 1):
    c = W(lev[nm] + (1,) if len(lev[nm]) == 2 else lev[nm])
    x, y, z = lev[nm][0] + OX, 1 + OY, lev[nm][1] + OZ
    lines.append(
        'execute if block %d %d %d minecraft:lever[powered=true] run tellraw @a '
        '{"text": "%d:%s ON", "color": "green"}' % (x, y, z, i, nm))
    lines.append(
        'execute if block %d %d %d minecraft:lever[powered=false] run tellraw @a '
        '{"text": "%d:%s off", "color": "gray"}' % (x, y, z, i, nm))
emit('levers', lines)

LV = {'B0': (3, 3), 'A0': (3, 13), 'B1': (3, 23), 'A1': (3, 33),
      'B2': (3, 43), 'A2': (3, 53), 'OP1': (3, 63), 'OP0': (3, 73),
      'B3': (3, 83), 'A3': (3, 93)}


def lever_set(powered):
    out = []
    for nm in order:
        x, z = LV[nm]
        out.append('setblock %d %d %d minecraft:lever[face=floor,facing=north,powered=%s]'
                   % (x + OX, 1 + OY, z + OZ, powered))
    return out


VECS = {
    'vec_t1': set(),
    'vec_t2a': set(order),
    'vec_t2b': set(order) - {'OP0'},
    'vec_t2c': set(order) - {'OP1'},
    'vec_t3': {'B0', 'A0', 'OP1'},
    'vec_t4': {'B0', 'A0', 'B1', 'A2', 'OP1'},
}
for name, on in VECS.items():
    out = []
    for nm in order:
        x, z = LV[nm]
        p = 'true' if nm in on else 'false'
        out.append('setblock %d %d %d minecraft:lever[face=floor,facing=north,powered=%s]'
                   % (x + OX, 1 + OY, z + OZ, p))
    emit(name, out)

# --- lamps (io keys are (x, z), lamp y=1) ---
lamps = [(nm, (c[0], 1, c[1])) for c, nm in io['lamps'].items()]
lines = []
for nm, c in sorted(lamps):
    x, y, z = W(c)
    lines.append(
        'execute if block %d %d %d minecraft:redstone_lamp[lit=true] run tellraw @a '
        '{"text": "%s=1", "color": "green"}' % (x, y, z, nm))
    lines.append(
        'execute if block %d %d %d minecraft:redstone_lamp[lit=false] run tellraw @a '
        '{"text": "%s=0", "color": "gray"}' % (x, y, z, nm))
emit('readsay', lines)
# manual alias with same content
emit('read', lines)

# --- wire probes: (fname, [(label, localcell)]) ---
nets = io['nets']


def cell(net, idx=0, end='east'):
    cells = sorted(c for c, n in nets.items() if n == net)
    if end == 'east':
        return cells[-1 - idx]
    return cells[idx]


PROBES = {
    'probesay': [('o22feed', (1025, 1, 281)), ('t32feed', (1027, 1, 279)),
                 ('Y2stub', (1028, 1, 281))],
    'probesay2': [('o22w', (1004, 1, 270)), ('o22a', (1009, 1, 281)),
                  ('o22b', (1017, 1, 281)), ('C4', (1502, 1, 250)),
                  ('m4', (1510, 1, 251))],
    'probesay3': [('o12e', cell('o12')), ('t22e', cell('t22')),
                  ('U3e', cell('U3')), ('A3B3e', cell('A3B3'))],
    'probesay4': [('m22e', cell('m22')), ('S2e', cell('S2')),
                  ('A3B3w', (1482, 1, 227)), ('C4b', (1502, 1, 250))],
    'probesay5': [('t22w', cell('t22', end='west')),
                  ('t22m', (1004, 1, 240)),
                  ('m22w', cell('m22', end='west')),
                  ('m22m', (999, 1, 231)),
                  ('S2w', cell('S2', end='west')),
                  ('S2m', (990, 1, 219)),
                  ('C2w', cell('C2', end='west')),
                  ('C2m', (908, 1, 174)),
                  ('C2e', cell('C2'))],
}
for fname, pts in PROBES.items():
    lines = []
    for label, c in pts:
        x, y, z = W(c)
        lines.append(
            'execute unless block %d %d %d minecraft:redstone_wire run tellraw @a '
            '{"text": "%s=NODUST", "color": "yellow"}' % (x, y, z, label))
        lines.append(
            'execute if block %d %d %d minecraft:redstone_wire[power=0] run tellraw @a '
            '{"text": "%s=0", "color": "gray"}' % (x, y, z, label))
        lines.append(
            'execute unless block %d %d %d minecraft:redstone_wire[power=0] run tellraw @a '
            '{"text": "%s=HOT", "color": "red"}' % (x, y, z, label))
    emit(fname, lines)

# --- forceload strips covering footprint [OX,OX+1979]x[OZ,OZ+284] ---
x0, x1, z0, z1 = OX, OX + 1979, OZ, OZ + 284
cx0, cx1, cz0, cz1 = x0 // 16, x1 // 16, z0 // 16, z1 // 16
lines = []
x = cx0
while x <= cx1:
    w = min(13, cx1 - x + 1)
    while (cz1 - cz0 + 1) * w > 256:
        w -= 1
    lines.append('forceload add %d %d %d %d'
                 % (x * 16, cz0 * 16, (x + w) * 16 - 1, (cz1 + 1) * 16 - 1))
    x += w
lines.append('tellraw @s {"text": "alu4 footprint force-loaded", "color": "green"}')
emit('load', lines)
emit('unload', ['forceload remove all',
                'tellraw @s {"text": "all force-loaded chunks released", "color": "yellow"}'])

# --- boot-once autostart (tick.json calls boot; boot arms once) ---
emit('boot', [
    'scoreboard objectives add alu4run dummy',
    'execute unless score cold alu4run matches 1 run function alu4:arm',
])
emit('arm', [
    'scoreboard players set cold alu4run 1',
    'tellraw @a {"text": "alu4 boot armed: cold read in 90s", "color": "gray"}',
    'schedule function alu4:coldauto 1800t',
])
emit('coldauto', [
    'tellraw @a {"text": "COLD-AUTO read:", "color": "yellow"}',
    'function alu4:probesay',
    'function alu4:probesay2',
    'function alu4:readsay',
    'tellraw @a {"text": "COLD-AUTO DONE", "color": "yellow"}',
])
emit('sweep', [
    'tellraw @a {"text": "SWEEP read:", "color": "yellow"}',
    'function alu4:probesay',
    'function alu4:probesay2',
    'function alu4:probesay3',
    'function alu4:probesay4',
    'function alu4:probesay5',
    'function alu4:readsay',
    'tellraw @a {"text": "SWEEP DONE", "color": "yellow"}',
])
tickdir = os.path.join(ROOT, '..', '..', '..', 'minecraft', 'tags', 'function')
os.makedirs(os.path.normpath(tickdir), exist_ok=True)
with open(os.path.normpath(os.path.join(tickdir, 'tick.json')), 'w') as f:
    f.write('{"values": ["alu4:boot"]}\n')
print('wrote tick.json')
print('origin', (OX, OY, OZ), 'footprint x', x0, x1, 'z', z0, z1,
      'chunks x', cx0, cx1, 'z', cz0, cz1)
