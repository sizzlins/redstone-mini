"""Block-level evolver: 1-bit full adder from raw atoms. No gates, no torch.

Genome = sparse dict of cells in a bounded box (absent = air). Fixed
pins (3 levers + 2 lamps at x=0, glass floor y=0 pre-laid as
scaffolding, never in the genome). Alphabet: air/dust/glass/top-slab/
target/repeaterx4/comparatorx4x2/leverON/leverOFF. Fitness: phase 1 =
lamp-points /16 (8 vectors x S,COUT); phase 2 (at 16/16) =
lexicographic (width, blocks), height free per operator. Every
candidate scored by serial _run_vec x8 (no nested pools); support
pre-filtered statically at mutation (the sim is blind to floating
levers the same way it was blind to y==1 floors -- lesson applied
proactively) with _check_supports as backstop (FLOATING = 0 points).

Usage: python scratch/evo_blocks.py <recipe> <workdir> [evals] [seed]
Writes best.pkl + memo.json + evo.log. Resumable (best.pkl re-verified
on load; memo engine-fingerprinted).
"""
import itertools
import os
import random
import sys
import time

sys.path.insert(0, r'D:\redstone-mini')

# ---- region + pins (fixed scaffolding, never evolved) ----
XMAX, YMAX, ZMAX = 8, 5, 9
PINS = [  # (x, y, z, bid, kind, name)
    (0, 1, 0, 'minecraft:lever[face=floor,facing=north,powered=false]',
     'lever', 'A'),
    (0, 1, 2, 'minecraft:lever[face=floor,facing=north,powered=false]',
     'lever', 'B'),
    (0, 1, 4, 'minecraft:lever[face=floor,facing=north,powered=false]',
     'lever', 'CIN'),
    (0, 1, 6, 'minecraft:redstone_lamp', 'lamp', 'S'),
    (0, 1, 8, 'minecraft:redstone_lamp', 'lamp', 'COUT'),
]
FLOOR = [(x, 0, z, 'minecraft:glass')
         for x in range(-1, XMAX + 2) for z in range(-1, ZMAX + 2)]

DUST = 'minecraft:redstone_wire'
GLASS = 'minecraft:glass'
SLAB = 'minecraft:stone_slab[type=top]'
TARGET = 'minecraft:target'
REPS = ['minecraft:repeater[facing=%s,delay=1]' % f
        for f in ('north', 'south', 'east', 'west')]
COMPS = ['minecraft:comparator[facing=%s,mode=%s]' % (f, m)
         for f in ('north', 'south', 'east', 'west')
         for m in ('compare', 'subtract')]
LEVON = 'minecraft:lever[face=floor,facing=north,powered=true]'
LEVOFF = 'minecraft:lever[face=floor,facing=north,powered=false]'
ALPHA = ['air', DUST, GLASS, SLAB, TARGET] + REPS + COMPS + [LEVON, LEVOFF]
NEEDS_BELOW = set(
    [DUST, SLAB, TARGET] + REPS + COMPS + [LEVON, LEVOFF])
SOLID_BELOW = set(['minecraft:glass', 'minecraft:stone_slab[type=top]',
                   'minecraft:target'])


def _solid_below(bmap, c):
    x, y, z = c
    if y - 1 == 0:
        return True  # pre-laid glass floor spans the region
    b = bmap.get((x, y - 1, z), '').split('[')[0]
    return b in ('minecraft:glass', 'minecraft:stone_slab',
                 'minecraft:target', 'minecraft:redstone_lamp')


def _neighbors(c):
    x, y, z = c
    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nb = (x + dx, y, z + dz)
        if 1 <= nb[0] <= XMAX and 1 <= nb[1] <= YMAX and 0 <= nb[2] <= ZMAX:
            yield nb


