"""Sweep every banked build pkl through the dual-engine gate.

Auto-matches each build to a recipe by its io pin NAMES (lever names must
equal the recipe's inputs, lamp names its outputs), so a stale pkl cannot be
scored against the wrong recipe -- which is how alu4_build.pkl looked like a
physics failure for a while.

NEVER HANGS: every gate invocation is a subprocess with a hard timeout, the
vector count is capped, and each pkl is wrapped in a wall-clock budget.

Usage:
  python scratch/sweep.py [--pkls a.pkl,b.pkl] [--max-vectors 4]
                          [--sim-timeout 600] [--cmc-timeout 900]
                          [--diff] [--out scratch/sweep.json]
"""
import glob
import json
import os
import re
import subprocess
import sys
import time

ROOT = r'D:\redstone-mini'
HERE = os.path.join(ROOT, 'scratch')


def io_names(pkl_path):
    """(sorted input names, sorted output names) from a build pkl, or None."""
    import pickle
    try:
        m = pickle.load(open(pkl_path, 'rb'))
    except Exception:
        return None
    if not isinstance(m, dict) or 'io' not in m or 'blocks' not in m:
        return None
    io = m['io']
    try:
        ins = sorted({str(v) for v in io.get('levers', {}).values()})
        outs = sorted({str(v) for v in io.get('lamps', {}).values()})
    except Exception:
        return None
    if not ins or not outs:
        return None
    return ins, outs


def recipe_io(path):
    """(inputs, outputs) from a recipe file, or None."""
    try:
        txt = open(path).read()
    except Exception:
        return None
    if 'IN ' not in txt or 'OUT ' not in txt:
        return None
    ins = re.search(r'^\s*IN\s+(.*)$', txt, re.M)
    outs = re.search(r'^\s*OUT\s+(.*)$', txt, re.M)
    if not ins or not outs:
        return None
    def names(s):
        return sorted({t.strip() for t in s.split(',') if t.strip()})
    return names(ins.group(1)), names(outs.group(1))


def candidate_recipes():
    pats = [os.path.join(ROOT, 'recipes', '*.txt'),
            os.path.join(HERE, 'cand_*.txt'),
            os.path.join(HERE, '*.recipe.txt')]
    out = []
    for p in pats:
        for f in sorted(glob.glob(p)):
            r = recipe_io(f)
            if r:
                out.append((f, r[0], r[1]))
    return out


def row_from_verdict(v, doc):
    """A sweep row from a verdict.json. Shared by the fresh and cached paths so
    a resumed run reports the SAME fields as the run that did the work."""
    r = {'sim': v.get('sim', {}).get('ok'),
         'cmc': v.get('cmc', {}).get('ok'),
         'sim_raised': (v.get('sim', {}).get('raised') or '')[:60],
         'blocks': len(json.load(open(doc))['blocks']),
         # Coverage, because a sampled green is not an exhaustive green. The
         # 10/4 sweep reported "0 diff" on alu4 at 4 of 1024 vectors while a
         # 64-vector run found 49814/1957248 -- the row must say what it
         # covered, or the next reader repeats the mistake.
         'n_vectors': v.get('n_vectors'),
         'vectors_sampled': json.load(open(doc)).get('sampled'),
         'engine': v.get('engine'),
         'cmc_stage': v.get('cmc', {}).get('stage')}
    # Builds sim cannot fully represent (Finding 3). A green here would be
    # reported on physics sim did not compute, so it must be visible.
    ul = v.get('unrepresentable_levers') or []
    if ul:
        r['unrepresentable_levers'] = ul
    d = v.get('diff')
    if d:
        r['diff_cells'] = d.get('mismatches')
        r['diff_total'] = d.get('cells')
        r['diff_rep'] = d.get('rep_mismatches')
        r['diff_rep_total'] = d.get('repeaters')
    return r


def engine_stamp():
    """Current engine identity, from verify2 (single source of truth)."""
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import verify2
        return verify2.engine_stamp()
    except Exception:                                        # noqa: BLE001
        return None


def load_verdict(doc):
    vp = doc + '.verdict.json'
    if os.path.exists(vp):
        try:
            return json.load(open(vp))
        except ValueError:
            return None
    return None


def flush(out_p, rows):
    """Rewrite the summary after EVERY row. ponytail: the 10/4 sweep ran to
    41/42 and then a tool timeout killed the process tree, and because the
    summary was written only after the loop, scratch/sweep.json DID NOT EXIST
    -- an entire night's evidence reduced to 44 orphaned verdict.json files
    that nobody could read without hand-parsing them. The work was cached but
    the record of it was not, which is the same loss the cache was meant to
    prevent. Cheap: a json.dump of a few dozen rows."""
    json.dump(rows, open(out_p, 'w'), indent=1)


