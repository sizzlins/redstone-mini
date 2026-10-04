# handoff — optimization agent (2026-10-04: band 0 DONE, then the speed shift)

Repo `D:\redstone-mini`, branch `phase2-design` (shared with the GA agent —
we both commit here; commits interleave). Mine:
`1be2186, ee61873, f462f6f, 325eac7, 2ca3f69, ddd500a, a5ee1ef, fe71ca1,
470c84c` + the uncommitted gate fixes below. `notes/handoff.md` was deleted in
the working tree (not by me — left that way, staged state untouched).

---

## Goal

Two shifts, both from the operator, in order:
1. **Band 0 campaign** (DONE): alu4 band 0 was the last red band; Y0 lives in
   it, so no full merge. Reached: **alu4 1024/1024** end to end.
2. **Speed, no matter how crazy**: *"find files or function … think of an
   optimization no matter how crazy or black magic or extremely time
   consuming, then implement it, then repeat."* Loop is open; this file is the
   state at the last commit.

Standing project goal unchanged: every recipe in `recipes/` generates,
verifies, exports. `alu4` done, `alu1` hier done (pinned, below), `cpu4`
untouched.

---

## Current state (all re-verified on the CURRENT engine, post comparator-fix)

| build | verdict | evidence |
|---|---|---|
| **alu4** (1024 vectors) | **GREEN 1024/1024** | `scratch/alu4ab2.pkl` `VERIFY OK: 1024 vectors, 16 chunks green`, 71,560 blocks (2198×353), 10 levers |
| alu4 bands | **6/6, rungs reproduced exactly** | b0 13304 `3,inputs_first,short` · b1 7518 · b2 6957 · b3 571 · b4 2414 · b5 4878 |
| **alu1 hier** | **GREEN 32/32** (again) | band 0 **10124** `2,gates_first,short` (pinned) · band 1 494 · MERGE 15104 (589×236) |
| alu1 flat (nonhier) | RED **by design** since `124d179` | 22-gate banded recipe, `22 < _TERR_MIN_GATES=40`; suite `EXPECT 13300` is stale |
| examples / micro1 / ctrl_decode | GREEN, bit-identical | 144 / 322 / 224 / 214 / 2925 / 5499 |
| cpu4 | untouched, still RED at merge (inherited) | Y2 coupling class, pre-dates this session |
| paste tests | **none ever pasted into Minecraft** | `build_alu4full.schem` is in your schematics folder, hash-verified |

Paste-ready: `build_alu4full.schem` / `.mcfunction` / `.html` (gitignored).
`build_alu4.*` and `build_alu4bank.*` are **stale** (pre-b0).

---

## What changed, with numbers

**Speed (the point of shift 2):**
1. **`verify_par` used the slow engine** (`a5ee1ef`). `_vec_child` called
   `sim._run_vec` per vector, so the repo's dominant compute never touched the
   table engine `sim_verify` ships. **104s → 47s per 64-vector chunk (2.2x)**,
   A/B on the same box minutes apart, both green.
2. **`_run_vec` now delegates to `run_scalar`** (`fe71ca1`) for the ordinary
   case (init None, no target_hits, no `until`) — ~60 direct callers get it.
   **1.311s → 0.678s per vector (1.93x)** on alu4merge_g. Latch builds keep the
   old path (exercised on cpu4merge). `REDSTONE_SERIES_VERIFY=1` forces the
   authority loop everywhere.
3. **Router** (`470c84c`, bit-identical, ladder reproduces): `astar.ok()` no
   longer builds a `(x,z)` tuple per call (1.65M per band compose) — hoisted
   allow-set + direct compare; `_support` memoized per search (pure over the
   static field); standard stale-pop guard; 16 lines of dead code after
   `ok()`'s `return True` deleted. Band 1 compose 4.4s → 4.2s.

**Gate fixes (found while certifying the above):**
4. **`diff_engine`'s baseline was rotten.** `scratch/ref_sim.py` was frozen
   10/3, *before* burnout and the lock/side narrowing, so the live engine
   "differed" from it on alu4 vec001+ (false DIFFERENCES against a provably
   neutral change; direct ref-vs-live on the failing case: IDENTICAL).
   `mkref.py` was worse — it extracted 3 functions and so omitted every
   module-level helper `_run_vec` calls. Now it freezes
   `git show HEAD:sim.py` **verbatim**. `diff_engine` ALL IDENTICAL again.
   *Corollary: earlier "ALL IDENTICAL" claims rested on a weaker baseline than
   they claimed; the independent gates (full 1024-vector verify against the
   logical oracle) carried the load.*
5. **`hier_verify` swallowed stage failures** (uncommitted). `run()` passed
   `check=False` and **discarded the child's return code**, so a RED stitch
   (`sys.exit(1)`) was ignored and the pipeline verified the *previous*
   `merge.pkl` — measured: one run printed `STITCH RED … no ground for t3` and
   then `VERIFY OK 32/32` from the stale merge. Now returns `r.returncode`.
