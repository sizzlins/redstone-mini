# Handoff — redstone-mini (2026-09-26, 3D Attempt 1)

## Goal (evolved)
1. Phase 1 port grid → DONE, PR #1 merged.
2. Phase 2 routing → lanes/trunks/relays walled → shipped maze per-hop +
   master boosters + bridges + astar cap + two-tier rip-up. PR #2 MERGED
   (`0e686a5`).
3. Single-lever panel (DECIDED: ship with ceiling) → MERGED in PR #2.
4. CPU builds (all 9 .txt green) → flat family
   exhausted with data. Owner DECIDED 3D. No more flat mechanisms.
   (The old "single lever everywhere" wording on this line was an
   over-generalisation; XOR builds carry 2 per input — see below.)
5. Sim correctness (shipped): lamp pointing rule + `sim_pulse` proofs.
6. Mechanics research (done): `scratch/redstone-mechanics-report.md`.
7. 3D router (IN PROGRESS, this session): Attempt 1 = 3D *wires* only, tiles
   stay flat. Approved corrections: per-level guards, slope-only coupling,
   supports stamped once on the winning path, repeaters keyed (x,y,z) and
   legal on pillars.

## Current state
- **Branch `phase2-design`** (ahead 22, behind 1 — sync still needs a force
  decision). Tracked tree CLEAN; everything below is committed.
- **Commit chain this session:** `b0e4788` handoff → `33f3f2a` 3D Attempt 1
  (6-dir A* escape router, per-level guards, priced level changes, pillar
  cover, SHORT3D, perf, determinism) → `f49061e` bridge slope guard →
  `c213e2b` handoff correction → `558ea86` single window on post-rip retries →
  `b0f0867` un-stamp a failed bridge hop → `2c03602` cover pass walks a chain.
- **Suite green** (re-verified after every commit): `recipe.py`, `sim.py`,
  `serve.py --check` (demo 246), `layout.py` (ports / or-lever / panel /
  bridge / **3d ok**).
- **Small .txt all green**: `example_and` 0.1s/156,
  `example_2gates` 0.2s/246, `latch_sr` 0.2s/216, `example_xor` 0.2s/164.
  **The "single lever per input" claim is CORRECT for AND/OR builds and WRONG
  for XOR builds** — the canary at `layout.py:1607` used only
  `y1 = a AND b / y2 = a AND c`, so XOR was never counted. The XOR tile
  stamps a side lever per input (`layout.py:1020`) and rings those levers'
  neighbours (`1023`), so a routed wire cannot reach the port and the local
  lever is the only source. Result: **2 levers per input on every XOR
  build** — 4 / 9 / 26 levers for example_xor / alu1 / alu4, i.e. the panel
  promise is off by **2.6x** on alu4 (16 of its 26 levers are tile levers,
  8 XOR tiles x 2 inputs; the parser does NOT constant-fold `X XOR 0`, so
  `S0 = X0 XOR 0` emits a tile too). Removing the side levers was measured:
  `SIM MISMATCH` on a=1,b=1, so they are load-bearing. Fixing this means
  letting a routed wire reach the XOR input port (ring redesign), not
  deleting a line. `layout.py` now PRINTS the miss every run (`xor-lever
  MISSED the panel bar`); the assert comes with the fix.
- **Flat byte-identity still holds** after every commit:
  `b1896abd3762dd99` / `777948c5fc963e20` / `7525f9fd37ae316e`, identical to
  pre-3D baseline and across processes.
