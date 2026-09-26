# Handoff — redstone-mini (2026-09-26, 3D Attempt 1)

## Goal (evolved)
1. Phase 1 port grid → DONE, PR #1 merged.
2. Phase 2 routing → lanes/trunks/relays walled → shipped maze per-hop +
   master boosters + bridges + astar cap + two-tier rip-up. PR #2 MERGED
   (`0e686a5`).
3. Single-lever panel (DECIDED: ship with ceiling) → MERGED in PR #2.
4. CPU builds (all 9 .txt green, single lever everywhere) → flat family
   exhausted with data. Owner DECIDED 3D. No more flat mechanisms.
5. Sim correctness (shipped): lamp pointing rule + `sim_pulse` proofs.
6. Mechanics research (done): `scratch/redstone-mechanics-report.md`.
7. 3D router (IN PROGRESS, this session): Attempt 1 = 3D *wires* only, tiles
   stay flat. Approved corrections: per-level guards, slope-only coupling,
   supports stamped once on the winning path, repeaters keyed (x,y,z) and
   legal on pillars.

## Current state
- **Branch `phase2-design`** (ahead 17, behind 1 — sync still needs a force
  decision). Tracked tree: `layout.py` + `export.py` modified, UNCOMMITTED
  (3D Attempt 1 + perf refactor). Everything else reverted/clean as before.
- **Suite green** (re-verified this session): `recipe.py`, `sim.py`,
  `serve.py --check` (demo 246), `layout.py` (ports / or-lever / panel /
  bridge / **3d ok** — new check).
- **Small .txt all green, single lever per input** (XOR keeps its two tile
  side-levers, exempt by geometry): `example_and` 0.1s, `example_2gates` 0.2s,
  `latch_sr` 0.2s, `example_xor` 0.2s.
- **Flat byte-identity PROVEN**: build hashes for the 4 small recipes are
  identical to pre-3D baseline (`b1896abd3762dd99`, `777948c5fc963e20`,
  `7525f9fd37ae316e`) and identical across 3 separate processes. This is the
  safety property everything else leans on — keep it.
- **Dense still red**: micro1 single-shot now dies at `T0 (108,13)->(122,14)`
  (it used to die at `T1 (126,12)->(196,12)`). T1 and Q — the two goals the
  handoff recorded as sealed — now route, via 3D. alu1/alu4/cpu4/ctrl_decode
  not re-measured this session (background ladder only got micro1 + alu1
  start before it was killed).
- **Known red with a named cause, now FIXED**: `SHORT3D: W slope-links S at
  (53,1,15)->(53,2,16)`. `bridge_free` never checked slope coupling, so a
  bridge could lay elevated dust that slope-links a foreign ground wire. Fixed
  additively in `bridge_free` (`cond=` param + one guard loop) with three
  self-check asserts that fire on hand-built cases. Consequence: micro1's wall
  moved from `T0` to `Q (73,14)->(124,12)` — the T0 and Q "escapes" existed
  only by shorting, so they were never valid builds (sim would have failed
  them). Correctness kept, no valid build lost.

## What changed (newest last)
1. **3D Attempt 1, uncommitted**: 6-dir A\* (`_H=3`, level change costs
   `_STEPCOST=4`), flat-first two-pass scheduling (`_PASSES=2`, env
   `REDSTONE_3D_PASSES`), per-level guards (y≥2 ignores tile columns/rings/
   torch-hug), slope-only coupling in both directions (`touches_foreign`),
   supports feasibility-checked in search and stamped once on the winner,
   `sup` pillar map, booster cover on straight runs at any level
   (`_straight3`/`_cover_gap`), repeaters keyed (x,y,z) with a support assert
   (`_has_support`), SHORT3D checker, OPEN trace slope rules, `stamp_wire`
   port exemption, `export.py` repeater keyed (x,y,z).
2. **Three bugs found and fixed while building it** (all mine, all caught by
   diffing the route sequence against baseline, not by reading):
   - Inverted torch-hug guard (`for/else` made it allow hugging and reject
     clean cells) — this broke the flat path outright, latch_sr 0/26 green.
   - `stamp_wire` ring-checked the router's own ports. `astar` must start and
     end on tile ports, which sit inside rings by construction; stamping must
     agree or a legal route dies at its own endpoint (`W hits guarded`,
     `T0 hits guarded`).
   - Per-route conductive-set rebuilds and per-rip `blocks` list rebuilds
     (O(n²)) — see perf below.
3. **Perf refactor (uncommitted)**: `far()` + 2 generators per candidate
   (5.3M calls) → precomputed `near`/`gexp` set lookups; `air` flag
   O(len(wires)) per search → maintained `aircells`; per-route conductive-set
   unions → maintained `cond`/`condg`; rip-up no longer rebuilds `blocks`
   (pillars live in `sup`, materialized once); 8 vertical-coupling lookups per
   flat candidate → 1 `airstrip` lookup; `junctions` only consulted on a
   confirmed foreign wire. dict.get 71.6M → 40M on micro1.
4. **Determinism pinned** (was a handoff-known repro bug): A* heap key keeps
   the 2D projection then the 3D cell; margin candidate order is an explicit
   stable sort; `try_bridge` candidate sort gained `p` as final tiebreak.
   Three processes now produce identical builds.