def _mutate(rng, genome):
    """Single-cell change with static support pre-filter (bounded tries).

    Half the draws land next to live cells: connectivity is what scores,
    and uniform sampling almost never extends a net.
    """
    g = dict(genome)
    bmap = dict(g)
    for _ in range(12):
        if g and rng.random() < 0.5:
            base = rng.choice(list(g))
            nbs = list(_neighbors(base))
            if not nbs:
                continue
            c = rng.choice(nbs)
        else:
            c = (rng.randint(1, XMAX), rng.randint(1, YMAX),
                 rng.randint(0, ZMAX))
        st = rng.choice(ALPHA)
        if st == 'air':
            if c in g:
                del g[c]
            return g
        if st in NEEDS_BELOW and not _solid_below(bmap, c):
            continue
        g[c] = st
        return g
    return g


def _grow(rng):
    """Fresh CONNECTED genome: random-walk dust trails out of every pin,
    comparators/repeaters sprinkled touching dust, a couple of constants.
    Hillclimbing from empty scores 8/16 forever (4032 evals, zero
    improvements measured) because single cells never complete a causal
    chain. Connected soup gives the fitness something to differentiate.
    """
    g, bmap = {}, {}

    def _put(c, st):
        if st in NEEDS_BELOW and not _solid_below(bmap, c):
            return False
        g[c] = st
        bmap[c] = st
        return True

    # dust trails out of the pins (pins live at x=0, y=1)
    for _, _, pz, _, kind, _ in PINS:
        c = (1, 1, pz)
        for _ in range(rng.randint(4, 12)):
            if 1 <= c[0] <= XMAX and 1 <= c[1] <= YMAX and 0 <= c[2] <= ZMAX:
                _put(c, DUST)
            mv = rng.choice([(1, 0), (-1, 0), (0, 1), (0, -1), (0, 0)])
            c = (max(1, min(XMAX, c[0] + mv[0])), 1,
                 max(0, min(ZMAX, c[2] + mv[1])))
    dustcells = [c for c, b in g.items() if b == DUST]
    # comparators touching dust (random facing/mode: the search, not me,
    # picks the motif)
    for _ in range(rng.randint(3, 8)):
        if not dustcells:
            break
        base = rng.choice(dustcells)
        nbs = list(_neighbors(base))
        if not nbs:
            continue
        c = rng.choice(nbs)
        _put(c, rng.choice(COMPS))
    # repeaters on dust trails (facing along a random axis)
    for _ in range(rng.randint(2, 6)):
        if not dustcells:
            break
        c = rng.choice(dustcells)
        if c in g:
            del g[c]
        _put(c, rng.choice(REPS))
    # constants: stuck levers (the only 15-source in the palette)
    for _ in range(rng.randint(0, 2)):
        c = (rng.randint(1, XMAX), 1, rng.randint(0, ZMAX))
        _put(c, LEVON)
    # sparse solid filler (glass/target: support + routing material)
    for _ in range(rng.randint(4, 14)):
        c = (rng.randint(1, XMAX), rng.randint(1, YMAX),
             rng.randint(0, ZMAX))
        _put(c, rng.choice([GLASS, TARGET, SLAB]))
    return g


def _crossover(rng, a, b):
    """Uniform cell mix of two elites. Justified by data, not hope: the
    memo holds hundreds of 10-pointers with DIFFERENT partial patterns
    (CIN-followers, A-followers...); mixing covers more vectors when the
    parents err on different ones. Genome stays raw atoms throughout."""
    g = {}
    for c in set(a) | set(b):
        src = a if rng.random() < 0.5 else b
        if c in src and rng.random() < 0.9:
            g[c] = src[c]
    return g


def _jump(rng, genome, steps=4):
    """Motif-sized jump: several coordinated cell changes as ONE candidate.
    Single cells can't install a comparator motif + its wiring; jumps can."""
    g = dict(genome)
    for _ in range(steps):
        g = _mutate(rng, g)
    return g


