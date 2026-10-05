import sys
import time

sys.path.insert(0, r'D:\redstone-mini\scratch')
from rcon import Rcon

PW = open('D:/put gitrepos here/mc-server-1.21/rcon_pass.txt').read().strip()


def cmd(c, to=120):
    try:
        r = Rcon('127.0.0.1', 25576, PW, timeout=to)
        return str(r._roundtrip(2, c)[0][1])[:400]
    except Exception as e:
        return 'ERR ' + str(e)[:80]


DQ = chr(34)
E = DQ + DQ


def wall(x, y, z, facing, text):
    msgs = '[' + DQ + text + DQ + ',' + E + ',' + E + ',' + E + ']'
    blk = DQ + 'black' + DQ
    return ('setblock %d %d %d minecraft:oak_wall_sign[facing=%s]'
            '{front_text:{messages:%s,color:%s,has_glowing_text:0b},'
            'back_text:{messages:%s,color:%s,has_glowing_text:0b}}'
            ) % (x, y, z, facing, msgs, blk, msgs, blk)


print('4-slot wall sign:')
print(' ', cmd(wall(205, 70, 700, 'north', 'A0 = 13')))
time.sleep(2)
print(' read:', cmd('data get block 205 70 700'))