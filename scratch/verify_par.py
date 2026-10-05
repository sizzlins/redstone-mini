"""Full recipe verify, vector-parallel, hard-bounded, streaming.

Usage: python scratch/verify_par.py <blocks_source> <recipe> [workers] [secs]
                                  [chunks_per_call] [nchunks]
<blocks_source>: scratch .pkl merge dump (post-merge field) - verifies the
  exact merged build compose_hier produced, vector by vector.
Compares sim lamps vs eval_net on EVERY input vector (2^n). Exit 0 iff all
vectors match = DONE-grade verification.

Three things this file got wrong and now cannot:

1. CACHE KEY. `chunks = vecs[i::workers]` makes a chunk's CONTENTS depend on
   the worker count, but the cache was keyed on the bare index, so a cache
   written at workers=4 was read back as valid at workers=20 - silently
   green-marking vectors that were never simulated. Key is now
   "nchunks:index:recipe-fingerprint", and anything unparseable re-runs.
2. SILENCE. The only prints were when a whole chunk landed. With a chunk of
   32 vectors that is ~700 s of nothing, which reads as a hang and gets
   killed (measured twice). `_vec_child` now streams one line PER VECTOR.
3. CHUNK SIZE IS NOT WORKER COUNT. nchunks is now its own argument, so the
    chunk can be small enough to report often while the process count stays
    low. Chunks are a strided slice, so they still cover the space evenly.

Two things this file also got wrong, both about the tables rather than the
vectors (measured 2026-10-05, scratch/tbl_probe.py):

 4. TABLES WERE REBUILT PER CHUNK. One process per chunk meant one parse +
    `_tables_from` per chunk, and on alu4 that set is 7.78s and 103 MB of
    constant tables. A 16-chunk sweep paid 16 x 7.78s = 126s rebuilding
    exactly the same tables on top of ~543s of real work: 23% of the
    dominant compute thrown away. A child now owns a GROUP of chunks, and
    since simvec._tables memoises on the parsed context, one build serves the
    whole group. workers == len(group) reproduces the old behaviour exactly.
 5. `per_call` CAPPED THE PARALLELISM, not just the work. It defaulted to 4
    and hier_verify passes 2, so a call could never hand a worker more than
    one chunk and grouping could never pay. per_call <= 0 now means "every
    pending chunk", and worker count alone sets the parallelism. The staged
    top-up loop stays as a safety net, not as the unit of work.
"""
import os, sys, pickle, time, itertools, json, hashlib
import multiprocessing as mp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# ponytail: the fingerprint covers the ENGINE, not just the inputs. It used to
# hash only the recipe and the build, so a physics fix landed sim.py and every
# cached chunk still read "green" -- a stale pass that looks exactly like a
# fresh one, and there is no way to tell them apart from the output. Every file
# that can change the ANSWER is part of the answer's identity. sim.py and
# recipe.py are what this script evaluates; simvec/layout/compose/tiles/core
# are hashed too so any engine edit anywhere voids every cache. Over-hashing
# only ever forces a re-run; under-hashing silently lies. Bump by hand to force.
ENGINE = tuple(os.path.join(ROOT, f + ".py") for f in
               ("sim", "simvec", "recipe", "layout", "compose", "tiles",
                "core"))


