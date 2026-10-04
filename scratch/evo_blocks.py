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

# ---- region + pins (defaults = FA stage; presets override) ----
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
ORACLE_TEXT = None  # None = read recipe file (FA); else inline text
FROZEN = {}  # coord -> bid, imposed after every op (scaffold, not genome)


def _impose(g):
    for c, b in FROZEN.items():
        g[c] = b
    return g


def _stage(name):
    """Stage presets: region + pins + oracle. Frozen patterns arrive via
    argv (workdir,dx,dz), never hand-designed."""
    global XMAX, YMAX, ZMAX, PINS, ORACLE_TEXT
    _lev = ('minecraft:lever[face=floor,facing=north,powered=false]',
            'lever')
    if name == 'not':
        XMAX, YMAX, ZMAX = 5, 3, 5
        PINS = [(0, 1, 0, _lev[0], 'lever', 'A'),
                (0, 1, 2, 'minecraft:redstone_lamp', 'lamp', 'Y')]
        ORACLE_TEXT = 'IN A\nOUT Y\nY = NOT A\n'
    elif name == 'xor':
        XMAX, YMAX, ZMAX = 6, 4, 7
        PINS = [(0, 1, 0, _lev[0], 'lever', 'A'),
                (0, 1, 2, _lev[0], 'lever', 'B'),
                (0, 1, 4, 'minecraft:redstone_lamp', 'lamp', 'Y')]
        ORACLE_TEXT = 'IN A, B\nOUT Y\nY = A XOR B\n'
    elif name == 'and':
        XMAX, YMAX, ZMAX = 6, 4, 7
        PINS = [(0, 1, 0, _lev[0], 'lever', 'A'),
                (0, 1, 2, _lev[0], 'lever', 'B'),
                (0, 1, 4, 'minecraft:redstone_lamp', 'lamp', 'Y')]
        ORACLE_TEXT = 'IN A, B\nOUT Y\nY = A AND B\n'
    elif name == 'fa':
        pass  # module defaults (XMAX=8, full pins, recipe file oracle)
    else:
        raise ValueError('unknown stage %r (want not|xor|and|fa)' % name)
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
    # constants: stuck levers (the only 15-source in the palette).
    # Count raised 0-2 -> 1-3 (2026-10-04): subtract motifs need a hot
    # rear and random soup rarely leaves one lying around.
    for _ in range(rng.randint(1, 3)):
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


_FACING_VEC = {'east': (1, 0), 'west': (-1, 0), 'south': (0, 1),
               'north': (0, -1)}


def _wired_comp(rng, genome):
    """Coherent comparator proposal: comparator + rear/side/output dust
    in consistent orientation (parser-confirmed mapping: rear sits at
    +facing, output at -facing, sides perpendicular). Approach #7:
    uniform 2x2x2 fills almost never land an oriented assembly; this
    proposes the assembly directly. Terminals placed best-effort (air
    only); function still fully discovered (mode random, drivers and
    constants up to the search)."""
    g = dict(genome)
    bmap = dict(g)
    x = rng.randint(1, XMAX)
    y = rng.randint(1, YMAX)
    z = rng.randint(0, ZMAX)
    f = rng.choice(['east', 'west', 'south', 'north'])
    fx, fz = _FACING_VEC[f]
    c = (x, y, z)
    if not _solid_below(bmap, c):
        return g
    g[c] = 'minecraft:comparator[facing=%s,mode=%s]' % (
        f, rng.choice(['compare', 'subtract']))
    bmap[c] = g[c]
    # ponytail: rear terminal is dust OR a stuck-ON lever (2026-10-04:
    # 7.7k NOT evals proved dust-only rears never go hot -- a subtract
    # comparator with a dark rear outputs 0 forever, so every such
    # proposal was dead on arrival). The constant is structural (any
    # 15-source), not logic: mode and wiring stay discovered.
    _rear_choices = [DUST, LEVON] if rng.random() < 0.5 else [DUST]
    for i, t in enumerate(((x + fx, y, z + fz), (x + fz, y, z + fx),
                          (x - fz, y, z - fx), (x - fx, y, z - fz))):
        if not (1 <= t[0] <= XMAX and 1 <= t[1] <= YMAX
                and 0 <= t[2] <= ZMAX):
            continue
        if t in g or t in FROZEN:
            continue
        if i == 0:
            st = rng.choice(_rear_choices)
            if st in NEEDS_BELOW and not _solid_below(bmap, t):
                continue
            g[t] = st
            bmap[t] = st
            continue
        if not _solid_below(bmap, t):
            continue
        g[t] = DUST
        bmap[t] = DUST
    return g


