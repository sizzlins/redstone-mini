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


SQ = chr(39)
DQ = chr(34)


def sign(x, y, z, kind, facing, text):
    return ('setblock %d %d %d minecraft:%s[facing=%s]'
            '{front_text:{messages:[' + DQ + text + DQ + '],color:'
            + DQ + 'black' + DQ + ',has_glowing_text:0b},'
            'back_text:{messages:[' + DQ + DQ + '],color:' + DQ + 'black' + DQ
            + ',has_glowing_text:0b}}') % (x, y, z, kind, facing)


print('D double-quoted msg:')
print(' ', cmd(sign(203, 70, 700, 'oak_wall_sign', 'north', 'A0 = 13')))
print(' ', cmd(sign(204, 70, 700, 'oak_sign', 'north', 'S7 COUT')))
time.sleep(2)
for x in (203, 204):
    print(x, cmd('data get block %d 70 700' % x))