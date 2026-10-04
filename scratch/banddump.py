"""Write hier band sub-recipes to disk, one file per band (so probes like
portwall.py can run against a single band).

Usage: python scratch/banddump.py <recipe.txt> <outdir> [band ...]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from recipe import parse_recipe, expand_gates
from compose import _strip_buffers


def bands(src):
    r = parse_recipe(open(src).read())
    gates = _strip_buffers(expand_gates(r["gates"], r["inputs"]), r["outputs"])
    prod = {}
    for g in gates:
        prod[g["out"]] = g.get("band", 0)
    out = {}
    for b in sorted({g.get("band", 0) for g in gates}):
        bg = [g for g in gates if g.get("band", 0) == b]
        need = set()
        for g in bg:
            for a in g["args"]:
                if a in ("0", "1"):
                    continue
                if a in r["inputs"] or prod.get(a, b) != b:
                    need.add(a)
        bd = sorted(x for x in need if x not in r["inputs"])
        sub = {"inputs": [x for x in r["inputs"] if x in need] + bd,
               "outputs": sorted(g["out"] for g in bg if g["out"] in r["outputs"]),
               "gates": [{k: v for k, v in g.items() if k != "band"} for g in bg],
               "edge": {n: ("W" if prod.get(n, b) < b else "E") for n in bd},
               "_band": b}
        out[b] = sub
    return r, out


def text(sub):
    L = []
    if sub.get("edge"):
        for n, e in sorted(sub["edge"].items()):
            L.append(f"EDGE {n} {e}")
    L.append("IN " + ", ".join(sub["inputs"]))
    L.append("OUT " + ", ".join(sub["outputs"]))
    for g in sub["gates"]:
        a = list(g["args"])
        L.append(f"{g['out']} = {g['op']} {a[0]}" if g["op"] == "NOT"
                 else f"{g['out']} = {a[0]} {g['op']} {a[1]}")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    src, outdir = sys.argv[1], sys.argv[2]
    want = [int(x) for x in sys.argv[3:]] or None
    import os as _o
    pre = _o.path.basename(src).replace(".txt", "b")
    r, bs = bands(src)
    for b, sub in bs.items():
        if want and b not in want:
            continue
        p = os.path.join(outdir, f"{pre}{b}.txt")
        open(p, "w").write(text(sub))
        print(f"band {b}: {len(sub['gates'])} gates, {len(sub['inputs'])} inputs "
              f"-> {p}")
        print("   " + text(sub).replace("\n", "\n   "))