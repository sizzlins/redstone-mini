import sys
import time

sys.path.insert(0, r'D:\redstone-mini\scratch')
from rcon import Rcon

PW = open('D:/put gitrepos here/mc-server-1.21/rcon_pass.txt').read().strip()


def cmd(c, to=300):
    try:
        r = Rcon('127.0.0.1', 25576, PW, timeout=to)
        rr = r._roundtrip(2, c)
        return str(rr[0][1])[:200] if rr else '?'
    except Exception as e:
        return 'ERR ' + str(e)[:90]


print('list:', cmd('datapack list'))
print('enable:', cmd('datapack enable ' + chr(34) + 'file/rig' + chr(34)))
time.sleep(4)
print('reload:', cmd('reload'))
time.sleep(12)
print('paste:', cmd('function rig:build'))