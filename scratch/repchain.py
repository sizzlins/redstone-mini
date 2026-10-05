"""Repeater-chain probe: does the SECOND repeater fire in both engines?

From alu4merge_g vec47: repeater 1588 fires 1/1, dust 1589-1595 agrees
15..9 in both, repeater 1596 fires sim=1 cmc=0 on identical input 9, and all
downstream goes sim=15..9 vs cmc=0. Isolated single repeater (repface.py)
agrees, so the split needs the chain: decayed input, delay pipeline, or
settle ticks. This replicates R1 -> 7 dust -> R2 -> 3 dust + lamp.

Exits 0 on agree, 1 on split. Takes --ticks so the settling discriminator
(ticks 400 vs 1600) is one flag apart.

NEVER HANGS: one sim run in-process, one node call under hard timeout.

Usage:  python scratch/repchain.py [--ticks N] [--cmc-timeout S]
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
W = 'minecraft:redstone_wire'

BUILD = [
    (0, 0, 0, STONE), (1, 0, 0, STONE), (2, 0, 0, STONE), (3, 0, 0, STONE),
    (4, 0, 0, STONE), (5, 0, 0, STONE), (6, 0, 0, STONE), (7, 0, 0, STONE),
    (8, 0, 0, STONE), (9, 0, 0, STONE), (10, 0, 0, STONE), (11, 0, 0, STONE),
    (12, 0, 0, STONE),
    (0, 1, 0, 'minecraft:lever[face=floor,facing=north,powered=false]'),
    (1, 1, 0, W),
    (2, 1, 0, 'minecraft:repeater[facing=west,delay=1]'),
    (3, 1, 0, W), (4, 1, 0, W), (5, 1, 0, W), (6, 1, 0, W),
    (7, 1, 0, W), (8, 1, 0, W), (9, 1, 0, W),
    (10, 1, 0, 'minecraft:repeater[facing=west,delay=1]'),
    (11, 1, 0, W), (12, 1, 0, 'minecraft:redstone_lamp'),
]

IO = {'levers': {(0, 0): 'A'}, 'lamps': {(12, 0): 'Y'}}
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
                                  for c, p in rlive.items()},
                    'ticks': nticks})
    return out


def cmc_run(ticks, timeout):
    doc_p = os.path.join(HERE, '_repchain.v2doc.json')
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
    print('SIM  R1(2,1,0)=%s mid(9,1,0)=%s R2(10,1,0)=%s out(11,1,0)=%s lamp=%s ticks=%s'
          % (simres[0]['repeaters'].get('2,1,0', '-'),
             simres[0]['cells'].get('9,1,0', 0),
             simres[0]['repeaters'].get('10,1,0', '-'),
             simres[0]['cells'].get('11,1,0', 0),
             simres[0]['lamps'].get('Y', False),
             simres[0]['ticks']), flush=True)

    cmcres, to = cmc_run(ticks, timeout)
    if cmcres is None:
        print('CMC  unavailable (%s) -- sim-only, no verdict'
              % ('TIMEOUT' if to else 'no JSON'), flush=True)
        return 2
    dump = cmcres.get('dump') or {}
    if dump.get('all'):
        cc = {tuple(int(v) for v in k.split(',')): int(p)
              for k, p in dump['all']['0']['cells'].items()}
        cr = {tuple(int(v) for v in k.split(',')): int(p)
              for k, p in dump['all']['0'].get('repeaters', {}).items()}
        print('CMC  R1=%s mid(9,1,0)=%s R2=%s out(11,1,0)=%s (ticks=%d)'
              % (cr.get((2, 1, 0), '-'), cc.get((9, 1, 0), 0),
                 cr.get((10, 1, 0), '-'), cc.get((11, 1, 0), 0), ticks),
              flush=True)
        pairs = [(c, simres[0]['cells'].get(c, 0),
                  cc.get(tuple(int(v) for v in c.split(',')), 0))
                 for c in ('9,1,0', '11,1,0')]
        rpairs = [(c, simres[0]['repeaters'].get(c, '-'),
                   cr.get(tuple(int(v) for v in c.split(',')), '-'))
                  for c in ('2,1,0', '10,1,0')]
        agree = all(s == m for _, s, m in pairs) and \
            all(s == m for _, s, m in rpairs)
        for c, s, m in pairs + rpairs:
            print('  %-7s sim=%-4s cmc=%-4s %s' % (c, s, m, 'ok' if s == m else 'DIFF'),
                  flush=True)
        print('\n%s' % ('ENGINES AGREE on the repeater chain (ticks=%d)' % ticks
                        if agree else
                        'ENGINES DISAGREE on the repeater chain (ticks=%d)' % ticks),
              flush=True)
        return 0 if agree else 1
    print('CMC verdict without cells dump: %s' % str(cmcres)[:200], flush=True)
    return 2


if __name__ == '__main__':
    sys.exit(main())
