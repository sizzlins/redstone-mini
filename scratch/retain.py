"""Which palette atoms actually RETAIN after setblock on this server?
Places each on a stone floor, waits, then checks identity. Anything that
reports 'Changed' but is not there afterwards is unusable in a pasted build.
Usage: retain.py <port> <passfile> [x y z].
"""
import sys
import time

sys.path.insert(0, 'D:/redstone-mini/scratch')
from rcon import Rcon

BIDS = [
    'minecraft:stone',
    'minecraft:glass',
    'minecraft:redstone_wire',
    'minecraft:repeater[facing=north]',
    'minecraft:comparator[facing=north]',
    'minecraft:lever[face=floor,facing=north,powered=true]',
    'minecraft:redstone_torch',
    'minecraft:redstone_wall_torch[facing=north]',
    'minecraft:redstone_lamp',
    'minecraft:redstone_block',
    'minecraft:target',
]


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 25576
    pf = sys.argv[2] if len(sys.argv) > 2 else \
        'D:/put gitrepos here/mc-server-1.21/rcon_pass.txt'
    X = int(sys.argv[3]) if len(sys.argv) > 3 else 48
    Y = int(sys.argv[4]) if len(sys.argv) > 4 else 70
    Z = int(sys.argv[5]) if len(sys.argv) > 5 else 48
    pw = open(pf).read().strip()
    rc = Rcon('127.0.0.1', port, pw, timeout=120)
    rc.exec('scoreboard objectives add __rig dummy')
    for i, bid in enumerate(BIDS):
        p = (X + i * 2, Y, Z)
        base = bid.split('[')[0]
        # floor under each so floor-mounted things have support
        rc.exec('setblock %d %d %d minecraft:stone' % (p[0], p[1] - 1, p[2]))
        rc.exec('setblock %d %d %d minecraft:air' % p)
        out = rc.exec('setblock %d %d %d %s' % (p + (bid,)))
        time.sleep(1.5)
        tag = 'B%d' % i
        rc.exec('execute store success score %s __rig if block %d %d %d %s'
                % ((tag,) + p + (base,)))
        there = 'has 1' in rc.exec('scoreboard players get %s __rig' % tag)
        tag2 = 'A%d' % i
        rc.exec('execute store success score %s __rig if block %d %d %d '
                'minecraft:air' % ((tag2,) + p))
        air = 'has 1' in rc.exec('scoreboard players get %s __rig' % tag2)
        print('%-46s set=%-28s retained=%s is_air=%s'
              % (bid, out.replace('Changed the block at', 'CHANGED')[:28],
                 there, air), flush=True)
    rc.close()


if __name__ == '__main__':
    main()
