"""Lever-driven repeater test -- mirrors sim.py's _lp3 canary exactly:
wall lever -> host block -> dust on top of host -> repeater -> dust.
No redstone blocks (setblock-placed sources do not emit in this world).
Usage: leverrep.py <port> <passfile> [x y z].
"""
import sys
import time

sys.path.insert(0, 'D:/redstone-mini/scratch')
from rcon import Rcon


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 25576
    pf = sys.argv[2] if len(sys.argv) > 2 else \
        'D:/put gitrepos here/mc-server-1.21/rcon_pass.txt'
    X = int(sys.argv[3]) if len(sys.argv) > 3 else 96
    Y = int(sys.argv[4]) if len(sys.argv) > 4 else 70
    Z = int(sys.argv[5]) if len(sys.argv) > 5 else 96
    pw = open(pf).read().strip()
    rc = Rcon('127.0.0.1', port, pw, timeout=120)
    rc.exec('scoreboard objectives add __rig dummy')

    def isb(tag, pos, kind):
        rc.exec('execute store success score %s __rig if block %d %d %d %s'
                % ((tag,) + pos + (kind,)))
        return 'has 1' in rc.exec('scoreboard players get %s __rig' % tag)

    host = (X, Y, Z)            # the block the lever is attached to
    dust_in = (X, Y + 1, Z)     # dust on top of the host
    rep = (X, Y + 1, Z - 1)     # repeater, input from the south
    dust_out = (X, Y + 1, Z - 2)
    lev = (X + 1, Y, Z)         # wall lever facing west onto the host
    cells = [host, dust_in, rep, dust_out, lev,
             (X, Y - 1, Z), (X, Y - 1, Z - 1), (X, Y - 1, Z - 2),
             (X + 1, Y - 1, Z)]
    for p in cells:
        rc.exec('setblock %d %d %d minecraft:stone' % (p[0], p[1] - 1, p[2]))
    for p in (dust_in, rep, dust_out, host, lev):
        rc.exec('setblock %d %d %d minecraft:air' % p)
    rc.exec('setblock %d %d %d minecraft:stone' % host)
    print('lever off =>', repr(rc.exec(
        'setblock %d %d %d '
        'minecraft:lever[face=wall,facing=west,powered=false]' % lev))[:60])
    rc.exec('setblock %d %d %d minecraft:redstone_wire' % dust_in)
    rc.exec('setblock %d %d %d minecraft:redstone_wire' % dust_out)
    rc.exec('setblock %d %d %d minecraft:repeater[facing=north]' % rep)
    time.sleep(3)
    print('LEVER OFF: dust_in15=%s rep_powered=%s dust_out15=%s (want F/F/F)'
          % (isb('o1', dust_in, 'minecraft:redstone_wire[power=15]'),
             isb('o2', rep, 'minecraft:repeater[powered=true]'),
             isb('o3', dust_out, 'minecraft:redstone_wire[power=15]')),
          flush=True)
    print('lever on  =>', repr(rc.exec(
        'setblock %d %d %d '
        'minecraft:lever[face=wall,facing=west,powered=true]' % lev))[:60])
    time.sleep(3)
    print('LEVER ON : dust_in15=%s rep_powered=%s dust_out15=%s (want T/?/T)'
          % (isb('n1', dust_in, 'minecraft:redstone_wire[power=15]'),
             isb('n2', rep, 'minecraft:repeater[powered=true]'),
             isb('n3', dust_out, 'minecraft:redstone_wire[power=15]')),
          flush=True)
    print('retained: host=%s dust_in=%s rep=%s dust_out=%s lever=%s'
          % (isb('r1', host, 'minecraft:stone'),
             isb('r2', dust_in, 'minecraft:redstone_wire'),
             isb('r3', rep, 'minecraft:repeater'),
             isb('r4', dust_out, 'minecraft:redstone_wire'),
             isb('r5', lev, 'minecraft:lever')), flush=True)
    for p in (dust_in, rep, dust_out, host, lev):
        rc.exec('setblock %d %d %d minecraft:air' % p)
    rc.close()


if __name__ == '__main__':
    main()
