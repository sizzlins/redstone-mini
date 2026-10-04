"""A/B in ONE session: does the server tick (torch + gametime) while a
repeater stays dead? Proves tester-alive vs repeater-broken.
Usage: ab.py (no args).
"""
import sys
import time

sys.path.insert(0, 'D:/redstone-mini/scratch')
from rcon import Rcon

OY = 70
OX, OZ = 150, -60


def yes(rc, tag, cond):
    rc.exec('execute store success score ' + tag + ' __rig ' + cond)
    return 'has 1' in rc.exec('scoreboard players get ' + tag + ' __rig')


def gametime(rc):
    o = rc.exec('time query gametime')
    return o.split()[-2] if 'tick' in o else o


def main():
    pw = open('D:/put gitrepos here/mc-server/rcon_pass.txt').read().strip()
    rc = Rcon('127.0.0.1', 25575, pw, timeout=120)
    print('t0 =', gametime(rc), flush=True)
    # --- test A: torch (needs a scheduled tick) ---
    st = (OX, OY + 1, OZ)
    tor = (OX + 1, OY + 1, OZ)
    lev = (OX, OY, OZ)
    for p in (st, tor, lev):
        rc.exec('setblock %d %d %d minecraft:stone' % (p[0], p[1] - 1, p[2]))
        rc.exec('setblock %d %d %d minecraft:air' % p)
    rc.exec('setblock %d %d %d minecraft:stone' % st)
    rc.exec('setblock %d %d %d minecraft:lever[face=floor,facing=north,powered=true]' % lev)
    rc.exec('setblock %d %d %d minecraft:redstone_wall_torch[facing=west]' % tor)
    time.sleep(6)
    a1 = yes(rc, 'A1', 'if block %d %d %d '
            'minecraft:redstone_wall_torch[lit=false]' % tor)
    rc.exec('setblock %d %d %d minecraft:lever[face=floor,facing=north,powered=false]' % lev)
    time.sleep(6)
    a2 = yes(rc, 'A2', 'if block %d %d %d '
            'minecraft:redstone_wall_torch[lit=true]' % tor)
    print('TEST A torch: burned_out_when_powered=%s relit_when_unpowered=%s'
          ' (both True => ticks run)' % (a1, a2), flush=True)
    # --- test B: repeater, same session, same spot ---
    back = (OX, OY, OZ + 2)
    rep = (OX, OY, OZ + 1)
    front = (OX, OY, OZ)
    for p in (back, rep, front):
        rc.exec('setblock %d %d %d minecraft:stone' % (p[0], p[1] - 1, p[2]))
        rc.exec('setblock %d %d %d minecraft:air' % p)
    rc.exec('setblock %d %d %d minecraft:redstone_block' % back)
    rc.exec('setblock %d %d %d minecraft:redstone_wire' % front)
    rc.exec('setblock %d %d %d minecraft:repeater[facing=north]' % rep)
    time.sleep(15)
    b1 = yes(rc, 'B1', 'if block %d %d %d '
            'minecraft:repeater[powered=true]' % rep)
    b2 = yes(rc, 'B2', 'if block %d %d %d '
            'minecraft:redstone_wire[power=15]' % front)
    print('TEST B repeater: powered=%s front_dust15=%s '
          '(True True => repeaters work)' % (b1, b2), flush=True)
    print('t1 =', gametime(rc), flush=True)
    for p in (st, tor, lev, back, rep, front):
        rc.exec('setblock %d %d %d minecraft:air' % p)
    rc.close()


if __name__ == '__main__':
    main()
