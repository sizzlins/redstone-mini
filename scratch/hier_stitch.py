"""Merge cached hier bands, stitch, and verify — seconds, no band recompose.

Usage: python scratch/hier_stitch.py <bands.pkl> <recipe.txt>
Uses compose.compose_hier's merge/stitch stage on the cached partition
state, so stitch iteration costs seconds (not the 30 min a full hier run
takes). Hard-bounded: only lwire/astar run here, on an already-valid field.
"""
import os, sys, pickle, time
import multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import compose as C
from compose import _strip_buffers, expand_gates, compose_hier
from recipe import parse_recipe
from sim import sim_verify


def main():
    pkl, src = sys.argv[1], sys.argv[2]
    log = open(os.path.join(os.path.dirname(pkl), "stitch.log"), "a",
               buffering=1)
    log.write(f"--- {time.strftime('%H:%M:%S')} {pkl} {src}\n")
    d = pickle.load(open(pkl, "rb"))
    log.write(f"bands loaded: {[e['b'] for e in d['bands']]}\n")
    # ponytail: refuse a stale band cache LOUD. Bands composed under an
    # older engine route differently; the merge would still sim-gate, but
    # the failure would read as a stitch wall instead of what it is (see
    # hier_bands._engine_fp). Re-climb with hier_bands.py.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from hier_bands import _engine_fp
    except ImportError:
        _engine_fp = None
    if _engine_fp is not None and d.get("__fp__") != _engine_fp():
        print(f"STITCH RED: band cache {pkl} built under engine "
              f"{d.get('__fp__')} (now {_engine_fp()}); re-run "
              f"hier_bands.py", flush=True)
        sys.exit(1)
    r = parse_recipe(open(src).read())
    gates = _strip_buffers(expand_gates(r["gates"], r["inputs"]), r["outputs"])
    log.write("recipe parsed\n")
    built = []
    for e in d["bands"]:
        built.append((e["b"], e["sub"], e["out"], C._hier_ctx(e["ctx"]),
                      e["shift"]))
    log.write("spawning stitch child\n")
    log.close()
    # Rule 7: the stitch stage runs lwire/astar with no internal clock, so
    # bound astar and run the whole thing in a killable child. (A chained
    # fan-out once ran >3 min with no output.)
    # ponytail: the child takes PATHS, not objects. Passing `built` (6 bands
    # of full field state, ~100k cells) through the spawn pipe cost minutes
    # before a single stitch ran — and every print below flushes, because a
    # wrapper kill eats buffered output and the evidence with it.
    os.environ.setdefault("REDSTONE_ASTAR_CAP", "20000")
    secs = float(sys.argv[3]) if len(sys.argv) > 3 else 90.0
    parent, child = mp.Pipe(duplex=False)
    p = mp.Process(target=_stitch_child, args=(child, pkl, src), daemon=False)
    p.start()
    child.close()
    got = None
    if parent.poll(secs):
        try:
            got = parent.recv()
        except EOFError:
            got = None
    p.join(2)
    if p.is_alive():
        p.terminate()
        p.join(3)
        if p.is_alive():
            p.kill()
            p.join(3)
        print(f"STITCH killed at {secs:g}s", flush=True)
        sys.exit(1)
    parent.close()
    if got is None or got[0] == "err":
        print("STITCH RED:", (got[1] if got else "child died")[:300], flush=True)
        sys.exit(1)
    out = got[1]
    print(f"MERGE {len(out[0])} blocks {out[1]}", flush=True)
    # ponytail: optional 4th arg saves the merge. The bands pkl is an INPUT to
    # this stage, so a red smoke still needs the stitched build on disk for
    # forensics (and verify_par reads a pkl, not stdout). argv[3] stays the
    # stitch timeout.
    if len(sys.argv) > 4:
        with open(sys.argv[4], "wb") as f:
            pickle.dump({"blocks": out[0], "io": out[2], "size": out[1]}, f,
                        protocol=4)
        print(f"saved {sys.argv[4]}", flush=True)
    # ponytail: smoke (4 vectors) here, full verify in verify_par. A full
    # sim_verify is 1024 silent vectors (~25 min) — that silence is what kept
    # reading as a hang. Smoke answers settle-vs-churn in seconds.
    from sim import _run_vec, _parse_build, _latch_hold_seed
    import recipe as R
    pst = _parse_build(out[0], out[2])
    hold = _latch_hold_seed(out[0], out[2])
    n = len(r["inputs"])
    for bits in ([0] * n, [1] * n, [i % 2 for i in range(n)],
                 [1 - i % 2 for i in range(n)]):
        vec = dict(zip(r["inputs"], bits))
        try:
            gotv = _run_vec(vec, hold, pst)[0]
        except RuntimeError as e:
            print(f"SMOKE {''.join(map(str, bits))} RED {str(e)[:120]}",
                  flush=True)
            sys.exit(1)
        want = R.eval_net(r, vec)
        bad = [o for o in r["outputs"]
               if bool(gotv.get(o, False)) != bool(want.get(o, False))]
        print(f"SMOKE {''.join(map(str, bits))} "
              f"{'OK' if not bad else f'MISMATCH {bad}'}", flush=True)
        if bad:
            sys.exit(1)


def _stitch_child(conn, pkl, src):
    try:
        dd = pickle.load(open(pkl, "rb"))
        rr = parse_recipe(open(src).read())
        gg = _strip_buffers(expand_gates(rr["gates"], rr["inputs"]), rr["outputs"])
        bb = [(e["b"], e["sub"], e["out"], C._hier_ctx(e["ctx"]), e["shift"])
              for e in dd["bands"]]
        conn.send(("ok", C.compose_hier_parts(bb, gg, rr)))
    except RuntimeError as e:
        conn.send(("err", str(e)))
    except Exception as e:
        conn.send(("err", f"{type(e).__name__}: {e}"))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
