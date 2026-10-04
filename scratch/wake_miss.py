"""Which edges did the exact-wake filter drop that were actually NEEDED?

NEVER HANGS: one build, two table sets (REDSTONE_WAKE_EXACT 0 and 1), no
simulation. Usage:

    python scratch/wake_miss.py [build.pkl]

The filter is a strict subset of the geometric map, so every dropped edge is a
cell with no NAMED relation to the change -- unless the enumeration in
simvec._tables_from missed a relation. This finds that by GENERICALLY scanning
every table for the dropped target, rather than hand-listing the relations a
second time (which is the mistake that hid the bug the first time).

Keys that hold ints which are NOT cell ids are excluded explicitly, and t_att
is only meaningful on a torch (it defaults to 0 elsewhere, and 0 is a valid id).
"""
import os
import sys
import pickle

sys.path.insert(0, r"D:\redstone-mini")
os.environ.pop("REDSTONE_SIM_GATE", None)
import sim                      # noqa: E402
import simvec                   # noqa: E402

# tables whose ints are cell ids (all of these except the exclusions)
EXCLUDE = {"r_delay", "ncells", "nid", "kind", "cell", "cid", "inp",
           "dust_ids", "pwr_ids", "torch_ids", "rep_ids", "comp_ids"}


def build(dp, exact):
    os.environ["REDSTONE_WAKE_EXACT"] = "1" if exact else "0"
    simvec._TBL.clear()
    d = pickle.load(open(dp, "rb"))
    P = sim._parse_build(d["blocks"], d["io"])
    return simvec._tables(P)


def ints_in(v, out):
    """Every int in a (possibly nested) table value."""
    if isinstance(v, bool):
        return
    if isinstance(v, int):
        out.add(v)
    elif isinstance(v, (tuple, list, set, frozenset)):
        for x in v:
            ints_in(x, out)


def main():
    dp = sys.argv[1] if len(sys.argv) > 1 else r"D:\redstone-mini\scratch\alu1merge.pkl"
    geo = build(dp, False)
    exc = build(dp, True)
    ids = exc["cell"]
    nid = exc["nid"]
    keys = [k for k in exc
            if k not in EXCLUDE and isinstance(exc[k], list)
            and len(exc[k]) == nid]

    dropped = 0
    bad = 0
    for i in range(nid):
        g = geo["wake"][i]
        e = exc["wake"][i]
        if len(g) == len(e):
            continue
        es = set(e)
        gone = [m for m in g if m not in es]
        dropped += len(gone)
        if not gone:
            continue
        # everything cell i's tables name, generically
        named = set()
        for k in keys:
            v = exc[k][i]
            if v is None:
                continue
            if k == "t_att" and exc["kind"][i] != 2:
                continue                    # meaningless off a torch
            ints_in(v, named)
        named.discard(-1)
        for m in gone:
            if m in named:
                bad += 1
                hits = [k for k in keys
                        if (exc[k][i] is not None
                            and (k != "t_att" or exc["kind"][i] == 2)
                            and m in (ints if False else _flat(exc[k][i])))]
                print(f"  NEEDED but dropped: reader {ids[i]} "
                      f"kind={exc['kind'][i]} target {ids[m]} via {hits}")
    print(f"\nedges dropped: {dropped}   of which NEEDED: {bad}")
    print("MISSED RELATIONS" if bad else "filter is clean (generic scan agrees)")


def _flat(v):
    out = set()
    ints_in(v, out)
    return out


if __name__ == "__main__":
    main()