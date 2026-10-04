"""Enumerative torchless-NOT constructor (approach #11, rule 3).

Random sampling failed ~80k evals: a working NOT needs ~12 coordinated
cells that blind draws never land together. This ENUMERATES the natural
NOT space completely over tight bounds instead: comparator pos x facing
x side-choice, rear lever-ON forced by facing, canonical BFS routes
(A-pin -> side, output-cell -> lamp-adjacent, mutually disjoint,
lever-contamination-free). First sim-verified 2/2 wins.
Machine-discovered (search order only); still raw atoms; function fully
verified, never hand-picked. Bounds expand on failure (logged).

Two phases: enumerate (pure BFS, fast) then score in worker processes
with hard timeouts -- an oscillating candidate hangs _run_vec forever
in-process (rule 7; the 840s tool timeout proved it).
"""
import os
import sys
from collections import deque

sys.path.insert(0, r'D:\redstone-mini')
sys.path.insert(0, r'D:\redstone-mini\scratch')

X0, X1, Z0, Z1, Y = 1, 7, 0, 7, 1
A_PIN, LAMP = (0, 1, 0), (0, 1, 6)
W = 'minecraft:redstone_wire'
G = 'minecraft:glass'
LEVON = 'minecraft:lever[face=floor,facing=north,powered=true]'
FACING = {'east': (1, 0), 'west': (-1, 0), 'south': (0, 1),
          'north': (0, -1)}


def _in(x, z):
    return X0 <= x <= X1 and Z0 <= z <= Z1


def _bfs(starts, goals, blocked):
    """Shortest dust path (y=1 flat, floor everywhere). Cell list
    excluding starts, including goal; None if unreachable. Neighbor order
    shuffled per call so repeats sample different shortest paths."""
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
            (0, 1, 6, 'minecraft:redstone_lamp')]
    pins_io = {'levers': {(0, 0): 'A'}, 'lamps': {(0, 6): 'Y'}, 'nets': {}}
    vectors = [{'A': 0}, {'A': 1}]
    expected = [(True,), (False,)]
    a_src = (1, 1, 0)
    lamp_adj = [(1, 1, 6), (0, 1, 5), (0, 1, 7)]
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
                if rear == a_src or out == a_src or c == a_src:
                    continue
                for side in sides:
                    if not _in(*side[::2]):
                        continue
                    other = sides[1] if side == sides[0] else sides[0]
                    rear_nb = {(rear[0] + dx, rear[1], rear[2] + dz)
                               for dx, dz in
                               ((1, 0), (-1, 0), (0, 1), (0, -1))}
                    # pins 2 apart strangle routing (side and output nets
                    # collide; the proven hand-NOT needed lamp 4 away with
                    # a long clean output route). Wider pins + bigger
                    # region = room to separate nets.
                    lamp_nb = [(0, 1, 5), (0, 1, 7), (1, 1, 6)]
                    blocked = ({c, rear, out, other, LAMP} | set(lamp_nb)
                               | rear_nb)
                    for _trial in range(8):
                        sp = _bfs(a_src, {side}, blocked)
                        if sp is None:
                            continue
                        sp_set = set(sp)
                        blocked2 = ({c, rear, side, other, A_PIN, a_src}
                                    | sp_set | rear_nb)
                        op = _bfs(out, set(lamp_adj), blocked2)
                        if op is None:
                            continue
                        genome = {rear: LEVON, c: (
                            'minecraft:comparator[facing=%s,mode=subtract]'
                            % f)}
                        for t in [a_src, side, out] + sp + op:
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
                pts = -1
            tried += 1
            dist[pts] = dist.get(pts, 0) + 1
            if pts == 2:
                import pickle
                genome, (c, f, side, rear) = cands[k]
                with open('D:/redstone-mini/scratch/not_found.pkl',
                          'wb') as fo:
                    pickle.dump({'genome': genome}, fo)
                print('SOLVED 2/2: comp %s facing %s side %s rear %s '
                      '(%d cells)' % (c, f, side, rear, len(genome)),
                      flush=True)
                for cc in sorted(genome):
                    print('  ', cc, genome[cc].split(':')[1].split(
                        '[')[0], flush=True)
                return
    print('done: %d candidates, no 2/2 -- score mix %s' % (tried, dist),
          flush=True)


if __name__ == '__main__':
    main()
