import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from compose import compose
from recipe import parse_recipe
from sim import sim_verify
def main():
    for f in ['recipes/example_and.txt', 'recipes/example_2gates.txt',
              'recipes/latch_sr.txt', 'recipes/example_xor.txt']:
        r = parse_recipe(open(f).read())
        out, size, io = compose(r)
        sim_verify(r, out, io, quiet=True)
        print(f, 'green', len(out), 'blocks')


# ponytail: main guard, defence in depth. sim_verify no longer fans out from
# inside a worker (see sim.py), but an unguarded script that reaches a spawn
# path re-imports itself under spawn, and this file is a plain top-level loop.
if __name__ == "__main__":
    main()
