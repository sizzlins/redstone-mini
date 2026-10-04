"""Raw-response diagnostic: is the blockstate readback working at all?
Usage: raw.py <port> <passfile> [x y z].
"""
import sys
import time

sys.path.insert(0, 'D:/redstone-mini/scratch')
from rcon import Rcon


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 25576
    pf = sys.argv[2] if len(sys.argv) > 2 else \
        'D:/put gitrepos here/mc-server-1.21/rcon_pass.txt'
    X = int(sys.argv[3]) if len(sys.argv) > 3 else 24
    Y = int(sys.argv[4]) if len(sys.argv) > 4 else 70
    Z = int(sys.argv[5]) if len(sys.argv) > 5 else 24
    pw = open(pf).read().strip()
    rc = Rcon('127.0.0.1', port, pw, timeout=120)
    rc.exec('scoreboard objectives add __rig dummy')
    A = (X, Y, Z)
    B = (X, Y, Z - 1)
    print('floor =>', repr(rc.exec('setblock %d %d %d minecraft:stone'
                                   % (A[0], A[1] - 1, A[2]))))
    print('rblk  =>', repr(rc.exec('setblock %d %d %d minecraft:redstone_block'
                                   % A)))
    print('dust  =>', repr(rc.exec('setblock %d %d %d minecraft:redstone_wire'
                                   % B)))
    print('chunk marks:', repr(rc.exec('forceload query %d %d' % (B[0],
                                                                    B[2]))))
    time.sleep(3)
    probes = [
        ('identity (no props)', 'if block %d %d %d minecraft:redstone_wire'
         % B),
        ('power=15', 'if block %d %d %d minecraft:redstone_wire[power=15]' % B),
        ('power=1', 'if block %d %d %d minecraft:redstone_wire[power=1]' % B),
        ('power=0', 'if block %d %d %d minecraft:redstone_wire[power=0]' % B),
        ('rblk identity', 'if block %d %d %d minecraft:redstone_block' % A),
        ('floor stone', 'if block %d %d %d minecraft:stone'
         % (A[0], A[1] - 1, A[2])),
        ('bogus property',
         'if block %d %d %d minecraft:redstone_wire[power=99]' % B),
    ]
    for i, (label, cond) in enumerate(probes):
        s = rc.exec('execute store success score D%d __rig %s' % (i, cond))
        g = rc.exec('scoreboard players get D%d __rig' % i)
        print('%-22s store=%-18r get=%r' % (label, s, g), flush=True)
    for p in (A, B):
        rc.exec('setblock %d %d %d minecraft:air' % p)
    rc.close()


if __name__ == '__main__':
    main()
