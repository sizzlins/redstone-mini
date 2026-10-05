"""Do the lamp blocks actually sit at the declared io['lamps'] pins?

The rig reads lamps by looking each pin coordinate up in the BLOCK list, so a
pin whose lamp lives elsewhere would be read at a cell that is not a lamp --
and `execute if block ... lamp[lit=true]` then reports "dark" for a lit lamp.
That is the same shape as the sampled-green trap: the gate looks green
because it never read the block it claimed to read.

NEVER HANGS: pure in-memory pickle + dict comparison, one pass per build.

Usage: python scratch/lamp_pin_check.py a.pkl b.pkl ...
"""
import os
import sys

sys.path.insert(0, r'D:\redstone-mini')


def check(path):
    import pickle
    m = pickle.load(open(path, 'rb'))
    lamps = [(x, y, z) for x, y, z, b in m['blocks']
             if str(b).startswith('minecraft:redstone_lamp')]
    pins = {}
    for k, v in m['io']['lamps'].items():
        pins[tuple(k) if isinstance(k, (list, tuple)) else (k,)] = v
    # a 2-tuple pin maps to y=1 (sim's _y rule); a 3-tuple is literal
    want = set()
    for k in pins:
        if len(k) == 2:
            want.add((k[0], 1, k[1]))
        elif len(k) == 3:
            want.add(tuple(k))
        else:
            print('   ODD pin key %r (%s) -- unhandled, skipped'
                  % (k, pins[k]), flush=True)
    have = set(lamps)
    missing = sorted(want - have)
    extra = sorted(have - want)
    print('%-34s lamps=%-3d pins=%-3d missing=%-2d extra=%-2d'
          % (os.path.basename(path), len(have), len(want),
             len(missing), len(extra)), flush=True)
    for c in missing[:4]:
        print('   MISSING lamp at %s (%s)' % (c, pins.get(c) or pins.get((c[0], c[2]))))
    for c in extra[:4]:
        print('   EXTRA   lamp at %s' % (c,))
    return not missing and not extra


if __name__ == '__main__':
    ok = all([check(p) for p in sys.argv[1:]])
    sys.exit(0 if ok else 1)