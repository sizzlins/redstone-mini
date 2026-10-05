"""One-repeater facing probe: which side does facing=west drive?

The alu4merge_g 64-vector diff's examples are flat repeater-fed runs:
repeater (1596,1,93) facing=west, dust east (1597..1603) sim=15..9 vs cmc=0.
sim stores facing negated (rep = -travel); cmc reads it oppositely on paper,
yet they agree on 4000+ cells -- except here. One repeater decides it.

BUILD: lever west -> dust -> repeater facing=west -> dust -> lamp east.
Sim convention (facing points output->input, rear=input at facing dir):
input west, output east, lamp must light. If cmc lights the mirror build
instead, the facing convention is the split.

Exits 0 when the engines agree on dust levels and the lamp, 1 on split.

NEVER HANGS: one sim._run_vec in-process, one node call under hard timeout.

Usage:  python scratch/repface.py [--ticks N] [--cmc-timeout S]
"""
import json
import os
import subprocess
import sys
import time

ROOT = r'D:\redstone-mini'
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

STONE = 'minecraft:stone'

BUILD = [
    (0, 0, 0, STONE), (1, 0, 0, STONE), (2, 0, 0, STONE),
    (3, 0, 0, STONE), (4, 0, 0, STONE),
    (0, 1, 0, 'minecraft:lever[face=floor,facing=north,powered=false]'),
    (1, 1, 0, 'minecraft:redstone_wire'),
    (2, 1, 0, 'minecraft:repeater[facing=west,delay=1]'),
    (3, 1, 0, 'minecraft:redstone_wire'),
    (4, 1, 0, 'minecraft:redstone_lamp'),
]

IO = {'levers': {(0, 0): 'A'}, 'lamps': {(4, 0): 'Y'}}
VECS = [{'A': 1}]
WANT = [{'Y': True}]


def sim_run():
    from sim import _parse_build, _run_vec
    P = _parse_build([tuple(b) for b in BUILD], IO)
    out = []
    for vec in VECS:
        got, live, tlive, nticks, rlive, conc = _run_vec(vec, None, P)
        out.append({'lamps': {k: bool(v) for k, v in got.items()},
                    'cells': {'%d,%d,%d' % c: int(p)
                              for c, p in live.items()},
                    'repeaters': {'%d,%d,%d' % c: int(p)
                                  for c, p in rlive.items()}})
    return out


def cmc_run(ticks, timeout):
    doc_p = os.path.join(HERE, '_repface.v2doc.json')
    doc = {
        'blocks': [[int(x), int(y), int(z), str(b)] for x, y, z, b in BUILD],
        'levers': [['%d,%d' % k, v] for k, v in IO['levers'].items()],
        'lamps': [['%d,%d' % k, v] for k, v in IO['lamps'].items()],
        'vectors': VECS,
        'expected': [{o: bool(v) for o in ('Y',)} for v in WANT],
        'sampled': False, 'n_inputs': 1,
    }
    json.dump(doc, open(doc_p, 'w'))
    cmd = ['node', os.path.join(HERE, 'cmc_harness.mjs'), doc_p,
           '--ticks', str(ticks),
           '--dump-cells', doc_p + '.cmccells.json', '--dump-all']
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=ROOT)
        rc, s, to = p.returncode, p.stdout + p.stderr, False
    except subprocess.TimeoutExpired:
        return None, True
    for line in s.splitlines():
        line = line.strip()
        if line.startswith('{'):
            try:
                blob = json.loads(line[line.index('{'):])
            except ValueError:
                continue
            if 'ok' in blob:
                return blob, to
    try:
        dump = json.load(open(doc_p + '.cmccells.json'))
        if dump.get('all'):
            return {'ok': None, 'dump': dump}, to
    except (OSError, ValueError):
        pass
    return None, to


def main():
    ticks, timeout = 400, 300
    a = sys.argv[1:]
    if '--ticks' in a:
        ticks = int(a[a.index('--ticks') + 1])
    if '--cmc-timeout' in a:
        timeout = int(a[a.index('--cmc-timeout') + 1])

    simres = sim_run()
    for i, (vec, want) in enumerate(zip(VECS, WANT)):
        got = simres[i]['lamps'].get('Y', False)
        print('SIM  A=%d -> Y=%-5s (want %-5s) %s'
              % (vec['A'], got, want['Y'],
                 'ok' if got == want['Y'] else 'WRONG'), flush=True)

    cmcres, to = cmc_run(ticks, timeout)
    if cmcres is None:
        print('CMC  unavailable (%s) -- sim-only, no verdict'
              % ('TIMEOUT' if to else 'no JSON'), flush=True)
        return 2
    dump = cmcres.get('dump') or {}
    agree = True
    for i, (vec, want) in enumerate(zip(VECS, WANT)):
        if dump.get('all'):
            cc = {tuple(int(v) for v in k.split(',')): int(p)
                  for k, p in dump['all'][str(i)]['cells'].items()}
            sval = [simres[i]['cells'].get(c, 0) for c in ('1,1,0', '3,1,0')]
            cval = [cc.get((1, 1, 0), 0), cc.get((3, 1, 0), 0)]
            agreed = (sval == cval)
            agree = agree and agreed
            print('OUT  A=%d west-dust(1,1,0) sim=%s cmc=%s east-dust(3,1,0) sim=%s cmc=%s %s'
                  % (vec['A'], sval[0], cval[0], sval[1], cval[1],
                     'agree' if agreed else 'DISAGREE'), flush=True)
    sim_lamp = simres[0]['lamps'].get('Y', False)
    print('\n%s' % ('ENGINES AGREE' if agree and sim_lamp == want['Y'] else
                    'ENGINES DISAGREE on repeater facing=west direction'),
          flush=True)
    return 0 if agree else 1


if __name__ == '__main__':
    sys.exit(main())
