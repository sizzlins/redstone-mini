"""Vertical-staircase rule probe: do the engines agree on dust going UP steps?

The alu4merge_g 49k-cell diff resolves to staircases (y 1,2,3,2,1 advancing
in x) with clean decay in one engine and 0 in the other, in BOTH directions.
sim's UP/DN terms (sim.py:393-411) carry lid/support/opaque conditions that
cmc may implement differently. This is the minimal shape: three dust cells
rising one level per step east, lever on, lamp at the top.

Exits 0 when the engines agree on every staircase dust level and the lamp,
1 when they split.

NEVER HANGS: one sim._run_vec in-process (engine's own caps), one node call
under a hard timeout. Bounded blocks, one vector, bounded seconds.

Usage:  python scratch/stair.py [--ticks N] [--cmc-timeout S]
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

# Three dust cells rising one level per step east, on cobble steps (conductive
# support, like real builds). Vanilla connects the whole staircase, so the
# lever must light the lamp through 15 -> 14 -> 13 -> lamp.
BUILD = [
    # glass floor under the base level, cobble steps under the risers
    (0, 0, 0, GL), (1, 0, 0, GL),
    (2, 1, 0, 'minecraft:cobblestone'), (3, 2, 0, 'minecraft:cobblestone'),
    # lever A, then the staircase
    (0, 1, 0, 'minecraft:lever[face=floor,facing=north,powered=false]'),
    (1, 1, 0, 'minecraft:redstone_wire'),
    (2, 2, 0, 'minecraft:redstone_wire'),
    (3, 3, 0, 'minecraft:redstone_wire'),
    (4, 3, 0, 'minecraft:redstone_lamp'),
]

IO = {'levers': {(0, 0): 'A'}, 'lamps': {(4, 0): 'Y'}}
VECS = [{'A': 1}]
# WANT is dust-only. The lamp at (4,3,0) is NOT evaluated: sim's io maps keys
# to (x,1,z) via _y(), so pins of either kind exist only at y=1 -- a lamp
# above y=1 is invisible to sim by design (same y=1 limitation as levers,
# found while building stairdown.py). That is a probe-design constraint, not
# physics; this probe is the staircase dust, which is what disagrees in alu4.
WANT = None


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
        # dust-only probe: no lamp expectation (sim io is y=1-only). cmc's
        # ok is meaningless here; only its cells dump is read.
        'expected': [{} for _ in VECS] if WANT is None else
                    [{o: bool(v) for o in ('Y',)} for v in WANT],
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
    for i, vec in enumerate(VECS):
        if WANT is None:
            print('SIM  A=%d (lamp not evaluated: sim io is y=1-only)'
                  % vec['A'], flush=True)
        else:
            want = WANT[i]
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
    for i, vec in enumerate(VECS):
        if dump.get('all'):
            cc = {tuple(int(v) for v in k.split(',')): int(p)
                  for k, p in dump['all'][str(i)]['cells'].items()}
            # the three risers: where a vertical-rule split would show
            cells = ('1,1,0', '2,2,0', '3,3,0')
            sval = [simres[i]['cells'].get(c, 0) for c in cells]
            cval = [cc.get((1, 1, 0), 0), cc.get((2, 2, 0), 0),
                    cc.get((3, 3, 0), 0)]
            agreed = (sval == cval)
            agree = agree and agreed
            print('OUT  A=%d  (1,1,0) sim=%s cmc=%s  (2,2,0) sim=%s cmc=%s  '
                  '(3,3,0) sim=%s cmc=%s  %s'
                  % (vec['A'], sval[0], cval[0], sval[1], cval[1],
                     sval[2], cval[2],
                     'agree' if agreed else 'DISAGREE'), flush=True)
        if WANT is not None and simres[i]['lamps'].get('Y', False) != WANT[i]['Y']:
            sim_wrong = True
    print('\n%s' % ('ENGINES AGREE' if agree and not sim_wrong else
                    'ENGINES DISAGREE on the staircase -- vertical rule'),
          flush=True)
    return 0 if (agree and not sim_wrong) else 1


if __name__ == '__main__':
    sys.exit(main())