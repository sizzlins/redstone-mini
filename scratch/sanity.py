"""Repeater/comparator sanity on a given server. Usage: sanity.py <port>
<passfile> [ox oy oz]. Verifies tick + diode + comparator in one session.
"""
import sys
import time

sys.path.insert(0, 'D:/redstone-mini/scratch')
from rcon import Rcon


def yes(rc, tag, cond):
    rc.exec('execute store success score ' + tag + ' __rig ' + cond)
    return 'has 1' in rc.exec('scoreboard players get ' + tag + ' __rig')


def gametime(rc):
    o = rc.exec('time query gametime')
    return o.split()[-2] if 'tick' in o else o


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 25576
    pf = sys.argv[2] if len(sys.argv) > 2 else \
        'D:/put gitrepos here/mc-server-1.21/rcon_pass.txt'
    OX = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    OY = int(sys.argv[4]) if len(sys.argv) > 4 else 70
    OZ = int(sys.argv[5]) if len(sys.argv) > 5 else 0
    pw = open(pf).read().strip()
    rc = Rcon('127.0.0.1', port, pw, timeout=120)
    print('version  =>', rc.exec('version')[:120].replace('\n', ' | '))
    print('t0 =', gametime(rc), flush=True)
    back = (OX, OY, OZ + 2)
    rep = (OX, OY, OZ + 1)
    front = (OX, OY, OZ)
    comp = (OX, OY, OZ - 1)
    front2 = (OX, OY, OZ - 2)
    cells = (back, rep, front, comp, front2)
    for p in cells:
        rc.exec('setblock %d %d %d minecraft:stone' % (p[0], p[1] - 1, p[2]))
        rc.exec('setblock %d %d %d minecraft:air' % p)
    # repeater: rblk on input (south), dust on output (north)
    rc.exec('setblock %d %d %d minecraft:redstone_block' % back)
    rc.exec('setblock %d %d %d minecraft:redstone_wire' % front)
    rc.exec('setblock %d %d %d minecraft:repeater[facing=north]' % rep)
    time.sleep(3)
    print('repeater facing=north: powered=%s front_dust15=%s  (True True = OK)'
          % (yes(rc, 'S1', 'if block %d %d %d '
                'minecraft:repeater[powered=true]' % rep),
             yes(rc, 'S2', 'if block %d %d %d '
                'minecraft:redstone_wire[power=15]' % front)), flush=True)
    # comparator: rblk on rear (south), dust on front (north)
    rc.exec('setblock %d %d %d minecraft:air' % rep)
    rc.exec('setblock %d %d %d minecraft:air' % front)
    rc.exec('setblock %d %d %d minecraft:comparator[facing=north]' % comp)
    rc.exec('setblock %d %d %d minecraft:redstone_wire' % front2)
    time.sleep(3)
    nbt = rc.exec('data get block %d %d %d' % comp)
    print('comparator facing=north: powered=%s front_dust15=%s | %s'
          % (yes(rc, 'S3', 'if block %d %d %d '
                'minecraft:comparator[powered=true]' % comp),
             yes(rc, 'S4', 'if block %d %d %d '
                'minecraft:redstone_wire[power=15]' % front2),
             nbt[nbt.find('OutputSignal'):][:30] if 'OutputSignal' in nbt
             else nbt[:60]), flush=True)
    # reverse the comparator to prove the facing convention
    rc.exec('setblock %d %d %d minecraft:air' % comp)
    rc.exec('setblock %d %d %d minecraft:air' % front2)
    rc.exec('setblock %d %d %d minecraft:redstone_wire' % front)
    rc.exec('setblock %d %d %d minecraft:comparator[facing=south]' % rep)
    time.sleep(3)
    print('comparator facing=south (rblk on its front): front_dust15=%s '
          '(True = it sources from the front, i.e. facing=output)'
          % yes(rc, 'S5', 'if block %d %d %d '
                'minecraft:redstone_wire[power=15]' % front), flush=True)
    print('t1 =', gametime(rc), flush=True)
    for p in cells:
        rc.exec('setblock %d %d %d minecraft:air' % p)
    rc.close()


if __name__ == '__main__':
    main()
