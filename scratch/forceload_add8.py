import sys
import time

sys.path.insert(0, r'D:\redstone-mini\scratch')
from rcon import Rcon

PW = open('D:/put gitrepos here/mc-server-1.21/rcon_pass.txt').read().strip()


def cmd(c, to=240):
    try:
        r = Rcon('127.0.0.1', 25576, PW, timeout=to)
        return str(r._roundtrip(2, c)[0][1])[:300]
    except Exception as e:
        return 'ERR ' + str(e)[:80]


# add8 footprint: build x 0..2007 -> world x 0..2071 ; z 0..292 -> world z 0..311
X1, Z1 = 2071, 311
total = 0
for cx in range(0, 130, 8):
    x0 = cx * 16
    x1 = min((cx + 7) * 16, X1)
    out = cmd('forceload add %d 0 %d %d' % (x0, x1, Z1))
    if out.startswith('Marked'):
        n = int(out.split()[1])
        total += n
        print('chunks x%3d..%3d  +%d  (running %d)' % (cx, cx + 7, n, total),
              flush=True)
    elif out.startswith('Too many'):
        print('chunks x%3d..%3d  CAP: %s' % (cx, cx + 7, out[:80]), flush=True)
        break
    else:
        print('chunks x%3d..%3d  %s (will verify by query)' % (cx, cx + 7, out[:60]),
              flush=True)
    time.sleep(6)

print()
print('marked this pass:', total)
time.sleep(5)
print('probe far end:', cmd('execute if block 1935 65 261 minecraft:redstone_lamp'))
print('probe mid:', cmd('execute if block 823 65 261 minecraft:redstone_lamp'))
print('probe west:', cmd('execute if block 3 65 13 minecraft:lever'))