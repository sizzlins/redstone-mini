"""Level-3 block compactor: post-pass hillclimb on a verified build.

Seed = (recipe, blocks, io) that already verifies green. Moves = single
block deletions, tried in seeded-random order within a type priority
(wire, repeater, cobble, comparator, torch, stone -- expected yield
order; lamps and levers are never candidates, I/O must exist). Accept
iff full sim_verify stays green. Monotone: best only ever shrinks, and
every accepted step is itself a verified build. Bounded: MAX_EVALS +
wall clock. The netlist never changes, so function is preserved by
construction and re-checked by the sim on every step.

Trust note, stated once: this optimizes against the sim, not the game.
The final artifact needs one game paste before banking (same rule as
everything else here).

Usage: python scratch/compact.py <recipe.txt> <workdir> [max_evals] [seed]
       [focus]
Writes best.pkl + compact.log + build_compact.{mcfunction,schem,html}.

focus pins one material tier for the whole slice (e.g. repeater): the
normal loop restarts from the wire tier after every accept, so lower
tiers are never reached while wire still yields. A focused slice sweeps
that tier exhaustively instead. focus must be a minecraft:* prefix from
PRIORITY (or 'all', the default).
"""
import os
import random
import sys
import time

sys.path.insert(0, r'D:\redstone-mini')

PRIORITY = ('minecraft:redstone_wire', 'minecraft:repeater',
            'minecraft:cobblestone', 'minecraft:comparator',
            'minecraft:redstone_wall_torch', 'minecraft:stone')
SKIP = ('minecraft:redstone_lamp', 'minecraft:lever')


def _base(bid):
    return bid.split('[')[0]


def _priority_key(block):
    b = _base(block[3])
    if b in SKIP:
        return -1
    try:
        return PRIORITY.index(b)
    except ValueError:
        return len(PRIORITY)


_NEED_BELOW = ('minecraft:redstone_wire', 'minecraft:repeater',
               'minecraft:comparator')
_FACING_MOUNT = {'east': (-1, 0), 'west': (1, 0),
                 'south': (0, -1), 'north': (0, 1)}


def _load_bearing(bmap, coord):
    """Static support check the sim cannot do (it models support power,
    never structural integrity: a floor deletion under live dust verifies
    green and collapses in-game -- measured 242/300 poisoned, 2026-10-04).
    Only stone/cobble can be supports (lamps are never candidates), so
    only those tiers call this. True = deletion forbidden, no eval spent.
    """
    x, y, z = coord
    ab = bmap.get((x, y + 1, z))
    if ab is not None:
        b = _base(ab)
        if b in _NEED_BELOW or (b == 'minecraft:lever'
                                and 'face=wall' not in ab):
            return True
    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nb = bmap.get((x + dx, y, z + dz))
        if nb is None:
            continue
        b = _base(nb)
        if b not in ('minecraft:redstone_wall_torch', 'minecraft:lever'):
            continue
        if b == 'minecraft:lever' and 'face=wall' not in nb:
            continue
        try:
            f = nb.split('facing=')[1].split(',')[0].split(']')[0]
        except IndexError:
            continue
        if _FACING_MOUNT.get(f) == (-dx, -dz):
            return True
    return False


