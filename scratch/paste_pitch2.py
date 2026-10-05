import json
import pickle
import sys
import time

sys.path.insert(0, r'D:\redstone-mini\scratch')
from rcon import Rcon

PW = open('D:/put gitrepos here/mc-server-1.21/rcon_pass.txt').read().strip()
HERE = r'D:\redstone-mini'
OY = 64
# pitch-2 build: levers at z 3..33, indicators at z 5,9,..,35 (x=2),
# sum lamps along z ~138. Park the whole thing at x offset 0, z offset 300 so
# it does not overlap the old 10-apart copy at z 3..153.
ZO = 300


def cmd(c, to=300):
    try:
        r = Rcon('127.0.0.1', 25576, PW, timeout=to)
        return str(r._roundtrip(2, c)[0][1])[:160]
    except Exception as e:
        return 'ERR ' + str(e)[:70]


m = pickle.load(open(HERE + r'\scratch\add8p2ind.pkl', 'rb'))
blocks = m['blocks']
print('blocks to paste:', len(blocks))

fn_dir = (r'D:\put gitrepos here\mc-server-1.21\world\datapacks\rig'
          r'\data\rig\function')
lines = ['setblock %d %d %d %s' % (x, OY + y, ZO + z, b) for x, y, z, b in blocks]
for i in range(0, len(lines), 6000):
    with open('%s\\p%d.mcfunction' % (fn_dir, i // 6000), 'w') as f:
        f.write('\n'.join(lines[i:i + 6000]) + '\n')
print('functions written:', (len(lines) + 5999) // 6000)

# forceload the whole footprint in <=200-chunk slices
X1 = max(b[0] for b in blocks) + 1
Z1 = ZO + max(b[2] for b in blocks) + 1
for cx in range(0, (X1 // 16) + 2, 8):
    x0 = cx * 16
    x1 = min((cx + 7) * 16, X1)
    out = cmd('forceload add %d %d %d %d' % (x0, ZO, x1, Z1))
    print('  forceload x%5d..%5d: %s' % (x0, x1, out[:60]), flush=True)
    time.sleep(4)

print('reload:', cmd('reload'), flush=True)
time.sleep(12)
n = (len(lines) + 5999) // 6000
for i in range(n):
    print('paste p%d: %s' % (i, cmd('function rig:p%d' % i)), flush=True)
    time.sleep(12)

# presence check
import random
random.seed(4242)
samp = random.sample(blocks, 50)
ok = 0
for x, y, z, b in samp:
    base = str(b).split('[')[0]
    if 'passed' in cmd('execute if block %d %d %d %s'
                        % (x, OY + y, ZO + z, base)).lower():
        ok += 1
print('present %d/50' % ok)