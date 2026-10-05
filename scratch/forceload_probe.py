import sys
import time

sys.path.insert(0, r'D:\redstone-mini\scratch')
from rcon import Rcon

PW = open('D:/put gitrepos here/mc-server-1.21/rcon_pass.txt').read().strip()


def cmd(c, to=180):
    try:
        r = Rcon('127.0.0.1', 25576, PW, timeout=to)
        return str(r._roundtrip(2, c)[0][1])[:300]
    except Exception as e:
        return 'ERR ' + str(e)[:90]


print('--- what is forceloaded right now ---')
print('list:', cmd('forceload query'))

print()
print('--- add8 footprint in chunks ---')
# add8 spans x 0..2007, z 0..292 -> chunk x 0..125, z 0..18
print('need:', (125 + 1) * (18 + 1), 'chunks')

print()
print('--- try adding the whole footprint in ONE call ---')
print(cmd('forceload add 0 0 2031 319'))

print()
print('--- try 100-chunk slices instead ---')
added = 0
for cx in range(0, 126, 10):
    x0 = cx * 16
    x1 = min((cx + 9) * 16, 2031)
    out = cmd('forceload add %d 0 %d 319' % (x0, x1))
    if 'Marked' in out:
        n = int(out.split()[1])
        added += n
        print('x %5d..%5d -> %s' % (x0, x1, out))
    else:
        print('x %5d..%5d -> %s' % (x0, x1, out[:90]))
        break
    time.sleep(1)

print()
print('total marked this pass:', added)
print('query spot:', cmd('forceload query 1000 200'))