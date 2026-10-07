"""Per-table heap breakdown for simvec's static tables. Bounded, __main__ guard.

Usage: python scratch/tbl_sizes.py [alu4|alu1|ctrl|<path>]

FINDING 2 measured 103 MB of tables for alu4 and 1.6 KiB per cell, but not
WHICH table. Rewriting the wrong one is how a session burns an hour, so this
walks the table set and deep-sizes every entry. The fix follows the number.
"""
import os
import sys
import pickle
from collections import deque

sys.path.insert(0, r"D:\redstone-mini")
os.environ.pop("REDSTONE_SIM_GATE", None)
import sim          # noqa: E402
import simvec       # noqa: E402

BUILDS = {
    "alu4": r"D:\redstone-mini\scratch\alu4merge_g.pkl",
    "alu1": r"D:\redstone-mini\scratch\alu1merge.pkl",
    "ctrl": r"D:\redstone-mini\scratch\ctrl_decode.pkl",
}
_SCALAR = (int, float, bool, type(None))


def deep(obj, seen=None):
    """Recursive sizeof, counting each container once."""
    if seen is None:
        seen = set()
    i = id(obj)
    if i in seen:
        return 0
    seen.add(i)
    n = sys.getsizeof(obj)
    if isinstance(obj, dict):
        for k, v in obj.items():
            n += deep(k, seen) + deep(v, seen)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for v in obj:
            n += deep(v, seen)
    return n


def main():
    key = sys.argv[1] if len(sys.argv) > 1 else "alu4"
    path = BUILDS.get(key, key)
    d = pickle.load(open(path, "rb"))
    st = simvec._tables_from(sim._parse_build(d["blocks"], d["io"]), {})

    rows = []
    for k, v in st.items():
        rows.append((deep(v), k, len(v) if hasattr(v, "__len__") else 1))
    rows.sort(reverse=True)
    total = sum(r[0] for r in rows)
    print(f"{os.path.basename(path)}  {len(d['blocks'])} blocks"
          f"   ncells={st['ncells']}")
    print(f"{'MB':>8}  {'entries':>9}  bytes/entry  key")
    for b, k, n in rows:
        print(f"{b/1048576:8.2f}  {n:9d}  {b/max(1,n):11.1f}  {k}")
    print(f"{total/1048576:8.2f}  TOTAL")

    # how much of the whole is (x,y,z) CELL TUPLES? they are the thing an
    # int-indexed rewrite deletes, and every table holds them as keys/values.
    seen = set()
    cells = 0
    for v in st.values():
        q = deque([v])
        while q:
            o = q.popleft()
            if isinstance(o, tuple) and len(o) == 3 and all(
                    isinstance(e, int) for e in o):
                if id(o) not in seen:
                    seen.add(id(o))
                    cells += sys.getsizeof(o)
                continue
            if isinstance(o, dict):
                q.extend(o.keys())
                q.extend(o.values())
            elif isinstance(o, (list, tuple, set, frozenset)):
                q.extend(o)
    print(f"\n3-tuple cell keys/values: {cells/1048576:.2f} MB "
          f"({cells*100//max(1,total)}% of the tables) in {len(seen)} objects")


if __name__ == "__main__":
    main()