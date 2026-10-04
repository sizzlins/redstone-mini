"""Readback controls on the clean 1.21.11 bench.
A) rblk adjacent to dust (no repeater) -> dust MUST read 15.
B) torch on floor stone + dust on top  -> dust MUST read 15.
C) rblk adjacent to repeater           -> does the repeater pass it?
If A and B pass and C fails, the readout is sound and repeaters are dead.
Usage: ctrl2.py <port> <passfile> [x y z].
"""
import sys
import time

sys.path.insert(0, 'D:/redstone-mini/scratch')
from rcon import Rcon


def yes(rc, tag, cond):
    rc.exec('execute store success score ' + tag + ' __rig ' + cond)
    return 'has 1' in rc.exec('scoreboard players get ' + tag + ' __rig')


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 25576
    pf = sys.argv[2] if len(sys.argv) > 2 else \
        'D:/put gitrepos here/mc-server-1.21/rcon_pass.txt'
    X = int(sys.argv[3]) if len(sys.argv) > 3 else 16
    Y = int(sys.argv[4]) if len(sys.argv) > 4 else 70
    Z = int(sys.argv[5]) if len(sys.argv) > 5 else 16
    pw = open(pf).read().strip()
    rc = Rcon('127.0.0.1', port, pw, timeout=120)
    rc.exec('scoreboard objectives add __rig dummy')
    A = (X, Y, Z)
    B = (X, Y, Z - 1)
    print('floor =>', rc.exec('setblock %d %d %d minecraft:stone'
                              % (A[0], A[1] - 1, A[2]))[:40])
    # A: rblk | dust
    for p in (A, B):
        rc.exec('setblock %d %d %d minecraft:air' % p)
    print('rblk =>', rc.exec('setblock %d %d %d minecraft:redstone_block'
                              % A)[:45])
    print('dust =>', rc.exec('setblock %d %d %d minecraft:redstone_wire'
                              % B)[:45])
    time.sleep(4)
    print('A) rblk adjacent dust: dust15=%s dust0=%s (expect True/False)'
          % (yes(rc, 'A1', 'if block %d %d %d '
                 'minecraft:redstone_wire[power=15]' % B),
             yes(rc, 'A2', 'if block %d %d %d '
                 'minecraft:redstone_wire[power=0]' % B)), flush=True)
    # B: torch + dust on top
    for p in (A, B):
        rc.exec('setblock %d %d %d minecraft:air' % p)
    print('floor2 =>', rc.exec('setblock %d %d %d minecraft:stone'
                               % (A[0], A[1] - 1, A[2]))[:40])
    print('torch =>', rc.exec('setblock %d %d %d minecraft:redstone_torch'
                              % (A[0], A[1] - 1, A[2]))[:45])
    print('dust2 =>', rc.exec('setblock %d %d %d minecraft:redstone_wire'
                              % (A[0], A[1], A[2]))[:45])
    time.sleep(4)
    print('B) dust above torch: dust15=%s (expect True)'
          % yes(rc, 'B1', 'if block %d %d %d '
                'minecraft:redstone_wire[power=15]' % (A[0], A[1], A[2])),
          flush=True)
    # C: rblk | repeater | dust
    rc.exec('setblock %d %d %d minecraft:air' % (A[0], A[1], A[2]))
    rc.exec('setblock %d %d %d minecraft:redstone_block' % B)
    rc.exec('setblock %d %d %d minecraft:redstone_wire' % (A[0], A[1] - 1, A[2] + 1))
    rc.exec('setblock %d %d %d minecraft:repeater[facing=north]'
            % (A[0], A[1], A[2]))
    time.sleep(4)
    print('C) rblk@B(S) repeater@north dust@-1(N): out15=%s rep_powered=%s'
          % (yes(rc, 'C1', 'if block %d %d %d '
                 'minecraft:redstone_wire[power=15]' % (A[0], A[1] - 1, A[2] + 1)),
             yes(rc, 'C2', 'if block %d %d %d '
                 'minecraft:repeater[powered=true]' % (A[0], A[1], A[2]))),
          flush=True)
    for p in (A, B, (A[0], A[1], A[2]), (A[0], A[1] - 1, A[2] + 1)):
        rc.exec('setblock %d %d %d minecraft:air' % p)
    rc.close()


if __name__ == '__main__':
    main()
