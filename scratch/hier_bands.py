"""Compose all hier bands in parallel, hard-bounded, cache to disk.

Usage: python scratch/hier_bands.py <recipe.txt> <cacheprefix> [secs]
Launches one child per rung per band (parallel), hard-kills at `secs`,
keeps the first compose+sim-green rung per band, pickles the merged-ready
partition state to <cacheprefix>.pkl. Hang-safe by construction: every child
is joined with a timeout then terminated.

Output: one line per band with the winning rung and block count. Exit 0 iff
every band has a green rung (the cache then holds them all).
"""
import os, sys, time, pickle
import multiprocessing as mp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from recipe import parse_recipe, expand_gates
import compose as C
from compose import _strip_buffers
from sim import sim_verify


def run_rung(args):
    sub, force, secs = args
    parent, child = mp.Pipe(duplex=False)
    p = mp.Process(target=_work, args=(child, sub, force, CROSS, PROD), daemon=False)
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
        parent.close()
        return None, "timeout"
    parent.close()
    if got is None:
        return None, "no result"
    if got[0] == "ok":
        return got[1], None
    return None, got[1]


CROSS = []
PROD = {}


def _run_all(jobs, workers=12):
    """Fan every job out as a direct child, bounded, without mp.Pool.

    Pool workers are daemonic and cannot spawn the per-rung child (Windows
    asserts), so this owns the fan-out: a queue of pending jobs, a fixed set
    of live children, and a hard kill on overrun. Never waits unbounded —
    every child has a deadline and the loop exits when the queue drains or
    every slot is empty.
    """
    pending = list(jobs)
    live = []  # [proc, parent_conn, deadline, idx]
    out = [None] * len(jobs)
    while pending or live:
        while pending and len(live) < workers:
            idx, sub, force, secs = pending.pop(0)
            parent, child = mp.Pipe(duplex=False)
            p = mp.Process(target=_work, args=(child, sub, force, CROSS, PROD), daemon=False)
            p.start()
            child.close()
            live.append([p, parent, time.monotonic() + secs, idx])
        time.sleep(0.2)
        still = []
        for item in live:
            (p, parent, dl, idx) = item
            done = False
            if parent.poll(0):
                try:
                    got = parent.recv()
                except EOFError:
                    got = None
                if got is not None and got[0] == "ok":
                    out[idx] = (got[1], None)
                elif got is not None:
                    out[idx] = (None, got[1])
                else:
                    out[idx] = (None, "no result")
                done = True
            elif time.monotonic() > dl:
                out[idx] = (None, "timeout")
                done = True
            if done:
                p.join(1)
                if p.is_alive():
                    p.terminate()
                    p.join(3)
                    if p.is_alive():
                        p.kill()
                        p.join(3)
                parent.close()
            else:
                still.append(item)
        live = still
    return out


def _work(conn, sub, force, cross, prod):
    os.environ["REDSTONE_FORCE"] = force
    try:
        out = C.compose_hier_part(sub)
        # module attribute, not a from-import: _last_ctx/_last_shift are
        # written by the child run, so a value binding captured at import
        # would still be None here.
        c = C._last_ctx
        ok = True
        err = None
        if sub["outputs"]:
            try:
                sim_verify(sub, out[0], out[2], quiet=True)
            except RuntimeError as e:
                ok, err = False, str(e)
        # Same acceptance bar compose_hier applies: a produced boundary net
        # whose port cell is not free (or has no exit) can never be
        # stitched, however green the partition sims. Reject the rung here so
        # the cache never hands a doomed partition to the stitch stage.
        if ok and cross:
            try:
                C.check_hier_ports(sub, c, C._last_shift, cross, prod)
            except RuntimeError as e:
                ok, err = False, str(e)
        cdict = {"blocks": c.blocks, "solid": c.solid, "rings": c.rings,
                 "wires": c.wires, "junctions": c.junctions,
                 "repeaters": c.repeaters, "pos": c.pos, "sup": c.sup,
                 "recs": c.recs}
        if ok:
            conn.send(("ok", (out, cdict, C._last_shift)))
        else:
            conn.send(("err", err))
        return
    except RuntimeError as e:
        conn.send(("err", str(e)))
    except Exception as e:
        conn.send(("err", f"{type(e).__name__}: {e}"))
    finally:
        conn.close()