def _move(rng, genome):
    """Relocate one block: remove a random live cell, place a random state
    at a random (supported) cell. Neutral drift: reorganizes without the
    delete-then-add valley crossing singles through a worse genome."""
    g = dict(genome)
    if not g:
        return _mutate(rng, g)
    bmap = dict(g)
    c = rng.choice(list(g))
    del g[c]
    for _ in range(12):
        d = (rng.randint(1, XMAX), rng.randint(1, YMAX),
             rng.randint(0, ZMAX))
        st = rng.choice(ALPHA)
        if st == 'air':
            return g
        if st in NEEDS_BELOW and not _solid_below(bmap, d):
            continue
        g[d] = st
        return g
    g[c] = bmap[c]
    return g


def _motif(rng, genome):
    """Fill a random 2x2x2 cube with a coordinated mix (dust, solids,
    complex blocks). Approach #6: 11+ needs ~6-cell coordinated motifs
    (comparator + rear/side wiring + supports) that singles/jumps never
    assemble in 25k evals. The cube is wiring patterns, not logic gates:
    function stays entirely discovered. Support chains inside the cube
    via live bmap."""
    g = dict(genome)
    bmap = dict(g)
    x0 = rng.randint(1, XMAX - 1)
    y0 = rng.randint(1, YMAX - 1)
    z0 = rng.randint(0, ZMAX - 1)
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                c = (x0 + dx, y0 + dy, z0 + dz)
                r = rng.random()
                if r < 0.25:
                    g.pop(c, None)
                elif r < 0.55:
                    st = rng.choice([DUST, DUST, GLASS, TARGET])
                    if st in NEEDS_BELOW and not _solid_below(bmap, c):
                        continue
                    g[c] = st
                    bmap[c] = st
                elif r < 0.8:
                    st = rng.choice(REPS + COMPS)
                    if not _solid_below(bmap, c):
                        continue
                    g[c] = st
                    bmap[c] = st
    return g


def _score_job(payload):
    """Worker: parse once, 8 serial vectors, lamp-points + raw outputs.
    Never raises."""
    import sys as _s
    _s.path.insert(0, r'D:\redstone-mini')
    genome, pins, floor, io, vectors, expected = payload
    try:
        from sim import _parse_build, _run_vec, _check_supports
        blocks = list(pins) + list(floor) + [
            (x, y, z, b) for (x, y, z), b in genome.items()]
        P = _parse_build(blocks, io)
        _check_supports(P)
        pts = 0
        outs = []
        for vec, exp in zip(vectors, expected):
            got, _, _, _, _, _ = _run_vec(dict(vec), None, P)
            s = bool(got.get('S', False))
            co = bool(got.get('COUT', False))
            outs.append((s, co))
            pts += (s == exp[0]) + (co == exp[1])
        w = max((c[0] for c in genome), default=0)
        return (pts, w, len(genome), outs, '')
    except Exception as e:
        return (0, 0, len(genome), [], '%s: %s'
                % (type(e).__name__, str(e)[:60]))


def _responsiveness(outs):
    """Free information-flow gradient on already-run vectors: for each
    output, input-bit and base vector, does flipping the bit flip the
    output? A CIN-follower scores 4/24; a true adder 18/24. No extra
    sims. Rewards routing every input to every output -- necessary (not
    sufficient) for correctness, and says nothing about HOW."""
    r = 0
    for o in (0, 1):
        for bit in range(3):
            for v in range(8):
                if outs[v][o] != outs[v ^ (1 << bit)][o]:
                    r += 1
    return r


def _key(g):
    return '|'.join('%d,%d,%d=%s' % (x, y, z, g[(x, y, z)])
                    for x, y, z in sorted(g))