def run_gate(pkl, recipe, doc, max_vectors, sim_to, cmc_to, diff):
    cmd = [sys.executable, '-u', os.path.join(HERE, 'verify2.py'),
           recipe, pkl, '--doc', doc, '--max-vectors', str(max_vectors),
           '--sim-timeout', str(sim_to), '--cmc-timeout', str(cmc_to)]
    if diff:
        cmd.append('--diff-all')
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=sim_to + cmc_to + 300, cwd=ROOT)
        out = p.stdout + p.stderr
        rc = p.returncode
    except subprocess.TimeoutExpired as e:
        out = 'GATE TIMEOUT: %s' % (e.stdout or b'')
        if isinstance(out, bytes):
            out = out.decode('utf8', 'replace')
        return {'gate': 'timeout', 'secs': round(time.time() - t0, 1),
                'raw': out[-300:]}
    # ponytail: never discard the child's exit code (the opt agent's
    # hier_verify did: check=False, return value dropped, so a RED stage
    # went on to verify the PREVIOUS artifact and printed a green that
    # certified a build that no longer existed). verify2 exits 0 green /
    # 1 red / 2 usage; anything else is a crash and must be loud.
    if rc not in (0, 1):
        return {'gate': 'crash', 'gate_rc': rc,
                'secs': round(time.time() - t0, 1), 'raw': out[-300:]}
    v = load_verdict(doc)
    if v is None:
        return {'gate': 'no-verdict', 'gate_rc': rc,
                'secs': round(time.time() - t0, 1), 'raw': out[-300:]}
    r = {'gate': 'ok', 'gate_rc': rc, 'secs': round(time.time() - t0, 1)}
    r.update(row_from_verdict(v, doc))
    return r


def main():
    args = sys.argv[1:]
    max_vectors, sim_to, cmc_to = 4, 600, 900
    diff = False
    skip_done = True
    cached_only = False
    out_p = os.path.join(HERE, 'sweep.json')
    only = None
    i = 0
    while i < len(args):
        if args[i] == '--pkls':
            only = args[i + 1].split(','); i += 2
        elif args[i] == '--max-vectors':
            max_vectors = int(args[i + 1]); i += 2
        elif args[i] == '--sim-timeout':
            sim_to = int(args[i + 1]); i += 2
        elif args[i] == '--cmc-timeout':
            cmc_to = int(args[i + 1]); i += 2
        elif args[i] == '--diff':
            diff = True; i += 1
        elif args[i] == '--force':
            skip_done = False
            i += 1
        elif args[i] == '--cached-only':
            # Rebuild the summary from cached verdicts and run NOTHING. Needed
            # whenever a sweep is killed before its final write: the work is
            # already cached, so re-gating it would burn hours to re-derive a
            # file we could have had in seconds. Earned twice on 10/4-10/05.
            cached_only = True
            i += 1
        elif args[i] == '--out':
            out_p = args[i + 1]; i += 2
        else:
            print('unknown arg', args[i])
            return 2
    if only:
        pkls = only
    else:
        pkls = sorted(set(glob.glob(os.path.join(HERE, '*.pkl'))
                          + glob.glob(os.path.join(HERE, '*', '*.pkl'))))
    recipes = candidate_recipes()
    cur_stamp = engine_stamp()
    print('sweeping %d pkls against %d recipes (max_vectors=%d diff=%s)'
          % (len(pkls), len(recipes), max_vectors, diff), flush=True)
    print('engine stamp: %s%s' % (cur_stamp,
          '' if cur_stamp else '  (UNAVAILABLE -- cached verdicts cannot be '
                               'checked for staleness)'), flush=True)
    rows = []
    t_start = time.time()
    for p in pkls:
        if not os.path.exists(p):
            continue
        names = io_names(p)
        if names is None:
            rows.append({'pkl': p, 'status': 'not-a-build'})
            continue
        ins, outs = names
        match = [(f, ri, ro) for f, ri, ro in recipes
                 if set(ri) == set(ins) and set(ro) == set(outs)]
        if not match:
            rows.append({'pkl': p, 'status': 'no-recipe',
                         'inputs': ins, 'outputs': outs})
            continue
        recipe = match[0][0]
        tag = os.path.basename(p)[:-4]
        doc = os.path.join(HERE, '_sweep_%s.v2doc.json' % tag)
