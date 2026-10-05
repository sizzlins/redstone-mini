import json
import sys
import time

sys.path.insert(0, r'D:\redstone-mini\scratch')
from rcon import Rcon

PW = open('D:/put gitrepos here/mc-server-1.21/rcon_pass.txt').read().strip()


def cmd(c, to=300):
    try:
        r = Rcon('127.0.0.1', 25576, PW, timeout=to)
        return str(r._roundtrip(2, c)[0][1])[:200]
    except Exception as e:
        return 'ERR ' + str(e)[:70]


print('chain limit:', cmd('gamerule max_command_sequence_length 200000'))
for i in (1, 2, 3, 4):
    t0 = time.time()
    out = cmd('function rig:build%d' % i)
    print('build%d -> %-40s %.0fs' % (i, out, time.time() - t0), flush=True)
    time.sleep(10)

print()
print('--- presence check (60 random blocks) ---')
import pickle
m = pickle.load(open(r'D:\redstone-mini\scratch\add8merge.pkl', 'rb'))
import random
random.seed(99)
samp = random.sample(m['blocks'], 60)
ok = 0
for x, y, z, b in samp:
    base = str(b).split('[')[0]
    if 'passed' in cmd('execute if block %d %d %d %s' % (x, 64 + y, z, base)).lower():
        ok += 1
    else:
        print('  MISSING %s' % ((x, 64 + y, z, base),))
print('present %d/60' % ok)