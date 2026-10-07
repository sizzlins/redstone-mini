"""Check a recipe's arithmetic against a reference model, no placement.

Usage: python scratch/recipe_check.py <recipe.txt> <expr> [more...]
  <expr> is a Python expression over the recipe's IN names returning
  a dict of the recipe's OUT names.

Exits nonzero on the first mismatch so it can gate a commit.
"""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from recipe import eval_net, parse_recipe

name = sys.argv[1]
r = parse_recipe(open(name).read())
ins = list(r["inputs"])
outs = list(r["outputs"])
exprs = sys.argv[2:]

bad = 0
for vals in itertools.product([0, 1], repeat=len(ins)):
    env = dict(zip(ins, vals))
    got = eval_net(r, env)
    for e in exprs:
        want = eval(e, {}, dict(env))
        for o in outs:
            g = 1 if got[o] else 0
            w = 1 if want[o] else 0
            if g != w:
                bad += 1
                print(f"MISMATCH {o} {env} got={g} want={w}  ({e})")
                break
print(f"{name}: {2 ** len(ins)} vectors, {len(exprs)} model(s), "
      f"{'OK' if not bad else str(bad) + ' BAD'}")
sys.exit(1 if bad else 0)
