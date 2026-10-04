"""How much of the geometric `wake` map is actually needed?

NEVER HANGS: one build, tables built once, no simulation. Usage:

    python scratch/wake_need.py [build.pkl]

`wake` is geometric: every cell that CHANGES wakes all ~26 cells around it,
because the geometry is where a dependency could hide. But the physics only
reads a cell through a handful of NAMED relations (a dust cell reads adjacent
dust for decay, solids read adjacent dust, repeaters read one input, torches
read their attachment block...). So the precise reverse-dependency map is
probably much smaller.

If it is, filtering wake is the largest remaining win, because the event count
is proportional to the edge count. If it is NOT smaller, the geometric map is
already tight and the idea dies here, for the price of one script.

This also computes the exact set the filter MUST contain, which is what makes
the filter provable rather than hopeful: every forward reference in every table
implies a reverse edge.
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
    ids = st["cell"]
    cid = st["cid"]

    need = [set() for _ in range(nid)]

    def dep(target, reader):
        if target >= 0:
            need[target].add(reader)

    # ---- what DUST reads -------------------------------------------------
    for i in range(nid):
        if st["kind"][i] != 0:
            continue
        for m in st["d_dust"][i]:
            dep(m, i)
        for m in st["d_cup"][i]:
            dep(m, i)
        for m in st["d_cdn"][i]:
            dep(m, i)
        for m in st["d_comp"][i]:
            dep(m, i)
        for m in st["d_cob"][i]:       # reads the solid's pbs
            dep(m, i)
        for m in st["d_torch"][i]:     # reads the torch's tl
            dep(m, i)
        for m in st["d_rep"][i]:       # reads the repeater's ron
            dep(m, i)
        dep(st["d_bt"][i], i)          # reads the torch below
        dep(st["d_bp"][i], i)          # reads the solid below

    # ---- what SOLIDS read ------------------------------------------------
    for i in range(nid):
        if st["kind"][i] != 1:
            continue
        for m in st["c_dust"][i]:
            dep(m, i)
        for m in st["c_torch"][i]:
            dep(m, i)
        for m in st["c_rep"][i]:
            dep(m, i)
        dep(st["c_up"][i], i)

    # ---- repeaters and comparators read ONE input -----------------------
    for i in range(nid):
        k = st["kind"][i]
        if k == 4:
            for spec in (st["r_src"][i], st["r_side"][i][0], st["r_side"][i][1]):
                if spec is not None and spec[0] != 2:
                    dep(spec[1], i)
        elif k == 6:
            for spec in (st["k_rear"][i], st["k_side"][i][0],
                         st["k_side"][i][1]):
                if spec is not None and spec[0] != 2:
                    dep(spec[1], i)
        elif k == 2:
            dep(st["t_att"][i], i)      # the torch reads its attachment block

    # ---- compare --------------------------------------------------------
    geo = 0
    prec = 0
    missing = 0
    extra = 0
    sample = []
    for i in range(nid):
        g = st["wake"][i]
        geo += len(g)
        prec += len(need[i])
        gs = set(g)
        ns = need[i]
        # every PRECISE edge must be present in the geometric map, or the
        # geometric map is already wrong somewhere
        for t in ns:
            if t not in gs:
                missing += 1
                if len(sample) < 6:
                    sample.append((ids[i], ids[t], "precise edge absent"))
        extra += len(gs - ns)
    print(f"{os.path.basename(dp)}: cells={nid}")
    print(f"  geometric wake edges : {geo}")
    print(f"  precise dependencies : {prec}")
    if geo:
        print(f"  ratio                : {prec / geo:.3f}"
              f"   -> a perfect filter would cut events by "
              f"{100 * (1 - prec / geo):.1f}%")
    print(f"  precise edges ABSENT from geometric map: {missing}"
          f"   (0 means the geometric map already contains every dependency)")
    print(f"  geometric edges with no dependency    : {extra}")
    for s in sample:
        print(f"    {s}")


if __name__ == "__main__":
    main()