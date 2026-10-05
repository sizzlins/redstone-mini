"""Dual-engine verification gate: our sim AND cmc, one command, hard
timeouts, per-cell differential. The vanilla RCON rig is NOT an oracle in
this environment (see LOG.md 2026-10-04 night), so this is the gate.

Two independent implementations agreeing on every vector is the strongest
evidence available here; a sim-only green is exactly how compact.py can
quietly overfit the simulator.

Usage:
  python scratch/verify2.py <recipe.txt> <build.pkl> [options]
    --doc PATH        reuse/write the cmc JSON doc (default: temp next to pkl)
    --vec N           vector index for the per-cell differential (default 0)
    --diff            run the per-cell differential (sim dust vs cmc dust)
    --ticks N         cmc settle ticks (default 400)
    --max-vectors N   cap vectors in the doc (default 64, exhaustive below)
    --sim-timeout S   hard kill for the sim child (default 900)
    --cmc-timeout S   hard kill for the cmc child (default 900)

Child role (used internally, safe to call directly):
  python scratch/verify2.py --sim-child <doc.json> <out.json> [--vec N]

Exit 0 only if BOTH engines pass every vector. Never hangs: every external
process runs under subprocess timeout, and the parent enforces a deadline.
"""
import itertools
import json
import os
import pickle
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r'D:\redstone-mini')

DIFF_MAX_REPORT = 40

# Files that define the two engines. A verdict produced by different bytes is
# not a verdict about this build -- it is a verdict about an older engine, and
# it looks identical in the cache. This is the same class as the stale ref_sim
# freeze: an artifact whose provenance is not recorded cannot be trusted after
# the thing it was derived from moves.
ENGINE_FILES = ('sim.py', 'simvec.py', os.path.join('scratch', 'cmc_harness.mjs'))


def engine_stamp():
    """sha256 over the engine sources + HEAD, so a cached verdict can be
    matched to the engine that produced it. Cheap: three file reads."""
    import hashlib
    h = hashlib.sha256()
    root = r'D:\redstone-mini'
    for rel in ENGINE_FILES:
        p = os.path.join(root, rel)
        h.update(rel.encode('utf8'))
        try:
            with open(p, 'rb') as f:
                h.update(f.read())
        except OSError:
            h.update(b'<missing>')
    # ponytail: deliberately NOT hashing HEAD. The stamp answers "was this
    # verdict produced by these engine bytes?", and a LOG.md commit must not
    # invalidate 50 cached verdicts -- that would make the cache useless and
    # turn every commit into a re-run.
    return h.hexdigest()[:16]


def keystr(k):
    """An io pin key as 'x,z' or 'x,y,z'. ponytail: build_doc assumed 2-tuples
    and crashed with `TypeError: not all arguments converted` on the first
    build carrying a 3D lamp key (stackfail's (51,6,35)). sim itself accepts
    both shapes (_y maps 2-tuples to y=1 and passes 3-tuples through), so the
    gate must too -- a gate that crashes on a key shape is a gate that cannot
    see a whole class of builds."""
    return ','.join(str(int(v)) for v in (k if isinstance(k, (tuple, list))
                                          else (k,)))


def unrepresentable_levers(blocks, io):
    """Lever blocks sim CANNOT power, listed so the gate never misreads them.

    sim powers a lever only when its io pin key is held true in the vector
    (sim.py:542 does `vec.get(lever[rear], False)`). A lever absent from io
    maps to its own floor coordinate, which no vector ever contains -- so it
    reads unpowered forever even when its blockstate says powered=true, while
    cmc and vanilla treat it as a real source (Finding 3, scratch/notmin.py).
    That is a silent wrong default in shared core: no error, no warning, just
    a wrong 0. This lists every such lever so the verdict says, in plain
    words, that the build uses a construct sim cannot represent -- instead of
    reporting a confident green or red on physics sim did not actually compute.
    Returns [(cell, powered_bool)].
    """
    pins = set()
    for k in (io.get('levers') or {}):
        pins.add(tuple(k) if isinstance(k, (list, tuple)) else k)
    out = []
    for b in blocks:
        if len(b) < 4:
            continue
        x, y, z, s = b[0], b[1], b[2], str(b[3])
        if s == 'minecraft:lever' or s.startswith('minecraft:lever['):
            floor = (x, y - 1, z)
            if floor not in pins and (x, z) not in pins:
                out.append(((x, y, z), 'powered=true' in s))
    return out


