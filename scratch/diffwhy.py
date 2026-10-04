"""Analyse a verify2 per-cell differential: which cells, which vectors, and
what the neighbourhood looks like (blocks + both engines' values).
Usage: diffwhy.py <doc.v2doc.json> [--examples N]
"""
import json
import os
import sys


def main():
    doc_p = sys.argv[1]
    maxex = int(sys.argv[sys.argv.index('--examples') + 1]) \
        if '--examples' in sys.argv else 3
    doc = json.load(open(doc_p))
    sim = json.load(open(doc_p + '.sim.json'))
    cmc = json.load(open(doc_p + '.cmccells.json'))
    blocks = {(b[0], b[1], b[2]): b[3] for b in doc['blocks']}
    nets = {}
    allv = cmc.get('all') or {}
    simall = sim.get('all') or {}
    pv = json.load(open(doc_p + '.verdict.json')).get('diff', {})
    print('per-vector mismatches:',
          [(v['vec'], v['mismatches']) for v in pv.get('per_vector', [])
           if v['mismatches']])
    cells = {}
    for k in sorted(allv, key=int):
        cc = allv[k].get('cells') or {}
        sc = (simall.get(k) or {}).get('cells') or {}
        for c in set(cc) | set(sc):
            a, b = int(sc.get(c, 0)), int(cc.get(c, 0))
            if a != b:
                cells.setdefault(c, []).append((k, a, b))
    print('\ndistinct mismatching cells: %d' % len(cells))
    for c, occ in sorted(cells.items()):
        print('  %-12s x%d  %s' % (c, len(occ), occ[:6]))
    for c, occ in list(sorted(cells.items()))[:maxex]:
        x, y, z = [int(v) for v in c.split(',')]
        print('\n=== context for %s (sim=%s cmc=%s) ==='
              % (c, occ[0][1], occ[0][2]))
        for dy in (0,):
            for dx in range(-3, 4):
                for dz in range(-3, 4):
                    p = (x + dx, y + dy, z + dz)
                    b = blocks.get(p)
                    if b is None:
                        continue
                    sv = 0
                    cv = 0
                    for k in allv:
                        sv = int(((simall.get(k) or {}).get('cells') or {})
                                 .get('%d,%d,%d' % p, 0))
                        cv = int((allv[k].get('cells') or {})
                                 .get('%d,%d,%d' % p, 0))
                        if sv or cv:
                            break
                    print('   %-14s %-46s sim=%-3s cmc=%s'
                          % (str(p), b[:46], sv, cv))


if __name__ == '__main__':
    main()
