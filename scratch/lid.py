"""Lid rule probe: does an opaque block over a wire joint cut horizontal flow?

The alu4merge_g staircase split centers on a joint with a cobble lid over it
((1097,1,182) dust, (1097,2,182) cobble, (1097,3,182) dust). Both engines have
a lid rule (sim.py:402, cmc engine.js:277). Minimal shape first: a straight
wire with an opaque lid over its middle cell. Vanilla conducts horizontally
under a lid (it only blocks upward connection), so the lamp must light.

Exits 0 when the engines agree, 1 when they split.

NEVER HANGS: one sim._run_vec in-process (engine's own caps), one node call
under a hard timeout. Bounded blocks, one vector, bounded seconds.

Usage:  python scratch/lid.py [--ticks N] [--cmc-timeout S]
"""
import json
import os
import subprocess
import sys
import time

ROOT = r'D:\redstone-mini'
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

GL = 'minecraft:glass'

# Straight wire with an opaque cobble lid over its middle cell. Horizontal flow
# must survive the lid in both engines; only upward connection is cut.
BUILD = [
    # glass floor, cobble lid over the middle dust
    (0, 0, 0, GL), (1, 0, 0, GL), (2, 0, 0, GL), (3, 0, 0, GL),
    (4, 0, 0, GL),
    (2, 2, 0, 'minecraft:cobblestone'),
    # lever A, three dust, lamp
    (0, 1, 0, 'minecraft:lever[face=floor,facing=north,powered=false]'),
    (1, 1, 0, 'minecraft:redstone_wire'),
    (2, 1, 0, 'minecraft:redstone_wire'),
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
                              for c, p in live.items()}})
    return out


def cmc_run(ticks, timeout):
    doc_p = os.path.join(HERE, '_notmin.v2doc.json')
    doc = {
        'blocks': [[int(x), int(y), int(z), str(b)] for x, y, z, b in BUILD],
        'levers': [['%d,%d' % k, v] for k, v in IO['levers'].items()],
        'lamps': [['%d,%d' % k, v] for k, v in IO['lamps'].items()],
        'vectors': VECS,
        'expected': [{o: bool(v) for o in ('Y',)} for v in WANT],
        'sampled': False, 'n_inputs': 1,
    }
    json.dump(doc, open(doc_p, 'w'))
    cmd = [sys.executable if False else 'node',
           os.path.join(HERE, 'cmc_harness.mjs'), doc_p,
           '--ticks', str(ticks),
           '--dump-cells', doc_p + '.cmccells.json', '--dump-all']
    t0 = time.time()
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
    # fall through to the cells file if stdout carried no verdict
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
    agree, sim_wrong = True, False
    for i, (vec, want) in enumerate(zip(VECS, WANT)):
        if dump.get('all'):
            cc = {tuple(int(v) for v in k.split(',')): int(p)
                  for k, p in dump['all'][str(i)]['cells'].items()}
            # the lidded middle cell and its neighbours
            sval = [simres[i]['cells'].get(c, 0) for c in ('1,1,0', '2,1,0',
                                                           '3,1,0')]
            cval = [cc.get((1, 1, 0), 0), cc.get((2, 1, 0), 0),
                    cc.get((3, 1, 0), 0)]
            agreed = (sval == cval)
            agree = agree and agreed
            print('OUT  A=%d  (1,1,0) sim=%s cmc=%s  (2,1,0)* sim=%s cmc=%s  '
                  '(3,1,0) sim=%s cmc=%s  %s'
                  % (vec['A'], sval[0], cval[0], sval[1], cval[1],
                     sval[2], cval[2],
                     'agree' if agreed else 'DISAGREE'), flush=True)
        if simres[i]['lamps'].get('Y', False) != want['Y']:
            sim_wrong = True
    print('\n%s' % ('ENGINES AGREE' if agree and not sim_wrong else
                    'ENGINES DISAGREE under the lid'),
          flush=True)
    return 0 if (agree and not sim_wrong) else 1


if __name__ == '__main__':
    sys.exit(main())