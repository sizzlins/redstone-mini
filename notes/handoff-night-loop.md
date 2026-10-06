# handoff — night loop (2026-10-05 ~08:00–13:00, sweep engines + measurement)

Read order: this file → repo-root `LOG.md` tail (loops 1–12 entries) →
`MORNING-REPORT.md` (operator view) → `notes/handoff-opt2 agent.md` (prior
session baseline). Branch `phase2-design`, shared with GA co-tenant agent
(evolve/squeeze + forensics lanes). Discipline kept all night: never
`checkout`/`stash` foreign files, `git commit -- <paths>` only, `git add -f`
under `scratch/`, LOG append-only, verdicts always checked (never timing-only).

## Goal

Operator sleep-shift orders: fully autonomous optimization loop (find file or
function, think of an optimization no matter how crazy, implement, verify,
repeat, do not stop), verify after every change, commit frequently + LOG,
MORNING-REPORT when done/blocked. Standing project goal unchanged: every
recipe generates, verifies, exports.

## Current state (all re-verified on final tree; gates below)

| build | verdict |
|---|---|
| **alu4** (10 inputs, 71,560 blocks) | **GREEN 1024/1024**, warm sweep ~30s (was 108.7s cold at session start) |
| **alu1 hier** | **GREEN 32/32** |
| **add8merge** (OR-less carry, 49,070 blocks, 16 inputs) | **GREEN 65536/65536, three ways** (warm, numba, hier) — first exhaustive proof ever (was sampled only) |
| examples / latch / xor / micro1 / ctrl_decode | GREEN, bit-identical |
| alu1 flat | RED **by design** (22-gate recipe) |
| cpu4merge2 | RED, identical signature in all 3 engines (warm/cold/authority agree) |
| `hier_verify alu4` end-to-end | GREEN, exit 0 |
| coldstart | **15/15 green** (full), 14/14 --quick repeatedly through the day |

Sweep wall: 108.7s → ~30s total (table engine 2.8x inherited + warm chain 1.39x
shipped tonight). Null-check discipline held: identical-code null reads
0.61–0.96x (thermal bias), so only >20% structural wins ship; micros rejected.

## What changed (shipped)

1. **Warm-start chains, verify_par default** (`42b4d5b`): sweep 44.3s→30–32s
   (1.36–1.39x, 4 runs). Previous vector's final levels seed the next run;
   lamps-mismatch or any raise falls back to cold; `_BOUT` snapshotted around
   discarded attempts. Verdict-neutral proven: greens stay green (alu4/alu1),
   reds stay red with identical signature (cpu4merge2).
   Escape: `REDSTONE_VERIFY_WARM=0`.
2. **`_cold` single-run** (`d65d7db`): verdict + chain refresh in one call
   (was two runs: 16 wasted runs/sweep + one per fallback).
3. **Numba core mirror, opt-in** (`82fa638`, `860dd06`): `scratch/simvec_numba.py`
   njit 1:1 port, ~3x in-process, ALL SIX FIELDS incl exact ticks, 20+ vectors
   over alu4/alu1/alu4bank_ins, same burnout cell on red vectors.
   `REDSTONE_VERIFY_ENGINE=numba`. Disk-cached compile (1.8s load), np bundle
   cache (33MB, atomic, fp-keyed), canonical sorted input order (a recipe/sorted
   mismatch once went RED in-sweep; harness now has permanent BUNDLE IDENTICAL
   self-test). Default stays warm-Python (sweep walls tied; data inconclusive).
4. **Hier staging fix** (`cf548cb`): `hier_verify` died on first 900s verify
   round (uncaught TimeoutExpired); now continues, chunk cache resumes.
   Required for 65k-vector builds. Success path untouched.
5. **Chunk budget scales** (`c299234`): secs was flat 400 regardless of chunk
   size (0.39s/vector at 1024/chunk → legit slow chunks terminated under
   load, recorded failed, retried green). Now
   `max(secs, ceil(nvec/nchunks)*2.0s)`; small builds unchanged. Only kills less.
6. **Numba-fail fallback** (loop 12): ENGINE=numba with numba missing fell to
   slow silently; now falls to the table engine.
7. **compose t= prefixes** (`5299e24`): elapsed timestamps on restart/rung
   prints (behavior-neutral strings). Enabled the add8 autopsy below.
8. Instruments (all force-added, docstring-first): `scratch/warm_proto.py`,
   `scratch/cone_probe.py`, `scratch/simvec_numba.py`, `scratch/nb_diff.py`
   (incl bundle self-test). `scratch/gray_check.py` used and deleted.