- **LADDER VERDICT (the gating number): 3D finishes NO dense build yet.**
  - **micro1: RED.** 36/36 attempts now produce a *complete* build
    (1963–3035 blocks) — the router no longer fails to route — but **every one
    is rejected by the sim: `sim not settling`** (a live-wire loop; e.g.
    `((5,1,12),13), ((5,1,13),14), ((5,1,14),15), ((6,1,12),12)…`). Different
    failure class than before: this is an electrical defect with the evidence
    printed, not a routing wall.
  - **micro1 is UNVERIFIED — DO NOT COUNT IT TOWARD THE ACCEPTANCE BAR.** It
  was green (`41.9s ticks=36 blocks=1963 y>=2=90 dupInputLevers=none`) **only
  under the buggy retry discipline**, where exactly one task per layout ever
  reached the 3D pass. Proven, not assumed: micro1's green seed (seed 0) made
  **3 three-D searches**, and pass 2 only runs when pass 1 exits via the
  exhaust-break — so that build depended on the under-trying bug. With the
  deferral in (`12dd3c9`), **no seed is green**:
  | seed | result with deferral |
  |---|---|
  | 0 | layout FAIL `lamp spot taken for Y at (222,12)` |
  | 1 | sim not settling (196 elevated) |
  | 2 | FAIL `no route for S: (36,13)->(50,17)` (114 3D searches) |
  | 3 | sim not settling (257 elevated) |
  | 4 | SIM MISMATCH x2 |
  | 5 | SIM MISMATCH x2 |
  That is **information, not regression**, and it is why the bar is not met
  yet: the previous "green" was measuring the bug, not the router.
