"""Split the exact wake edges into LEVEL readers and BOOLEAN readers.

NEVER HANGS: one build, tables once, no simulation. Usage:

    python scratch/wake_split.py [build.pkl]

Most of what a changed cell wakes does not care HOW MUCH it changed:

- LEVEL readers want the exact 0..15: dust reading adjacent dust (decay),
  the cup/cdn slopes, and a comparator's output.
- BOOLEAN readers only test truthiness: a solid tests `pw >= 1` on adjacent
  dust, dust tests `pbs`/`tl`/`ron` truthily, a torch tests its attachment's
  `pb`, repeaters and comparators test their one input truthily.

So for a boolean edge, waking on 15 -> 14 is wasted work: the reader's answer
cannot change. If a dust cell's changes are mostly NOT truthiness crossings,
this split removes a large fraction of the ring events. This script measures
the ceiling BEFORE anyone builds it.
"""
import os
import sys
import pickle

sys.path.insert(0, r"D:\redstone-mini")
os.environ.pop("REDSTONE_SIM_GATE", None)
import sim          # noqa: E402
import simvec       # noqa: E402

BUILD = {"alu4": r"D:\redstone-mini\scratch\alu4merge_g.pkl",
         "alu1": r"D:\redstone-mini\scratch\alu1merge.pkl"}


def main():
    key = sys.argv[1] if len(sys.argv) > 1 else "alu4"
    dp = BUILD.get(key, key)
    d = pickle.load(open(dp, "rb"))
    P = sim._parse_build(d["blocks"], d["io"])
    st = simvec._tables(P)
    nid = st["nid"]
    kind = st["kind"]

    lvl = [0] * nid        # reader wants the level
    boo = [0] * nid        # reader only wants truthiness
    dust_ids = st["dust_ids"]

    def bump(t, r, level):
        if t < 0:
            return
        if level:
            lvl[t] += 1
        else:
            boo[t] += 1

    for i in range(nid):
        k = kind[i]
        if k == 0:
            for m in st["d_dust"][i]:
                bump(m, i, True)
            for m in st["d_cup"][i]:
                bump(m, i, True)
            for m in st["d_cdn"][i]:
                bump(m, i, True)
            for m in st["d_comp"][i]:
                bump(m, i, True)
            for m in st["d_cob"][i]:
                bump(m, i, False)
            for m in st["d_torch"][i]:
                bump(m, i, False)
            for m in st["d_rep"][i]:
                bump(m, i, False)
            bump(st["d_bt"][i], i, False)
            bump(st["d_bp"][i], i, False)
        elif k == 1:
            for m in st["c_dust"][i]:
                bump(m, i, False)
            for m in st["c_torch"][i]:
                bump(m, i, False)
            for m in st["c_rep"][i]:
                bump(m, i, False)
            bump(st["c_up"][i], i, False)
        elif k == 4:
            sp = st["r_src"][i]
            if sp is not None and sp[0] != 2:
                bump(sp[1], i, False)
            s0, s1 = st["r_side"][i]
            if s0 is not None and s0[0] != 2:
                bump(s0[1], i, False)
            if s1 is not None and s1[0] != 2:
                bump(s1[1], i, False)
        elif k == 6:
            sp = st["k_rear"][i]
            if sp is not None and sp[0] != 2:
                bump(sp[1], i, False)
            s0, s1 = st["k_side"][i]
            if s0 is not None and s0[0] != 2:
                bump(s0[1], i, False)
            if s1 is not None and s1[0] != 2:
                bump(s1[1], i, False)
        elif k == 2:
            bump(st["t_att"][i], i, False)

    # how many edges does the exact wake actually have, by category?
    wl = wb = 0
    for i in range(nid):
        for m in st["wake"][i]:
            pass
    tot_l = sum(lvl)
    tot_b = sum(boo)
    print(f"{os.path.basename(dp)}: cells={nid}")
    print(f"  edges wanting the LEVEL : {tot_l}")
    print(f"  edges wanting only TRUE : {tot_b}")
    if tot_l + tot_b:
        print(f"  boolean share           : {tot_b / (tot_l + tot_b):.3f}")
    print(f"  cells with any level edge : {sum(1 for x in lvl if x)}")
    print(f"  cells with any bool edge  : {sum(1 for x in boo if x)}")
    print(f"  dust cells               : {len(dust_ids)}")


if __name__ == "__main__":
    main()