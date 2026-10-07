"""Hash every green build's block list, so any layout drift is loud."""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from compose import compose
from recipe import parse_recipe

for n in ("recipes/example_and.txt", "recipes/example_2gates.txt",
          "recipes/latch_sr.txt", "recipes/example_xor.txt",
          "recipes/micro1.txt"):
    try:
        b, s, io = compose(parse_recipe(open(n).read()))
    except RuntimeError as e:
        print(f"{n:20} RED  {' '.join(str(e).split())[:80]}")
        continue
    h = hashlib.sha256(repr(sorted(b)).encode()).hexdigest()[:12]
    print(f"{n:20} {len(b):6d} blocks  {s}  {h}")