# ponytail: resume. A long sweep gets killed by whoever launched it
        # (tool timeouts kill the process tree), so never redo finished work.
        if skip_done and os.path.exists(doc + '.verdict.json'):
            r = {'status': 'cached'}
            v = load_verdict(doc)
            # A verdict from DIFFERENT engine bytes is not a verdict about this
            # build, and in the cache it is indistinguishable from a current one
            # -- the stale ref_sim freeze all over again. Re-gate instead.
            # An UNSTAMPED verdict (written before stamping existed) is accepted
            # but flagged: re-gating 50 builds to add provenance nobody asked
            # for is not worth the hours, but it must not read as certified.
            if v and v.get('engine') and cur_stamp and v['engine'] != cur_stamp:
                print('%-34s %-26s STALE VERDICT (engine %s != %s), re-gating'
                      % (tag, os.path.basename(recipe)[:26], v['engine'],
                         cur_stamp), flush=True)
            else:
                # Rehydrate from the cached verdict. Previously this wrote a bare
                # {'status': 'cached'} with NO sim/cmc/diff fields, so a resumed
                # run produced a sweep.json that looked complete and reported
                # zero differences for every build -- because it carried no
                # numbers at all, rather than because there were none. That is
                # the worst possible failure for a gate: it reads as a clean
                # sweep.
                if v is not None:
                    r.update(row_from_verdict(v, doc))
                    if not v.get('engine'):
                        r['status'] = 'cached-unstamped'
                else:
                    r['status'] = 'cached-unreadable'
                rows.append(r)
                rows[-1].update({'pkl': p,
                                 'recipe': os.path.relpath(recipe, ROOT),
                                 'inputs': ins, 'n_recipes': len(match)})
                flush(out_p, rows)
                print('%-34s %-26s %s sim=%-5s cmc=%-5s %s'
                      % (tag, os.path.basename(recipe)[:26],
                         r['status'].upper()[:14], r.get('sim'), r.get('cmc'),
                         ('cells %s/%s rep %s/%s' % (r.get('diff_cells'),
                                                     r.get('diff_total'),
                                                     r.get('diff_rep'),
                                                     r.get('diff_rep_total')))
                      if 'diff_cells' in r else ''), flush=True)
                continue
        if cached_only:
            # never clobber a live sweep's summary: two writers to one out_p
            # means whichever flushed last wins, silently
            out_p = out_p if '--out' in args else os.path.join(
                HERE, 'sweep_cached.json')
            rows.append({'pkl': p, 'status': 'not-gated',
                         'inputs': ins, 'outputs': outs})
            flush(out_p, rows)
            print('%-34s %-26s NOT GATED (--cached-only)'
                  % (tag, os.path.basename(recipe)[:26]), flush=True)
            continue
        r = run_gate(p, recipe, doc, max_vectors, sim_to, cmc_to, diff)
        r.update({'pkl': p, 'recipe': os.path.relpath(recipe, ROOT),
                  'inputs': ins, 'n_recipes': len(match)})
        rows.append(r)
        flush(out_p, rows)
        flag = 'DIFF' if (r.get('diff_cells') or 0) else ''
        print('%-34s %-26s sim=%-5s cmc=%-5s %s%s'
              % (tag, os.path.basename(recipe)[:26], r.get('sim'),
                 r.get('cmc'),
                 ('cells %s/%s rep %s/%s' % (r.get('diff_cells'),
                                             r.get('diff_total'),
                                             r.get('diff_rep'),
                                             r.get('diff_rep_total')))
                 if 'diff_cells' in r else '',
                 ('  ' + flag) if flag else ''), flush=True)
    flush(out_p, rows)
    good = [r for r in rows if r.get('sim') is True and r.get('cmc') is True]
    diffs = [r for r in rows if (r.get('diff_cells') or 0)]
    noref = [r for r in rows if r.get('status') in ('not-a-build', 'no-recipe')]
    bad = [r for r in rows if r.get('sim') is False or r.get('cmc') is False]
    print('\n' + '=' * 66)
    print('sweep done in %.0fs: %d builds' % (time.time() - t_start, len(rows)))
    print('  green in BOTH engines : %d' % len(good))
    print('  per-cell DIFFERENCES  : %d  <-- investigate first'
          % len(diffs))
    print('  failing an engine     : %d' % len(bad))
    print('  skipped (no build/recipe): %d' % len(noref))
    for r in bad:
        print('   FAIL %-30s sim=%-5s cmc=%-5s %s'
              % (os.path.basename(r['pkl']), r.get('sim'), r.get('cmc'),
                 r.get('sim_raised', '')))
    for r in diffs:
        print('   DIFF %-30s %s/%s cells, %s/%s repeaters'
              % (os.path.basename(r['pkl']), r.get('diff_cells'),
                 r.get('diff_total'), r.get('diff_rep'),
                 r.get('diff_rep_total')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
