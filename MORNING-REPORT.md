# MORNING REPORT — autonomous opt + verify session 2026-10-04

## DONE (this session)

1. **Serial fast path for tiny sweeps** (`simvec.py`): `verify_par`
   skips the spawn pool when `<=8 vectors AND <=100k cell-vectors`
   (0.26s -> 0.01s on example_and, 26x). Same `_serial_shard` the pool
   runs (latch fallback + fail-fast intact). `REDSTONE_SERIAL_CELLVEC`
   overrides. Threshold deliberately tight so slow-vector builds still
   fan out.
2. **Parse once per worker** (`simvec.py`): `_serial_shard` re-parsed the
   whole build per shard (64 shards = 64 parses); now cached per worker
   via `_parse_build_ctx`, reset in `_init_worker` (without the reset,
   sequential verifies in one process simulate builds 2-4 with build 1's
   tables -- caught by inspection, gated by compose_check's 4-build run).
3. **Band-cache fingerprint** (`hier_bands.py` writes `__fp__`,
   `hier_stitch.py` refuses mismatch LOUD): stale band caches cost a full
   session once; engine has since moved twice. Proven: old cache refused
   (`built under engine None`), fresh climb green.
4. **alu1 re-verified end-to-end** from the promoted recipe with all of
   the above in place: stamped bands -> MERGE 15104 -> smoke 4/4 ->
   **VERIFY OK 32/32**. alu1 stays green.

## Measured, no action (with numbers)

- **Dirty-bit wake: pivoted, not implemented.** 73% of evals find no
  change (880k evals / 238k wakes), so headroom exists -- but the
  wake->eval term info has nowhere cheap to ride in CPython (side-channel
  dict ops ~= the term-checks saved; heap-tuple widening collides with
  coalescing). Same lesson as SWAR: don't outsmart, de-fat. Full analysis
  in LOG. Next sim wins: none cheap remain (dict.get/max are the work).
- **Router/exporters/simvec loop**: no env-in-hot-loop, copies are
  failure-path-only and second-order. Untouched.
- **OP0 y=3 orphan**: CLOSED. The 66 lit cells belonged to a superseded
  merge iteration (re-stitched 3x during the night); the cells don't exist
  in either verified merge (0 lit). Not a checker hole.
- **Rust/C++**: assessed with numbers, recommended against (see LOG):
  10-20x physics -> 3-5x end-to-end (Amdahl: spawn/IPC, stragglers,
  pre-roll, untouched router), vs dual-implementation drift on physics
  that changed 3x this week + Windows toolchain + undebuggable core.
  Cython-before-Rust if ever; revisit when physics stabilizes AND
  physics >80% of end-to-end after driver fixes.

## What still fails / needs hands

1. **alu4bank.pkl smoke 2/4 RED (Y2, COUT) -- PRE-EXISTING, not a
   regression.** Fault shape matches the documented pillar-feed saga
   exactly (Y2 stuck lit on all-off, elevated runs hot; LOG-history
   "Finding: Y2 stuck lit"). The bank predates the below-feeds physics
   fix; the fixed sim correctly flags it. Fix = re-route off
   torch-topped pillars (separate phase, as logged in October).
   cpu4retry_merge.pkl smokes 4/4 GREEN under the current engine.
2. **LOG.md sharing**: GA agent rewrote it wholesale again tonight
   (history + my entries wiped from worktree/HEAD twice). Recovery in
   git (`notes/LOG-history-2026-10-04.md`) + my trace in
   `notes/alu1-green-2026-10-04.md` + commit messages. Still needs your
   merge decision; I keep entries to short appends.
3. **Work-stealing pool** (straggler tail on big verifies): deferred for
   lack of tail evidence on current builds; implement only with a measured
   skewed tail in hand.

## GA agent status (observed, not touched)

Squeeze loop still running (`compact.py`, add2opt 43xx). My commits are
engine/scratch-gate paths only; their files untouched. One incident,
mine: an unguarded probe + spawn pool fork-bombed (hundreds of procs);
killed only my orphans by command-line match, their `compact.py`
verified untouched, probe fixed+guarded, rule re-learned. No other
collisions. Tree clean except the two protected `.bak` files.
