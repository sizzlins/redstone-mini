"""Warm-start differential probe: does starting from the previous vector's final state cut work?

NEVER HANGS: fixed vector count (default 8), engine caps forced, no pool, no
compose, in-process. Compares lamps/live/torch/rep/comp cold-vs-warm (ticks
allowed to differ -- warm changes the path, lamps must not). Prints speedup
and lamp agreement; exit 1 on lamp divergence, exit 0 otherwise.

Usage: python scratch/warm_proto.py [nvec]
"""
import os
import sys
import time
import pickle

sys.path.insert(0, r"D:\redstone-mini")
sys.path.insert(0, r"D:\redstone-mini\scratch")
os.environ.pop("REDSTONE_SIM_GATE", None)
os.environ["REDSTONE_SIM_TICKS"] = "20000"
os.environ["REDSTONE_SIM_STEPS"] = "2000000"
import sim  # noqa: E402
import simvec  # noqa: E402
from recipe import parse_recipe  # noqa: E402


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    n = max(1, min(n, 32))
    dp = r"D:\redstone-mini\scratch\alu4merge_g.pkl"
    rp = r"D:\redstone-mini\recipes\alu4.txt"
    r = parse_recipe(open(rp).read())
    ins = r["inputs"]
    d = pickle.load(open(dp, "rb"))
    P = sim._parse_build(d["blocks"], d["io"])
    ctx = P
    span = 2 ** len(ins)
    idxs = [round(k * (span - 1) / max(1, n - 1)) for k in range(n)] if n > 1 else [0]
    tcold = twarm = 0.0
    bad = 0
    tickdiff = 0
    state = None
    for i in idxs:
        vec = {ins[j]: (i >> j) & 1 for j in range(len(ins))}
        if hasattr(sim, "_BOUT"):
            sim._BOUT.clear()
        t = time.monotonic()
        a = simvec.run_scalar(vec, ctx)
        tcold += time.monotonic() - t
        if hasattr(sim, "_BOUT"):
            sim._BOUT.clear()
        exp = {}
        t = time.monotonic()
        try:
            b = simvec.run_scalar(vec, ctx, _warm=state, _expose=exp)
        except Exception as e:  # noqa: BLE001 -- probe reports, never hangs
            print(f"vec{i:5d} WARM-RAISED {type(e).__name__}: {e}", flush=True)
            bad += 1
            state = None
            continue
        twarm += time.monotonic() - t
        # TRUE CHAIN: next warm starts from THIS warm final (drift risk measured here)
        state = exp
        lamp_ok = a[0] == b[0]
        rest_ok = a[1] == b[1] and a[2] == b[2] and a[4] == b[4] and a[5] == b[5]
        if a[3] != b[3]:
            tickdiff += 1
        if not lamp_ok or not rest_ok:
            print(f"vec{i:5d} DIVERGE lamps_ok={lamp_ok} rest_ok={rest_ok} "
                  f"ticks cold={a[3]} warm={b[3]}", flush=True)
            bad += 1
        else:
            print(f"vec{i:5d} ok lamps={sum(1 for v in a[0].values() if v)} "
                  f"ticks {a[3]}->{b[3]}", flush=True)
    print(f"\n{n} vectors: cold {tcold:.2f}s warm {twarm:.2f}s "
          f"speedup {tcold/max(1e-9, twarm):.2f}x divergences={bad} "
          f"tickdiffs={tickdiff}")
    if bad:
        print("WARM PROTO: DIVERGED")
        sys.exit(1)
    print("WARM PROTO: LAMPS-IDENTICAL")


if __name__ == "__main__":
    main()
