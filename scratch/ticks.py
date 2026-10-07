"""Worst-case settle ticks: the speed half of (compact, fast).

Timing model (cmc engine.js, confirmed read, not assumed): dust networks
recompute instantly with -1 falloff per hop (0 ticks); torches invert at
1 rt; repeaters delay 1-4 rt (ours are delay-1, so 1 rt each); comparators
re-fire at 1 rt; lamps take 4 gt to turn OFF. So a build's settling time
is the longest input->output chain of device delays -- which is exactly
what sim's tick count measures per vector. worst_ticks() takes the max
over vectors: the number to minimize.

Usage:
  python scratch/ticks.py <recipe.txt> <build.pkl> [max_vecs]
Prints worst ticks + the vector that caused it. Exit 0 always (it is a
measurement, not a gate); callers decide what wins.

Sampling honesty (sweep lesson): n<=10 runs the full space; above that
a 64-vector spread sample, and the output says SAMPLED.
"""
import itertools
import pickle
import sys

sys.path.insert(0, r'D:\redstone-mini')


def spread_vectors(inputs, n=64):
    """Deterministic spread: single-bit, alternating, then strided."""
    import hashlib
    vecs = []
    vecs.append({k: 0 for k in inputs})
    for i, k in enumerate(inputs):
        vecs.append({kk: 1 if kk == k else 0 for kk in inputs})
    m = len(inputs)
    for alt in (0x55, 0xAA):
        vecs.append({k: (alt >> (i % 8)) & 1 for i, k in enumerate(inputs)})
    i = len(vecs)
    while len(vecs) < n:
        h = int(hashlib.sha256(str(i).encode()).hexdigest(), 16)
        vecs.append({k: (h >> j) & 1 for j, k in enumerate(inputs)})
        i += 1
    seen, out = set(), []
    for v in vecs:
        t = tuple(v[k] for k in inputs)
        if t not in seen:
            seen.add(t)
            out.append(v)
    return out[:n]


def all_vectors(inputs):
    out = []
    for bits in itertools.product((0, 1), repeat=len(inputs)):
        out.append(dict(zip(inputs, bits)))
    return out


def worst_ticks(blocks, io, inputs, vecs=None):
    """Max sim settle ticks over vecs. Returns (worst, worst_vec, n)."""
    from sim import _parse_build, _run_vec
    if vecs is None:
        if len(inputs) <= 10:
            vecs = all_vectors(inputs)
            sampled = False
        else:
            vecs = spread_vectors(inputs)
            sampled = True
    else:
        sampled = len(vecs) < 2 ** len(inputs)
    P = _parse_build([tuple(b) for b in blocks], io)
    worst, wvec = -1, None
    for v in vecs:
        full = {k: v.get(k, 0) for k in set(io['levers'].values())}
        _, _, _, ticks, _, _ = _run_vec(full, None, P)
        if ticks > worst:
            worst, wvec = ticks, dict(v)
    return worst, wvec, len(vecs), sampled


def main():
    from recipe import parse_recipe
    if '--help' in sys.argv or len(sys.argv) < 3:
        print(__doc__)
        return
    src, pkl = sys.argv[1], sys.argv[2]
    cap = int(sys.argv[3]) if len(sys.argv) > 3 else None
    r = parse_recipe(open(src).read())
    d = pickle.load(open(pkl, 'rb'))
    vecs = None
    if cap is not None:
        vecs = spread_vectors(r['inputs'], cap)
    worst, wvec, n, sampled = worst_ticks(d['blocks'], d['io'], r['inputs'], vecs)
    print('worst_ticks=%d n=%d%s worst_vec=%s'
          % (worst, n, ' SAMPLED' if sampled else ' exhaustive',
             ''.join(str(wvec[k]) for k in r['inputs'])))


if __name__ == '__main__':
    if len(sys.argv) > 2:
        main()
    else:
        # Self-checks (repo convention: asserts, no framework).
        # 1. Agreement with the authority: worst_ticks over a tiny build
        #    equals the max of direct _run_vec ticks (same engine).
        from recipe import parse_recipe
        from sim import _parse_build, _run_vec
        from compose import compose
        r = parse_recipe('IN A, B\nOUT Y\nx0 = A XOR B\nY = x0 AND x0\n')
        blocks, _, io = compose(r)
        P = _parse_build([tuple(b) for b in blocks], io)
        expect = -1
        for a in (0, 1):
            for b in (0, 1):
                _, _, _, t, _, _ = _run_vec({'A': a, 'B': b}, None, P)
                expect = max(expect, t)
        got, _, n, sampled = worst_ticks(blocks, io, ['A', 'B'])
        assert not sampled and n == 4, (n, sampled)
        assert got == expect, (got, expect)
        # 2. Ticks are finite and non-negative on every vector.
        assert isinstance(got, int) and got >= 0
        # 3. Spread mode is honest about sampling.
        _, _, n2, sampled2 = worst_ticks(
            blocks, io, ['A%d' % i for i in range(12)])
        assert sampled2 and n2 == 64, (n2, sampled2)
        print('ticks ok: and-gate worst=%d (exhaustive 4v)' % got)