- **The ground SHORT is FIXED and it was not the search** (`c321674`). Root
  cause: `stamp_wire` refused a cell that *holds* a foreign wire but not one
  that merely *side-touches* a foreign net. A\* guarantees routed paths never
  do that, but every non-searched stamp did: output taps, bank stubs, tile port
  rows, XOR side wires, the cover tail. Proven by provenance, not guessed:
  `SHORT: m0 touches Y at (223,1,13)->(222,1,13)` — m0's cell was in its
  recorded routed path (#135), Y's cell was in **no routed path at all**; Y is
  micro1's output and x=222 is the far east end, i.e. the output lamp's
  zero-wire tap, stamped after routing so no route could avoid it. Both cells
  are routed-path cells (not cover-tail: a tail only exists within 12 cells of
  the goal, and W's only phase-1 cell is its south-edge bank stub), so the
  search was right and the stamp was wrong. Fix: the adjacency guard in
  `stamp_wire` (one place, covers every non-searched stamp) plus the output
  tap dodging adjacency. Flat builds unchanged — hashes still
  `b1896abd3762dd99` / `777948c5fc963e20` / `7525f9fd37ae316e`.
- **The escalation fix is in** (`12dd3c9`): exhausted tasks are deferred in a
  list and the pass keeps draining, instead of abandoning the pass so only one
  task per layout ever reached 3D.
- **micro1's "sim not settling" was a BUDGET artifact, not an oscillator**
  (measured, `6ae2a74`). The sim capped settling at 500 ticks / 20000 steps; a
  dense build legitimately needs more. Raise the caps and the same build
  settles in 0.4s with `ticks=36`. Caps are now env knobs defaulting to
  5000 / 300000, cost ceiling ledgered. **Still marginal**: seeds that settle
  do so at ~87-99 elevated cells while 147-257 elevated cells still exhaust the
  raised caps, so the budget likely scales with 3D content — unproven, and the
  next thing to check before trusting any "not settling" on a dense build.
- **RETRACTED — do not re-derive this.** I diagnosed micro1 as "a real ring
  oscillator in the router's topology" from a churn heuristic (cells changing
  value ≥3 times). That inference was **wrong**: in a converging system a cell's
  value can change many times as its neighbours settle, so churn is not
  evidence of oscillation. The traced 16-node ring is the LATCH's cross-coupled
  NOR pair — legitimate, and present in green `latch_sr` too.
- **POST-deferral search-phase breakdown (re-taken; the old numbers are
  void).** The pre-deferral "3D = 0.9%" was measured at 19:17, two hours
  before `12dd3c9` made 3D reachable — it described a router that was not
  trying. Re-measured: micro1 s0 266 searches (86.8% flat/post-rip, **1.9%
  3D**), micro1 s1 147 (75.5%, **2.0%**), alu1 s0 **3842 searches in 300s
  unfinished (98.6% flat/post-rip, 0.6% 3D)**. **Bounding the 3D escalation
  would buy ~1%** — the cost is flat re-litigation after rip-ups.
- **Search budget added** (`3862eee`, `REDSTONE_SEARCH_CAP`, default OFF so no
  behaviour change). Raises the NORMAL error, so the debug dump still lands and
  a census can read it. Makes a dense attempt bounded: alu1 seed 1 goes from
  >300s to **18.3s** at cap 700; micro1 (147 searches) is unaffected.
- **alu1 census, bounded, 6 samples at grow 0 (~20s each) — and the deferral
  did NOT change the failure set** (the owner's prediction that it would
  "change completely" is NOT supported):
  | seed | routed | unreached | failing nets (first 6) |
  |---|---|---|---|
  | 0 | 34 | 8 | A, B, OP0, o1, o2, t0 |
  | 1 | 32 | 10 | A, AB, OP0, U, o1, o2 |
  | 2 | 33 | 9 | A, B, OP0, U, o1, t0 |
  | 3 | 33 | 9 | AB, B, OP0, U, o2, t0 |
  | 4 | 33 | 9 | AB, B, OP0, U, o1, o2 |
  | 5 | 32 | 10 | A, AB, B, U, o1, o2 |
  Totals **197 loads routed / 55 unreached**, all 6 seeds hitting the cap, so
  these are **lower bounds**. Stable across seeds: `OP0` 6/6, `o1` 5/6,
  `o2` 5/6, `U` 4/6, `B` 4/6, `AB` 3/6, `A` 3/6. **Gate nets fail as
  stably as input nets** (`o1`, `o2`, `U`, `AB`, `t0`), and they overlap the
  pre-deferral census — so **spine-on-top as an input-only mechanism still
  does not cover alu1.** Attempt 2's scope must either generalise the spine to
  any net, or be two mechanisms.
- **PERF: router is 1.7x faster (`812c464`, `7626779`, `c3db58a`)** — three
  hoists, all verified behaviour-preserving, not just faster:
  | what | why it was slow | now |
  |---|---|---|
  | coupling predicate | re-probed ~12 neighbours per **candidate** (10.1M calls, 63M `dict.get` on alu1 = the entire layout cost) though it depends only on the cell + wires + support | one `forb` set per search, built from the **foreign** side |
  | `ok()` | probed solid + rings + sup (3-6 lookups) to reach three `return False` exits | one `hard` set; coupling test inlined (was 10M calls) |
  | `forb` build | scanned every foreign wire in the build (790 builds, 7.5M `set.add`, 12% of layout) | windowed to the search's own margin box ±1 |

  | workload | before | after | |
  |---|---|---|---|
  | alu1 s1 (cap 700) | 18.3s | **10.65s** | 1.72x |
  | micro1 s1 | 1.10s | **0.63s** | 1.75x |
  | `layout_retry(micro1, 3 tries, verify)` | 8.70s | **5.59s** | 1.56x |

  **`REDSTONE_XCHECK=1` is the proof, and it earns its keep**: it runs the old
  predicate beside the hoisted one on *every* candidate and asserts
  biconditional equality. It caught three inversion bugs I would otherwise
  have shipped — the support cell belongs UNDER the foreign upper, the y=1
  candidate sits at `cy-1`, and the junction gate reads the **foreign**
  column. Green on micro1 s0/s1 + alu1 s1. Keep it green when touching `forb`.
- **PERF: measured, then declined.** A settling `sim_verify` is **0.03s**
  (example_2gates, 4412 `dust_lvl` calls) — the sim is irrelevant next to a
  multi-second router, so `dust_lvl`'s ~32 tuple allocations per call were NOT
  worth touching. micro1's 1.8s vector is 300k steps of oscillation, a
  symptom of the bug, not a hot path. Space: `flips` is keyed by cell, so it
  is O(cells) not O(steps) — no memory win available either.
- **PERF: one hoist tried and REVERTED** (`7626779`): building `forb` per route
  instead of per search gained nothing (11.13 -> 11.17s) because the flat
  post-rip phase that is 98.6% of all searches uses a single margin window,
  so there is nothing to share. Kept out on purpose.
- **The next speed lever is algorithmic, not constant-factor**: 790 searches
  x ~12.8k candidates for 42 loads, 98.6% of them flat post-rip re-litigation.
  Cutting that means fewer searches (path reuse on retry) or smaller windows
  (a stronger admissible heuristic) — both change *which* path wins a tie, so
  they break flat byte-identity. Needs an explicit call, not a drive-by.
- **micro1's oscillator: the kicker is TILE geometry, not the router.**
  Traced via the churn set (after `9508bda` made it block-aware): a 16-node
  cycle through the LATCH's cross-coupled NOR pair, torch (78,15) <-> (81,14),
  attaches (77,15)/(81,15). Their neighbourhoods hold foreign nets **R at
  (76,15)** and **S at (81,16)** — but `(81,1,16)` is the latch's OWN `Sdust`
  stub (`[(ox+4,gz+3),(ox+4,gz+2),(ox+4,gz+1)]` with ox=77, gz=15), not a
  routed wire. **No search constraint could refuse it.** The ring is the
  victim; the real oscillator is upstream (whatever makes S toggle). Four
  router-constraint attempts were made and all four were apparatus bugs or
  mis-framed hypotheses (no-op; too broad — cost 5 seeds and 6 flat blocks;
  1-cell walk; 2-tuple vs 3-tuple compare). Reverted. **Do not attempt a
  fifth without a new hypothesis** — the constraint belongs in the tiles.
- alu4 / ctrl_decode / cpu4: **never measured.** Stage-1 reads are ~2s each.

## Method note (the part worth keeping)
- **540s → 113s came from fixing two real bugs, NOT from the margin trim.**
  `try_bridge` left orphaned elevated dust when a hop failed (the OPEN that
  made all 36 attempts redundant), and the cover pass walked a tree while
  assuming a chain. Both were found by reading failures, not by tuning.
  "Read the failures, don't tune" is the method that worked.
- **A diagnostic that prints leftovers is not a diagnostic — and a wrong
  diagnostic is worse than none.** Three layers of this, in order:
  1. `sim not settling` printed `live` (leftovers at timeout). On a
     not-quite-settling build that is a monotone decay gradient naming nothing.
  2. I "fixed" it to print the churn set + a same-level/slope edge split. That
     is a better message and it still pointed at a phantom, because churn ≠
     oscillation. A diagnostic must be validated against a case where you
     already know the answer.
  3. The actual fault was one layer up: the *budget* that decides "not
     settling" was a constant sized for small builds. When a verdict is
     "impossible", check the threshold before theorising about the system.


## Method note (the part worth keeping)
- **540s → 113s came from fixing two real bugs, NOT from the margin trim.**
  `try_bridge` left orphaned elevated dust when a hop failed (the OPEN that
  made all 36 attempts redundant), and the cover pass walked a tree while
  assuming a chain. Both were found by reading failures, not by tuning.
  "Read the failures, don't tune" is the method that worked.
- **A diagnostic that prints leftovers is not a diagnostic.** The original
  `sim not settling` message dumped `live` — whatever was lit at timeout, which
  on a ring oscillator is a monotone decay gradient naming nothing. The user's
  correction was right and is now enforced in code: the raise reports the
  churn set (cells that kept changing after everything settled) plus the
  same-level/slope edge split, which is what makes the class question
  answerable at all.

- **Perf, measured (quiet machine, micro1 single-shot, grow 0):** 2.3s/240
  searches (flat baseline) → 3.2s/234 searches. Per-search cost is flat
  (~10ms); the earlier "3x slower" was route-attempt count, and the two bug
  fixes below removed most of it. **micro1's full 36-attempt budget: 540s →
  113s.**

## What changed (newest last)
1. **Cover pass walks a chain, not a tree** (`2c03602`) — the stub-tail walk
   appended cells in *discovery* order, so consecutive entries could be two
   cells apart (`(114,1,13) -> (114,1,11)`). `_straight3` still calls that
   triple collinear and `place_rep` died on `KeyError: (0,-2)`. Pre-existing
   bug, newly reachable because 3D paths make the tail walk find cells.
2. **A failed bridge now un-stamps itself** (`b0f0867`) — `try_bridge` relied
   on the caller raising (discarding the layout). The two-pass loop keeps going
   after a failed task, so half-placed elevated dust survived and the next pass
   died on `OPEN (unconnected dust)`. That OPEN was making all 36 attempts
   redundant: 540s → layouts that finish in ~3s.
3. **Single window on post-rip retries** (`558ea86`) — windows are nested
   (None ⊇ 40 ⊇ 12), so a narrower window finds a *shorter* path when it finds
   one (12 won 16/17) but can find nothing. A retry needs room, so it takes the
   single middle window. micro1 searches 642 → 234, route attempts 214 → 10.
4. **Bridge slope guard** (`f49061e`) — `bridge_free` never checked slope
   coupling, so a hop could lay elevated dust that slope-links a foreign ground
   wire (`SHORT3D: W slope-links S`). Additive, three self-check asserts.
5. Earlier 3D work: 6-dir A\* (`_H=3`, `_STEPCOST=4`), flat-first two-pass
   scheduling (`_PASSES=2`, env `REDSTONE_3D_PASSES`), per-level guards,
   slope-only coupling, supports stamped once on the winner, booster cover on
   straight runs at any level, repeaters keyed (x,y,z) with a support assert,
   SHORT3D checker, `stamp_wire` port exemption, `export.py` repeater (x,y,z),
   determinism pins (A\* heap key, margin order, bridge candidate `p` tiebreak),
   perf refactor (`near`/`gexp` sets, maintained `cond`/`condg`/`aircells`,
   no O(blocks) rebuild per rip).

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
1. **Re-census alu1 under the deferral** (`12dd3c9`). The old census is a lower
   bound taken while 25 nets were never attempted, so Attempt 2's scope is still
   unsettled — the owner's prediction that the failure set changes completely is
   consistent with everything since. Write Attempt 2's scope from THAT census.
2. **Settle the sim budget question on dense builds.** Seeds settle at ~87-99
   elevated cells and exhaust the raised caps at 147-257, so "not settling" on
   a 3D-heavy build is still not trustworthy. Either scale the budget with
   build size or report a distinct "budget exhausted" verdict — do not read
   either as a router fault until this is settled.
3. **micro1's three residual failures under the deferral**, in the order the
   evidence suggests: seed 0's `lamp spot taken for Y` (the output tap has no
   free direction once adjacency counts — the tap is stamped after routing, so
   it must be *reserved* in phase 1 rather than dodge), then the SIM MISMATCH ×2
   seeds, then `no route for Q`. micro1 counts toward the bar only when it is
   green *with* the deferral in.
4. **Stage-1 reads for alu4 / ctrl_decode / cpu4** (~2s each): one of them may
   already pass, which would change the priority order.
5. **Sync remote** — ahead ~30, behind 1; needs explicit force-with-lease
   approval. Nothing at risk locally.
6. **Do NOT:** count micro1 toward the acceptance bar while it is green only
   under the buggy retry discipline; change shipping `layout_retry` defaults
   (12×3 is a product decision — the ladder harness uses 1×1 then 12×3, a test
   choice); run dense builds in the foreground; treat a "not settling" verdict
   as a system fact before checking the budget that produced it; write
   Attempt 2's scope from a census taken under the old loop; compare timings
   across runs that die at different walls or on a loaded machine; merge
   `scratch/` or the untracked plans.