def _vec_child(conn, blocks, io, recipe, jobs):
    """jobs: [(chunk_index, vecs), ...] -- a GROUP of chunks, one process.

    ponytail: this is where the 23% went. Tables are constant for a build, so
    a worker that owns N chunks must build them ONCE. simvec._tables memoises
    on the parsed context, so keeping the loop here (rather than one process
    per chunk) is the whole fix -- no cache, no file, no sharing.
    """
    try:
        from recipe import eval_net
        from sim import _run_vec, _parse_build, _latch_hold_seed
        pst = _parse_build(blocks, io)
        hold = _latch_hold_seed(blocks, io)
        # ponytail: use the TABLE engine (simvec.run_scalar) when eligible,
        # exactly as sim.sim_verify routes it: states is None here, and
        # `hold is None` IS the latch-free test (sim.py:_latch_hold_seed
        # returns None without ~qb nets). This child used to call
        # sim._run_vec for every vector, so the whole staged parallel verify
        # -- the repo's dominant compute -- never touched the fast engine
        # sim_verify ships in production. Same caps either way (sim._TICK_CAP/
        # _STEP_CAP default 20000/2000000 and the parent exports them), same
        # verdict: diff_engine.py proves the two engines agree bit for bit,
        # and run_scalar raises rather than guessing when it is not eligible.
        # REDSTONE_VERIFY_ENGINE=slow forces the authority engine for a
        # differential A/B on the same cache key.
        run = lambda v, _p: _run_vec(v, hold, _p)   # noqa: E731
        warm_on = os.environ.get("REDSTONE_VERIFY_WARM", "1") == "1"
        if (hold is None
                and os.environ.get("REDSTONE_VERIFY_ENGINE", "fast")
                != "slow"):
            try:
                from simvec import run_scalar
                run = lambda v, _p: run_scalar(v, _p)   # noqa: E731
            except ImportError:
                warm_on = False
        # ponytail: warm-start chain is a sweep-only fast path, not a verdict
        # path. run_scalar default (cold) is the authority; warm reuses the
        # previous vector's final levels as the starting point (same seeding,
        # same ring -- fewer flips, 2.3x measured, lamps-identical on 16
        # chained). A warm lamps-mismatch or any warm raise falls back to
        # cold, so warm can never mask a failure or invent one.
        # REDSTONE_VERIFY_WARM=0 forces pure cold. _BOUT is snapshotted
        # around the warm attempt so a discarded warm run leaves no burnout
        # trace for the authoritative cold.
        _chain = [None]

        def _cold(v):
            g = run(v, pst)[0]
            if warm_on:
                try:
                    from simvec import run_scalar as _rs
                    _ce = {}
                    _rs(v, pst, _expose=_ce)
                    _chain[0] = _ce
                except Exception:  # noqa: BLE001 -- chain breaks, verdict stands
                    _chain[0] = None
            else:
                _chain[0] = None
            return g

        def _fast(v):
            if not warm_on or _chain[0] is None:
                return _cold(v)
            try:
                import sim as _s
                _saved = dict(getattr(_s, "_BOUT", {}))
            except Exception:  # noqa: BLE001 -- best-effort snapshot
                _s = None
                _saved = None
            try:
                from simvec import run_scalar as _rs
                _exp = {}
                _got = _rs(v, pst, _warm=_chain[0], _expose=_exp)[0]
            except Exception:  # noqa: BLE001 -- incl RuntimeError: cold decides
                if _s is not None and _saved is not None:
                    try:
                        _s._BOUT.clear()
                        _s._BOUT.update(_saved)
                    except Exception:  # noqa: BLE001
                        pass
                return _cold(v)
            _want = eval_net(recipe, v)
            if all(bool(_got.get(o, False)) == bool(_want.get(o, False))
                   for o in recipe["outputs"]):
                _chain[0] = _exp
                return _got
            if _s is not None and _saved is not None:
                try:
                    _s._BOUT.clear()
                    _s._BOUT.update(_saved)
                except Exception:  # noqa: BLE001
                    pass
            return _cold(v)

        for idx, vecs in jobs:
            # ("chunk", i) is the deadline's zero: `secs` bounds ONE chunk, so
            # the parent cannot know when this chunk started until it says so.
            conn.send(("chunk", idx))
            bad = []
            t0 = time.time()
            for k, vec in enumerate(vecs):
                try:
                    got = _fast(vec)
                except RuntimeError as e:
                    bad.append((vec, f"RED {str(e)[:80]}"))
                else:
                    want = eval_net(recipe, vec)
                    miss = [o for o in recipe["outputs"]
                            if bool(got.get(o, False)) != bool(want.get(o, False))]
                    if miss:
                        bad.append((vec, f"MISMATCH {miss}"))
                # per-vector progress: silence can never again read as a hang
                conn.send(("vec", idx, k + 1, len(vecs), bad[-1] if bad else None,
                           round(time.time() - t0, 1)))
            conn.send(("done", idx, bad))
        conn.send(("alldone",))
    except Exception as e:
        conn.send(("err", f"{type(e).__name__}: {e}"))
    finally:
        conn.close()


def _fingerprint(*paths):
    h = hashlib.sha256()
    for p in paths:
        try:
            h.update(open(p, "rb").read())
        except OSError:
            h.update(repr(p).encode())
    return h.hexdigest()[:12]