def _wired_rep(rng, genome):
    """Coherent repeater proposal: repeater + input/output dust aligned
    (input at +facing, output at -facing per parser). Same rationale."""
    g = dict(genome)
    bmap = dict(g)
    x = rng.randint(1, XMAX)
    y = rng.randint(1, YMAX)
    z = rng.randint(0, ZMAX)
    f = rng.choice(['east', 'west', 'south', 'north'])
    fx, fz = _FACING_VEC[f]
    c = (x, y, z)
    if not _solid_below(bmap, c):
        return g
    g[c] = 'minecraft:repeater[facing=%s,delay=1]' % f
    bmap[c] = g[c]
    for t in ((x + fx, y, z + fz), (x - fx, y, z - fz)):
        if not (1 <= t[0] <= XMAX and 1 <= t[1] <= YMAX
                and 0 <= t[2] <= ZMAX):
            continue
        if t in g or t in FROZEN:
            continue
        if not _solid_below(bmap, t):
            continue
        g[t] = DUST
        bmap[t] = DUST
    return g


def _bridge(rng, genome):
    """Lay dust along an L-path between two live dust cells (or dust and
    a lamp-adjacent cell). Approach #9: the proven 12-cell NOT needs a
    7-dust OUTPUT ROUTE to the lamp pin, and random walks almost never
    thread comp-output to lamp-net. Bridges propose connections
    directly (right or wrong -- the score decides). Air + supported
    cells only; blocked paths leave partial variation."""
    g = dict(genome)
    bmap = dict(g)
    dust = [c for c, b in g.items() if b == DUST]
    if len(dust) < 2:
        return g
    a = rng.choice(dust)
    lamps = [(x, y, z) for x, y, z, b, k, n in PINS if k == 'lamp']
    _t = rng.choice(dust)
    if lamps and rng.random() < 0.5:
        lx, ly, lz = rng.choice(lamps)
        cands = [(lx + dx, ly, lz + dz) for dx, dz in
                 ((1, 0), (-1, 0), (0, 1), (0, -1))]
        cands = [c for c in cands if 1 <= c[0] <= XMAX
                 and 1 <= c[1] <= YMAX and 0 <= c[2] <= ZMAX]
        if cands:
            _t = rng.choice(cands)
    x0, y0, z0 = a
    x1, y1, z1 = _t[0], a[1], _t[2]
    path = []
    x, z = x0, z0
    while (x, z) != (x1, z1):
        if x != x1 and (z == z1 or rng.random() < 0.5):
            x += 1 if x1 > x else -1
        else:
            z += 1 if z1 > z else -1
        path.append((x, y0, z))
    for c in path:
        if c in g or c in FROZEN:
            continue
        if not (1 <= c[0] <= XMAX and 0 <= c[2] <= ZMAX):
            continue
        if not _solid_below(bmap, c):
            continue
        g[c] = DUST
        bmap[c] = DUST
    return g


def _const_io(genome, pins_io, vectors):
    """Register genome levers as constant inputs (approach #8 root fix).

    The sim reads levers ONLY through vec (never the bid): an unregistered
    lever-ON is invisible (vec.get -> False). So all 50k block-evals ran
    with ZERO functional constants -- the De Morgan path was impossible
    the entire time (NOT unsolvable, FA stuck at constant-free CIN
    routing). Fix: every genome lever becomes a named constant input
    with its bid's powered value frozen into every vector.
    """
    auto = {}
    for c, b in genome.items():
        if b.split('[')[0] == 'minecraft:lever':
            auto[c] = 'g_%d_%d_%d' % (c[0], c[1], c[2])
    io2 = {'levers': dict(pins_io['levers']),
           'lamps': dict(pins_io['lamps']), 'nets': {}}
    pw = {}
    for c, n in auto.items():
        io2['levers'][(c[0], c[2])] = n
        pw[n] = ('powered=true' in genome[c])
    if not auto:
        return io2, [dict(v) for v in vectors]
    return io2, [dict(v, **pw) for v in vectors]


