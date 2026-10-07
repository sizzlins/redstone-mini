"""Finish line: compose -> verify -> evolve -> compact -> best export.

The operator's rule: when the program finishes, hand over the most compact
AND fastest build -- not the first green one. Score is (blocks, ticks)
lexicographic: fewer blocks wins, worst-case sim settle ticks breaks ties
(timing model confirmed against cmc engine.js: dust instant, every
repeater/gate costs delay; ours are all 1-tick devices).

Usage:
  python scratch/finish.py <recipe.txt> [--pkl BUILD.pkl] [--evals N]
      [--compact-evals N] [--out NAME] [--ticks-vecs N] [--dry-run]

  --pkl skips compose (uses a verified build's blocks; still re-verified).
  --evals/--compact-evals bound the search slices (0 = skip that stage).
  --ticks-vecs caps the tick sample per candidate (default 64; full space
    at n<=10 inputs, stated in the receipt either way).
  --dry-run validates plumbing only: parse, plan, no paid evals.

Stages never hang: every child runs under subprocess timeout; evolve and
compact enforce their own budgets. Exit 0 with a receipt on success.
"""
import os
import pickle
import subprocess
import sys
import time

sys.path.insert(0, r'D:\redstone-mini')
sys.path.insert(0, os.path.join(r'D:\redstone-mini', 'scratch'))

ROOT = r'D:\redstone-mini'


def run(args, timeout, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    try:
        r = subprocess.run(args, cwd=ROOT, timeout=timeout, check=False,
                           env=e, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        return 1, '', 'TIMEOUT'
    return r.returncode, r.stdout[-2000:], r.stderr[-500:]


def measure(recipe, blocks, io, tick_vecs):
    """(blocks, ticks, note). Ticks measured once per finalist, never
    during search (search uses its own sampled fitness)."""
    import ticks as _ticks
    from recipe import parse_recipe
    r = parse_recipe(recipe) if isinstance(recipe, str) else recipe
    vecs = None
    if len(r['inputs']) > 10:
        import ticks as _t
        vecs = _t.spread_vectors(r['inputs'], tick_vecs)
    w, _, n, sampled = _ticks.worst_ticks(blocks, io, r['inputs'], vecs)
    return len(blocks), w, '%dv%s' % (n, '-sampled' if sampled else '')


def main():
    a = sys.argv[1:]
    if not a or '--help' in a:
        print(__doc__)
        return
    src = a[0]
    pkl = evals = compact_evals = out = tick_vecs = dry = None
    evals, compact_evals, tick_vecs = 0, 0, 64
    it = iter(a[1:])
    for x in it:
        if x == '--pkl':
            pkl = next(it)
        elif x == '--evals':
            evals = int(next(it))
        elif x == '--compact-evals':
            compact_evals = int(next(it))
        elif x == '--out':
            out = next(it)
        elif x == '--ticks-vecs':
            tick_vecs = int(next(it))
        elif x == '--dry-run':
            dry = True
    from recipe import parse_recipe
    recipe = parse_recipe(open(src).read())
    name = out or os.path.splitext(os.path.basename(src))[0]
    work = os.path.join('scratch', 'finish_' + name)
    plan = ['base compose+verify',
            'evolve x%d%s' % (evals, ' (ticks fitness)' if os.environ.get('REDSTONE_EVO_TICKS') == '1' else ''),
            'compact x%d' % compact_evals, 'score (blocks,ticks)', 'export build_%s.*' % name]
    print('finish plan for %s [%s]' % (src, ' | '.join(plan)), flush=True)
    if dry:
        print('dry run ok: recipe parses (%d gates, %d inputs)'
              % (len(recipe['gates']), len(recipe['inputs'])))
        return
    os.makedirs(work, exist_ok=True)
    cands = {}  # tag -> (blocks, io, recipe_text_or_None)

    # Stage 1: base (compose or given pkl, always re-verified here).
    from compose import compose
    from sim import sim_verify
    if pkl:
        m = pickle.load(open(pkl, 'rb'))
        blocks, io = [tuple(b) for b in m['blocks']], m['io']
        print('base: %s (%d blocks)' % (pkl, len(blocks)), flush=True)
    else:
        t0 = time.monotonic()
        blocks, size, io = compose(recipe)
        print('base composed %d blocks in %.0fs' % (len(blocks), time.monotonic() - t0), flush=True)
    sim_verify(recipe, blocks, io, quiet=True)
    print('base verifies green', flush=True)
    cands['base'] = (blocks, io, None)

    # Stage 2: evolve (bounded; env decides ticks fitness, default off).
    if evals > 0:
        evdir = os.path.join(work, 'evo')
        rc, so, se = run([sys.executable, 'scratch/evolve.py', src, evdir,
                          str(evals)], 3900)
        print('evolve rc=%d %s' % (rc, (so + se)[-300:]), flush=True)
        if rc == 0:
            try:
                etxt = open(os.path.join(evdir, 'best.txt')).read()
                er = parse_recipe(etxt)
                eb, _, eio = compose(er)
                sim_verify(er, eb, eio, quiet=True)
                cands['evo'] = (eb, eio, etxt)
                print('evo best verifies green', flush=True)
            except Exception as e:
                print('evo best rejected: %s' % str(e)[:120], flush=True)

    # Stage 3: compact (bounded slice on the current best recipe).
    if compact_evals > 0:
        best_src = os.path.join(work, 'compact_in.txt')
        tag = min(cands, key=lambda t: (len(cands[t][0]), 0))
        rtxt = cands[tag][2] or open(src).read()
        open(best_src, 'w').write(rtxt)
        codir = os.path.join(work, 'compact')
        rc, so, se = run([sys.executable, 'scratch/compact.py', best_src,
                          codir, str(compact_evals)], 3900)
        print('compact rc=%d %s' % (rc, (so + se)[-300:]), flush=True)
        if rc == 0:
            try:
                cm = pickle.load(open(os.path.join(codir, 'best.pkl'), 'rb'))
                cands['compact'] = (cm['blocks'], cm['io'], None)
                print('compact best loads', flush=True)
            except Exception as e:
                print('compact best rejected: %s' % str(e)[:120], flush=True)

    # Stage 4: score (blocks, ticks) lexicographic, export winner + receipt.
    scored = {}
    for tag, (b, io, _) in cands.items():
        nb, wt, note = measure(open(src).read(), b, io, tick_vecs)
        scored[tag] = (nb, wt)
        print('candidate %-8s blocks=%d ticks=%d (%s)' % (tag, nb, wt, note),
              flush=True)
    win = min(scored, key=lambda t: scored[t])
    wb, wio, _ = cands[win]
    from export import export_mcfunction, export_schem, export_html
    export_mcfunction([tuple(b) for b in wb], 'build_%s.mcfunction' % name, io=wio)
    export_schem([tuple(b) for b in wb], 'build_%s.schem' % name)
    size = (max(b[0] for b in wb) + 1, max(b[2] for b in wb) + 1)
    export_html([tuple(b) for b in wb], size, 'build_%s.html' % name, name)
    with open('build_%s.RECEIPT.txt' % name, 'w') as f:
        f.write('finish %s winner=%s blocks=%d ticks=%d\n' % (src, win, scored[win][0], scored[win][1]))
        for tag, (nb, wt) in sorted(scored.items(), key=lambda kv: kv[1]):
            f.write('  %-8s blocks=%d ticks=%d\n' % (tag, nb, wt))
    print('WINNER %s blocks=%d ticks=%d -> build_%s.*'
          % (win, scored[win][0], scored[win][1], name))


if __name__ == '__main__':
    main()
