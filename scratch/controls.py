"""Controls: prove lamp + dust + rblk work, so the repeater result is real.
1) rblk | lamp            -> lamp lit (rblk powers neighbour)
2) rblk | dust | lamp     -> lamp lit (powered dust powers neighbour)
3) rblk | repeater | lamp -> lamp lit? (the failing case)
Usage: controls.py (no args).
"""
import sys
import time

sys.path.insert(0, 'D:/redstone-mini/scratch')
from rcon import Rcon

OY, OX, OZ = 70, 144, -60


def yes(rc, tag, cond):
    rc.exec('execute store success score ' + tag + ' __rig ' + cond)
    return 'has 1' in rc.exec('scoreboard players get ' + tag + ' __rig')


def run(rc, label, cells, settle=15):
    for p in cells:
        rc.exec('setblock %d %d %d minecraft:stone' % (p[0], p[1] - 1, p[2]))
        rc.exec('setblock %d %d %d minecraft:air' % p)
    for p, bid in cells_bids:
        rc.exec('setblock %d %d %d %s' % (p + bid))
    time.sleep(settle)
    print('%-34s %s' % (label, verify()), flush=True)


def verify():
    return ''


def main():
    global cells_bids
    pw = open('D:/put gitrepos here/mc-server/rcon_pass.txt').read().strip()
    rc = Rcon('127.0.0.1', 25575, pw, timeout=120)
    a = (OX, OY, OZ + 2)
    b = (OX, OY, OZ + 1)
    c = (OX, OY, OZ)
    d = (OX, OY, OZ - 1)

    def setup(pairs):
        global cells_bids
        cells = [p for p, _ in pairs]
        for p in cells:
            rc.exec('setblock %d %d %d minecraft:stone' % (p[0], p[1] - 1, p[2]))
            rc.exec('setblock %d %d %d minecraft:air' % p)
        cells_bids = pairs

    def lamp_state(p):
        return yes(rc, 'L', 'if block %d %d %d '
                   'minecraft:redstone_lamp[lit=true]' % p)

    setup([(a, 'minecraft:redstone_block'), (c, 'minecraft:redstone_lamp')])
    time.sleep(12)
    print('1 rblk(a) ... lamp(c), one gap        lit=%s (expect True)'
          % lamp_state(c), flush=True)
    setup([(a, 'minecraft:redstone_block'), (b, 'minecraft:redstone_wire'),
           (c, 'minecraft:redstone_lamp')])
    time.sleep(12)
    print('2 rblk(a) dust(b) ... lamp(c)        lit=%s (expect True)'
          % lamp_state(c), flush=True)
    setup([(b, 'minecraft:redstone_block'), (c, 'minecraft:repeater[facing=north]'),
           (d, 'minecraft:redstone_lamp')])
    time.sleep(20)
    print('3 rblk(b) repeater(c) lamp(d)       lit=%s (expect True if reps work)'
          % lamp_state(d), flush=True)
    for p in (a, b, c, d):
        rc.exec('setblock %d %d %d minecraft:air' % p)
    rc.close()


if __name__ == '__main__':
    main()