6. **alu1 hier is green again** and the pin is durable. The GA's comparator
   physics fix (`38b872f`) made band 0 sim-green at spread 1, whose compact
   6874-block shape walls the stitch. `recipes/alu1.skip` pins band 0 to
   spread ≥ 2; `hier_bands.py` reads a `<recipe>.skip` sibling (env still
   wins, `#` comments allowed). Proven in a worktree at `85d74cd`: identical
   bands with and without my layout change, so **my router work is exonerated
   and the physics fix is the cause**.

---

## What failed / was reverted (do not re-derive)

- **Micro-opts in `simvec._dust_lvl_s`/`_cob_state_s`** (hot-loop locals +
  early exits): 0.515s vs 0.514s — noise. Reverted; those helpers' cost is
  real work, not lookups.
- **Candidate-list neighbour build** in astar (ups/dns rebuilt per direction):
  4.3s vs 4.2s. A list alloc costs what the 3-tuple concat costs.
- **Pre-astar unreachability flood** (DFS 13.4s, BFS 7.5s vs 4.2s): successful
  searches pay for the flood twice over.
- **Bound prune / iterative deepening on f**: `scratch/astar_waste.py` shows
  `pops_above_goal = 0` in *every* search — A* never expands past optimal, so
  there is nothing to prune.
- **Stale-pop guard**: correct and free, but measured 0 pops saved (no
  duplicates exist). Kept anyway — it is 3 lines and closes a real hole.
- **Router window** (`margin = man + 64`): the actual lever, see next.

---

## Files I touched

Tracked: `compose.py`, `layout.py`, `sim.py`, `scratch/verify_par.py`,
`scratch/hier_bands.py`, `scratch/hier_verify.py`, `scratch/mkref.py`,
`scratch/ref_sim.py`, `scratch/prof_scalar.py`, `scratch/bench_scalar.py`,
`scratch/prof_runvec.py`, `scratch/astar_waste.py`, `scratch/rss_probe.py`,
`recipes/alu1.skip` (new), `LOG.md`, `MORNING-REPORT.md`,
`notes/PONYTAIL-DEBT.md`, `notes/handoff-opt agent.md` (this),
`notes/to-ga-agent.md`.

Not touched (theirs): `scratch/evo_*`, `evolve.py`, `compact.py`, `enum_*`,
`memo.json`, `rig_verify.py`, `rcon.py`, `dustcmp.py`, `unweave.py`,
`muxlevel.py`, `notes/to-opt-agent.md`, `notes/handoff-ga- agent.md`.
`sim.py` edits were pre-announced in `notes/to-ga-agent.md` because their
memo fingerprints it.

---

## What we should do next

1. **The astar window is the big remaining router lever, and it needs a
   decision, not more cleverness.** `_astar_wrap` passes `margin = man + 64`,
   so the search window is the field plus 64 empty cells in every direction; a
   *failing* flat-only search walks all of it (100k distinct pops in a
   28.5k-cell field, and 3 of 10 band searches = 86% of all pops). A tighter
   window can only return a *different* path or fail **loud** (never silently
   wrong), so it is safe to A/B but not to default blind. Suggest:
   `REDSTONE_ASTAR_MARGIN` env, measure ladder + all flat recipes, then decide.
2. **Verify-worker scaling A/B.** 8 concurrent children run ~2.1× slower each
   than one alone (0.68s → ~1.44s/vector) — the box (20 cores, 3 GB free, a
   Minecraft server resident) gives ~3.8× effective, not 8×. Measure 4 vs 8
   workers; `verify_par` defaults to 4 and `hier_verify` passes 16.
3. **cpu4** if it climbs: the corridor-blame + diode-drop machinery is
   combination-friendly (both fired on band 3 unprompted).
4. **Re-freeze discipline**: any commit touching `sim.py`/`simvec.py` must be
   followed by `python scratch/mkref.py` or `diff_engine` silently compares
   against the wrong baseline. Worth a pre-commit hook eventually.
5. **Operator items**: paste `build_alu4full.schem`; decide whether the stale
   `build_alu4.*` / `build_alu4bank.*` / `build.*.bak` files get deleted (I
   never delete).

---

## Build notes that cost time

- Every probe/script hard-bounded, `__main__` guard (spawn re-import = fork
  bomb). Band caches need `REDSTONE_ASTAR_CAP` unset. `lwire` will not route a
  span over ~350 cells. Repeater facing is stored `-travel`.
- `check_shorts` runs before `finish_assembly`: SHORT3D masks repeater loops,
  so fix shorts first, then re-read the loop error.
- The GA agent's `dustcmp` lesson: a 3-state probe (`power=15/1/0`) read an
  analog level and reported 1617 fake mismatches; probe the sim's level first,
  then scan descending. That fix exposed a real divergence which turned out to
  be the comparator-front sim bug — theirs, fixed, and the physics gates all
  re-ran green on it.
