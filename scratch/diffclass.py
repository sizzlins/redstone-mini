"""Classify the sim-vs-cmc per-cell disagreement on a gate run.

alu4bank_ins.pkl shows 21619/103260 dust cells and 3017/14764 repeaters
disagreeing -- 21% of the build -- while every other gated build shows 0. The
question that decides whether the dual-engine gate is trustworthy: is this a
PER-CELL PHYSICS RULE difference (which would mean the gate can be red on a
correct build, and 'diff=0 on the banked builds' is luck) or one stuck region
in a broken artifact (which makes it a red herring)?

Direction matters more than count. sim's power map is sparse (absent = 0), so
every cell falls into exactly one bucket:

    sim0_cmc+   sim unpowered, cmc powered   <- cmc has spurious power
    sim+_cmc0   sim powered, cmc unpowered   <- sim has spurious power
    both_diff   both powered, different level <- a real decay/lock rule gap
    both_same   agree

If it is one stuck region, sim0_cmc+ cells will be spatially CONTIGUOUS and
clustered; if it is a rule difference, they will be scattered along wires.

Reads only the two JSON tables verify2 already wrote. No engine calls, no
subprocess, no loops over blocks. Bounded by construction.

Usage:  python scratch/diffclass.py <doc.v2doc.json> [vec]
"""
import json
import sys
from collections import defaultdict


def parse(s):
    if not s:
        return {}
    return {tuple(int(v) for v in k.split(',')): int(p) for k, p in s.items()}


def main():
    doc = sys.argv[1]
    vec = sys.argv[2] if len(sys.argv) > 2 else None
    simj = json.load(open(doc + '.sim.json'))
    cmcj = json.load(open(doc + '.cmccells.json'))

    if simj.get('all') and cmcj.get('all'):
        keys = sorted(simj['all'], key=int)
        k = vec or keys[0]
        if k not in simj['all']:
            k = keys[0]
        sv, cv = simj['all'][k], cmcj['all'][k]
        print('using --dump-all tables, vector %s  (%s)'
              % (k, json.dumps(sv.get('vec'))))
    else:
        k = 'single'
        sv, cv = {'cells': simj.get('cells') or {},
                  'repeaters': simj.get('repeaters') or {}}, cmcj
        print('using single-vector tables (re-run with --diff-all for all)')

    for field in ('cells', 'repeaters'):
        s, c = parse(sv.get(field)), parse(cv.get(field))
        keys = set(s) | set(c)
        buckets = defaultdict(int)
        for q in keys:
            a, b = s.get(q, 0), c.get(q, 0)
            if a == b:
                buckets['both_same'] += 1
            elif a == 0:
                buckets['sim0_cmc+'] += 1
            elif b == 0:
                buckets['sim+_cmc0'] += 1
            else:
                buckets['both_diff'] += 1
        print('\n== %s : %d cells compared ==' % (field, len(keys)))
        for name in ('both_same', 'sim0_cmc+', 'sim+_cmc0', 'both_diff'):
            n = buckets[name]
            print('  %-11s %7d  %5.1f%%' % (name, n, 100.0 * n / len(keys)))
        if field != 'cells':
            continue
        # spatial shape of the dominant disagreement bucket
        bad = [(q, s.get(q, 0), c.get(q, 0)) for q in keys
               if s.get(q, 0) != c.get(q, 0)]
        if not bad:
            continue
        xs = [q[0] for q, _, _ in bad]
        ys = [q[1] for q, _, _ in bad]
        zs = [q[2] for q, _, _ in bad]
        print('  spread   x %d..%d   y %d..%d   z %d..%d'
              % (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
        # a stuck region shows up as a small number of distinct y layers and
        # a cmc level distribution that is NOT a decay ladder
        lv = defaultdict(int)
        for _, _, b in bad:
            lv[b] += 1
        top = sorted(lv.items(), key=lambda t: -t[1])[:8]
        print('  cmc levels on disagreeing cells: %s'
              % ', '.join('%d:%d' % t for t in top))
        byl = defaultdict(int)
        for q, _, _ in bad:
            byl[q[1]] += 1
        print('  disagreeing cells per y layer: %s'
              % ', '.join('y%d:%d' % t for t in sorted(byl.items())))
        print('  first 8: %s' % ', '.join(
            '(%d,%d,%d) s=%d c=%d' % (q[0], q[1], q[2], a, b)
            for q, a, b in sorted(bad)[:8]))
    return 0


if __name__ == '__main__':
    sys.exit(main())