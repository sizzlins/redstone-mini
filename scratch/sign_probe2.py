import sys
import time

sys.path.insert(0, r'D:\redstone-mini\scratch')
from rcon import Rcon

PW = open('D:/put gitrepos here/mc-server-1.21/rcon_pass.txt').read().strip()


def cmd(c, to=120):
    try:
        r = Rcon('127.0.0.1', 25576, PW, timeout=to)
        return str(r._roundtrip(2, c)[0][1])[:260]
    except Exception as e:
        return 'ERR ' + str(e)[:80]


Q = chr(39)   # single quote
D = chr(34)   # double quote

# candidate A: minimal, only messages
a = ('setblock 200 70 700 minecraft:oak_wall_sign[facing=north]'
     '{front_text:{messages:[' + Q + 'A0 = 13' + Q + ']}}')
print('A:', cmd(a))

# candidate B: full triple with byte written as 0b
b = ('setblock 201 70 700 minecraft:oak_sign'
     '{front_text:{messages:[' + Q + 'S7 COUT' + Q + '],color:' + D + 'black' + D
     + ',has_glowing_text:0b}}')
print('B:', cmd(b))

# candidate C: with back_text present too (1.21 wants both sides?)
c = ('setblock 202 70 700 minecraft:oak_wall_sign[facing=north]'
     '{front_text:{messages:[' + Q + 'C1' + Q + '],color:' + D + 'black' + D
     + ',has_glowing_text:0b},'
     'back_text:{messages:[' + Q + '' + Q + '],color:' + D + 'black' + D
     + ',has_glowing_text:0b}}')
print('C:', cmd(c))

time.sleep(2)
for x, tag in ((200, 'A'), (201, 'B'), (202, 'C')):
    print(tag, cmd('data get block %d 70 700 front_text messages' % x))