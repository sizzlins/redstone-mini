"""Does a LAMP pin actually light? Smallest check that fails if it breaks.

In-memory only, bounded vectors, no subprocess -- runnable as a gate.

The bug this pins down: `LAMP <name> AT <x> <z>` used to stamp a lamp and one
dust tap and route NOTHING to it, so every pinned lamp read dark. The fix makes
the pin a routing goal (core.pin_tap_cell -> build_netspec load ->
tiles._tap_pinned tap). This asserts the lamp is lit by sim for a real vector,
so a regression cannot pass as "the pin compiled".

Usage:  python scratch/pin_lamp_check.py
"""
import sys

sys.path.insert(0, r'D:\redstone-mini')

from recipe import parse_recipe
from compose import compose
from sim import sim_verify

RECIPE = """
IN A0, A1, B0, B1
OUT S0, S1
x0 = A0 XOR B0
S0 = x0 AND x0
x1 = A1 XOR B1
S1 = x1 XOR x1
"""


def check(pin_x, pin_z):
    txt = RECIPE + "\nLAMP S0 AT %d %d\n" % (pin_x, pin_z)
    r = parse_recipe(txt)
    blocks, size, io = compose(r)
    lamps = {c: n for c, n in io['lamps'].items() if n == 'S0'}
    assert lamps, 'no S0 lamp at all - pin broke lamp placement'
    sim_verify(r, blocks, io, quiet=True)
    return blocks, size, io, list(lamps)[0]


def main():
    # Pin far from the natural lamp spot: the whole point is that the wire has
    # to be ROUTED there, not just stamped there.
    px, pz = 60, 5
    blocks, size, io, lamp = check(px, pz)
    print('pinned S0 lamp at %s  build %d blocks  size %s' % (lamp, len(blocks), size))

    # The tap cell must be a WIRE in the finished build, not just a stamped
    # cell. This is the assertion that actually pins down the bug: before the
    # fix the tap existed and carried nothing.
    taps = [c for c in io['lamps'] if c == lamp]
    assert taps, 'lamp vanished from io'
    wire_at_tap = [(x, y, z) for x, y, z, b in blocks
                   if 'redstone_wire' in str(b)
                   and abs(x - lamp[0]) <= 1 and abs(z - lamp[1]) <= 1 and y == 1]
    assert wire_at_tap, 'no wire beside the pinned lamp - the tap was never routed'
    print('tap wire beside the pinned lamp: %s' % (wire_at_tap,))

    from sim import _parse_build, _run_vec
    P = _parse_build([tuple(b) for b in blocks], io)
    lit_n = dark_n = 0
    for a0 in (0, 1):
        for b0 in (0, 1):
            vec = {'A0': a0, 'A1': 0, 'B0': b0, 'B1': 0}
            out, _, _, _, _, _ = _run_vec(vec, None, P)
            want = bool(a0 ^ b0)          # S0 = A0 XOR B0
            got = bool(out.get('S0'))      # sim's read OF THE PINNED LAMP
            assert got == want, ('pinned lamp disagrees with the sum',
                                 vec, 'lamp=%s' % got, 'sum=%s' % want)
            lit_n += got
            dark_n += not got
    print('pinned lamp followed the sum: %d lit, %d dark, 0 disagreements'
          % (lit_n, dark_n))

    # And the control: with the pin REMOVED the recipe must still build, or the
    # pin changed unrelated behaviour.
    r2 = parse_recipe(RECIPE)
    b2, s2, io2 = compose(r2)
    print('unpinned control still builds: %d blocks' % len(b2))

    negative_test()
    print('PIN LAMP OK: a pinned lamp is a routed load, not a decoration')


def negative_test():
    """A gate that cannot fail is decoration. Break the fix, expect dark.

    Only `layout`'s view is stubbed, not `tiles`': layout is what turns the pin
    into a routing goal. With no goal the tap is still stamped (that part never
    moved) but nothing drives it -- which is exactly the original bug, and it
    must show up as a dark lamp rather than passing quietly.
    """
    import layout
    real = layout.pin_tap_cell
    layout.pin_tap_cell = lambda name, recipe: None
    try:
        txt = RECIPE + "\nLAMP S0 AT 60 5\n"
        blocks, size, io = compose(parse_recipe(txt))
    except (RuntimeError, TypeError) as e:
        # Also a reproduction. Without the load the pin is a lamp on a dead
        # cell, and downstream code that walks the loads trips over the hole.
        print('negative test ok: with the pin load removed the build dies '
              '(%s: %s)' % (type(e).__name__, str(e)[:60]))
        return
    finally:
        layout.pin_tap_cell = real

    lamp = [c for c, n in io['lamps'].items() if n == 'S0']
    assert lamp, 'negative test: pin broke lamp placement entirely'
    from sim import _parse_build, _run_vec
    P = _parse_build([tuple(b) for b in blocks], io)
    out, _, _, _, _, _ = _run_vec({'A0': 0, 'A1': 0, 'B0': 1, 'B1': 0}, None, P)
    assert not out.get('S0'), ('negative test FAILED to reproduce the bug: '
                              'the lamp is still correct with the pin load '
                              'removed, so this gate proves nothing')
    print('negative test ok: with the pin load removed the lamp reads dark, '
          'so the check above has teeth')


if __name__ == '__main__':
    main()