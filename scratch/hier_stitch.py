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


def _apply_bank_pin(src):
    """Lever-bank pitch pin, same `<recipe>.bank` sibling hier_bands reads.

    The bank is laid during the MERGE, not per band, so hier_bands setting the
    env is not enough -- this is a separate process and needs its own read.
    Without this the pin prints, takes effect nowhere, and the build comes out
    at the default pitch looking like the pin silently failed.
    """
    import os as _os
    if _os.environ.get("REDSTONE_BANK_PITCH"):
        return None
    try:
        with open(_os.path.splitext(src)[0] + ".bank") as f:
            val = next((ln.strip() for ln in f
                        if ln.strip() and not ln.strip().startswith("#")), "")
    except OSError:
        return None
    if val:
        _os.environ["REDSTONE_BANK_PITCH"] = val.split()[0]
        print("BANK PITCH: %s (from %s.bank)"
              % (_os.environ["REDSTONE_BANK_PITCH"],
                 _os.path.basename(src)), flush=True)
    return None


def main():
    pkl, src = sys.argv[1], sys.argv[2]
    _apply_bank_pin(src)
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
    # ponytail: if this recipe declares a pending ins_target pillar swap, a
    # smoke MISMATCH is expected rather than fatal -- the swap has not run yet
    # and hier_verify.py runs it immediately after this stage, then verifies the
    # swapped build. Without this, hier_verify could never reach its own
    # ins_target step: the smoke lives HERE and hard-exited first, which is
    # exactly why the gate omitted the swap in the first place and why
    # `hier_verify.py recipes/alu4.txt` died at SMOKE 1010101010 while the
    # documented manual chain went 4/4. Only advisory when the sibling exists;
    # with no sibling the smoke stays exactly as strict as it was.
    _adj = os.path.splitext(sys.argv[2])[0] + ".ins_target" if len(
        sys.argv) > 2 else ""
    advisory = bool(_adj) and os.path.exists(_adj)
    pst = _parse_build(out[0], out[2])
    hold = _latch_hold_seed(out[0], out[2])
    n = len(r["inputs"])
    smoke_bad = []
    for bits in ([0] * n, [1] * n, [i % 2 for i in range(n)],
                 [1 - i % 2 for i in range(n)]):
        vec = dict(zip(r["inputs"], bits))
        try:
            gotv = _run_vec(vec, hold, pst)[0]
        except RuntimeError as e:
            print(f"SMOKE {''.join(map(str, bits))} RED {str(e)[:120]}",
                  flush=True)
            if advisory:
                print("  (advisory: %s pending -- not failing here)"
                      % os.path.basename(_adj), flush=True)
                continue
            sys.exit(1)
        want = R.eval_net(r, vec)
        bad = [o for o in r["outputs"]
               if bool(gotv.get(o, False)) != bool(want.get(o, False))]
        print(f"SMOKE {''.join(map(str, bits))} "
              f"{'OK' if not bad else f'MISMATCH {bad}'}", flush=True)
        if bad:
            if advisory:
                smoke_bad.append((''.join(map(str, bits)), bad))
                continue
            sys.exit(1)
    if smoke_bad:
        print("SMOKE: %d vector(s) red pre-swap, %s pending -- the gate will "
              "apply it and verify the corrected build."
              % (len(smoke_bad), os.path.basename(_adj)), flush=True)


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