def main():
    src, pre = sys.argv[1], sys.argv[2]
    secs = float(sys.argv[3]) if len(sys.argv) > 3 else 45.0
    r = parse_recipe(open(src).read())
    gates = _strip_buffers(expand_gates(r["gates"], r["inputs"]), r["outputs"])
    prod = {}
    for g in gates:
        prod[g["out"]] = g.get("band", 0)
    bands = sorted({g.get("band", 0) for g in gates})
    subs = []
    for b in bands:
        bg = [g for g in gates if g.get("band", 0) == b]
        need = set()
        for g in bg:
            for a in g["args"]:
                if a in ("0", "1"):
                    continue
                if a in r["inputs"] or prod.get(a, b) != b:
                    need.add(a)
        bd = sorted(x for x in need if x not in r["inputs"])
        sub = {"inputs": [x for x in r["inputs"] if x in need] + bd,
               "outputs": sorted(g["out"] for g in bg
                                 if g["out"] in r["outputs"]),
               "gates": [{k: v for k, v in g.items() if k != "band"}
                         for g in bg],
               "edge": {n: ("W" if prod.get(n, b) < b else "E") for n in bd},
               "_band": b}
        # boundary nets this band PRODUCES (consumed by a later band): the
        # ports the stitch will land on, checked by check_hier_ports.
        _cb = set()
        for _g in bg:
            for _a in _g["args"]:
                if _a in prod and prod[_a] != b:
                    _cb.add(_a)
        subs.append((b, sub, sorted(_cb)))
    global CROSS, PROD
    CROSS = sorted({a for (b, sub, cb) in subs for a in cb})
    rungs = []
    for jog in ("short", "long"):
        for spread in (1, 2, 3, 4):
            for order in ("gates_first", "inputs_first"):
                rungs.append(f"{spread},{order},{jog}")
    # ponytail: per-band rung skip (HIER_SKIP="b:rung;b:rung", rung like
    # "1,inputs_first,long"). Forces a band off a rung whose geometry poisons
    # the merge (measured: band-5 long1i parks C2's driver port inside
    # AL_AB0's stub pocket) onto its next sim-green rung. Env-gated.
    _skip = set()
    for _spec in os.environ.get("HIER_SKIP", "").split(";"):
        if ":" in _spec:
            _bb, _rr = _spec.split(":", 1)
            _skip.add((int(_bb.strip()), _rr.strip()))
    jobs, meta = [], []
    for (b, sub, _cb) in subs:
        for f in rungs:
            if (b, f) in _skip:
                continue
            jobs.append((len(jobs), sub, f, secs))
            meta.append((b, f))
    t0 = time.time()
    results = _run_all(jobs)
    print(f"{len(jobs)} band-rungs in {time.time()-t0:.0f}s (parallel)", flush=True)
    best, bad = {}, 0
    if os.environ.get("HIER_VERBOSE"):
        for (b, f), res in zip(meta, results):
            print(f"  b{b} {f}: {'no result' if not res else (res[1] or 'OK')}")
    for (b, f), res in zip(meta, results):
        if not res or res[0] is None:
            continue
        out, cdict, sh = res[0]
        # ponytail: smallest green rung, not first. First-green picked a
        # 619-wide sprawl (band 5) that pushed the merge past 3000 cells and
        # doomed 2000-cell stitches; among sim-green + open-port rungs the
        # compact one stitches shorter. All rungs already ran (parallel).
        if b not in best or len(out[0]) < len(best[b][1][0]):
            best[b] = (f, out, cdict, sh)
    for (b, sub, _cb) in subs:
        if b not in best:
            bad += 1
            print(f"band {b}: NO GREEN RUNG")
        else:
            f, out, cdict, sh = best[b]
            print(f"band {b}: {f} {len(out[0])} blocks {out[1]}")
    if bad:
        print(f"FAIL {bad} bands")
        sys.exit(1)
    with open(pre + ".pkl", "wb") as f:
        pickle.dump({"bands": [{"b": b, "sub": sub, "rung": best[b][0],
                                "out": best[b][1], "ctx": best[b][2],
                                "shift": best[b][3]}
                               for (b, sub, _cb) in subs if b in best],
                     "inputs": r["inputs"], "prod": prod}, f)
    print(f"cached {pre}.pkl ({len(subs)} bands)")


if __name__ == "__main__":
    main()
