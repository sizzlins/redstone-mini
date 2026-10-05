import json
import sys
import time

sys.path.insert(0, r'D:\redstone-mini\scratch')
from rcon import Rcon

PW = open('D:/put gitrepos here/mc-server-1.21/rcon_pass.txt').read().strip()
OY = 64


def cmd(c, to=180):
    try:
        r = Rcon('127.0.0.1', 25576, PW, timeout=to)
        rr = r._roundtrip(2, c)
        return str(rr[0][1])[:200] if rr else '?'
    except Exception as e:
        return 'ERR ' + str(e)[:90]


def passed(c):
    return 'passed' in cmd(c).lower()


def run(doc, dz=0, dx=0, settle=6, limit=None):
    d = json.load(open(doc))
    lever_bid = {}
    for x, y, z, b in d['blocks']:
        if b.startswith('minecraft:lever'):
            lever_bid['%d,%d' % (x, z)] = b
    lamp_at = {}
    for x, y, z, b in d['blocks']:
        if b.startswith('minecraft:redstone_lamp'):
            lamp_at['%d,%d' % (x, z)] = (x, y, z)
            lamp_at['%d,%d,%d' % (x, y, z)] = (x, y, z)
    lev = {}
    for coord, name in d['levers']:
        x, z = (int(v) for v in coord.split(','))
        b = lever_bid[coord]
        on = b.replace('powered=false', 'powered=true')
        lev[name] = (x + dx, OY + 1, z + dz, b, on)
    lam = {}
    for coord, name in d['lamps']:
        # 2-part key is (x,z) with the lamp at y=1; 3-part is literal (x,y,z).
        # lever_lamps writes the indicator pins as 3-tuples, so both occur.
        p = [int(v) for v in coord.split(',')]
        if len(p) == 2:
            lam[name] = (p[0] + dx, OY + lamp_at[coord][1], p[1] + dz)
        else:
            lam[name] = (p[0] + dx, OY + p[1], p[2] + dz)
    vecs = d['vectors'][:limit] if limit else d['vectors']
    results = []
    for vec in vecs:
        for name, (x, y, z, off, on) in lev.items():
            cmd('setblock %d %d %d %s' % (x, y, z, on if vec.get(name) else off))
        time.sleep(settle)
        got = {}
        for name, (x, y, z) in lam.items():
            got[name] = passed('execute if block %d %d %d minecraft:redstone_lamp[lit=true]'
                               % (x, y, z))
        want = d['expected'][d['vectors'].index(vec)]
        bad = [k for k in want if got.get(k) != bool(want[k])]
        results.append((vec, got, want, bad))
        print('%-34s got=%s bad=%s' % (str(vec), got, bad or 'ok'), flush=True)
    fails = [r for r in results if r[3]]
    print('\n%d/%d vectors green' % (len(results) - len(fails), len(results)))
    return results


if __name__ == '__main__':
    doc = sys.argv[1]
    dz = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    run(doc, dz=dz, limit=int(sys.argv[3]) if len(sys.argv) > 3 else None)