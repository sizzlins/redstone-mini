"""Staircase+lid joint probe: the last mile of the alu4merge_g 49k diff.

Isolated rise agrees, isolated fall on cobble agrees, straight lid agrees --
but the real diff centers on a joint with a cobble lid OVER it:
(1097,1,182) dust, (1097,2,182) cobble, (1097,3,182) dust, with side dusts
at y=2 east/west on cobble pillars ((1096,1,182) and (1098,1,182) cobble).
This is that motif, shifted to the origin, repeaters stripped (the split is
dust-only per compdiff, no repeater inside any disagreeing component).

Exits 0 when the engines agree on every joint dust level and the lamp,
1 when they split.

NEVER HANGS: one sim._run_vec in-process (engine's own caps), one node call
under a hard timeout. Bounded blocks (~25), one vector, bounded seconds.

Usage:  python scratch/stairlid.py [--ticks N] [--cmc-timeout S]
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
COB = 'minecraft:cobblestone'

# Lower N-S dust row at y=1 on stone, cobble lids at y=2 above each, upper
# E-W dust row at y=3 on the lids, side y=2 dusts east/west of the joint on
# cobble pillars. Lever drives the lower row; lamp observes the upper row.
BUILD = [
    # stone floor under the whole joint
    (0, 0, -1, STONE), (0, 0, 0, STONE), (0, 0, 1, STONE),
    (1, 0, -2, STONE),
    (1, 0, -1, STONE), (1, 0, 0, STONE), (1, 0, 1, STONE),
    (2, 0, -1, STONE), (2, 0, 0, STONE), (2, 0, 1, STONE),
    # cobble pillars east/west of the joint (equiv 1096/1098 y=1)
    (0, 1, 0, COB), (2, 1, 0, COB),
    # lever A driving the lower row from the south
    (1, 1, -2, 'minecraft:lever[face=floor,facing=north,powered=false]'),
    # lower N-S dust row at y=1 (middle cell equiv 1097,1,182)
    (1, 1, -1, 'minecraft:redstone_wire'),
    (1, 1, 0, 'minecraft:redstone_wire'),
    (1, 1, 1, 'minecraft:redstone_wire'),
    # cobble lids at y=2 above the lower row (middle equiv 1097,2,182)
    (1, 2, -1, COB), (1, 2, 0, COB), (1, 2, 1, COB),
    # side dusts at y=2 east/west of the joint (equiv 1096/1098 y=2)
    (0, 2, 0, 'minecraft:redstone_wire'),
    (2, 2, 0, 'minecraft:redstone_wire'),
    # upper dust row at y=3 on the lids (middle equiv 1097,3,182)
    (1, 3, -1, 'minecraft:redstone_wire'),
    (1, 3, 0, 'minecraft:redstone_wire'),
    (1, 3, 1, 'minecraft:redstone_wire'),
    (1, 3, 2, 'minecraft:redstone_lamp'),
]

IO = {'levers': {(1, -2): 'A'}, 'lamps': {(1, 3, 2): 'Y'}}
VECS = [{'A': 1}]
# Direct dust-cobble-dust stacks never link (no support, no link): the upper
# row stays dark in BOTH engines. The probe's signal is the dust-level
# agreement at the joint, not the lamp -- WANT False records that.
WANT = [{'Y': False}]


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


def keystr(k):
    return ','.join(str(int(v)) for v in
                    (k if isinstance(k, (tuple, list)) else (k,)))


def cmc_run(ticks, timeout):
    doc_p = os.path.join(HERE, '_stairlid.v2doc.json')
    doc = {
        'blocks': [[int(x), int(y), int(z), str(b)] for x, y, z, b in BUILD],
        'levers': [[keystr(k), v] for k, v in IO['levers'].items()],
        'lamps': [[keystr(k), v] for k, v in IO['lamps'].items()],
        'vectors': VECS,
        'expected': [{o: bool(v) for o in ('Y',)} for v in WANT],
        'sampled': False, 'n_inputs': 1,
    }
    json.dump(doc, open(doc_p, 'w'))
    cmd = [sys.executable if False else 'node',
           os.path.join(HERE, 'cmc_harness.mjs'), doc_p,
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
    for i, vec in enumerate(VECS):
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
            cells = ('1,1,0', '1,2,0', '1,3,0', '0,2,0', '2,2,0')
            sval = [simres[i]['cells'].get(c, 0) for c in cells]
            cval = [cc.get((1, 1, 0), 0), cc.get((1, 2, 0), 0),
                    cc.get((1, 3, 0), 0), cc.get((0, 2, 0), 0),
                    cc.get((2, 2, 0), 0)]
            agreed = (sval == cval)
            agree = agree and agreed
            print('OUT  A=%d lower(1,1,0) sim=%s cmc=%s lid(1,2,0) sim=%s cmc=%s '
                  'upper(1,3,0) sim=%s cmc=%s sideW sim=%s cmc=%s sideE sim=%s cmc=%s %s'
                  % (vec['A'], sval[0], cval[0], sval[1], cval[1],
                     sval[2], cval[2], sval[3], cval[3], sval[4], cval[4],
                     'agree' if agreed else 'DISAGREE'), flush=True)
        if simres[i]['lamps'].get('Y', False) != WANT[i]['Y']:
            sim_wrong = True
    print('\n%s' % ('ENGINES AGREE' if agree and not sim_wrong else
                    'ENGINES DISAGREE on the staircase+lid joint'),
          flush=True)
    return 0 if (agree and not sim_wrong) else 1


if __name__ == '__main__':
    sys.exit(main())
