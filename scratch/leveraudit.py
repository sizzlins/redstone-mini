"""Blast radius: how many builds use a lever that is NOT a declared input pin?

sim can only power a lever that appears in io['levers'] -- comp_in does
`vec.get(lever[rear], False)`, and the vector is keyed by pin NAME. A lever
placed in the build but absent from io is therefore permanently off in sim
even when its blockstate says powered=true, which is what vanilla does. cmc
honours the blockstate, so the two engines disagree on such builds (proved on
not_full.pkl: sim Y=false, cmc Y=true, a comparator-subtract inverter).

That is only worth changing if the construct actually occurs in builds we
care about. This scans every pkl in the tree and reports, per build, the
number of lever blocks with no matching io entry, split by whether the
blockstate claims powered=true.

Read-only. Bounded: one pickle load per pkl, no engine calls, no sim.

Usage:  python scratch/leveraudit.py [glob ...]
"""
import glob
import os
import pickle
import re
import sys

ROOT = r'D:\redstone-mini'


def scan(path):
    try:
        m = pickle.load(open(path, 'rb'))
    except Exception as e:                                # noqa: BLE001
        return ('unreadable', str(e)[:40], 0, 0)
    if not isinstance(m, dict) or 'blocks' not in m or 'io' not in m:
        return ('not-a-build', '', 0, 0)
    io = m['io']
    pins = set()
    for k in (io.get('levers') or {}):
        pins.add(tuple(k) if isinstance(k, (tuple, list)) else k)
    npin = npin_on = 0
    for b in m['blocks']:
        if len(b) < 4:
            continue
        x, y, z, s = b[0], b[1], b[2], str(b[3])
        # LEVERS ONLY. Wall torches are a different source with different
        # semantics (sim tracks them lit/unlit in `torch`); counting them here
        # reported 138 "non-pin levers" in a build that has 10 levers.
        if s == 'minecraft:lever' or s.startswith('minecraft:lever['):
            floor = (x, y - 1, z)
            # io keys are (x, z) or (x, y, z)
            if floor not in pins and (x, z) not in pins:
                npin += 1
                if 'powered=true' in s:
                    npin_on += 1
    return ('ok', '', npin, npin_on)


def main():
    pats = sys.argv[1:] or [os.path.join(ROOT, 'scratch', '**', '*.pkl')]
    files = []
    for p in pats:
        files += glob.glob(p, recursive=True)
    files = sorted(set(files))
    hits, rows = [], []
    for f in files:
        status, err, npin, npin_on = scan(f)
        rel = os.path.relpath(f, ROOT)
        if status != 'ok':
            continue
        rows.append((rel, npin, npin_on))
        if npin:
            hits.append((rel, npin, npin_on))
    print('scanned %d build pkls (%d readable)'
          % (len(files), len(rows)))
    with_levers = [r for r in rows if r[1]]
    print('builds containing a lever block at all: %d' % len(with_levers))
    print('builds with a NON-PIN lever            : %d' % len(hits))
    for rel, n, non in sorted(hits, key=lambda t: -t[2])[:40]:
        print('   %-46s non-pin levers=%-3d of which powered=true: %d'
              % (rel, n, non))
    if not hits:
        print('\n=> No build relies on a non-pin lever. sim is consistent with '
              'vanilla on every build in the tree; the gap is latent and only '
              'reachable by hand/search-built candidates.')
    return 0


if __name__ == '__main__':
    sys.exit(main())