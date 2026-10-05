"""Dump one dust cell's physics tables from BOTH engines, side by side.

NEVER HANGS: one build, one cell, both table sets built once. Usage:

    python scratch/dump_cell.py <x> <y> <z> [build.pkl] [recipe.txt]

When the int-index rewrite diverges from the tuple engine, the answer is
always in the tables for the first cell that differs -- not in the ring loop,
which is why this prints them side by side instead of asking the engines to
explain themselves.
"""
import os
import sys
import pickle

sys.path.insert(0, r"D:\redstone-mini")
sys.path.insert(0, r"D:\redstone-mini\scratch")
os.environ.pop("REDSTONE_SIM_GATE", None)
import sim                      # noqa: E402
import simvec                   # noqa: E402
import simvec_old               # noqa: E402
from recipe import parse_recipe  # noqa: E402


def old_view(st, c, P):
    pwr, lever = P[4], P[6]
    if c in st["c_dust"] or c in pwr:
        return {
            "role": "pwr",
            "c_dust": list(st["c_dust"].get(c, ())),
            "c_rep": list(st["c_rep"].get(c, ())),
            "c_torch": list(st["c_torch"].get(c, ())),
            "c_lev": list(st["c_lev"].get(c, ())),
            "c_rblk": st["c_rblk"].get(c),
            "c_up": st["c_up"].get(c),
        }
    d = st["d_dirs"].get(c)
    return {
        "role": "dust",
        "d_below": st["d_below"].get(c),
        "dirs": [(m, code, payload, cup, cdn) for m, code, payload, cup, cdn
                 in (d or ())],
    }


def new_view(st, c):
    ids = st["cell"]
    cid = {x: i for i, x in enumerate(ids)}   # rebuilt; not in hot tables
    i = cid[c]
    if st["kind"][i] == 1:
        return {
            "role": "pwr",
            "c_dust": [ids[x] for x in st["c_dust"][i]],
            "c_rep": [ids[x] for x in st["c_rep"][i]],
            "c_torch": [ids[x] for x in st["c_torch"][i]],
            "c_lev": list(st["c_lev"][i]),
            "c_rblk": st["c_rblk"][i],
            "c_up": ids[st["c_up"][i]] if st["c_up"][i] >= 0 else None,
        }
    return {
        "role": "dust",
        "d_bt": ids[st["d_bt"][i]] if st["d_bt"][i] >= 0 else None,
        "d_bp": ids[st["d_bp"][i]] if st["d_bp"][i] >= 0 else None,
        "d_cob": [ids[x] for x in st["d_cob"][i]],
        "d_torch": [ids[x] for x in st["d_torch"][i]],
        "d_dust": [ids[x] for x in st["d_dust"][i]],
        "d_rep": [ids[x] for x in st["d_rep"][i]],
        "d_comp": [ids[x] for x in st["d_comp"][i]],
        "d_cup": [ids[x] for x in st["d_cup"][i]],
        "d_cdn": [ids[x] for x in st["d_cdn"][i]],
        "d_rblk": st["d_rblk"][i],
        "d_lev": list(st["d_lev"][i]),
        "wake": [ids[x] for x in st["wake"][i]],
    }


def main():
    x, y, z = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    dp = sys.argv[4] if len(sys.argv) > 4 else r"D:\redstone-mini\scratch\alu1merge.pkl"
    rp = sys.argv[5] if len(sys.argv) > 5 else r"D:\redstone-mini\recipes\alu1.txt"
    c = (x, y, z)
    d = pickle.load(open(dp, "rb"))
    P = sim._parse_build(d["blocks"], d["io"])
    told = simvec_old._tables_from(P, {})
    tnew = simvec._tables_from(P, {})
    orth = ((x + 1, y, z), (x - 1, y, z), (x, y, z + 1), (x, y, z - 1))

    print(f"cell {c}   dust={c in told['dust']} pwr={c in told['pwr']} "
          f"rep={c in told['rep']} torch={c in told['torch']}")
    print("\n--- OLD ---")
    for k, v in old_view(told, c, P).items():
        print(f"  {k}: {v}")
    print("\n--- NEW ---")
    for k, v in new_view(tnew, c).items():
        print(f"  {k}: {v}")

    print("\n--- neighbourhood roles (from P, the authority parse) ---")
    for m in orth + ((x, y - 1, z), (x, y + 1, z)):
        roles = [n for n, s in (("dust", P[0]), ("torch", P[1]), ("rep", P[2]),
                                 ("rblk", P[3]), ("pwr", told["pwr"]),
                                 ("lever", P[6]), ("comp", P[9]),
                                 ("glass", P[11]), ("slab", P[12]))
                 if m in s]
        print(f"  {m}: {roles or ['-']}"
              + (f"  lever={P[6][m]!r}" if m in P[6] else "")
              + (f"  rep={P[2][m]}" if m in P[2] else ""))


if __name__ == "__main__":
    main()