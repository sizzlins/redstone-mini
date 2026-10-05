"""One-repeater facing probe, all 4 facings: which side drives?

The alu4merge_g 64-vector diff's worst examples were flat repeater-fed runs
(sim=15..9 vs cmc=0 downstream). sim stores facing negated (rep = -travel);
cmc reads it oppositely on paper, yet they agree on 4000+ repeaters -- so the
convention does not resolve from verdict tables. One repeater per facing,
known input side, both engines, decides it. (Settling, not facing, explained
alu4merge_g -- repchain.py -- but the facing test stands on its own and closes
the open item without picking a side from JSON.)

Per facing: lever on the input side (rear at +facing per sim convention),
dust, repeater, dust, lamp on the output side. Exits 0 iff all 4 agree.

NEVER HANGS: one sim._run_vec per facing in-process, one node call per
facing under a hard timeout. Bounded blocks, one vector each.

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
W = 'minecraft:redstone_wire'

FACINGS = {'east': (1, 0), 'west': (-1, 0), 'south': (0, 1), 'north': (0, -1)}


def build_for(face):
    fx, fz = FACINGS[face]
    rx, rz = 2, 0
    ix, iz = rx + fx, rz + fz
    lx, lz = rx + 2 * fx, rz + 2 * fz
    ox, oz = rx - fx, rz - fz
    px, pz = rx - 2 * fx, rz - 2 * fz
    xs = [x for x, z in [(lx, lz), (ix, iz), (rx, rz), (ox, oz), (px, pz)]]
    zs = [z for x, z in [(lx, lz), (ix, iz), (rx, rz), (ox, oz), (px, pz)]]
    floor = [(x, 0, z, STONE) for x in range(min(xs) - 1, max(xs) + 2)
             for z in range(min(zs) - 1, max(zs) + 2)]
    build = floor + [
        (lx, 1, lz, 'minecraft:lever[face=floor,facing=north,powered=false]'),
        (ix, 1, iz, W),
        (rx, 1, rz, 'minecraft:repeater[facing=%s,delay=1]' % face),
        (ox, 1, oz, W),
        (px, 1, pz, 'minecraft:redstone_lamp'),
    ]
    io = {'levers': {(lx, lz): 'A'}, 'lamps': {(px, pz): 'Y'}}
    return build, io


def sim_run(build, io):
    from sim import _parse_build, _run_vec
    P = _parse_build([tuple(b) for b in build], io)
    got, live, tlive, nticks, rlive, conc = _run_vec({'A': 1}, None, P)
    return ({k: bool(v) for k, v in got.items()},
            {'%d,%d,%d' % c: int(p) for c, p in live.items()},
            {'%d,%d,%d' % c: int(p) for c, p in rlive.items()})


def cmc_run(face, build, io, ticks, timeout):
    doc_p = os.path.join(HERE, '_repface_%s.v2doc.json' % face)
    doc = {
        'blocks': [[int(x), int(y), int(z), str(b)] for x, y, z, b in build],
        'levers': [['%d,%d' % k, v] for k, v in io['levers'].items()],
        'lamps': [['%d,%d' % k, v] for k, v in io['lamps'].items()],
        'vectors': [{'A': 1}],
        'expected': [{'Y': True}],
        'sampled': False, 'n_inputs': 1,
    }
    json.dump(doc, open(doc_p, 'w'))
    cmd = ['node', os.path.join(HERE, 'cmc_harness.mjs'), doc_p,
           '--ticks', str(ticks),
           '--dump-cells', doc_p + '.cmccells.json', '--dump-all']
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=ROOT)
        s = p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        return None
    for line in s.splitlines():
        line = line.strip()
        if line.startswith('{'):
            try:
                blob = json.loads(line[line.index('{'):])
            except ValueError:
                continue
            if 'ok' in blob:
                return blob
    try:
        dump = json.load(open(doc_p + '.cmccells.json'))
        if dump.get('all'):
            return {'ok': None, 'dump': dump}
    except (OSError, ValueError):
        pass
    return None


def main():
    ticks, timeout = 400, 300
    a = sys.argv[1:]
    if '--ticks' in a:
        ticks = int(a[a.index('--ticks') + 1])
    if '--cmc-timeout' in a:
        timeout = int(a[a.index('--cmc-timeout') + 1])
    bad = []
    for face, (fx, fz) in FACINGS.items():
        build, io = build_for(face)
        lamps, cells, reps = sim_run(build, io)
        sim_lamp = lamps.get('Y', False)
        ix, iz = 2 + fx, 0 + fz
        ox, oz = 2 - fx, 0 - fz
        icell = '%d,1,%d' % (ix, iz)
        ocell = '%d,1,%d' % (ox, oz)
        rcell = '2,1,0'
        cmcres = cmc_run(face, build, io, ticks, timeout)
        if cmcres is None:
            print('%-5s CMC unavailable -- sim-only, no verdict' % face,
                  flush=True)
            bad.append(face)
            continue
        dump = cmcres.get('dump') or {}
        if dump.get('all'):
            cc = {k: int(p) for k, p in dump['all']['0']['cells'].items()}
            cr = {k: int(p) for k, p in
                  dump['all']['0'].get('repeaters', {}).items()}
            agreed = (cells.get(icell, 0) == cc.get(icell, 0) and
                      cells.get(ocell, 0) == cc.get(ocell, 0) and
                      reps.get(rcell, '-') == cr.get(rcell, '-') and
                      sim_lamp is True)
            print('%-5s in(%s) sim=%s cmc=%s rep sim=%s cmc=%s out(%s) sim=%s cmc=%s lamp=%s %s'
                  % (face, icell, cells.get(icell, 0), cc.get(icell, 0),
                     reps.get(rcell, '-'), cr.get(rcell, '-'), ocell,
                     cells.get(ocell, 0), cc.get(ocell, 0), sim_lamp,
                     'agree' if agreed else 'DISAGREE'), flush=True)
            if not agreed:
                bad.append(face)
    print('\n%s' % ('ALL 4 FACINGS AGREE' if not bad else
                    'DISAGREE on: %s' % ','.join(bad)), flush=True)
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