def main():
    import json
    from recipe import parse_recipe, eval_net
    from sim import _parse_build, _run_vec
    src, workdir = sys.argv[1], sys.argv[2]
    max_evals = int(sys.argv[3]) if len(sys.argv) > 3 else 1000
    seed = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    rng = random.Random(seed)
    os.makedirs(workdir, exist_ok=True)
    log = open(os.path.join(workdir, 'evo.log'), 'a')
    t_end = time.monotonic() + 3600

    oracle = parse_recipe(open(src).read())
    ins = oracle['inputs']
    vectors, expected = [], []
    for vals in itertools.product([0, 1], repeat=len(ins)):
        env = dict(zip(ins, vals))
        gout = eval_net(oracle, env)
        vectors.append(env)
        expected.append((bool(gout['S']), bool(gout['COUT'])))
    pins = [(x, y, z, b) for x, y, z, b, _, _ in PINS]
    io = {'levers': {(x, z): n for x, y, z, b, k, n in PINS if k == 'lever'},
          'lamps': {(x, z): n for x, y, z, b, k, n in PINS if k == 'lamp'},
          'nets': {}}

    # engine fingerprint (stale physics must never score genomes)
    import hashlib
    _h = hashlib.sha256()
    for _f in ('sim.py', 'simvec.py'):
        _h.update(open(os.path.join(r'D:\redstone-mini', _f), 'rb').read())
    _fp = _h.hexdigest()[:16]
    _mp = os.path.join(workdir, 'memo.json')
    try:
        memo = json.load(open(_mp))
        if memo.get('__fp__') != _fp:
            memo = {'__fp__': _fp}
    except Exception:
        memo = {'__fp__': _fp}

    # resume: best.pkl re-verified live before trusting (drift-proof)
    best, bestscore = {}, (0, 0, 0)
    try:
        import pickle
        _r = pickle.load(open(os.path.join(workdir, 'best.pkl'), 'rb'))
        if isinstance(_r, dict) and 'genome' in _r:
            P0 = _parse_build(list(pins) + list(FLOOR) + [
                (x, y, z, b) for (x, y, z), b in _r['genome'].items()], io)
            _pts = 0
            _outs = []
            for _v, _e in zip(vectors, expected):
                _g, _, _, _, _, _ = _run_vec(dict(_v), None, P0)
                _s = bool(_g.get('S', False))
                _co = bool(_g.get('COUT', False))
                _outs.append((_s, _co))
                _pts += (_s == _e[0]) + (_co == _e[1])
            _w = max((c[0] for c in _r['genome']), default=0)
            best = dict(_r['genome'])
            # ponytail: same convention as the live key_ ((pts,-w,-n) at
            # 16, (pts,resp,-n,-w) below). Zeroing the tiebreak here once
            # made (10,0,0) unbeatable and wasted 15k evals searching
            # against a phantom incumbent (2026-10-04). Responsiveness is
            # recomputed live (8 serial sims, ms) so the resume is exact.
            _resp = _responsiveness(_outs) if _outs else 0
            bestscore = (_pts, -_w, -len(best)) if _pts >= 16 else \
                (_pts, _resp)
            print('resumed: points=%d/16 resp=%d blocks=%d'
                  % (_pts, _resp, len(best)), flush=True)
    except Exception as _e:
        print('resume skipped (%s)' % str(_e)[:60], flush=True)

    from concurrent.futures import ProcessPoolExecutor
    BATCH, WORKERS = 16, 4
    evals, stall = 0, 0
    elites = [dict(best)] if best else []
    # score convention: (points, -width, -blocks) once points hit 16,
    # else (points, responsiveness). NO size tiebreak while hunting
    # (approach #5, rule 3 third strike): the old (pts,resp,-n,-w) tiebreak
    # REJECTED every growth step, so the hunt minimized itself into a
    # 7-block corner it could never grow out of (22->7 descent PROVES it).
    # Assembling new logic REQUIRES temporary growth; size is phase 2's
    # job. Ties drift at 10% (neutral exploration, not churn).
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        while evals < max_evals and time.monotonic() < t_end:
            batch, keys = [], []
            _tries = 0
            while len(batch) < BATCH and _tries < BATCH * 6:
                _tries += 1
                # 25% mutate, 10% relocate, 15% crossover, 15% jump,
                # 15% motif-fill, 20% grow. Motif-fill is approach #6:
                # coordinated 2x2x2 installs (singles/jumps plateaued at
                # 10/16 over 25k evals; 11+ needs multi-cell motifs).
                _r = rng.random()
                if not best or _r < 0.25:
                    cand = _mutate(rng, best) if best else _grow(rng)
                elif _r < 0.35 and best:
                    cand = _move(rng, best)
                elif _r < 0.5 and len(elites) >= 2:
                    _a, _b = rng.sample(elites, 2)
                    cand = _crossover(rng, _a, _b)
                elif _r < 0.65 and best:
                    cand = _jump(rng, best)
                elif _r < 0.8:
                    cand = _motif(rng, best if best else _grow(rng))
                else:
                    cand = _grow(rng)
                k = _key(cand)
                if k in memo or k in keys:
                    continue
                if len(cand) > 150:
                    continue  # bloat cap: growth-tolerant, not infinite
                keys.append(k)
                batch.append(cand)
            futs = [ex.submit(_score_job, (c, pins, FLOOR, io, vectors,
                                           expected)) for c in batch]
            # ponytail: future timeout (rule 7: never hang). 30k evals with
            # zero worker hangs observed, but an unbounded result() would
            # wedge the whole slice on the first one. Timeout falls back
            # to a failed eval; the wall clock bounds everything regardless.
            res = []
            for _f in futs:
                try:
                    res.append(_f.result(timeout=180))
                except Exception:
                    res.append((0, 0, 0, [], 'worker-timeout'))
            improved = False
            for cand, k, (pts, w, n, outs, err) in zip(batch, keys, res):
                memo[k] = [pts, w, n]
                evals += 1
                resp = _responsiveness(outs) if outs else 0
                key_ = (pts, -w, -n) if pts >= 16 else (pts, resp)
                cur = bestscore
                drift = key_ == cur and rng.random() < 0.1
                if key_ > cur:
                    bestscore = key_
                    best = dict(cand)
                    improved = True
                    stall = 0
                    elites.append(dict(cand))
                    elites = elites[-32:]
                    import pickle
                    with open(os.path.join(workdir, 'best.pkl'),
                              'wb') as f:
                        pickle.dump({'genome': best, 'score': key_,
                                     'evals': evals}, f)
                    print('E%d points=%d/16 resp=%d width=%d blocks=%d%s'
                          % (evals, pts, resp, w, n,
                             ' SOLVED' if pts >= 16 else ''), flush=True)
                    log.write('E%d pts=%d resp=%d w=%d n=%d %s\n'
                              % (evals, pts, resp, w, n, err))
                elif drift:
                    best = dict(cand)  # silent neutral wander, no save
            if not improved:
                stall += 1
            print('... evals=%d best=(%d/16) stall=%d elapsed=%.0fs'
                  % (evals, bestscore[0], stall,
                     time.monotonic() - (t_end - 3600)), flush=True)
            log.flush()
            with open(_mp, 'w') as f:
                json.dump(memo, f)
            if stall >= 12:
                # ponytail: regrow, don't grind. Shaking a plateaued genome
                # with single cells re-rolls the same dozen mutants (measured:
                # 4000 evals, zero improvements). A fresh connected genome
                # restarts exploration; best.pkl keeps the best ever found.
                print('stall: regrowing fresh connected genome', flush=True)
                best = _grow(rng)
                stall = 0
                if bestscore[0] < 16 and evals > max_evals // 2:
                    break
    with open(_mp, 'w') as f:
        json.dump(memo, f)
    print('done evals=%d best=%s' % (evals, bestscore), flush=True)


if __name__ == '__main__':
    main()