def build_doc(recipe_p, pkl_p, out_p, max_vectors):
    from recipe import parse_recipe, eval_net
    r = parse_recipe(open(recipe_p).read())
    m = pickle.load(open(pkl_p, 'rb'))
    ins, outs = r['inputs'], r['outputs']
    combos = list(itertools.product([0, 1], repeat=len(ins)))
    sampled = False
    if len(combos) > max_vectors:
        step = len(combos) / float(max_vectors)
        combos = [combos[int(i * step)] for i in range(max_vectors)]
        sampled = True
    vectors, expected = [], []
    for vals in combos:
        env = dict(zip(ins, vals))
        gout = eval_net(r, env)
        vectors.append(env)
        expected.append({o: bool(gout[o]) for o in outs})
    io = m['io']
    doc = {
        'blocks': [[int(x), int(y), int(z), b]
                   for (x, y, z, b) in m['blocks']],
        'levers': [[keystr(k), v] for k, v in io['levers'].items()],
        'lamps': [[keystr(k), v] for k, v in io['lamps'].items()],
        'vectors': vectors,
        'expected': expected,
        'sampled': sampled,
        'n_inputs': len(ins),
        'max_vectors': max_vectors,
    }
    json.dump(doc, open(out_p, 'w'))
    return doc, len(doc['blocks'])


def run_sim_child(doc_p, out_p, vec, dump_all=False):
    """Run every vector through sim._run_vec; optionally dump per-vector
    dust/repeater power tables for the differential."""
    from sim import _parse_build, _run_vec
    doc = json.load(open(doc_p))
    # _parse_build wants the original io shape: {(x,z): name} for levers and
    # lamps (it maps a pin's y from the block list).
    io = {'levers': {tuple(int(v) for v in k.split(',')): n
                     for k, n in doc['levers']},
          'lamps': {tuple(int(v) for v in k.split(',')): n
                    for k, n in doc['lamps']}}
    P = _parse_build([tuple(b) for b in doc['blocks']], io)
    results = []
    cells = None
    reps = None
    allv = {}
    # An engine verdict can be a RAISE, not just a mismatch: sim rejects
    # torch-burnout builds outright. Report it as a first-class verdict so
    # the gate never prints a bare "None" and hides the reason.
    raised = None
    for i, vecenv in enumerate(doc['vectors']):
        try:
            got, live, tlive, nticks, rlive, conc = _run_vec(vecenv, None, P)
        except BaseException as e:                       # noqa: BLE001
            raised = '%s: %s' % (type(e).__name__, e)
            results.append({'i': i, 'vec': vecenv, 'ok': False,
                            'raised': raised, 'bad': ['<engine raised>']})
            continue
        got = {k: bool(v) for k, v in got.items()}
        want = doc['expected'][i]
        bad = sorted(k for k in want if got.get(k) != want[k])
        results.append({'i': i, 'vec': vecenv, 'got': got, 'want': want,
                        'ok': not bad, 'bad': bad})
        if dump_all:
            allv[str(i)] = {
                'vec': vecenv,
                'cells': {'%d,%d,%d' % c: int(p) for c, p in live.items()},
                'repeaters': {'%d,%d,%d' % c: int(p)
                              for c, p in rlive.items()},
            }
        elif i == vec:
            cells = {'%d,%d,%d' % c: int(p) for c, p in live.items()}
            reps = {'%d,%d,%d' % c: int(p) for c, p in rlive.items()}
    fails = [r for r in results if not r['ok']]
    json.dump({'ok': not fails, 'n': len(results),
               'fails': fails[:8], 'cells': cells, 'repeaters': reps,
               'raised': raised, 'all': allv or None}, open(out_p, 'w'))
    return 0 if not fails else 1


def run_child(argv, timeout, label):
    """subprocess with a hard timeout; returns (rc, stdout, timed_out)."""
    t0 = time.time()
    try:
        p = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, cwd=r'D:\redstone-mini')
        return p.returncode, p.stdout + p.stderr, False, time.time() - t0
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b'').decode('utf8', 'replace') if isinstance(
            e.stdout, bytes) else (e.stdout or '')
        err = (e.stderr or b'').decode('utf8', 'replace') if isinstance(
            e.stderr, bytes) else (e.stderr or '')
        return -9, out + err, True, time.time() - t0


def parse_json_blob(s):
    """Pull the last JSON object out of a child's stdout."""
    depth = 0
    start = None
    for i, ch in enumerate(s):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(s[start:i + 1])
                except ValueError:
                    start = None
    return None


