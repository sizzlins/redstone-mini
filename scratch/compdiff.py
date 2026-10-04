"""alu4bank_ins: is the 21% disagreement one root cause or a systemic gap?

scratch/diffclass.py already showed 87.7% of cells agree, that the 3069
disagreeing cells are sim=0/cmc=powered with a clean cmc decay ladder, and that
only 45 cells are both-powered-at-different-levels. That shape is consistent
with ONE upstream difference (some comparator outputs a level in cmc and not in
sim) and everything else being downstream decay -- but "consistent with" is not
evidence.

This tests it directly: find the build's comparators, and ask both engines what
each one OUTPUTS. If exactly one comparator disagrees, the 21% is downstream of
a single cell and the finding is "one comparator rule", not "the engines
disagree about redstone". If many disagree in the same direction, it is
systemic.

Reads only the cached JSON tables verify2 already wrote. No engine calls, no
sim, no node -- safe to run while another agent is editing simvec.py.

NEVER HANGS: two JSON reads, bounded loops over cells already in memory.

Usage:  python scratch/compdiff.py <doc.v2doc.json> [vec]
"""
import json
import sys


def parse(s):
    if not s:
        return {}
    return {tuple(int(v) for v in k.split(',')): int(p) for k, p in s.items()}


def main():
    doc = sys.argv[1]
    vec = sys.argv[2] if len(sys.argv) > 2 else None
    simj = json.load(open(doc + '.sim.json'))
    cmcj = json.load(open(doc + '.cmccells.json'))
    blocks = {(b[0], b[1], b[2]): str(b[3]) for b in json.load(open(doc))['blocks']}

    if simj.get('all') and cmcj.get('all'):
        keys = sorted(simj['all'], key=int)
        k = vec or keys[0]
        sv, cv = simj['all'][k], cmcj['all'][k]
    else:
        k = 'single'
        sv = {'cells': simj.get('cells') or {}, 'repeaters': simj.get('repeaters') or {}}
        cv = cmcj
    print('vector %s  sim cells=%d  cmc cells=%d'
          % (k, len(sv.get('cells') or {}), len(cv.get('cells') or {})))

    comps = sorted(c for c, b in blocks.items() if 'comparator' in b)
    reps = sorted(c for c, b in blocks.items() if 'repeater' in b)
    print('build has %d comparators, %d repeaters' % (len(comps), len(reps)))

    # BFS from every disagreeing cell to the nearest disagreeing cell that is
    # NOT dust: a comparator, a repeater or a lamp. That is the smallest
    # description of "where the two engines start to differ".
    sc = parse(sv.get('cells'))
    cc = parse(cv.get('cells'))
    diff = {q for q in set(sc) | set(cc) if sc.get(q, 0) != cc.get(q, 0)}
    print('disagreeing cells: %d' % len(diff))
    seen = set()
    roots = []
    for q in diff:
        if q in seen:
            continue
        stack, comp = [q], []
        seen.add(q)
        while stack:
            x = stack.pop()
            comp.append(x)
            for d in ((1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)):
                n = (x[0] + d[0], x[1] + d[1], x[2] + d[2])
                if n in diff and n not in seen:
                    seen.add(n)
                    stack.append(n)
        roots.append(comp)
    roots.sort(key=len, reverse=True)
    print('connected components of disagreement: %d' % len(roots))
    print('largest component: %d cells (%.0f%% of all disagreement)'
          % (len(roots[0]), 100.0 * len(roots[0]) / max(len(diff), 1)))

    print('\nnon-dust blocks sitting inside disagreement components:')
    hits = 0
    for comp in roots[:6]:
        for x in comp:
            b = blocks.get(x, '')
            if 'redstone_wire' in b:
                continue
            hits += 1
            if hits <= 14:
                print('   %-16s %-52s sim=%-3s cmc=%-3s'
                      % (str(x), b.replace('minecraft:', '')[:52],
                         sc.get(x, '-'), cc.get(x, '-')))
    if not hits:
        print('   (none -- the disagreement is confined to dust, so it is a '
              'LEVEL/decay difference, not a component firing differently)')

    print('\ncomparator output cells (the cell each one drives):')
    print('   %-16s %-30s %-18s %s' % ('comparator', 'mode/facing', 'drives',
                                       'sim / cmc'))
    for c in comps:
        b = blocks[c].replace('minecraft:comparator', '')
        facing = 'west'
        for f in ('east', 'west', 'north', 'south'):
            if 'facing=%s' % f in b:
                facing = f
        mode = 'subtract' if 'subtract' in b else 'compare'
        # output is opposite the rear; sim puts rear at +facing
        off = {'east': (-1, 0), 'west': (1, 0), 'north': (0, 1),
               'south': (0, -1)}[facing]
        out = (c[0] + off[0], c[1], c[2] + off[1])
        # absent in sim's SPARSE map means 0 -- comparing that against cmc's
        # dense 0 would report a disagreement that is not one.
        so, co = sc.get(out, 0), cc.get(out, 0)
        flag = '  <-- DISAGREE' if so != co else ''
        print('   %-16s %-30s %-18s %s / %s%s'
              % (str(c), '%s,%s' % (mode, facing), str(out), so, co, flag))
    return 0


if __name__ == '__main__':
    sys.exit(main())