"""What actually walls S0's driver in? Print the neighbourhood.

`seal_confirm.py` falsified the ring theory: S0 owns 0 ring cells in the merged
field, and clearing cobble changed nothing. So the "no ground" wall is something
else. Print the merged field around the driver and name every occupant, so the
next hypothesis is read off the map instead of guessed.

Legend: `.` free  `A` wire of the named net  `r` repeater  `#` solid/cobble
`o` ring cell (owner shown by digit)  `T` torch  `L` lamp  `t` tile cobble
"""
import pickle
import sys

MERGE = r'D:\redstone-mini\scratch\add8merge.pkl'
NET = 'S0'
R = 9


def main():
    d = pickle.load(open(MERGE, 'rb'))
    wires, solid, rings = d['wires'], d['solid'], d['rings']
    reps = d['repeaters']
    a = tuple(d['pos'][NET])
    ax, az = a
    lamps = {tuple(c) if len(tuple(c)) == 2 else (c[0], c[2]): n
             for c, n in d['io']['lamps'].items()}
    blocks = {}
    for x, y, z, bid in d['blocks']:
        blocks[(x, z, y)] = bid

    print('%s driver at %s' % (NET, a))
    hdr = '     ' + ''.join('%d' % ((ax + dx) % 10) for dx in range(-R, R + 1))
    print(hdr)
    for dz in range(-R, R + 1):
        row = []
        for dx in range(-R, R + 1):
            c = (ax + dx, az + dz)
            ch = '.'
            if c in solid:
                ch = 't' if solid[c][0] != 'lamp' else 'L'
                if solid[c][0] == 'lamp':
                    ch = 'L'
            w = wires.get((c[0], 1, c[1]))
            if w:
                ch = NET[-1] if w == NET else 'x'
            if (c[0], 1, c[1]) in reps:
                ch = 'r'
            for y in (1, 2, 3):
                if (c[0], c[1], y) in blocks and 'torch' in blocks[(c[0], c[1], y)]:
                    ch = 'T'
            if c in lamps:
                ch = 'L'
            row.append(ch)
        print('%4d %s' % (az + dz, ''.join(row)))

    print()
    print('cells within radius %d owned by %s in rings: %d'
          % (R, NET, sum(1 for k, v in rings.items()
                         if v == NET and abs(k[0] - ax) <= R
                         and abs(k[1] - az) <= R)))
    print('distinct ring owners nearby: %s'
          % sorted({v for k, v in rings.items()
                    if abs(k[0] - ax) <= R and abs(k[1] - az) <= R})[:20])
    near = [(c, wires.get((c[0], 1, c[1])))
            for c in ((ax + dx, az + dz) for dx in range(-R, R + 1)
                      for dz in range(-R, R + 1))
            if wires.get((c[0], 1, c[1]))]
    from collections import Counter
    print('wire owners nearby: %s' % Counter(n for _, n in near).most_common(8))


if __name__ == '__main__':
    main()