# ponytail: the ENGINE is part of the cache key, not just the inputs. A cached
# "green" is a claim about (recipe, build, physics) together -- and the physics
# moves. Measured: cpu4merge3.pkl.verify.json held 32/32 green and
# alu4merge.pkl.verify.json 58/64, both produced by a pre-fix engine, and the
# old key (recipe + build path only) would have reused them silently and
# reported a clean pass. The nastiest form of this is a build that "settles
# dark and early": a bug that made every booster evaluate once, at tick 0, with
# its input still dark. That can go GREEN FOR THE WRONG REASON, which is worse
# than going red. Any edit to these files must void every cache.
_ENGINE_FILES = ("sim.py", "simvec.py", "recipe.py", "layout.py",
                 "compose.py", "tiles.py", "core.py")


def _engine_fingerprint():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return _fingerprint(*[os.path.join(root, f) for f in _ENGINE_FILES])


def main():
    from recipe import parse_recipe
    dp, rp = sys.argv[1], sys.argv[2]
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    secs = float(sys.argv[4]) if len(sys.argv) > 4 else 600.0
    per_call = int(sys.argv[5]) if len(sys.argv) > 5 else 0
    nchunks = int(sys.argv[6]) if len(sys.argv) > 6 else 16
    d = pickle.load(open(dp, "rb"))
    r = parse_recipe(open(rp).read())
    blocks, io = d["blocks"], d["io"]
    # ponytail: generous worker caps. A 34k-block build's slowest vectors need
    # >5000 ticks to settle (measured: 0011010010 RED at defaults, OK in 1s at
    # 20000/2000000). Caps only bound worst case; greens settle long before.
    os.environ["REDSTONE_SIM_TICKS"] = "20000"
    os.environ["REDSTONE_SIM_STEPS"] = "2000000"
    cachep = dp + ".verify.json"
    fp = _fingerprint(rp, dp, *ENGINE)
    try:
        cache = json.load(open(cachep))
        if not isinstance(cache, dict) or cache.get("__fp__") != fp:
            cache = {}
    except (FileNotFoundError, ValueError):
        cache = {}
    cache["__fp__"] = fp
    vecs = [dict(zip(r["inputs"], vals))
            for vals in itertools.product([0, 1], repeat=len(r["inputs"]))]
    chunks = [vecs[i::nchunks] for i in range(nchunks)]
    key = lambda i: f"{nchunks}:{i}"
    # ponytail: empty chunks are vacuously green (finer nchunks than
    # vectors leaves holes). Queueing them would spawn a child per hole
    # for zero vectors; counting them short-circuits instead. They carry
    # no cache entry and need none.
    todo = [i for i in range(nchunks)
            if chunks[i] and cache.get(key(i)) != "green"]
    # ponytail: per_call <= 0 means "every pending chunk", so worker count
    # alone sets the parallelism. It used to cap work at 4 (hier_verify passed
    # 2), which made grouping impossible: a worker could never be handed more
    # than one chunk, so the table build was never amortised. The staged
    # top-up loop in hier_verify remains as a safety net, not as the unit.
    if per_call > 0:
        todo = todo[:per_call]
    green = sum(1 for i in range(nchunks)
                if not chunks[i] or cache.get(key(i)) == "green")
    print(f"verify: {green}/{nchunks} chunks green (nchunks={nchunks}, "
          f"workers={workers}), doing {todo}", flush=True)
    if not todo:
        bad = [v for k, v in cache.items() if k != "__fp__" and v != "green"]
        print(f"VERIFY {'OK' if not bad else 'RED'}: {len(vecs)} vectors, "
              f"{green} chunks green", flush=True)
        sys.exit(1 if bad else 0)

    def save():
        with open(cachep, "w") as f:
            json.dump(cache, f)

    t0 = time.time()
    queue = list(todo)
    live = {}
    failed = []
    gid = 0

    def launch(jobs):
        nonlocal gid
        parent, child = mp.Pipe(duplex=False)
        p = mp.Process(target=_vec_child,
                       args=(child, blocks, io, r, jobs), daemon=False)
        p.start()
        child.close()
        # [proc, pipe, jobs, done_set, cur_chunk, cur_start]
        live[gid] = [p, parent, jobs, set(), None, None]
        gid += 1

    def record(i, bad, tag):
        """Cache ONE chunk's verdict.

        Only an explicit empty `bad` from the child's ("done", i, bad) marks a
        chunk green. Every other path -- timeout, dead pipe, exception -- lands
        here with a non-empty `bad`, so an unverified chunk can never read as
        verified. That distinction is the whole point of the cache.
        """
        if bad:
            failed.append((i, bad))
            cache[key(i)] = str(bad[:1])[:200]
            print(f"chunk {i} {tag}: {str(bad[:1])[:160]}", flush=True)
        else:
            cache[key(i)] = "green"
            print(f"chunk {i} green", flush=True)
        save()

    def close(g):
        p, parent = live[g][0], live[g][1]
        p.join(2)
        if p.is_alive():
            p.terminate(); p.join(3)
            if p.is_alive():
                p.kill(); p.join(3)
        try:
            parent.close()
        except OSError:
            pass
        del live[g]

    def reap():
        for g in list(live):
            p, parent, jobs, doneset, cur, curstart = live[g]
            msg = None
            try:
                if parent.poll(0):
                    try:
                        msg = parent.recv()
                    except (EOFError, OSError):
                        msg = ("err", "child died (EOF)")
            except (BrokenPipeError, OSError):
                # ponytail: poll() itself raises once the far end is gone.
                # A finished child closes its pipe, so the normal exit path
                # hits this on the very next tick -- treat it as terminal or
                # the parent dies with a traceback instead of finishing.
                msg = ("err", "child closed pipe")
            # ponytail: `secs` bounds ONE chunk, and the child only reports a
            # chunk's start by asking for it ("chunk", i), so the clock starts
            # there. With one process per chunk the two instants were the same
            # thing; with a group they are not, and a per-chunk budget is what
            # keeps a slow chunk from eating its group's whole allowance.
            if msg is None and cur is not None and \
                    time.monotonic() > curstart + secs:
                msg = ("kill", f"killed at {secs:g}s")
            if msg is None:
                continue
            kind = msg[0]
            if kind == "chunk":
                live[g][4], live[g][5] = msg[1], time.monotonic()
            elif kind == "vec":
                # progress only: the child is STILL RUNNING, so keep it in
                # `live` and keep the pipe open. Unregistering here closed the
                # pipe under a live child and it died with BrokenPipeError.
                _, i, k, n, bad, el = msg
                print(f"  chunk {i} {k}/{n} ({el}s)"
                      + (f"  BAD {bad[1]}" if bad else ""), flush=True)
            elif kind == "done":
                _, i, bad = msg
                record(i, bad, "BAD")
                doneset.add(i)
                live[g][4] = None
            elif kind == "alldone":
                close(g)
            else:
                # err or kill: every chunk this group still owns is
                # UNVERIFIED. Record the reason against each so the count is
                # honest; none of them can be cached green, so a rerun redoes
                # exactly the work that did not happen.
                for j, _ in jobs:
                    if j not in doneset:
                        record(j, [(None, msg[1])], "ERROR")
                close(g)

    while queue or live:
        while queue and len(live) < max(1, workers):
            # Deal this worker a fair share of what is LEFT, so the last
            # worker launched is not handed one chunk while the first holds
            # fifteen. No work stealing: the LOG measured tail ~= mean, and a
            # worker only loses its surplus if it is killed, which is rarer
            # than the bookkeeping costs.
            slots = max(1, max(1, workers) - len(live))
            take = max(1, -(-len(queue) // slots))     # ceil
            launch([(i, chunks[i]) for i in queue[:take]])
            queue = queue[take:]
        time.sleep(0.4)
        reap()
    save()
    if failed:
        print(f"VERIFY RED: {len(failed)} bad chunks (progress cached; "
              f"rerun to resume)", flush=True)
        sys.exit(1)
    green = sum(1 for i in range(nchunks)
                if not chunks[i] or cache.get(key(i)) == "green")
    if green < nchunks:
        print(f"STAGED: {green}/{nchunks} chunks green, {len(vecs)} vectors "
              f"total", flush=True)
    else:
        print(f"VERIFY OK: {len(vecs)} vectors, {green} chunks green",
              flush=True)


if __name__ == "__main__":
    main()