def main():
    a = sys.argv[1:]
    if a and a[0] == '--sim-child':
        return run_sim_child(a[1], a[2],
                             int(a[4]) if len(a) > 4 and a[3] == '--vec'
                             else 0,
                             dump_all='--dump-all' in a)
    if len(a) < 2:
        print(__doc__)
        return 2
    recipe_p, pkl_p = a[0], a[1]
    doc_p = None
    vec, diff, ticks = 0, False, 400
    diff_all = False
    max_vectors = 64
    sim_to, cmc_to = 900, 900
    i = 2
    while i < len(a):
        if a[i] == '--doc':
            doc_p = a[i + 1]; i += 2
        elif a[i] == '--vec':
            vec = int(a[i + 1]); i += 2
        elif a[i] == '--diff':
            diff = True; i += 1
        elif a[i] == '--diff-all':
            diff = True; diff_all = True; i += 1
        elif a[i] == '--ticks':
            ticks = int(a[i + 1]); i += 2
        elif a[i] == '--max-vectors':
            max_vectors = int(a[i + 1]); i += 2
        elif a[i] == '--sim-timeout':
            sim_to = int(a[i + 1]); i += 2
        elif a[i] == '--cmc-timeout':
            cmc_to = int(a[i + 1]); i += 2
        else:
            print('unknown arg %s' % a[i])
            return 2
    doc_p = doc_p or os.path.splitext(pkl_p)[0] + '.v2doc.json'
    if not os.path.exists(doc_p):
        doc, nblocks = build_doc(recipe_p, pkl_p, doc_p, max_vectors)
        print('doc: %d blocks, %d vectors%s -> %s'
              % (nblocks, len(doc['vectors']),
                 ' (SAMPLED)' if doc['sampled'] else '', doc_p), flush=True)
    else:
        doc = json.load(open(doc_p))
        print('doc: reused %s (%d blocks, %d vectors)'
              % (doc_p, len(doc['blocks']), len(doc['vectors'])), flush=True)
        # ponytail: --max-vectors was silently ignored whenever the doc already
        # existed, so `--max-vectors 1` against a cached 4-vector doc still ran
        # all 4 and the caller had no way to tell. A cached doc is a cache
        # keyed on more than its path -- say so loudly instead of quietly
        # disagreeing with the flag.
        if doc.get('max_vectors') not in (None, max_vectors):
            print('doc: WARNING cached doc was built with max_vectors=%s but '
                  '%s was requested; the CACHED vector set wins. Delete the '
                  'doc to change it.' % (doc.get('max_vectors'), max_vectors),
                  flush=True)

    verdict = {'doc': doc_p, 'pkl': pkl_p, 'recipe': recipe_p, 'vec': vec,
               'engine': engine_stamp(), 'n_vectors': len(doc['vectors']),
               'argv': sys.argv[1:]}
    # Flag builds sim cannot fully represent BEFORE the engines run, so a green
    # or red is never reported on physics sim did not compute.
    try:
        io4 = {'levers': {tuple(int(v) for v in k.split(',')): n
                          for k, n in doc['levers']}}
        strange = unrepresentable_levers(
            [(b[0], b[1], b[2], b[3]) for b in doc['blocks']], io4)
    except (ValueError, KeyError, TypeError):
        strange = []
    verdict['unrepresentable_levers'] = [
        {'cell': list(c), 'powered': p} for c, p in strange]
    if strange:
        print('GATE WARNING: %d lever(s) sim cannot power (not input pins): %s'
              % (len(strange), ', '.join(
                  '%s%s' % (c, ' ON' if p else '') for c, p in strange)),
              flush=True)

    # --- engine 1: sim (child process, hard timeout) ---
    sim_out = doc_p + '.sim.json'
    simcmd = [sys.executable, '-u', os.path.join(HERE, 'verify2.py'),
              '--sim-child', doc_p, sim_out, '--vec', str(vec)]
    if diff_all:
        simcmd.append('--dump-all')
    rc, out, to, dt = run_child(simcmd, sim_to, 'sim')
    simres = parse_json_blob(out)
    if simres is None and os.path.exists(sim_out):
        simres = json.load(open(sim_out))
    verdict['sim'] = {'rc': rc, 'timeout': to, 'secs': round(dt, 1),
                      'ok': simres.get('ok') if simres else None,
                      'n': simres.get('n') if simres else None,
                      'raised': simres.get('raised') if simres else None,
                      'fails': simres.get('fails') if simres else None}
    print('SIM : ok=%s n=%s %s%.0fs%s' % (
        verdict['sim']['ok'], verdict['sim']['n'],
        'TIMEOUT ' if to else '', dt,
        ' RAISED: ' + verdict['sim']['raised'] if verdict['sim']['raised']
        else ''), flush=True)

    # --- engine 2: cmc (node child, hard timeout) ---
    cells_p = doc_p + '.cmccells.json' if diff else None
    cmd = ['node', os.path.join(HERE, 'cmc_harness.mjs'), doc_p,
           '--ticks', str(ticks)]
    if diff_all:
        cmd += ['--dump-cells', cells_p, '--dump-all']
    elif diff:
        cmd += ['--dump-cells', cells_p, '--dump-vec', str(vec),
                '--vectors', str(vec)]
    rc, out, to, dt = run_child(cmd, cmc_to, 'cmc')
    cmcres = parse_json_blob(out)
    verdict['cmc'] = {'rc': rc, 'timeout': to, 'secs': round(dt, 1),
                      'ok': cmcres.get('ok') if cmcres else None,
                      'n': cmcres.get('n') if cmcres else None,
                      'fails': cmcres.get('fails') if cmcres else None,
                      'stage': cmcres.get('stage') if cmcres else None,
                      'popped': cmcres.get('popped') if cmcres else None,
                      'stderr': None if cmcres else out[-400:]}
    print('CMC : ok=%s n=%s %s%.0fs%s' % (
        verdict['cmc']['ok'], verdict['cmc']['n'],
        'TIMEOUT ' if to else '', dt,
        '' if not verdict['cmc']['stage'] else
        ' STAGE=%s%s' % (verdict['cmc']['stage'],
                         (' popped=%s' % verdict['cmc']['popped'])
                         if verdict['cmc']['popped'] else '')), flush=True)
    # ponytail: cmc REFUSES some builds structurally (its `support` stage pops
    # blocks that lack support) and never simulates them. That is a completely
    # different verdict from "we both simulated it and the lamps disagree", and
    # reporting both as `cmc=False` made a structural rejection look like a
    # physics disagreement. It is how alu4mergeNEW/alu4mergeNEW4 read as the
    # "interesting sim-overfit class" for a day: cmc never ran. Now it says so.
    if cmcres and cmcres.get('stage') and not cmcres.get('n'):
        print('  NOTE: cmc rejected this build at its %r stage WITHOUT '
              'simulating it; there is no physics disagreement to read here.'
              % cmcres['stage'], flush=True)

    # --- per-cell differential ---
    if diff and simres and os.path.exists(cells_p):
        cmc_dump = json.load(open(cells_p))
        pairs = []
        if cmc_dump.get('all') and simres.get('all'):
            for k in sorted(cmc_dump['all'], key=int):
                if k in simres['all']:
                    pairs.append((k, simres['all'][k], cmc_dump['all'][k]))
        else:
            pairs.append((str(vec), {'cells': simres.get('cells') or {},
                                     'repeaters': simres.get('repeaters') or {},
                                     'vec': None}, cmc_dump))
        tot_cells = tot_mism = tot_reps = tot_rmism = 0
        worst = []
        per_vec = []
        for k, sv, cv in pairs:
            sc = sv.get('cells') or {}
            cc = cv.get('cells') or {}
            keys = set(sc) | set(cc)
            # sim's power map is SPARSE (only cells carrying charge), so an
            # absent key means 0 -- cmc's dump is dense.
            mism = [(c, int(sc.get(c, 0)), int(cc.get(c, 0)))
                    for c in sorted(keys)
                    if int(sc.get(c, 0)) != int(cc.get(c, 0))]
            sr = sv.get('repeaters') or {}
            cr = cv.get('repeaters') or {}
            rmis = [(c, int(sr.get(c, 0)), int(cr.get(c, 0)))
                    for c in sorted(set(sr) | set(cr))
                    if int(sr.get(c, 0)) != int(cr.get(c, 0))]
            tot_cells += len(keys)
            tot_mism += len(mism)
            tot_reps += len(set(sr) | set(cr))
            tot_rmism += len(rmis)
            per_vec.append({'vec': k, 'cells': len(keys),
                            'mismatches': len(mism), 'rep_mismatches':
                            len(rmis)})
            worst += mism + rmis
        verdict['diff'] = {'vectors': len(pairs), 'cells': tot_cells,
                           'mismatches': tot_mism, 'repeaters': tot_reps,
                           'rep_mismatches': tot_rmism,
                           'per_vector': per_vec,
                           'examples': worst[:DIFF_MAX_REPORT]}
        print('DIFF: %d vectors, dust %d/%d cells differ, repeaters %d/%d differ'
              % (len(pairs), tot_mism, tot_cells, tot_rmism, tot_reps),
              flush=True)
        for c, s, cm in worst[:12]:
            print('   %-14s sim=%-5s cmc=%-5s' % (c, s, cm), flush=True)

    ok = bool(verdict['sim']['ok']) and bool(verdict['cmc']['ok'])
    if diff and 'diff' in verdict:
        ok = ok and verdict['diff']['mismatches'] == 0 \
            and verdict['diff']['rep_mismatches'] == 0
    verdict['ok'] = ok
    print('=' * 60)
    print('DUAL-ENGINE VERDICT: %s   (sim=%s cmc=%s%s)' % (
        'PASS' if ok else 'FAIL', verdict['sim']['ok'], verdict['cmc']['ok'],
        '' if not diff else ' diff=%s/%s cells' % (
            verdict.get('diff', {}).get('mismatches'),
            verdict.get('diff', {}).get('cells'))))
    json.dump(verdict, open(doc_p + '.verdict.json', 'w'), indent=1)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
