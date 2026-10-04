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
    # `wake[i]` is the cells to re-evaluate when cell i CHANGES, so i is the
    # TARGET and m is the READER. The question is therefore "does the READER m
    # reference the TARGET i?", NOT "does i reference m" -- asking it the
    # other way round is the exact inversion that cost the engine a debugging
    # session, and it reports confident nonsense here.
    for i in range(nid):
        g = geo["wake"][i]
        e = exc["wake"][i]
        # the exact map stores boolean-only edges NEGATED (~m) so the list keeps
        # its order whether or not suppression is on; normalise before comparing
        es = {m if m >= 0 else ~m for m in e}
        gone = [m for m in g if m not in es]
        if not gone:
            continue
        dropped += len(gone)
        for m in gone:
            if i in readers(exc, m):          # reader m reads target i
                bad += 1
                if bad <= 12:
                    print(f"  NEEDED but dropped: target {ids[i]} "
                          f"kind={exc['kind'][i]} reader {ids[m]} "
                          f"kind={exc['kind'][m]} via {named_by(exc, m, i)}")
    print(f"\nedges dropped: {dropped}   of which NEEDED: {bad}")
    print("MISSED RELATIONS" if bad else "filter is clean (generic scan agrees)")


def _flat(v):
    out = set()
    ints_in(v, out)
    return out


def readers(st, i):
    """Every cell id that cell i's tables REFERENCE (i.e. i reads).

    Generic over the table set rather than hand-listed, because hand-listing is
    how the original bug stayed hidden.
    """
    out = set()
    for k, v in st.items():
        if k in EXCLUDE or not isinstance(v, list) or len(v) != st["nid"]:
            continue
        if k == "t_att" and st["kind"][i] != 2:
            continue                      # meaningless off a torch
        if k == "wake":
            continue                      # edges, not reads
        val = v[i]
        if val is None:
            continue
        ints_in(val, out)
    out.discard(-1)
    return out


if __name__ == "__main__":
    main()