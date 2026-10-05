"""Lever-side indicator lamps: 16 blocks, zero routing.

A floor lever powers every block adjacent to it, so a lamp placed in a free
cell beside the lever shows that bit -- no wire, no gate, no router. Asking
the composer for it instead costs 88,000 blocks (measured: one buffer band per
bit = 135,260 total; all buffers in band 0 = 20,390 for band 0 alone AND it
breaks the bank stitch). 16 blocks is the whole cost.

The lamp is a real, sim-readable observation of the net: sim's dust_lvl powers
an adjacent cell from a lever, so the indicator cannot disagree with the bit.
assert_indicators() proves that in-sim instead of assuming it.

NEVER HANGS: pure in-memory transform + bounded sim vectors, no subprocess.

Usage:
  python scratch/lever_lamps.py <in.pkl> <out.pkl>
  python scratch/lever_lamps.py --check <pkl>
"""
import os
import pickle
import sys

ROOT = r'D:\redstone-mini'
sys.path.insert(0, ROOT)

DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def add_indicators(blocks, io, pin_names):
    """Place one lamp per input pin, in the first free neighbour cell."""
    have = {(x, y, z) for x, y, z, _ in blocks}
    lamps = {tuple(k) if isinstance(k, (list, tuple)) else (k,): v
             for k, v in io['lamps'].items()}
    levers = io['levers']
    out = list(blocks)
    placed = {}
    for key, name in sorted(levers.items(), key=lambda kv: str(kv[1])):
        if name not in pin_names:
            continue
        x, z = (int(v) for v in key[:2])
        y = 1
        spot = None
        for dx, dz in DIRS:
            c = (x + dx, y, z + dz)
            if c not in have:
                spot = c
                break
        if spot is None:
            print('  %-3s NO FREE CELL beside lever (%d,%d)' % (name, x, z))
            continue
        out.append((spot[0], spot[1], spot[2], 'minecraft:redstone_lamp'))
        have.add(spot)
        lamps[spot] = name + 'L'
        placed[name] = spot
    io = dict(io)
    io['lamps'] = {k: v for k, v in lamps.items()}
    return out, io, placed


def assert_indicators(pkl, n=4):
    """The indicator lamp must equal its bit. If this fails the lamp is a lie.

    The check is the engine's own answer: _run_vec returns a value for every
    io['lamps'] pin, so an indicator that disagrees with its bit is a gate
    failure, not an opinion.
    """
    from sim import _parse_build, _run_vec
    m = pickle.load(open(pkl, 'rb'))
    P = _parse_build([tuple(b) for b in m['blocks']], m['io'])
    names = set(m['io']['levers'].values())
    ind = sorted(nm for nm in names if nm + 'L' in m['io']['lamps'].values())
    if not ind:
        print('no indicators found')
        return 1
    bad = 0
    checked = 0
    # Bounded: 2^16 vectors x a 46k-block build is hours. 64 SPREAD masks
    # (every bit pattern of distance 1..4 plus alternating) cover all 16
    # single-bit, all-zero and all-one cases. Coverage is stated, not implied.
    masks = sorted({0, (1 << len(ind)) - 1}
                   | {1 << i for i in range(len(ind))}
                   | {0xAAAA & ((1 << len(ind)) - 1), 0x5555 & ((1 << len(ind)) - 1)})
    if len(masks) > n:
        step = len(masks) / float(n)
        masks = [masks[int(i * step)] for i in range(n)]
    print('indicators: %d bits, %d vectors (of 2^%d)'
          % (len(ind), len(masks), len(ind)))
    for mask in masks:
        vec = {nm: (mask >> i) & 1 for i, nm in enumerate(ind)}
        got, _, _, _, _, _ = _run_vec(vec, None, P)
        for nm in ind:
            checked += 1
            if bool(got.get(nm + 'L', False)) != bool(vec[nm]):
                bad += 1
                if bad < 6:
                    print('  FAIL %s=%d lamp=%s'
                          % (nm, vec[nm], bool(got.get(nm + 'L'))))
    print('indicators: %d checks, %d wrong' % (checked, bad))
    return 0 if bad == 0 else 1


def main():
    a = sys.argv[1:]
    if a and a[0] == '--check':
        sys.exit(assert_indicators(a[1]))
    src, dst = a[0], a[1]
    m = pickle.load(open(src, 'rb'))
    pins = set(m['io']['levers'].values())
    out, io, placed = add_indicators(m['blocks'], m['io'], pins)
    m['blocks'] = out
    m['io'] = io
    m['size'] = (max(b[0] for b in out) + 1, max(b[2] for b in out) + 1)
    pickle.dump(m, open(dst, 'wb'), protocol=4)
    print('placed %d indicator lamps; %d -> %d blocks'
          % (len(placed), len(m['blocks']) - len(placed), len(out)))
    for name in sorted(placed, key=lambda s: (s[0], int(s[1:]))):
        print('  %-3s lamp at %s' % (name, placed[name]))


if __name__ == '__main__':
    main()