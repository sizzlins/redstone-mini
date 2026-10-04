"""All four (source side x facing) repeater combos on a clean bench, with
per-cell verification, to settle both 'do repeaters work' and 'which side
is the input'. Usage: four.py <port> <passfile> [x y z].
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
    X = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    Y = int(sys.argv[4]) if len(sys.argv) > 4 else 70
    Z = int(sys.argv[5]) if len(sys.argv) > 5 else 8
    pw = open(pf).read().strip()
    rc = Rcon('127.0.0.1', port, pw, timeout=120)
    rc.exec('scoreboard objectives add __rig dummy')
    S = (X, Y, Z + 1)
    M = (X, Y, Z)
    N = (X, Y, Z - 1)
    print('floor =>', [rc.exec('setblock %d %d %d minecraft:stone'
                               % (p[0], p[1] - 1, p[2]))[:20]
                        for p in (S, M, N)], flush=True)
    combos = [('rblk@S', S, 'north', N), ('rblk@S', S, 'south', N),
              ('rblk@N', N, 'north', S), ('rblk@N', N, 'south', S)]
    for i, (sname, src, facing, dst) in enumerate(combos):
        for p in (S, M, N):
            rc.exec('setblock %d %d %d minecraft:air' % p)
        rc.exec('setblock %d %d %d minecraft:redstone_block' % src)
        rc.exec('setblock %d %d %d minecraft:redstone_wire' % dst)
        rc.exec('setblock %d %d %d minecraft:repeater[facing=%s]'
                % (M + (facing,)))
        v_src = yes(rc, 'a%d' % i, 'if block %d %d %d '
                    'minecraft:redstone_block' % src)
        v_rep = yes(rc, 'b%d' % i, 'if block %d %d %d '
                    'minecraft:repeater[facing=%s]' % (M + (facing,)))
        v_dst = yes(rc, 'c%d' % i, 'if block %d %d %d '
                    'minecraft:redstone_wire' % dst)
        time.sleep(5)
        out = yes(rc, 'd%d' % i, 'if block %d %d %d '
                  'minecraft:redstone_wire[power=15]' % dst)
        pwr = yes(rc, 'e%d' % i, 'if block %d %d %d '
                  'minecraft:repeater[powered=true]' % M)
        print('%s facing=%-5s placed(blk=%s rep=%s dust=%s) -> out15=%s '
              'rep_powered=%s' % (sname, facing, v_src, v_rep, v_dst, out, pwr),
              flush=True)
    for p in (S, M, N):
        rc.exec('setblock %d %d %d minecraft:air' % p)
    rc.close()


if __name__ == '__main__':
    main()