def main():
    src, workdir = sys.argv[1], sys.argv[2]
    max_evals = int(sys.argv[3]) if len(sys.argv) > 3 else 300
    seed = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    focus = sys.argv[5] if len(sys.argv) > 5 else 'all'
    rng = random.Random(seed)
    os.makedirs(workdir, exist_ok=True)
    log = open(os.path.join(workdir, 'compact.log'), 'a')
    t_end = time.monotonic() + 1200

    from recipe import parse_recipe
    from compose import compose
    from sim import sim_verify

    recipe = parse_recipe(open(src).read())
    # resume: a prior slice's best.pkl is a verified build, so continue the
    # climb from it instead of re-rolling the seed (compose is not
    # deterministic run to run, and re-rolling would throw away progress).
    import pickle as _pk
    _resume = os.path.join(workdir, 'best.pkl')
    blocks, size, io = None, None, None
    try:
        with open(_resume, 'rb') as _f:
            _r = _pk.load(_f)
        if _r.get('recipe') == open(src).read():
            from sim import sim_verify as _sv
            _sv(recipe, _r['blocks'], _r['io'], quiet=True)
            blocks, size, io = _r['blocks'], _r['size'], _r['io']
            print('resumed %d blocks, verified green' % len(blocks),
                  flush=True)
            log.write('resumed %d green\n' % len(blocks))
            log.flush()
    except Exception as _e:
        print('resume skipped (%s)' % str(_e)[:60], flush=True)
    t0 = time.monotonic()
    if blocks is None:
        blocks, size, io = compose(recipe)
        print('seed composed: %d blocks in %.1fs'
              % (len(blocks), time.monotonic() - t0), flush=True)
    n0 = len(blocks)
    # the seed must verify before a single deletion is attempted; a red
    # seed would let the hillclimb "improve" a broken build into a
    # smaller broken build and call it progress.
    sim_verify(recipe, blocks, io, quiet=True)
    print('seed verifies green', flush=True)
    log.write('seed %d blocks green\n' % n0)
    log.flush()

    import pickle
    _bestp = os.path.join(workdir, 'best.pkl')

    def _save_best():
        with open(_bestp, 'wb') as _f:
            pickle.dump({'recipe': open(src).read(), 'blocks': best,
                         'io': io, 'size': size}, _f)

    best, bestn = list(blocks), n0
    evals, accepted, skipped = 0, 0, 0
    improved = True
    t_start = time.monotonic()
    while improved and evals < max_evals and time.monotonic() < t_end:
        improved = False
        order = [b for b in best if _priority_key(b) >= 0]
        if focus != 'all':
            # focused slice: only this material, so the tier is swept
            # exhaustively (accepts still restart the scan, now within
            # the tier). Unknown focus = fail loud, never silently 'all'.
            assert focus in PRIORITY, 'bad focus %r' % focus
            order = [b for b in order if _base(b[3]) == focus]
        # seeded shuffle within each priority tier (deterministic, and a
        # second seed replays a different order, not a different build).
        tiers = {}
        for b in order:
            tiers.setdefault(_priority_key(b), []).append(b)
        for t in tiers.values():
            rng.shuffle(t)
        bmap = {c[:3]: c[3] for c in best}
        for tier in sorted(tiers):
            for b in tiers[tier]:
                if evals >= max_evals or time.monotonic() > t_end:
                    break
                # support screen: the sim cannot judge structural support,
                # so load-bearing solids are skipped statically (no eval).
                if (_base(b[3]) in ('minecraft:stone',
                                    'minecraft:cobblestone')
                        and _load_bearing(bmap, b[:3])):
                    skipped += 1
                    continue
                cand = [c for c in best if c[:3] != b[:3]]
                if len(cand) == len(best):
                    continue  # duplicate coordinate, never delete blind
                evals += 1
                try:
                    sim_verify(recipe, cand, io, quiet=True)
                except Exception:
                    continue
                best, bestn = cand, len(cand)
                accepted += 1
                improved = True
                _save_best()  # crash-safe: a killed run keeps every accept
                log.write('accept %d: -%s now %d\n' % (evals, b[3][:40],
                                                      bestn))
                log.flush()
                print('accept %d: removed %s -> %d blocks'
                      % (evals, b[3].split('[')[0].split(':')[1], bestn),
                      flush=True)
                break
            if improved:
                break
        # heartbeat: visible life even through long dry spells (the run
        # that looked stuck was fine; the pipe was buffering, but a
        # quiet loop still reads as dead to a human watching)
        _el = time.monotonic() - t_start
        print('... evals=%d blocks=%d accepted=%d skipped=%d elapsed=%.0fs'
              ' (%.1f evals/s)'
              % (evals, bestn, accepted, skipped, _el,
                 evals / _el if _el > 0 else 0.0), flush=True)
        log.write('pass done evals=%d blocks=%d\n' % (evals, bestn))
        log.flush()
    print('done: %d -> %d blocks (%d accepted / %d evals)'
          % (n0, bestn, accepted, evals), flush=True)
    log.write('done %d -> %d accepted=%d evals=%d\n'
              % (n0, bestn, accepted, evals))
    log.flush()

    import pickle
    with open(os.path.join(workdir, 'best.pkl'), 'wb') as f:
        pickle.dump({'recipe': open(src).read(), 'blocks': best,
                     'io': io, 'size': size}, f)
    if bestn < n0:
        from export import export_mcfunction, export_schem, export_html
        export_mcfunction(best, os.path.join(workdir,
                                             'build_compact.mcfunction'))
        export_schem(best, os.path.join(workdir, 'build_compact.schem'))
        export_html(best, size, os.path.join(workdir, 'build_compact.html'),
                    'add2 compacted %d -> %d' % (n0, bestn))
        print('exported build_compact.*', flush=True)


if __name__ == '__main__':
    main()
