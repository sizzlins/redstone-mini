"""Pin add8's nine sum lamps back to the lever row. THE ORIGINAL REQUEST.

"Take the wire that powers the sum lamp all the way to the levers ending in
lamps, and put signs on the levers and the lamps."

Nine routed runs is not a small thing -- the naive composer route measured
135,260 blocks. So: compose ONE band of add8 (S0's band) with its lamp pinned
into the lever row, and see what one run actually costs and whether it routes
at all. If one band routes cleanly, the other eight are the same shape.

NEVER HANGS: in-memory compose with a wall-clock cap, no server, no subprocess.
"""
import os
import sys
import time

sys.path.insert(0, r'D:\redstone-mini')
sys.path.insert(0, r'D:\redstone-mini\scratch')

from recipe import parse_recipe, expand_gates
from compose import _strip_buffers, _compose_once

SRC = r'D:\redstone-mini\recipes\add8.txt'
# lever row for the pitch-2 bank: x=3, z=3..33 (A0 at z=5, A1 at z=9, ...)
# pin the sum lamps just north of it, in the free cells x=5..7.
PINS = {'S0': (6, 5), 'S1': (6, 9), 'S2': (6, 13), 'S3': (6, 17),
        'S4': (6, 21), 'S5': (6, 25), 'S6': (6, 29), 'S7': (6, 33),
        'COUT': (6, 37)}


def band_recipe(band_out):
    """One band's gates as a standalone recipe, inputs all 16 bits."""
    r = parse_recipe(open(SRC).read())
    gates = _strip_buffers(expand_gates(r['gates'], r['inputs']), r['outputs'])
    prod = {g['out']: g.get('band', 0) for g in gates}
    bg = [g for g in gates if g.get('band', 0) == prod[band_out]]
    return {'inputs': list(r['inputs']),
            'outputs': [band_out],
            'gates': [{k: v for k, v in g.items() if k != 'band'} for g in bg],
            'lamps_at': {band_out: PINS[band_out]}}


def main():
    for out in ('S0', 'S7', 'COUT'):
        sub = band_recipe(out)
        txt = ['IN ' + ', '.join(sub['inputs']),
               'OUT ' + out]
        for g in sub['gates']:
            if g['op'] == 'NOT':
                txt.append('%s = NOT %s' % (g['out'], g['args'][0]))
            else:
                txt.append('%s = %s %s %s'
                           % (g['out'], g['args'][0], g['op'], g['args'][1]))
        txt.append('LAMP %s AT %d %d' % (out, *PINS[out]))
        r = parse_recipe('\n'.join(txt) + '\n')
        t0 = time.time()
        try:
            blocks, size, io = _compose_once(r)
        except Exception as e:
            print('%-5s FAILED after %5.1fs: %s: %s'
                  % (out, time.time() - t0, type(e).__name__, str(e)[:90]))
            continue
        lamp = [c for c, n in io['lamps'].items() if n == out]
        print('%-5s %6d blocks  %5.1fs  size %-12s lamp at %s (pinned %s)'
              % (out, len(blocks), time.time() - t0, size, lamp, PINS[out]))


if __name__ == '__main__':
    main()