## What failed (with evidence, no theory)
- **Flat dense delivery: still exhausted, unchanged** (handoff item 4). 3D is
  the only direction tried; it moves walls but does not close micro1.
- **The 3D router is ~3x slower, and NOT because searches got expensive.**
  Controlled, same session, quiet machine: micro1 single-shot baseline **2.3s
  / 240 A\* searches** vs 3D **6.9s / 642 searches**. Per-search cost is
  essentially flat (9.6ms → 10.7ms, +11%). The whole 3x is **route attempts:
  80 → 214**. The 4 small builds are unchanged (0.049s → 0.045s, 36 searches
  both) because they never leave the ground.
- **Search breakdown (the number that matters), micro1 single-shot:**
  214 route() attempts × 3 margin passes = 642 searches —
  **94.4% flat/post-rip, 4.7% flat/first-attempt, 0.9% 3D.** So the 3D pass
  is ~1% of the work, and the margin ladder burns 2 of every 3 searches
  (the Manhattan early-exit essentially never fires in a maze).
  **Consequence: windowing the 3D pass can win at most ~1%.** The real cost is
  flat searches re-run from scratch after every rip-up — there is no
  memoization of "flat cannot do this (net, src, dst)".
- **RETRACTED, do not repeat**: an earlier handoff revision said the 3D router
  was "43x slower" (103.9s vs 2.4s). That measurement was taken on a loaded
  machine (a background process was still alive). The real ratio is 3.0x. Also
  retracted: "2.5-3x faster per unit work" — that compared two runs that died
  at different walls, which says nothing about speed. **Never compare timings
  across runs that die at different walls, and check for stray load first.**

- **Bridge slope coupling**: `bridge_free` checks wires/guard/solid/repeaters
  but not dy-coupling, so bridges can create shorts the 3D checker rejects.
  Caught live as `SHORT3D: W slope-links S`.
- **Seeded retry cost is unchanged and untouched by request**: shipping
  `layout_retry(verify=True)` = 12 seeds × 3 grows ≈ up to 36 layouts × ~100s
  on dense. Probe harness uses `tries=3, grows=1` instead.

## Files touched
- **Tracked, modified, UNCOMMITTED:** `layout.py` (3D Attempt 1 + perf +
  determinism + `3d ok` self-check), `export.py` (repeater keyed (x,y,z) so a
  pillar repeater renders; the 2D `repinfo` crashed with `KeyError`).
- **Tracked, unchanged:** `sim.py`, `core.py`, `recipe.py`, `serve.py`,
  `debug.py`, `PONYTAIL-DEBT.md`, all `.txt`, `handoff.md` (this file).
  `PONYTAIL-DEBT.md` does **not** yet carry the 3D rows — the new ceilings
  (`_H=3`, `_STEPCOST`, one 3D pass, `_PASSES`) are ledgered only here.
- **Untracked (never merge):** `docs/plans/2026-09-26-{deterministic-input-
  lanes,input-port-corridors,single-lever-panel,spine-fed-input-distribution}.md`.
- **Gitignored probes (new this session, `scratch/`)**: `probe_3d_*.py`
  (latch/open/seed/price/panel/micro1/phys/rep/why/route/h/prof),
  `probe_determinism.py`, `probe_prof.py`, `probe_seq.py`, `bench.py`,
  `ladder.py`, `ladder_dense.py`, `fix_loop.py`, `loop_orig.txt`,
  `layout_head.py`, `seq_*.txt`, `ladder3d.log`.
- **Not committed by policy:** the 4 untracked plans, all of `scratch/`.

## What next (in order)
1. **Committed next, in this order, measuring between:**
   a. `bridge_free` slope guard — additive only, reject a bridge whose dust
      slope-couples a foreign net. Do not touch bridge emission or the dust
      plan (flat byte-identity depends on it). Measure: micro1 single-shot +
      suite.
   b. Window the 3D pass — window sized from the flat pass's blocking frontier
      bounding box + generous margin (NOT a fixed radius; measured escapes are
      24–40 elevated cells). One pass, not the 12/40/None ladder. Keep-or-
      revert: if a seal full-field 3D solved becomes unroutable, revert and
      report which sealer.
2. **Measure before optimizing** (owner question, still open): where do the
   1740 searches actually go — flat-first attempts vs 3D attempts vs
   re-attempts after rip-up? If every re-route re-proves "flat can't do this"
   from scratch, memoizing that per (net, source, goal) may dwarf the window
   win. Count by phase first.
3. **Then Attempt 2** (spine-on-top) as its own attempt/diff — do not fold it
   into Attempt 1.
4. **Sync remote** — branch diverged (ahead 17, behind 1); needs explicit
   force-with-lease approval. Nothing at risk locally either way.
5. **Do NOT:** change shipping `layout_retry` defaults (12×3 is a product
   decision); fold spine into the 3D diff; run dense builds in the foreground
   (background + 600s-silence kill, `cmd /c start /b ... > log 2>&1`);
   compare builds across processes without the pinned candidate order (done
   now, keep it); trust mental tile coordinates (`debug.py` + dumps); merge
   `scratch/` or the untracked plans; compare speed across runs that die at
   different walls.
