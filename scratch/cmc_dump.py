"""Bridge: banked build (pkl + recipe) -> JSON for the cmc harness.

Usage: python scratch/cmc_dump.py <recipe.txt> <build.pkl> <out.json>
  [--max-vectors N]
Writes {blocks:[[x,y,z,bid]...], levers:{x,z:name}, lamps:{...},
vectors:[{...}], expected:[{net:bool}]}. Truth table exhaustive up to
64 vectors, else deterministic stride-sampled (noted in output).
"""
import itertools
import json
import pickle
import random
import sys

sys.path.insert(0, r'D:\redstone-mini')
from recipe import parse_recipe, eval_net


def main():
    args = sys.argv[1:]
    recipe_p, pkl_p, out_p = args[0], args[1], args[2]
    maxv = 64
    for i, a in enumerate(args):
        if a == '--max-vectors':
            maxv = int(args[i + 1])
    r = parse_recipe(open(recipe_p).read())
    m = pickle.load(open(pkl_p, 'rb'))
    ins, outs = r['inputs'], r['outputs']
    combos = list(itertools.product([0, 1], repeat=len(ins)))
    sampled = False
    if len(combos) > maxv:
        step = len(combos) / maxv
        combos = [combos[int(i * step)] for i in range(maxv)]
        sampled = True
    vectors, expected = [], []
    for vals in combos:
        env = dict(zip(ins, vals))
        gout = eval_net(r, env)
        vectors.append(env)
        expected.append({o: bool(gout[o]) for o in outs})
    io = m['io']
    doc = {
        'blocks': [[int(x), int(y), int(z), b]
                   for (x, y, z, b) in m['blocks']],
        'levers': [['%d,%d' % k, v] for k, v in io['levers'].items()],
        'lamps': [['%d,%d' % k, v] for k, v in io['lamps'].items()],
        'vectors': vectors,
        'expected': expected,
        'sampled': sampled,
        'n_inputs': len(ins),
    }
    json.dump(doc, open(out_p, 'w'))
    print('dumped %d blocks, %d vectors%s -> %s'
          % (len(doc['blocks']), len(vectors),
             ' (SAMPLED)' if sampled else '', out_p))


if __name__ == '__main__':
    main()
