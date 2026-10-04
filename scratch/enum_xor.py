"""Enumerative torchless-XOR constructor v7 (dual-subtract, TIGHT+EXACT).

XOR(A,B) = OR(A-B, B-A). Final synthesis of every diagnosed rule:
- TIGHT pins/region (A z=0, B z=3, Y z=5; x1..6 z0..6): short runs.
- per-net DOORSTEP reservation (early routes seal later pin-exits).
- SHARED output penultimate (2,1,5) + forced straight ending (1,1,5):
  lamp-pointing deterministic, no lottery. Guards (1,1,4),(1,1,6) air.
- EXACT level rules per branch (derived, triple-checked): with L =
  output hops (o->...->lamp), need a+L <= 14 (fire reaches lamp) AND
  a+L >= b (kill at (1,1): (b-a)-L <= 0). Asymmetric per branch
  (L1 vs L2) since outputs join only at the shared penultimate.
- isolation: A/B/O nets disjoint AND non-adjacent (merges fatal).
NO refresher (tight runs stay hot), NO zones (tight region constrains),
NO hand-placed logic (positions/facings/routes all enumerated).
First sim-verified 4/4 wins. Raw atoms, machine-discovered.
"""
import sys
from collections import deque

sys.path.insert(0, r'D:\redstone-mini')
sys.path.insert(0, r'D:\redstone-mini\scratch')

X0, X1, Z0, Z1, Y = 1, 10, 0, 6, 1
A_PIN, B_PIN, LAMP = (0, 1, 0), (0, 1, 3), (0, 1, 5)
W = 'minecraft:redstone_wire'
G = 'minecraft:glass'
FACING = {'east': (1, 0), 'west': (-1, 0), 'south': (0, 1),
          'north': (0, -1)}
A_DOOR = {(2, 1, 0), (1, 1, 1)}
B_DOOR = {(2, 1, 3), (1, 1, 4), (1, 1, 2)}
L_DOOR = {(1, 1, 5)}
MID, LAMPADJ = (2, 1, 5), (1, 1, 5)


def _in(x, z):
    return X0 <= x <= X1 and Z0 <= z <= Z1


