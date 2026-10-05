import os
import pickle
import re
import sys
from collections import Counter

sys.path.insert(0, r'D:\redstone-mini')
sys.path.insert(0, r'D:\redstone-mini\scratch')
os.environ.setdefault("REDSTONE_ASTAR_CAP", "30000")

import compose as C
from tiles import new_ctx
from core import TORCH_BACK

d = pickle.load(open(r'D:\redstone-mini\scratch\add8merge.pkl', 'rb'))
ctx = new_ctx(list(d['blocks']), dict(d['solid']), dict(d['rings']),
              dict(d['wires']), dict(d['junctions']), dict(d['repeaters']),
              dict(d['pos']), [], dict(d['sup']))
guard = set()
for x, y, z, bid in ctx.blocks:
    if 'wall_torch' in bid:
        guard.add((x, z))
        dx, dz = TORCH_BACK[bid.split('facing=')[1].rstrip(']')]
        guard.add((x + dx, z + dz))
sup = dict(d['sup'])

PAT = re.compile(r'^compose:\s*([a-zA-Z ]+)')


def why(e):
    m = PAT.match(str(e))
    return m.group(1).strip() if m else str(e)[:46]


for name in ('S0', 'S1', 'S2', 'S7', 'COUT'):
    a = tuple(ctx.pos[name])
    errs = Counter()
    for z in range(3, 34):
        try:
            cells = C.lwire(ctx, sup, guard, a, (6, z), name)
            errs['OK (%d cells)' % len(cells)] += 1
        except RuntimeError as e:
            errs[why(e)] += 1
    print('%-4s driver %-12s  31 targets at x=6:' % (name, str(a)))
    for k, v in errs.most_common():
        print('       %3d x  %s' % (v, k))