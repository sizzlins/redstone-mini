"""Debug instrument: timed single-shot layouts + state dumps + map views.

Usage:
  python debug.py <recipefile> [seed] [grow] [x0,z0,x1,z1 | net <name>]

Runs ONE layout (no retry swallowing, loud error), writes the planning
frame (gates, netspec, plan, tile-only field) to the temp dump, and prints
a compact summary. Replaces all ad-hoc Temp probes (dbg*.py, sweep*.py).
Test style matches the repo: assert-free print script run via python.
"""

import json
import os
import sys
import time

DUMP = r"C:\Users\LOQ\AppData\Local\Temp\opencode\dbg_state.json"


def dump_state(path, gates, netspec, solid, wires, rings, W, D):
    """Planning-frame snapshot (called from layout.py, both paths)."""
    def ck(cell):
        return ",".join(map(str, cell))
    doc = {"W": W, "D": D, "gates": gates,
           "netspec": {n: {"drv": s.get("drv"), "loads": s.get("loads")}
                       for n, s in netspec.items()},
           "solid": {ck(c): v for c, v in solid.items()},
           "wires": {ck(c): v for c, v in wires.items()},
           "rings": {ck(c): sorted(v) for c, v in rings.items()}}
    json.dump(doc, open(path, "w"))


def show_map(doc, x0, z0, x1, z1):
    solid = {tuple(map(int, k.split(","))) for k in doc["solid"]}
    wires = {tuple(map(int, k.split(","))) for k in doc["wires"]}
    rings = {tuple(map(int, k.split(","))) for k in doc["rings"]}
    for z in range(z0, z1 + 1):
        row = []
        for x in range(x0, x1 + 1):
            if (x, z) in solid:
                row.append("S")
            elif (x, 1, z) in wires:
                row.append("w")
            elif (x, z) in rings:
                row.append("r")
            else:
                row.append(".")
        print(f"z={z:3d} " + "".join(row))


if __name__ == "__main__":
    sys.path.insert(0, r"D:\redstone-mini")
    from recipe import parse_recipe
    from layout import layout

    f = sys.argv[1]
    seed = None if len(sys.argv) < 3 or sys.argv[2] == "None" else int(sys.argv[2])
    grow = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 0
    rest = [a for a in sys.argv[2:] if not (a == "None" or a.isdigit())]
    r = parse_recipe(open(f).read())
    os.environ["REDSTONE_DEBUG"] = DUMP
    if os.path.exists(DUMP):
        os.remove(DUMP)
    t0 = time.time()
    ok = True
    err = ""
    try:
        blocks, size, io = layout(r, seed=seed, grow=grow)
        dt = time.time() - t0
        print(f"ok blocks={len(blocks)} size={size} t={dt:.1f}s")
    except RuntimeError as e:
        ok = False
        err = str(e)
        dt = time.time() - t0
        print(f"FAIL t={dt:.1f}s: {err[:400]}")
    if not os.path.exists(DUMP):
        print("(no dump: failed before planning)")
        sys.exit(1)
    doc = json.load(open(DUMP))
    print(f"gates={len(doc['gates'])} nets={len(doc['netspec'])} field={doc['W']}x{doc['D']}")
    for g in doc["gates"]:
        print(f"  band={g.get('band')} {g['op']} {g['out']} {g['args']}")
    if rest and rest[0] == "net":
        n = rest[1]
        print("NET", n, doc["netspec"].get(n))
    elif rest:
        x0, z0, x1, z1 = map(int, rest[0].split(","))
        show_map(doc, x0, z0, x1, z1)
    elif not ok:
        import re as _re
        m = _re.search(r"for (\S+?)(?:\s|$|hub=|:)", err)
        if m and m.group(1) in doc["netspec"]:
            print("NET", m.group(1), doc["netspec"][m.group(1)])
    sys.exit(0 if ok else 1)
