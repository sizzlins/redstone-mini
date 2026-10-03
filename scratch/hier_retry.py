"""Combination-aware hier loop: bands are green standalone but the merge
can still disagree (cross-band handoff). On a merge smoke mismatch, find
the failing outputs' fanin bands, skip their current rungs, re-climb only
those bands, re-stitch, re-smoke. Bounded iterations, hang-safe (every
stage is itself bounded; this driver only polls).

Usage: python scratch/hier_retry.py <recipe.txt> <workprefix> <iters>
Work files: <workprefix>_bands.pkl, <workprefix>_merge.pkl.
Needs: hier_bands.py, hier_stitch.py (same dir), sim.py R.eval_net.
"""
import os
import pickle
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from recipe import eval_net, parse_recipe  # noqa: E402

BAND_SECS = 240
STITCH_SECS = 1200


def run(cmd, timeout, logpath, env=None):
    with open(logpath, 'w') as log:
        p = subprocess.Popen(cmd, cwd=os.path.dirname(HERE),
                             stdout=log, stderr=subprocess.STDOUT,
                             env=env)
        try:
            rc = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(5)
            return 124, 'TIMEOUT'
        return rc, 'rc=%d' % rc


def fanin_bands(recipe, outputs):
    """Bands feeding the given outputs (gate-arg closure -> band set)."""
    prod = {}
    for g in recipe['gates']:
        prod[g['out']] = g.get('band', 0)
    need, seen = set(outputs), set()
    bands = set()
    while need:
        n = need.pop()
        if n in seen or n in recipe['inputs']:
            continue
        seen.add(n)
        b = prod.get(n)
        if b is None:
            continue
        bands.add(b)
        g = next((g for g in recipe['gates'] if g['out'] == n), None)
        if g:
            need.update(a for a in g['args'] if a not in ('0', '1'))
    return bands


def main():
    src, pre, iters = sys.argv[1], sys.argv[2], int(sys.argv[3])
    recipe = parse_recipe(open(src).read())
    skip = [s for s in (sys.argv[4].split(';') if len(sys.argv) > 4 else [])
            if s]
    bandspkl = pre + '_bands.pkl'
    mergepkl = pre + '_merge.pkl'
    for it in range(iters + 1):
        env = dict(os.environ)
        if skip:
            env['HIER_SKIP'] = ';'.join(skip)
        print('=== iter %d skip=[%s] ===' % (it, ' '.join(skip)), flush=True)
        b = dict(env)
        rc, msg = run([sys.executable, 'scratch/hier_bands.py', src,
                       pre + '_bands', '150'], BAND_SECS + 300,
                      pre + '_bands%d.log' % it, env=b)
        print('bands:', msg, flush=True)
        if rc != 0:
            print('BANDS RED, see %s' % (pre + '_bands%d.log' % it), flush=True)
            return 1
        rungs = {}
        try:
            bp = pickle.load(open(bandspkl, 'rb'))
            for band in bp['bands']:
                rungs[band['b']] = band['rung']
        except Exception as e:
            print('cannot read rungs:', e, flush=True)
            return 1
        rc, msg = run([sys.executable, 'scratch/hier_stitch.py', bandspkl,
                       src, '900', mergepkl], STITCH_SECS + 300,
                      pre + '_stitch%d.log' % it)
        print('stitch:', msg, flush=True)
        if rc not in (0, 1):
            print('STITCH ERROR (not smoke), see %s'
                  % (pre + '_stitch%d.log' % it), flush=True)
            return 1
        bad = set()
        nsmoke = 0
        for line in open(pre + '_stitch%d.log' % it, errors='replace'):
            if 'SMOKE' in line and ('OK' in line or 'MISMATCH' in line):
                nsmoke += 1
            m = re.search(r'SMOKE (\S+) MISMATCH \[(.*)\]', line)
            if m:
                bad.update(x.strip().strip("'\"") for x in m.group(2).split(','))
        bad = {x for x in bad if x}
        if not bad:
            if nsmoke == 0:
                print('NO SMOKE LINES (structural fail)', flush=True)
                return 1
            print('GREEN iter %d' % it, flush=True)
            return 0
        print('mismatch outputs:', sorted(bad), flush=True)
        if it >= iters:
            print('BUDGET EXHAUSTED', flush=True)
            return 2
        bands = fanin_bands(recipe, bad)
        print('fanin bands:', sorted(bands), flush=True)
        newskip = ['%d:%s' % (bb, rungs[bb]) for bb in sorted(bands)
                   if bb in rungs]
        if not newskip or all(s in skip for s in newskip):
            print('NO NEW RUNGS TO SKIP', flush=True)
            return 3
        skip.extend(s for s in newskip if s not in skip)
    return 2


if __name__ == '__main__':
    sys.exit(main())
