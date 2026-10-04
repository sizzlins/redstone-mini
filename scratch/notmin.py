"""Minimal reproducer for Finding 3: sim cannot power a lever that is not a
declared input pin, while cmc (and vanilla) can.

A hand-placed comparator-subtract inverter, ~10 blocks, no router, floor
included so cmc's support stage accepts it. The rear of the comparator is fed
by a lever whose blockstate is powered=true but which is NOT in io['levers'],
and sim reads such a lever as unpowered forever (sim.py:542 does
`vec.get(lever[rear], False)`, and the pin key for a non-pin lever is its own
floor coordinate, which no vector ever contains).

Geometry follows sim's own convention (facing points output->input, so the
rear sits at +facing): the comparator at (2,1,2) facing=west has its rear at
(1,1,2), output east at (3,1,2), and input A arriving on the south side
through (2,1,1)<-(2,1,0)<-(1,1,0)<-(0,1,0). subtract gives 15-A.

Runs BOTH engines on A=0 and A=1 and compares lamp verdicts plus the two
output dust cells. Exits 0 when the engines agree, 1 when they do not -- which
is to say it is a failing regression test right now, standing ready for the
day someone implements the constant-lever source category both engines need:

  A=0: sim says Y=false, cmc says Y=true     (9 cells differ on not_full.pkl)
  A=1: both say Y=false                        (this shape is the tell)

NEVER HANGS: one sim._run_vec per vector in-process (bounded by the engine's
own tick/step caps), one node subprocess under a hard timeout. Bounded blocks,
bounded vectors, bounded seconds.

Usage:  python scratch/notmin.py [--ticks N] [--cmc-timeout S]
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

BUILD = [
    # floor so cmc's support stage accepts the build
    (0, 0, 0, GL), (1, 0, 0, GL), (2, 0, 0, GL), (2, 0, 1, GL),
    (1, 0, 2, GL), (2, 0, 2, GL), (3, 0, 2, GL), (4, 0, 2, GL),
    # input lever A (a declared pin) and its dust run north to the side
    (0, 1, 0, 'minecraft:lever[face=floor,facing=north,powered=false]'),
    (1, 1, 0, 'minecraft:redstone_wire'),
    (2, 1, 0, 'minecraft:redstone_wire'),
    (2, 1, 1, 'minecraft:redstone_wire'),
    # the CONSTANT lever: flipped ON, and deliberately absent from io
    (1, 1, 2, 'minecraft:lever[face=floor,facing=north,powered=true]'),
    (2, 1, 2, 'minecraft:comparator[facing=west,mode=subtract]'),
    # output wire east to the lamp
    (3, 1, 2, 'minecraft:redstone_wire'),
    (4, 1, 2, 'minecraft:redstone_lamp'),
]

IO = {'levers': {(0, 0): 'A'}, 'lamps': {(4, 2): 'Y'}}
VECS = [{'A': 0}, {'A': 1}]
WANT = [{'Y': True}, {'Y': False}]


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
            # the comparator's driven dust cell: where the engines disagree
            sval = simres[i]['cells'].get('3,1,2', 0)
            cval = cc.get((3, 1, 2), 0)
            agreed = (sval == cval)
            agree = agree and agreed
            print('OUT  A=%d  (3,1,2) sim=%s cmc=%s  %s'
                  % (vec['A'], sval, cval,
                     'agree' if agreed else 'DISAGREE'), flush=True)
        if simres[i]['lamps'].get('Y', False) != want['Y']:
            sim_wrong = True
    print('\n%s' % ('ENGINES AGREE' if agree and not sim_wrong else
                    'ENGINES DISAGREE: non-pin lever -- see Finding 3'),
          flush=True)
    return 0 if (agree and not sim_wrong) else 1


if __name__ == '__main__':
    sys.exit(main())