## What failed (measured, reverted or shelved — do not re-derive)

- **Gray-code contiguous chunks** (reverted): 31.47s vs 30.94s strided. Strided
  spreads hard vectors evenly (load balance); contiguous concentrates them.
  Lesson: order for BALANCE first, adjacency second.
- **Cone-restricted seeding** (reverted): 31.06–32.55s vs 31.8–32.1 baseline.
  Seed evals are a small fraction (cascade + fixed costs dominate); the
  per-vector cone filter eats the savings. Two bugs caught en route: sort by
  gray-DECODE position (not gray code) for adjacency; chunk keys must carry
  order tags + scans scoped to current keys.
- **Worker-count sweeps**: 8 far worse (55–58s), 20 tied with 16. 16 stays.
- **add8-flat compose autopsy** (`scratch/add8_run.log`, 27KB kept): 1122s,
  31 dead rungs on the pre-rewrite recipe — no cross-rung memory (long-1
  re-dies short-1's OPEN cell, 27s), late OPEN detection (142s rungs),
  ground-search radiating x609→4504, final order-cycle raise. MOOT: recipe
  went green via bands (`17460d0`); fix logged as wanted-list, correctly
  unshipped (no failing witness to verify against).
- **cpu4 probe**: hierarchical path, no grind found; first attempt fork-bombed
  (missing `__main__` guard, own Temp script only, cleaned). Every probe gets
  the guard before launch.
- **Parent console I/O**: 2000 prints = 0.04s. Rejected, observability kept.

## Files touched

Tracked mods: `simvec.py` (+_warm/+_expose only, default path byte-identical),
`scratch/verify_par.py` (chain, single-run, numba branch, budget scaling,
fallback), `scratch/hier_verify.py` (staging continue), `compose.py` (t=
prefixes only), `notes/to-ga-agent.md` (Notes 6–8 outbox), `LOG.md`,
`MORNING-REPORT.md` pending (§next). New tracked instruments listed above.
Test copies (add8merge_t*, alu1merge_t*, cpu4merge2_t*) created and deleted;
caches cleaned. Restored GA bytes once (`add8bands/merge.pkl` recompute race).

Never touched: `sim.py` semantics, `evolve.py`, `evo_*`, `compact*`,
`memo.json`, `rig_verify.py`, `sweep*`, `mkref.py`, `ref*`, `verify2.py`,
`diffwhy/simwhy.py`, GA processes/recipes (`add8b*`, `alu8.txt`), `build.*.bak`.

## What next (priority order)

1. **Pending operator decision: `REDSTONE_COMPOSE_SECS` default 600.**
   Default 0 = unbounded ladder (the 1122s was possible only for this reason).
   One-line change, GA gets veto note. Awaiting explicit word — do not ship
   silently (shared policy).
2. **Router ladder-memory** (fatal-OPEN memory, early abort on repeat OPEN,
   bounded ground radius): implement ONLY against the next grinding recipe.
   Wanted-list logged; witness required.
3. **alu8 merge sweep** when GA lands the merge pkl (new recipe `7b1fca1`):
   first exhaustive sweep with warm default; expect ~10+ min at 10+ inputs.
4. **Numba default? NO** until decisive data (tied walls; needs best-of-3
   showing >20%). Stays opt-in.
5. **Guard duty**: `--quick` heartbeats (~4 min), full coldstart after any
   sim/verify commit, MORNING-REPORT section at window end.
6. Operator items (not mine): paste `build_alu4full.schem`; stale
   `build_alu4*` deletions; cpu4 lane stays GA's.

## Gates (in order; first failure stops)

    python scratch/mkref.py                    # ONLY after sim.py/simvec.py commit
    python scratch/diff_engine.py              # ALL IDENTICAL
    python compose.py                          # buffers ok
    python scratch/compose_check.py            # 144/322/224/214
    python scratch/nonhier_suite.py            # 6/6
    python scratch/hier_verify.py recipes/alu1.txt   # 32/32
    python scratch/verify_par.py scratch/alu4merge_g.pkl recipes/alu4.txt 16 400 0 16  # 1024/1024
    python scratch/coldstart.py                # 15/15 (or --quick for 14/14)

Fresh-path copies for honest timing (new pkl path voids chunk cache);
`git checkout --` never on foreign files; LOG append-only. Second agent live
in tree: re-earn `diff_engine` on new HEAD, expect timing noise.
