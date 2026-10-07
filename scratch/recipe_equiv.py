"""Prove two recipes compute the same function on all input vectors.

Usage: python scratch/recipe_equiv.py <old.txt> <new.txt>
O(2^n) evals, no placement. Exits nonzero on first mismatch.
"""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from recipe import eval_net, parse_recipe

old = parse_recipe(open(sys.argv[1]).read())
new = parse_recipe(open(sys.argv[2]).read())
assert old["inputs"] == new["inputs"], "input mismatch"
assert old["outputs"] == new["outputs"], "output mismatch"
ins, outs = old["inputs"], old["outputs"]
bad = 0
for vals in itertools.product([0, 1], repeat=len(ins)):
    env = dict(zip(ins, vals))
    go, gn = eval_net(old, env), eval_net(new, env)
    for o in outs:
        if bool(go[o]) != bool(gn[o]):
            bad += 1
            print(f"MISMATCH {o} {env} old={go[o]} new={gn[o]}")
            break
print(f"{sys.argv[1]} vs {sys.argv[2]}: {2 ** len(ins)} vectors, "
      f"{'EQUIVALENT' if not bad else str(bad) + ' DIFFER'}")
sys.exit(1 if bad else 0)
