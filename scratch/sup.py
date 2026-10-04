"""Fully-supported repeater test with per-step verification.
Every cell gets a stone floor first (dust/repeater/torch need support).
Usage: sup.py <port> <passfile> [x y z].
"""
import sys
import time

sys.path.insert(0, 'D:/redstone-mini/scratch')
from rcon import Rcon


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 25576
    pf = sys.argv[2] if len(sys.argv) > 2 else \
        'D:/put gitrepos here/mc-server-1.21/rcon_pass.txt'
    X = int(sys.argv[3]) if len(sys.argv) > 3 else 80
    Y = int(sys.argv[4]) if len(sys.argv) > 4 else 70
    Z = int(sys.argv[5]) if len(sys.argv) > 5 else 80
    pw = open(pf).read().strip()
    rc = Rcon('127.0.0.1', port, pw, timeout=120)
    rc.exec('scoreboard objectives add __rig dummy')

    def isb(tag, pos, kind):
        rc.exec('execute store success score %s __rig if block %d %d %d %s'
                % ((tag,) + pos + (kind,)))
        return 'has 1' in rc.exec('scoreboard players get %s __rig' % tag)

    S = (X, Y, Z + 1)      # south
    M = (X, Y, Z)
    N = (X, Y, Z - 1)      # north
    cells = (S, M, N)
    for p in cells:
        rc.exec('setblock %d %d %d minecraft:stone' % (p[0], p[1] - 1, p[2]))
    print('STEP 1 readout validation: rblk | dust, both supported')
    for p in cells:
        rc.exec('setblock %d %d %d minecraft:air' % p)
    rc.exec('setblock %d %d %d minecraft:redstone_block' % S)
    rc.exec('setblock %d %d %d minecraft:redstone_wire' % N)
    time.sleep(2)
    print('  rblk_there=%s dust_there=%s dust15=%s dust0=%s  (want T/T/T/F)'
          % (isb('v1', S, 'minecraft:redstone_block'),
             isb('v2', N, 'minecraft:redstone_wire'),
             isb('v3', N, 'minecraft:redstone_wire[power=15]'),
             isb('v4', N, 'minecraft:redstone_wire[power=0]')), flush=True)
    print('STEP 2 repeater in the middle, rblk behind (facing north)')
    rc.exec('setblock %d %d %d minecraft:repeater[facing=north]' % M)
    time.sleep(3)
    print('  rep_there=%s rep_powered=%s dust15=%s (want T/T/T)'
          % (isb('v5', M, 'minecraft:repeater'),
             isb('v6', M, 'minecraft:repeater[powered=true]'),
             isb('v7', N, 'minecraft:redstone_wire[power=15]')), flush=True)
    print('STEP 3 same but facing=south (input would be the far side)')
    rc.exec('setblock %d %d %d minecraft:repeater[facing=south]' % M)
    time.sleep(3)
    print('  rep_there=%s rep_powered=%s dust15=%s (want T/F/F)'
          % (isb('v8', M, 'minecraft:repeater'),
             isb('v9', M, 'minecraft:repeater[powered=true]'),
             isb('vA', N, 'minecraft:redstone_wire[power=15]')), flush=True)
    print('STEP 4 dust feeds the repeater directly (input cell = dust)')
    for p in cells:
        rc.exec('setblock %d %d %d minecraft:air' % p)
    rc.exec('setblock %d %d %d minecraft:redstone_block' % S)
    rc.exec('setblock %d %d %d minecraft:redstone_wire' % M)
    rc.exec('setblock %d %d %d minecraft:redstone_wire' % N)
    rc.exec('setblock %d %d %d minecraft:repeater[facing=north]'
            % (X, Y, Z + 1))
    # repeater between dust(M) and dust(N): move it properly
    rc.exec('setblock %d %d %d minecraft:redstone_block' % S)
    rc.exec('setblock %d %d %d minecraft:redstone_wire' % M)
    rc.exec('setblock %d %d %d minecraft:air' % N)
    rc.exec('setblock %d %d %d minecraft:repeater[facing=north]'
            % (X, Y, Z))
    time.sleep(3)
    print('  setup: rblk@S dust@M rep? (rep overwritten) -- skip', flush=True)
    print('STEP 5 clean repeater between two supported dust cells')
    for p in cells:
        rc.exec('setblock %d %d %d minecraft:air' % p)
    rc.exec('setblock %d %d %d minecraft:redstone_block' % S)
    rc.exec('setblock %d %d %d minecraft:redstone_wire' % N)
    rc.exec('setblock %d %d %d minecraft:redstone_wire' % (X, Y, Z + 2))
    rc.exec('setblock %d %d %d minecraft:repeater[facing=north]' % M)
    time.sleep(3)
    print('  rblk@S dust@(Z+2) rep@M facing=north: rep=%s powered=%s '
          'dust_out15=%s'
          % (isb('vB', M, 'minecraft:repeater'),
             isb('vC', M, 'minecraft:repeater[powered=true]'),
             isb('vD', N, 'minecraft:redstone_wire[power=15]')), flush=True)
    for p in cells + ((X, Y, Z + 2),):
        rc.exec('setblock %d %d %d minecraft:air' % p)
    rc.close()


if __name__ == '__main__':
    main()
