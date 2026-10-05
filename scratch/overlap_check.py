import pickle
import sys

sys.path.insert(0, r'D:\redstone-mini\scratch')
from rcon import Rcon

PW = open('D:/put gitrepos here/mc-server-1.21/rcon_pass.txt').read().strip()
OY, ZO = 64, 300


def cmd(c, to=180):
    try:
        r = Rcon('127.0.0.1', 25576, PW, timeout=to)
        return str(r._roundtrip(2, c)[0][1])[:140]
    except Exception as e:
        return 'ERR ' + str(e)[:60]


m = pickle.load(open(r'D:\redstone-mini\scratch\add8p2ind.pkl', 'rb'))
claim = {(x, y, z): b for x, y, z, b in m['blocks']}

# the cells first_divergence flagged as game=hot sim=0
flagged = [(39, 2, 137), (39, 3, 128), (40, 1, 108), (40, 1, 128),
           (40, 1, 135), (40, 1, 138), (41, 1, 108), (42, 1, 128),
           (42, 1, 136)]
print('does the world hold what add8 claims at these cells?')
for x, y, z in flagged:
    want = claim.get((x, y, z))
    c = (x, OY + y, ZO + z)
    got = 'passed' in cmd('execute if block %d %d %d %s' % (c[0], c[1], c[2], want)).lower() \
        if want else False
    print('  %-16s world z=%d  claimed=%-42s present=%s'
          % (str((x, y, z)), c[2], str(want)[:42], got))

# footprint overlap between the two live builds
a2 = pickle.load(open(r'D:\redstone-mini\scratch\add2opt.pkl', 'rb'))
z8 = [b[2] + ZO for b in m['blocks']]
z2 = [b[2] + 400 for b in a2['blocks']]
print()
print('add8  (at z+300) world z range: %d .. %d' % (min(z8), max(z8)))
print('add2opt(at z+400) world z range: %d .. %d' % (min(z2), max(z2)))
print('OVERLAP in z: %s' % (not (min(z8) > max(z2) or min(z2) > max(z8))))
n_overlap = sum(1 for v in z8 if min(z2) <= v <= max(z2))
print('add8 blocks sitting inside add2opt\'s z band: %d of %d'
      % (n_overlap, len(z8)))