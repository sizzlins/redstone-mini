"""Enumerative torchless-AND constructor (enum_not's sibling).

AND(A,B) = compare(rear=A, side=B) in ONE comparator, no constants
(verified by truth table: 0>=0->0, 15>=0->15, 0>=15->0, 15>=15->15).
Smaller search than NOT (no lever, fixed compare, fixed rear=A/side=B
assignment -- compare is asymmetric so only this orientation works).
Enumerate comp pos x facing x side-choice with BFS routes (A-pin ->
rear, B-pin -> side, output-cell -> lamp-adjacent, all mutually
disjoint). First sim-verified 4/4 wins. Raw atoms, machine-discovered.
"""
import sys
from collections import deque

sys.path.insert(0, r'D:\redstone-mini')
sys.path.insert(0, r'D:\redstone-mini\scratch')

X0, X1, Z0, Z1, Y = 1, 10, 0, 12, 1
A_PIN, B_PIN, LAMP = (0, 1, 0), (0, 1, 6), (0, 1, 12)
W = 'minecraft:redstone_wire'
G = 'minecraft:glass'
FACING = {'east': (1, 0), 'west': (-1, 0), 'south': (0, 1),
          'north': (0, -1)}


def _in(x, z):
    return X0 <= x <= X1 and Z0 <= z <= Z1


def _bfs(starts, goals, blocked):
    import random as _r
    if isinstance(starts, tuple):
        starts = [starts]
    _dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    _r.shuffle(_dirs)
    seen = set(starts)
    q = deque([(s, [s]) for s in starts])
    while q:
        c, path = q.popleft()
        if c in goals:
            return path[1:]
        for dx, dz in _dirs:
            nb = (c[0] + dx, c[1], c[2] + dz)
            if not _in(nb[0], nb[2]) or nb in seen or nb in blocked:
                continue
            seen.add(nb)
            q.append((nb, path + [nb]))
    return None


