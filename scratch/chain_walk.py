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


def live_power(c):
    """max power 0..15 the game reports for a wire cell, else 0"""
    for l in (15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1):
        if 'passed' in cmd('execute if block %d %d %d '
                            'minecraft:redstone_wire[power=%d]' % (c[0], c[1], c[2], l)).lower():
            return l
    return 0


m = pickle.load(open(r'D:\redstone-mini\scratch\add8p2ind.pkl', 'rb'))
nets = m['io'].get('nets') or {}

# all levers OFF
OFF = 'minecraft:lever[face=floor,facing=north,powered=false]'
for (x, z), name in m['io']['levers'].items():
    cmd('setblock %d %d %d %s' % (x, OY + 1, ZO + z, OFF))
time.sleep(6)

# sim expectation for all-zero
P = _parse_build([tuple(b) for b in m['blocks']], m['io'])
vec = {k: 0 for k in m['io']['levers'].values()}
_, live, _, _, _, _ = _run_vec(vec, None, P)

# walk the carry-bearing nets, lowest x first, and find the first hot cell
for net in ('C1', 'C2', 'S1', 'S2'):
    cells = sorted([c for c, n in nets.items() if n == net])
    if not cells:
        print('%s: not in nets table' % net)
        continue
    wire = [c for c in cells if abs(c[0]) < 10000]
    first_hot = None
    for c in cells:
        wx, wy, wz = c[0], OY + c[1], ZO + c[2]
        if 'passed' not in cmd('execute if block %d %d %d '
                               'minecraft:repeater' % (wx, wy, wz)).lower():
            continue
        p = live_power((c[0] + 1, c[1], c[2]))
        sp = live.get((c[0], c[1], c[2]), 0)
        print('  %-3s rep %-16s game_input=%2d sim=%2d %s'
              % (net, str(c), p, sp, '<-- MISMATCH' if p != sp else ''))
        if first_hot is None and p != sp:
            first_hot = c
    print('%s: %d cells' % (net, len(cells)), 'first mismatch:', first_hot)