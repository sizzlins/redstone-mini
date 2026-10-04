"""How much of the tree is actually verified? The 50 builds no recipe matches.

scratch/sweep.py gates a build by matching its io pin NAMES against
recipes/*.txt. 50 of 98 pkls match nothing and are reported 'no-recipe', which
reads like a skip but means those builds have NO verification at all -- not a
weak check, none.

This says what they actually are, because the answer splits into two very
different situations:

  BAND SLICE   a band/intermediate artifact whose levers are a SUBSET of the
               recipe's (alu4bands*, cpu4bands*, *_states). Un-gateable by
               construction, and correctly so: it is a rung, not a circuit.
               Counting it as "unverified build" would be misleading.
  REAL BUILD   a finished circuit whose pins genuinely match no recipe -- a
               stale io, a renamed pin, or a recipe that was never written.
               That IS a coverage hole and it should be visible.

Read-only. No engine calls. Bounded: one pickle header read per pkl.

Usage:  python scratch/coverage.py
"""
import glob
import os
import pickle
import re
import sys

HERE = r'D:\redstone-mini\scratch'


def pins(d):
    io = d.get('io') or {}
    return (sorted({str(v) for v in (io.get('levers') or {}).values()}),
            sorted({str(v) for v in (io.get('lamps') or {}).values()}))


def recipes():
    out = []
    for p in (glob.glob(os.path.join(HERE, '..', 'recipes', '*.txt'))
              + glob.glob(os.path.join(HERE, 'cand_*.txt'))
              + glob.glob(os.path.join(HERE, '*.recipe.txt'))):
        try:
            txt = open(p).read()
        except OSError:
            continue
        mi = re.search(r'^\s*IN\s+(.*)$', txt, re.M)
        mo = re.search(r'^\s*OUT\s+(.*)$', txt, re.M)
        if not (mi and mo):
            continue
        nm = lambda s: sorted({t.strip() for t in s.split(',') if t.strip()})
        out.append((os.path.basename(p), nm(mi.group(1)), nm(mo.group(1))))
    return out


def main():
    rc = recipes()
    print('%d recipes with IN/OUT lines' % len(rc))
    pkls = sorted(set(glob.glob(os.path.join(HERE, '*.pkl'))
                      + glob.glob(os.path.join(HERE, '*', '*.pkl'))))
    slice_like, hole, unreadable = [], [], []
    for p in pkls:
        try:
            d = pickle.load(open(p, 'rb'))
        except Exception:                                   # noqa: BLE001
            unreadable.append(p)
            continue
        if not isinstance(d, dict) or 'blocks' not in d or 'io' not in d:
            unreadable.append(p)
            continue
        ins, outs = pins(d)
        if not ins or not outs:
            unreadable.append(p)
            continue
        if any(set(i) == set(ins) and set(o) == set(outs) for _, i, o in rc):
            continue                                        # gated elsewhere
        # subset of some recipe's pins => a band slice / partial rung
        sub = None
        for name, i, o in rc:
            if set(ins) <= set(i) and set(outs) <= set(o):
                sub = name
                break
        name = os.path.basename(p)[:-4]
        (slice_like if sub else hole).append((name, len(d['blocks']), sub,
                                              ins[:4], outs[:4]))
    print('%d pkls total, %d not gateable\n' % (len(pkls), len(slice_like) + len(hole)))
    print('BAND SLICES (pins are a subset of a recipe -- ungateable by '
          'construction): %d' % len(slice_like))
    for n, b, s, i, o in sorted(slice_like)[:14]:
        print('   %-30s %7d blk  subset of %-14s in=%s out=%s'
              % (n, b, s, i, o))
    if len(slice_like) > 14:
        print('   ... and %d more' % (len(slice_like) - 14))
    print('\nPOSSIBLE REAL COVERAGE HOLES (pins match no recipe, not a '
          'subset): %d' % len(hole))
    for n, b, s, i, o in sorted(hole, key=lambda t: -t[1]):
        print('   %-30s %7d blk  in=%s out=%s' % (n, b, i, o))
    print('\nnot builds at all: %d' % len(unreadable))
    return 0


if __name__ == '__main__':
    sys.exit(main())