def _moat(cells):
    """Cells + orthogonal neighbors. Routing a net must avoid another
    net's moat (not just its cells): adjacent dust merges nets even
    without overlap. The isolation post-check catches violations, but
    avoiding moats during BFS finds separated layouts instead of
    hoping."""
    out = set(cells)
    for (x, y, z) in cells:
        out.add((x + 1, y, z))
        out.add((x - 1, y, z))
        out.add((x, y, z + 1))
        out.add((x, y, z - 1))
    return out


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
    import os as _os
    DBG = _os.environ.get('ENUM_DBG') == '1'
    _cnt = {'topo': 0, 'p1': 0, 'p4': 0, 'p2': 0, 'p3': 0, 'q1': 0,
            'q2': 0, 'bal': 0, 'iso': 0, 'cands': 0, 'routes': 0,
            'merge': 0}
    from evo_blocks import _score_job
    from concurrent.futures import ProcessPoolExecutor
    floor = [(x, 0, z, G) for x in range(X0 - 1, X1 + 2)
             for z in range(Z0 - 1, Z1 + 2)]
    pins = [(0, 1, 0,
             'minecraft:lever[face=floor,facing=north,powered=false]'),
            (0, 1, 3,
             'minecraft:lever[face=floor,facing=north,powered=false]'),
            (0, 1, 5, 'minecraft:redstone_lamp')]
    pins_io = {'levers': {(0, 0): 'A', (0, 3): 'B'},
               'lamps': {(0, 5): 'Y'}, 'nets': {}}
    vectors = [{'A': a, 'B': b} for a in (0, 1) for b in (0, 1)]
    expected = [(False,), (True,), (True,), (False,)]
    a_src, b_src = (1, 1, 0), (1, 1, 3)
    cells = [(x, Y, z) for x in range(X0, X1 + 1)
             for z in range(Z0, Z1 + 1)]
    cands = {}
    for c1 in cells:
        # ponytail: no degenerate placements (2026-10-04, diagnosed from
        # a miss-(3) that was a double A-buffer: adjacent comps share
        # side/body cells, structurally excluding B. Comp cells must avoid
        # each other (Manhattan>=2: orthogonal adjacency collides
        # terminals) and feed/lamp-adj cells (would occupy the tap).
        if c1 in (a_src, b_src) or c1 == LAMPADJ:
            continue
        for f1, (fx1, fz1) in FACING.items():
            r1 = (c1[0] + fx1, Y, c1[2] + fz1)
            o1 = (c1[0] - fx1, Y, c1[2] - fz1)
            s1s = [(c1[0] + fz1, Y, c1[2] + fx1),
                   (c1[0] - fz1, Y, c1[2] - fx1)]
            if not _in(*r1[::2]) or not _in(*o1[::2]):
                continue
            for s1 in s1s:
                if not _in(*s1[::2]):
                    continue
                for c2 in cells:
                    if c2 == c1:
                        continue
                    if c2 in (a_src, b_src) or c2 == LAMPADJ:
                        continue
                    if abs(c2[0] - c1[0]) + abs(c2[2] - c1[2]) < 2:
                        continue
                    for f2, (fx2, fz2) in FACING.items():
                        r2 = (c2[0] + fx2, Y, c2[2] + fz2)
                        o2 = (c2[0] - fx2, Y, c2[2] - fz2)
                        s2s = [(c2[0] + fz2, Y, c2[2] + fx2),
                               (c2[0] - fz2, Y, c2[2] - fx2)]
                        if not _in(*r2[::2]) or not _in(*o2[::2]):
                            continue
                        for s2 in s2s:
                            if not _in(*s2[::2]):
                                continue
                            fixed = {c1, r1, o1, s1, c2, r2, o2, s2,
                                     LAMP, A_PIN, B_PIN, a_src, b_src,
                                     MID, LAMPADJ, (1, 1, 4), (1, 1, 6)}
                            for _t in range(4):
                                # ponytail: NET floods (2026-10-04): same-net
                                # routes share freely (forcing p4 to avoid
                                # p1's cells doubled wire for zero electrical
                                # reason). A floods first (p1+p4 sharing),
                                # then B (avoid A, share self), then O
                                # (avoid A+B, share self). Order A,B,O;
                                # later nets route around earlier ones.
                                p1 = _bfs(a_src, {r1},
                                          (fixed | B_DOOR | L_DOOR)
                                          - {r1})
                                if p1 is None:
                                    continue
                                sA = set(p1) | {a_src, r1}
                                # ponytail: TRUNK TAPPING (2026-10-04): later
                                # routes start from ANY cell of their own
                                # net so far (not just the pin), tapping the
                                # trunk like real wiring. Halves wire, eases
                                # isolation (fewer distinct corridors), and
                                # shortens runs (hotter levels). BFS handles
                                # multi-start natively (nearest wins).
                                p4 = _bfs(list(set(p1) | {a_src}), {s2},
                                          (fixed | B_DOOR | L_DOOR)
                                          - {s2})
                                if p4 is None:
                                    continue
                                sA |= set(p4) | {s2}
                                p2 = _bfs(b_src, {s1},
                                          (fixed | sA | _moat(sA) | A_DOOR
                                           | L_DOOR) - {s1})
                                if p2 is None:
                                    continue
                                sB = set(p2) | {b_src, s1}
                                p3 = _bfs(list(set(p2) | {b_src}), {r2},
                                          (fixed | sA | _moat(sA) | A_DOOR
                                           | L_DOOR) - {r2})
                                if p3 is None:
                                    continue
                                sB |= set(p3) | {r2}
                                q1 = _bfs(o1, {MID},
                                          (fixed | sA | sB | _moat(sA)
                                           | _moat(sB) | A_DOOR | B_DOOR
                                           | L_DOOR) - {MID})
                                if q1 is None:
                                    continue
                                sO = set(q1) | {o1, MID}
                                # ponytail: q2 stays SINGLE-start (o2 must
                                # connect; multi-start could strand it on a
                                # nearer trunk, leaving branch-2 dead). It
                                # still shares q1-net freely (sO unblocked).
                                q2 = _bfs(o2, {MID},
                                          (fixed | sA | sB | _moat(sA)
                                           | _moat(sB) | A_DOOR | B_DOOR
                                           | L_DOOR) - {MID})
                                if q2 is None:
                                    continue
                                sO |= set(q2) | {o2}
                                s_ = sA | sB | sO
                                # ponytail: TRUE electrical lengths (2026-10-04,
                                # diagnosed: construction lengths lie when nets
                                # merge/share (pj short-circuits, trunks tap).
                                # Measure shortest dust-paths on the assembled
                                # graph; the level rules become exact and the
                                # sim verdicts the rest. None = disconnected.
                                _dust = (set(p1) | set(p2) | set(p3)
                                         | set(p4) | set(q1) | set(q2)
                                         | {a_src, r1, s2, b_src, s1, r2,
                                            o1, o2, MID, LAMPADJ})
                                def _dist(_a, _b):
                                    _seen, _q = {_a}, [(_a, 0)]
                                    while _q:
                                        _c, _d = _q.pop(0)
                                        if _c == _b:
                                            return _d
                                        for _e in ((1, 0), (-1, 0),
                                                   (0, 1), (0, -1)):
                                            _nb = (_c[0] + _e[0], _c[1],
                                                   _c[2] + _e[1])
                                            if _nb in _dust and \
                                                    _nb not in _seen:
                                                _seen.add(_nb)
                                                _q.append((_nb, _d + 1))
                                    return None
                                a1 = _dist(a_src, r1)
                                b1 = _dist(b_src, s1)
                                a2 = _dist(b_src, r2)
                                b2 = _dist(a_src, s2)
                                L1 = _dist(o1, LAMPADJ)
                                L2 = _dist(o2, LAMPADJ)
                                if None in (a1, b1, a2, b2, L1, L2):
                                    continue
                                if DBG:
                                    _cnt['routes'] += 1
                                if not (a1 + L1 <= 14 and a2 + L2 <= 14):
                                    continue
                                if DBG:
                                    _cnt['bal'] += 1
                                if not (a1 + L1 >= b1 and a2 + L2 >= b2):
                                    continue
                                _A = {a_src, r1, s2} | set(p1) | set(p4)
                                _B = {b_src, s1, r2} | set(p2) | set(p3)
                                _O = {o1, o2, MID, LAMPADJ} | set(q1) \
                                    | set(q2)
                                _netof = {}
                                for _c in _A:
                                    _netof[_c] = 0
                                for _c in _B:
                                    _netof[_c] = 1
                                for _c in _O:
                                    _netof[_c] = 2
                                _ok = True
                                for _c in list(_A | _B | _O):
                                    for _d in ((1, 0), (-1, 0), (0, 1),
                                               (0, -1)):
                                        _nb = (_c[0] + _d[0], _c[1],
                                               _c[2] + _d[1])
                                        if _nb in _netof and \
                                                _netof[_nb] != _netof[_c]:
                                            _ok = False
                                            break
                                    if not _ok:
                                        break
                                if not _ok:
                                    _cnt['merge'] += 1 if DBG else 0
                                # ponytail: isolation NOT enforced as filter
                                # (2026-10-04: correct rule, unsatisfiable as
                                # prefilter at this density -- killed all 1158
                                # route-sets. Merged nets score truthfully
                                # low in sim, so skipping the filter only
                                # costs sim calls, never promotes wrong builds.
                                # Violation counts logged for diagnostics.)
                                if DBG:
                                    _cnt['iso'] += 1
                                genome = {
                                    c1: ('minecraft:comparator[facing=%s,'
                                         'mode=subtract]' % f1),
                                    c2: ('minecraft:comparator[facing=%s,'
                                         'mode=subtract]' % f2)}
                                for t in [a_src] + p1 + [b_src] + p2 \
                                        + p3 + p4 + [o1, o2] + q1 + q2 \
                                        + [MID, LAMPADJ]:
                                    if t not in genome:
                                        genome[t] = W
                                k = '|'.join(
                                    '%d,%d,%d=%s' % (x, y, z, genome[
                                        (x, y, z)])
                                    for x, y, z in sorted(genome))
                                cands[k] = (dict(genome),
                                            (c1, f1, c2, f2))
    print('enumerated %d unique candidates' % len(cands), flush=True)
    if DBG:
        print('DBG stages:', _cnt, flush=True)
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
                pts = -1
            tried += 1
            dist[pts] = dist.get(pts, 0) + 1
            if pts == 3 and outs:
                _exp = [(False,), (True,), (True,), (False,)]
                _miss = tuple(i for i, (o, e) in enumerate(zip(outs, _exp))
                              if tuple(o) != e)
                dist[('miss', _miss)] = dist.get(('miss', _miss), 0) + 1
                # ponytail: save FIRST miss-(3) for level-tracing (why does
                # balanced+isolated output stay lit on (1,1)?). Diagnostic
                # artifact, overwritten per run, never a product.
                if _miss == (3,) and not dist.get('saved3', 0):
                    dist['saved3'] = 1
                    import pickle
                    with open('D:/redstone-mini/scratch/xor_miss3.pkl',
                              'wb') as fo:
                        pickle.dump({'genome': dict(cands[k][0])}, fo)
            if pts == 4:
                import pickle
                genome, (c1, f1, c2, f2) = cands[k]
                with open('D:/redstone-mini/scratch/xor_found.pkl',
                          'wb') as fo:
                    pickle.dump({'genome': genome}, fo)
                print('SOLVED 4/4: %s/%s + %s/%s (%d cells)'
                      % (c1, f1, c2, f2, len(genome)), flush=True)
                for cc in sorted(genome):
                    print('  ', cc, genome[cc].split(':')[1].split(
                        '[')[0], flush=True)
                return
    print('done: %d candidates, no 4/4 -- score mix %s' % (tried, dist),
          flush=True)


if __name__ == '__main__':
    main()
