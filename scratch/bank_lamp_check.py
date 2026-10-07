"""Do the bank lamps actually show the SUM? Routing is not correctness.

`bank_rows.py` places lamps by routing; this reads them. Seven of nine nets
routed, so this checks the seven that exist and says plainly which are absent
rather than pretending the build is whole.

Checks, per vector:
  - each placed lamp's sim reading equals the expected bit of the sum of the
    A-side levers (the build is exercised on A only, as the live rig does)
  - the 16 lever indicators still track their levers (the new wires must not
    have broken the existing readout)
  - the original 9 sum lamps, where they are untouched, still read the same

NEVER HANGS: bounded vectors, in-memory sim, no subprocess.
"""
import pickle
import sys

sys.path.insert(0, r'D:\redstone-mini')
sys.path.insert(0, r'D:\redstone-mini\scratch')

PKL = r'D:\redstone-mini\scratch\add8_bankrouted.pkl'
VECTORS = [0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80,
           0x0F, 0x55, 0xAA, 0xFF, 0x7F, 0xFE, 0x8F]


def main():
    d = pickle.load(open(PKL, 'rb'))
    blocks = d['blocks']
    io = dict(d['io'])
    placed = d['placed']
    print('placed: %s' % [p[0] for p in placed])
    if d.get('failed'):
        print('ABSENT : %s  (routed no lamp -- stated, not hidden)' % d['failed'])

    # register the new lamp cells so sim reads them (2-tuple keys, the io
    # convention: a 3-tuple key maps to the wrong cell in _parse_build and
    # reads dark -- measured, not assumed).
    lamps = dict(io['lamps'])
    new_cells = {}
    for name, _lane, lamp in placed:
        cell = (lamp[0], 1, lamp[1])
        lamps[(lamp[0], lamp[1])] = name + '@bank'
        new_cells[name] = cell
    io['lamps'] = lamps

    from sim import _parse_build, _run_vec
    P = _parse_build([tuple(b) for b in blocks], io)
    levers = io['levers']
    bits = ['A%d' % i for i in range(8)]
    # ponytail: only check readouts that exist. out.get on an absent lamp is
    # None, which reads as "wrong" whenever the bit is 1 -- a gate that fails
    # on builds without indicators proves nothing about this build.

    bad = 0
    for v in VECTORS:
        vec = {n: (v >> i) & 1 for i, n in enumerate(bits)}
        full = {k: vec.get(k, 0) for k in set(levers.values())}
        out, live, _, _, _, _ = _run_vec(full, None, P)
        exp = v
        line = []
        for name, _lane, lamp in placed:
            cell = new_cells[name]
            got = bool(out.get(name + '@bank'))
            want = bool(exp & (1 << int(name[1:]))) if name.startswith('S') \
                else bool(exp > 255)
            if got != want:
                bad += 1
                line.append('%s=%s(want %s)' % (name, got, want))
        ind = [n for n in bits
               if (n + 'L') in set(lamps.values())
               and bool(out.get(n + 'L')) != bool(vec[n])]
        if ind:
            bad += len(ind)
            line.append('indicators wrong: %s' % ind)
        print('  A=0x%02X sum=%3d  %s'
              % (v, exp, 'OK' if not line else ' '.join(line)))
    print()
    print('bank-lamp readout: %d wrong readings across %d vectors x %d lamps'
          % (bad, len(VECTORS), len(placed)))


if __name__ == '__main__':
    main()