def main():
    from evo_blocks import _score_job
    floor = [(x, 0, z, G) for x in range(X0 - 1, X1 + 2)
             for z in range(Z0 - 1, Z1 + 2)]
    pins = [(0, 1, 0,
             'minecraft:lever[face=floor,facing=north,powered=false]'),
            (0, 1, 6,
             'minecraft:lever[face=floor,facing=north,powered=false]'),
            (0, 1, 12, 'minecraft:redstone_lamp')]
    pins_io = {'levers': {(0, 0): 'A', (0, 6): 'B'},
               'lamps': {(0, 12): 'Y'}, 'nets': {}}
    vectors = [{'A': a, 'B': b} for a in (0, 1) for b in (0, 1)]
    expected = [(False,), (False,), (False,), (True,)]
    a_src, b_src = (1, 1, 0), (1, 1, 6)
    lamp_adjs = [(1, 1, 12)]
    cands = {}
    for cx in range(X0, X1 + 1):
        for cz in range(Z0, Z1 + 1):
            for f, (fx, fz) in FACING.items():
                c = (cx, Y, cz)
                rear = (cx + fx, Y, cz + fz)
                out = (cx - fx, Y, cz - fz)
                sides = [(cx + fz, Y, cz + fx), (cx - fz, Y, cz - fx)]
                if not _in(*rear[::2]) or not _in(*out[::2]):
                    continue
                if rear in (a_src, b_src) or out in (a_src, b_src) \
                        or c in (a_src, b_src):
                    continue
                for side in sides:
                    if not _in(*side[::2]):
                        continue
                    other = sides[1] if side == sides[0] else sides[0]
                    # ROUTE OUTPUT FIRST (2026-10-04: routing A then B
                    # first lets them form a sealed box around the output
                    # cell. Most-constrained routes first; A/B go around).
                    # ponytail: resample per trial (lamp-pointing hinges on
                    # the output ENDING geometry; single-shot BFS picks one
                    # ending and corner-endings leave hot dust dark-lamped).
                    base = ({c, rear, out, side, other, LAMP, A_PIN, B_PIN,
                             a_src, b_src} | {(0, 1, 5), (0, 1, 7)})
                    for _trial in range(8):
                        op = _bfs(out, {(1, 1, 12)}, base - {(1, 1, 12)})
                        if op is None:
                            continue
                        ops = set(op)
                        blocked = ((base | ops) - {rear})
                        r1 = _bfs(a_src, {rear}, blocked)
                        if r1 is None:
                            continue
                        r1s = set(r1)
                        blocked_b = ((base | ops | r1s) - {b_src, side})
                        r2 = _bfs(b_src, {side}, blocked_b)
                        if r2 is None:
                            continue
                        # ponytail: ANALOG LEVEL DISCIPLINE (2026-10-04,
                        # diagnosed from 976 identical (1,1)-dark misses).
                        # Compare outputs the REAR LEVEL (not refreshed):
                        # end-lamp level = 15-len(r1)-len(op) must stay >=1,
                        # and (1,1) needs rear >= side i.e. len(r1)<=len(r2)
                        # (a longer A-run makes side win and kills output).
                        # Vanilla-analog, not a sim artifact: any compare-AND
                        # must balance input runs or refresh first.
                        if len(r1) + len(op) > 13:
                            continue
                        if len(r1) > len(r2):
                            continue
                        r2s = set(r2)
                        _A = {a_src, rear} | r1s
                        _B = {b_src, side} | r2s
                        _O = {out} | ops | {(1, 1, 12)}
                        _netof = {}
                        for _c in _A:
                            _netof[_c] = 0
                        for _c in _B:
                            _netof[_c] = 1
                        for _c in _O:
                            _netof[_c] = 2
                        _ok = True
                        for _c in list(_A | _B | _O):
                            for _d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                                _nb = (_c[0] + _d[0], _c[1], _c[2] + _d[1])
                                if _nb in _netof and \
                                        _netof[_nb] != _netof[_c]:
                                    _ok = False
                                    break
                            if not _ok:
                                break
                        if not _ok:
                            continue
                        genome = {c: (
                            'minecraft:comparator[facing=%s,mode=compare]'
                            % f)}
                        for t in [a_src, rear] + r1 + [b_src, side] + r2 \
                                + [out] + op:
                            if t not in genome:
                                genome[t] = W
                        k = '|'.join('%d,%d,%d=%s' % (x, y, z, genome[
                            (x, y, z)]) for x, y, z in sorted(genome))
                        cands[k] = (dict(genome), (c, f, side, rear))
    print('enumerated %d unique candidates' % len(cands), flush=True)
    from concurrent.futures import ProcessPoolExecutor
    jobs = [(g, pins, floor, pins_io, vectors, expected, ['Y'])
            for g, _ in cands.values()]
    keys = list(cands)
    tried, dist = 0, {}
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(_score_job, j) for j in jobs]
        for k, fu in zip(keys, futs):
            try:
                pts, w, n, outs, err = fu.result(timeout=60)
            except Exception:
                pts, outs = -1, []
            tried += 1
            dist[pts] = dist.get(pts, 0) + 1
            # fail-vector fingerprint for 3/4s (which single vector is
            # wrong diagnoses reach vs pointing vs contamination).
            if pts == 3 and outs:
                _exp = [(False,), (False,), (False,), (True,)]
                _miss = tuple(i for i, (o, e) in enumerate(zip(outs, _exp))
                              if tuple(o) != e)
                dist[('miss', _miss)] = dist.get(('miss', _miss), 0) + 1
            if pts == 4:
                import pickle
                genome, (c, f, side, rear) = cands[k]
                with open('D:/redstone-mini/scratch/and_found.pkl',
                          'wb') as fo:
                    pickle.dump({'genome': genome}, fo)
                print('SOLVED 4/4: comp %s facing %s side %s rear %s '
                      '(%d cells)' % (c, f, side, rear, len(genome)),
                      flush=True)
                for cc in sorted(genome):
                    print('  ', cc, genome[cc].split(':')[1].split(
                        '[')[0], flush=True)
                return
    print('done: %d candidates, no 4/4 -- score mix %s' % (tried, dist),
          flush=True)


if __name__ == '__main__':
    main()