def _score_job(payload):
    """Worker: parse once, serial vectors over recipe outputs, lamp-points
    + raw outputs. Never raises."""
    import sys as _s
    _s.path.insert(0, r'D:\redstone-mini')
    genome, pins, floor, io, vectors, expected, outputs = payload
    try:
        from sim import _parse_build, _run_vec, _check_supports
        import sys as _s2
        _s2.path.insert(0, r'D:\redstone-mini\scratch')
        from evo_blocks import _const_io
        io2, vecs = _const_io(genome, io, vectors)
        blocks = list(pins) + list(floor) + [
            (x, y, z, b) for (x, y, z), b in genome.items()]
        P = _parse_build(blocks, io2)
        _check_supports(P)
        pts = 0
        outs = []
        for vec, exp in zip(vecs, expected):
            got, _, _, _, _, _ = _run_vec(dict(vec), None, P)
            row = tuple(bool(got.get(o, False)) for o in outputs)
            outs.append(row)
            pts += sum(a == b for a, b in zip(row, exp))
        w = max((c[0] for c in genome), default=0)
        return (pts, w, len(genome), outs, '')
    except Exception as e:
        return (0, 0, len(genome), [], '%s: %s'
                % (type(e).__name__, str(e)[:60]))


def _responsiveness(outs, n_ins):
    """Free information-flow gradient on already-run vectors: for each
    output, input-bit and base vector, does flipping the bit flip the
    output? Rewards routing every input to every output -- necessary, not
    sufficient, and silent about HOW."""
    if not outs:
        return 0
    r = 0
    for o in range(len(outs[0])):
        for bit in range(n_ins):
            for v in range(len(outs)):
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
    global FLOOR, FROZEN
    stage, workdir = sys.argv[1], sys.argv[2]
    max_evals = int(sys.argv[3]) if len(sys.argv) > 3 else 1000
    seed = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    frozen_spec = sys.argv[5] if len(sys.argv) > 5 else ''
    rng = random.Random(seed)
    os.makedirs(workdir, exist_ok=True)
    log = open(os.path.join(workdir, 'evo.log'), 'a')
    t_end = time.monotonic() + 3600

    _stage(stage)
    FLOOR = [(x, 0, z, 'minecraft:glass')
             for x in range(-1, XMAX + 2) for z in range(-1, ZMAX + 2)]
    # frozen scaffolds: discovered patterns from prior stages
    # (workdir,dx,dz;...), translated by (+dx,+dz), bounds-checked loud.
    FROZEN = {}
    if frozen_spec.strip():
        import pickle as _pk
        for _item in frozen_spec.strip().split(';'):
            _wd, _dx, _dz = _item.split(',')
            _pat = _pk.load(open(os.path.join(_wd, 'best.pkl'), 'rb'))
            _pg = _pat['genome'] if isinstance(_pat, dict) else _pat
            for (x, y, z), b in _pg.items():
                _c = (x + int(_dx), y, z + int(_dz))
                assert 1 <= _c[0] <= XMAX and 1 <= _c[1] <= YMAX \
                    and 0 <= _c[2] <= ZMAX, \
                    'frozen cell %s out of stage region' % (_c,)
                assert _c not in FROZEN, 'frozen overlap at %s' % (_c,)
                FROZEN[_c] = b
        print('frozen scaffold: %d cells from %s'
              % (len(FROZEN), frozen_spec), flush=True)

    if ORACLE_TEXT is None:
        _src = os.path.join(r'D:\redstone-mini', 'recipes', 'fa1.txt')
        oracle = parse_recipe(open(_src).read())
    else:
        oracle = parse_recipe(ORACLE_TEXT)
    ins, outs = oracle['inputs'], oracle['outputs']
    MAXPTS = (2 ** len(ins)) * len(outs)
    vectors, expected = [], []
    for vals in itertools.product([0, 1], repeat=len(ins)):
        env = dict(zip(ins, vals))
        gout = eval_net(oracle, env)
        vectors.append(env)
        expected.append(tuple(bool(gout[o]) for o in outs))
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
            _io2, _vecs = _const_io(_r['genome'], io, vectors)
            P0 = _parse_build(list(pins) + list(FLOOR) + [
                (x, y, z, b) for (x, y, z), b in _r['genome'].items()], _io2)
            _pts = 0
            _outs = []
            for _v, _e in zip(_vecs, expected):
                _g, _, _, _, _, _ = _run_vec(dict(_v), None, P0)
                _row = tuple(bool(_g.get(o, False)) for o in outs)
                _outs.append(_row)
                _pts += sum(a == b for a, b in zip(_row, _e))
            _w = max((c[0] for c in _r['genome']), default=0)
            best = dict(_r['genome'])
            # ponytail: same convention as the live key_. Zeroing the
            # tiebreak here once made (10,0,0) unbeatable and wasted 15k
            # evals searching against a phantom incumbent (2026-10-04).
            # Responsiveness recomputed live so the resume is exact.
            _resp = _responsiveness(_outs, len(ins)) if _outs else 0
            bestscore = (_pts, -_w, -len(best)) if _pts >= MAXPTS else \
                (_pts, _resp)
            print('resumed: points=%d/%d resp=%d blocks=%d'
                  % (_pts, MAXPTS, _resp, len(best)), flush=True)
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
                # 20% mutate, 5% relocate, 15% crossover, 10% jump,
                # 10% motif-fill, 12% wired-comp, 8% wired-rep, 10% bridge,
                # 10% grow. Bridges are approach #9: output ROUTES to pins
                # (proven 12-cell NOT needs 7 routed dust; random walks
                # never thread comp-output to lamp-net).
                _r = rng.random()
                if not best or _r < 0.2:
                    cand = _mutate(rng, best) if best else _grow(rng)
                elif _r < 0.25 and best:
                    cand = _move(rng, best)
                elif _r < 0.4 and len(elites) >= 2:
                    _a, _b = rng.sample(elites, 2)
                    cand = _crossover(rng, _a, _b)
                elif _r < 0.5 and best:
                    cand = _jump(rng, best)
                elif _r < 0.6:
                    cand = _motif(rng, best if best else _grow(rng))
                elif _r < 0.72:
                    cand = _wired_comp(rng, best if best else _grow(rng))
                elif _r < 0.8:
                    cand = _wired_rep(rng, best if best else _grow(rng))
                elif _r < 0.9:
                    cand = _bridge(rng, best if best else _grow(rng))
                else:
                    cand = _grow(rng)
                # frozen scaffold (prior-stage discovered patterns): ops may
                # place junk on or delete frozen cells; impose restores them
                # after. Support misjudgments from transient junk are caught
                # by the sim backstop (FLOATING = 0). One site, all ops.
                cand = _impose(cand)
                k = _key(cand)
                if k in memo or k in keys:
                    continue
                if len(cand) > 150:
                    continue  # bloat cap: growth-tolerant, not infinite
                keys.append(k)
                batch.append(cand)
            futs = [ex.submit(_score_job, (c, pins, FLOOR, io, vectors,
                                           expected, outs)) for c in batch]
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
                resp = _responsiveness(outs, len(ins)) if outs else 0
                key_ = (pts, -w, -n) if pts >= MAXPTS else (pts, resp)
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
                    print('E%d points=%d/%d resp=%d width=%d blocks=%d%s'
                          % (evals, pts, MAXPTS, resp, w, n,
                             ' SOLVED' if pts >= MAXPTS else ''), flush=True)
                    log.write('E%d pts=%d resp=%d w=%d n=%d %s\n'
                              % (evals, pts, resp, w, n, err))
                elif drift:
                    best = dict(cand)  # silent neutral wander, no save
            if not improved:
                stall += 1
            print('... evals=%d best=(%d/%d) stall=%d elapsed=%.0fs'
                  % (evals, bestscore[0], MAXPTS, stall,
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
                if bestscore[0] < MAXPTS and evals > max_evals * 0.9:
                    break
    with open(_mp, 'w') as f:
        json.dump(memo, f)
    print('done evals=%d best=%s' % (evals, bestscore), flush=True)


if __name__ == '__main__':
    main()
