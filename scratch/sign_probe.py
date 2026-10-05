import sys
import time

sys.path.insert(0, r'D:\redstone-mini\scratch')
from rcon import Rcon

PW = open('D:/put gitrepos here/mc-server-1.21/rcon_pass.txt').read().strip()


def cmd(c, to=120):
    try:
        r = Rcon('127.0.0.1', 25576, PW, timeout=to)
        rr = r._roundtrip(2, c)
        return str(rr[0][1])[:240] if rr else '?'
    except Exception as e:
        return 'ERR ' + str(e)[:90]


X, Y, Z = 200, 70, 700
print('tp:', cmd('tp steve %d 90 %d' % (X, Z)))
time.sleep(6)
print('floor:', cmd('setblock %d %d %d minecraft:stone' % (X, Y - 1, Z)))
print('wall sign facing:',
      cmd('setblock %d %d %d minecraft:oak_wall_sign[facing=north]{TextComponent:\'A0 = 13\'}'
          % (X, Y, Z)))
print('standing sign:',
      cmd('setblock %d %d %d minecraft:oak_sign{TextComponent:\'S7 = COUT\'}'
          % (X + 1, Y, Z)))
time.sleep(2)
print('read wall:', cmd('data get block %d %d %d' % (X, Y, Z)))
print('read stand:', cmd('data get block %d %d %d' % (X + 1, Y, Z)))