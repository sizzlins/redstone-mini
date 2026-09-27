# Handoff — redstone-mini (2026-09-27, vanilla gaps closed: lamp/comp/burnout)

> **Read this section first.** It is the state of play; everything below is
> the detailed history, kept for the evidence.

## Goal

Ship a generator whose output is **100% vanilla Minecraft compatible** — every
build is exported to `.schem` and pasted into a real world, so the simulator is
a *shipping* gate, not a design aid. A false green is a broken build in
someone's world.

In order: (1) make the sim trustworthy against the wiki, (2) make the tiles
correct under those rules, (3) only then make the dense builds
(`alu1/alu4/cpu4/micro1`) generate.

## Current state

Branch `phase2-design`, **75 ahead / 1 behind** `origin` (remote sync needs
explicit approval). Tree clean apart from untracked plan docs. HEAD `d95460f`.
Suite green: `recipe.py`, `sim.py` (now with `dlatch`, `pointing-mirror`,
`lamp-sources`, `comp-side-dust` and `torch-burnout` canaries), `layout.py`,
`serve.py --check`.

**Steps 1–4 of the 100%-vanilla plan are landed and committed** (four separable
commits, each verified green in its own tree). The sim now models pointing, the
exporter now bakes wire blockstates, and the XOR panel promise holds. **Phase 3
(dense builds) is measured and unbuilt** — see the reframing row, it is the
single most important thing in this file.

**The governing discovery: this project had no external oracle.** The sim and
the layout encode no redstone *pointing* rule at all, so they agreed with each
other — layout stamped a wire end-cell beside a block, `cob_state` said
"adjacent dust powers it", the tile verified green, and both were wrong the
same way. Everything below follows from that. It is now **fixed**; the wiki
states the rule four separate ways, and the owner accepted the wiki as the
oracle in place of the in-game test.

| item | state |
|---|---|
| Router performance | **1.7x faster**, A/B'd, with a biconditional `REDSTONE_XCHECK=1` |
| `dust_points()` pointing table | landed `9512d23`, wiki-asserted for all 5 shapes, **consumed**: sim `cob_state` (`48824d9`) + exporter `wire_bid`/`export-rt` (`0421c54`) |
| AND tile `~a` stub | **fixed and verified** `67987b0` (was dead under the wiki rule) |
| NOT tile input port | **fixed** `48824d9` (own E-W stub ends at `(bx-1,bz)`, points east at host; guard change skipped — cheap kill took `probe_not` to 0 flips) + pointing sim **landed** same commit |
| XOR levers | **1 per input, asserted** `32b6fc6` (side feeds are repeaters; wiki strong-side rule quoted in message) |
| Export blockstates | **fixed** `0421c54` (every wire line carries side/none states) + `.schem` round-trip check; negative control 66/66 bare-id cells fail it |
| **Dense builds � sensing was mirrored; s3 green** | ee8faf\: corner sensing unmirrored (wiki unit first), tiles funnelled, loops avoided at cover. D-latch 7/7, micro1-s3 green (2452 blocks, export-rt open). s5 1-mismatch, s4 OPEN T0 fragment remain. Corridor work still last. |
| **Tile input arrival level — FIXED 7/7** | **`32c54b6`: repeater cells are not dust.** Two faces of one root cause (the tile `del`s the wire label, the router re-added it by stepping onto the cell): seeds 4/5 double-stamped wire+repeater, so the sim modelled both — a phantom loop holding SET across hold (the world gets one block); seed 1 routed *through* the east-facing S-row repeater north-south, so the load behind it never fed. Search guard in `astar.ok()` (all searches funnel through it; XCHECK reference mirrored, green) + repeater-wins at materialization. `dlatch` canary (7 seeds, sequence + no-dup assert) landed in `sim.py __main__` same commit. |
| Census re-run (item 2) — DONE | alu1 6 seeds cap 700 post-fix: **41 NO-ATTEMPT (unchanged), 19 no-search (was 26), 1 solid, total 67→61.** Same cast eating the budget (A/B/OP0/CIN 94–501 tries), gate nets still starved. **Corridor conclusion survives.** The 1 solid (seed 2, B load on bridge-stamped cobble) is cap-order fallout, not a finding. |
| **Single-lever panel** | **VERIFIED, and now enforced electrically** (`c1fe1c5`). An input feeding N gates costs **1** lever: all 9 recipes, and the load is reachable from that one lever by walking the real net graph. Measured saving: alu4 43→10 levers, alu1 15→5, cpu4 30→7, ctrl_decode 12→3, micro1 8→4. The old bars counted *labels* only; the new one also proves no lever shorts a second net. Two negative controls fire. |
| **One-circuit-per-net** | **ATTEMPTED AND REJECTED — the check does not discriminate** (see "What failed"). The idea is right; a probe implementation of it flags `example_xor`, which the suite accepts. The invariant belongs in `sim.py` beside `dust_lvl`, not in a probe that re-derives the coupling rules. |
| Byte-identity canary | `e79bfa6d` / `b4a9cc9b` / `40730f4c` unchanged; xor **`8de8a1ef`→`59638d5c` (`32c54b6`, 332→344 blocks, y>=2 47→0)** — its old route crossed a tile repeater cell, now illegal, so it cascades flat (+12 blocks). Honest movement, same bug class. Bridge splice still fires on every D-latch seed, which the new `dlatch` canary locks. |
| **Lamp sources — 3 gaps closed** | `_lit` only fired on end/isolated dust. Wiki (+cmc engine): dust on top lights, powered block beside lights, lit free torch lights. All three now in `_lit` (+rblk/lever same sentence), each with a canary. Passing-line stays dark (both agree). |
| **Comparator sides — dust counts** | `comp_in` ignored side dust; vanilla/cmc count it at full level (subtract clock with dust sides works in-game). 3-line branch. Turned `example_xor` red on all 7 seeds (b-wire beside C2 south: side 5 ≥ rear 3 → out 0; vanilla agrees) — see layout fallout below. Side torch ignored by both ours and cmc; left alone. |
| **Torch burnout — missing, now raised** | Hunts raised `not settling`; vanilla burns the torch dark (>8 OFF-toggles/60 game ticks = 30 sim ticks). Counter + loud `TORCH BURNOUT` raise; hunts terminate vanilla-identically (dark) instead of hanging. First version (all flips, 60-window) false-fired on a healthy latch settle — evidence forced OFF-only/30-tick correction. |
| **XOR side-wall fallout — FIXED** | Layout parked b-wire beside C2's side on all 7 seeds (tile assumed "dust never counts"). All four comparator side cells now wall in `solid` as `cmpside`: search/bridge/taps route around, tile stamps already done. All 7 XOR seeds green, suite green, XCHECK green. |

## What changed

### Vanilla gaps closed: lamp/comp/burnout (`d506b74` + `8da0cb1`)

- **Method:** every claim reproduced minimally first (`scratch/vanilla_audit.py`,
  kept gitignored); wiki + cmc engine (`src/core/redstone/engine.js`, fetched
  read-only — no repo installed, not needed) as oracles. Side torch left
  alone *because* cmc ignores it too; repeater locking/delays, comp delay-2,
  containers skipped (never trigger in our builds — stated, not built).
- **Lamp (3 real gaps, all safe-direction):** dust-on-top, powered-block-beside,
  free-torch-beside all ignored. Each is a few lines in `_lit` + canary.
  Passing-line stays dark (wiki agrees); cross/dot already worked.
- **Comp sides (1 real gap, dangerous direction):** side dust ignored → false
  green where vanilla suppresses. Fixed (3 lines); turned XOR red everywhere
  (true coupling, proven by provenance: b-wire at C2 south, side 5 ≥ rear 3).
- **Burnout (missing mechanic):** counter + `TORCH BURNOUT` raise. Corrected
  pre-commit from all-flips/60 to OFF-only/30 ticks after evidence (healthy
  latch settle flips 9× total but only 4 OFFs — vanilla would not burn it).
- **Layout fallout (1 real bug, fixed):** all-four comparator side cells wall
  as `cmpside` in `solid` (new kind, inert everywhere except search/stamp/
  bridge/tap/placement walls). Exact cells only, no halo (halo would starve
  the rear feed at (9,12)). All 7 XOR seeds green.
- **Vindicated, no change:** repeater-loop latching (vanilla latches too —
  burnout is torch-only), side torch (cmc agrees), weak-block feeding dust
  (`pbs` is strong-only already), comparator formulas/facing (match wiki).
- **Render question (no fix):** lamp beside lit passing dust, dark in
  `build.html` — checked on the shipped layout across all vectors, vanilla
  agrees (passing line points away). True, no change. `scratch/lampaudit.py`.

### Sensing unmirrored + tiles funnelled (`7ee8faf` — D-latch 7/7, s3 green)

- **Root cause (failing test first): `cob_state` read block→dust instead of
  dust→block, mirroring corner/T sensing.** Symmetric shapes (line/end/cross)
  cannot tell, so the whole suite stayed green around it; the docstring
  already said dust→block. One-tuple fix + `pointing-mirror` canary (corner
  N+E, S block dark). `_lit` verified clean (checks the link explicitly).
- **Tiles+routes had tuned to the mirror** (D-latch 6/7 red on the fix
  alone): routed joins corner input stubs (parallel hug + tip turn), killing
  the east point. Fix: funnel stubs with cobble (AND/NOT/latch-R; straight
  dust reads identically either convention, so green-by-construction;
  footprints already cover; +solids move small hashes, xor pinned).
  Rejected instead: input repeaters fronting blocks (back-feed supply
  through the block into route dust = permanent latch, measured on seed
  None; S-row/XOR repeaters front dust/comps, different, safe) and
  route-end loop rejection (punishes transients: seed 4 green→oscillator).
- **Cover skips loop-closing booster spots** (ordered max→min, unwind +
  fallback; seed4 green via min-j). Loop checks traverse cobble now
  (block-mediated loops); `_loop_rep` at the end, `_closes_loop` (one BFS on
  the new pair only) at cover. Route-end stays out (transients).
- **`_snap` restores repeaters** (failed placements leaked phantoms).
  Ports check accepts east repeaters (max-j boosts tails); dlatch canary
  flags dust-involved dups only (benign cobble+cobble pillar dup exists).
- **micro1-s3 GREEN** (first ever: 2452 blocks, ticks=42, 8 vectors —
  export-rt still to close the bar). s5 1-mismatch, s4 OPEN T0 2-cell
  fragment remain; s0/s1/s2 need uncapped re-measure post-fix.

### Tap reservation retry-scoped (`c1d8daa` — s0/s1 route, then oscillate)

- **Always-on REJECTED twice.** Global tap rings moved xor@s7g1 into
  `SHORT3D: b slope-links y at (6,2,18)` — the verbatim v1 failure. Reverted
  to retry-scoped: `layout(reserve=False)` default; `layout_retry` runs one
  reserve round only after a lamp-spot failure. Green trajectories never see
  rings (hashes pinned, suite green). Reserve = tap+clearance+lamp rings with
  output family only; no wire pre-seeding (v2's poison).
- **s0/s1 route past taps** (2565/2562 blocks, detour-fat, ~1s) but SIM-FAIL
  on oscillators (churn 469/551, torch loops — needs churn-trace; new wall,
  not reservation's verdict to give). Detour bloat noted (+1700 blocks).
- **RecursionError seen once under a double-wrapped probe harness** (wrap
  assigned twice); clean retry shows normal FAIL. Harness artifact, not
  product — recorded so it isn't re-investigated.

### Fragments fed, queue deduped (`b42cc85` — s0 down two walls, now R-wall)

- **Cover feeds fragments tail-first.** Non-source-rooted entries with a
  DANGLING head (no same-net dust outside, verified on s0-Q `(96,12)`) and no
  span inside tile reversed (flow hot-to-dark); rooted/joined/span entries
  keep order (span direction is load-bearing — reversing a spliced hop would
  face its boosters backwards). s2-nOP loud-fail gone (OP tiles); s0-Q
  turn-head gone. Zero green impact (hashes pinned).
- **Duplicate queued tasks skipped at pop via O(1) Counter** (a pops×pending
  scan is quadratic on dense). s0-S routed in 8 beads with one task twice;
  twins defeated value-removal and fragmented cover's view. Green-neutral
  (no re-queues there; counts identical).
- **Checkers name cells:** OPEN reports `(cell, net)`; unboostable-gap names
  the head cell. Temporary COVDUMP used for the s0-Q autopsy, reverted.
- **Route-end loop rejection ATTEMPTED AND REVERTED.** Failing the task on a
  completed loop punished transients: D-latch seed 4 went green→oscillator
  (950 blocks) via congest-detour; revert restored 786 byte-identical. Reason:
  path cells are always rippable, so every route-completed loop may die later
  anyway — only the end-of-layout check (final topology) is sound. The
  placed-stability refinement doesn't save it (same outcome).
- **s0 uncapped trajectory this session:** budget-hit (capped) → Q cover-gap
  → OPEN S-row fragment → now `no route for R: (60,13)->(76,12)` (3D
  self-lid, 13 unroutable). S chains; R is the next wall (3D pass flies its
  own pillar into its slope — one-pass limitation, session-sized).
- **Oversight corrected:** test/probe code stays linear-or-better (BFS
  O(V+E), Counter O(1)/pop); the stuck runs were unbounded `layout()` itself
  (alu4 ~100 ms/search), now always bounded with heartbeats.

### Dense items 1–4 worked (2026-09-27, three commits, no dense green yet)

- **Item 1 — alu4 at grows=2: FAIL, joins the budget class.** Bounded
  (`REDSTONE_SEARCH_CAP=3000`, heartbeat every 200 searches): 3092 searches,
  222 tasks pending, ~100 ms/search (field scale). Placement passes, routing
  nowhere close. grows=3 not tried (bigger field, worse per-search — the
  discriminator is answered). Probe: `scratch/alu4_grow.py` (kept, gitignored).
- **Item 2 — all-or-nothing hops (`53dd91d`).** Failed `pb` now unwinds `pa`
  (entry + labels + pillars, no congest — its corridor is fine). Fires 2× on
  micro1-None (16+14 cells). Zero green impact. Does NOT close S: pocket is
  real (W spine wins; W re-wins via shortest path, congest+5 won't dislodge a
  spine). A feet-stampability guard was tried and **reverted** (fired nowhere
  that mattered; W arrives after the hop — order effect, not hop-time check).
  S wall reclassified corridor-class.
- **Item 3 — repeater-loop reject (`983e383`).** Static finder
  (`scratch/loopfind.py`) validated first: clean on 4 small + D-latch 7, fires
  only micro1-s2 `(80,1,19)`. Enforcement: one `_loop_rep` call at
  materialization (O(1) pre-check per repeater, BFS on same-net pairs only,
  first-loop exit; flat adjacency, slope-closed loops a known miss). s2 now
  fails loud naming the cell. Zero green impact.
- **Item 4 — cover floor (`97cd430`).** Per-entry 14-floor assumed a live
  source at path[0]; bridge/rip-up segments start mid-chain dark (micro1-s2
  OP split bank→(148,37) + (148,33)→tile). Cover now tiles source-rooted
  entries to 14 (unchanged) and segment entries to 0; twisty heads fail loud.
  Zero green impact (all green entries source-rooted). s2 converts SIM-FAIL
  to LAYOUT-FAIL (`unboostable gap on nOP near index 1`).
- **Still red after 1–4:** micro1-s2 needs S-loop *search avoidance*
  (end-reject burns whole layouts; router keeps closing the loop) + an nOP
  segment with a boostable head; s1 lamp-spot, s4 T0-wall, s0/s3/s5 budget.
  Next: tap reservation (old item 7), ctrl_decode n2, corridor last.

### Dense walls researched (2026-09-27, no code — triage + dumps only)

- **Triage, all bounded post-fix:** alu1 budget/97 pending; micro1 `no route
  for S: (47,16)->(47,17)` (1-cell gap, "touches W"); alu4 `AND blocked for
  A0B0` verbatim (placement unchanged by the search guard — phase 1, no
  `astar` involved); cpu4 budget/413 pending; ctrl_decode budget-like at cap
  700 (hard `n2` wall uncapped).
- **micro1 seed None — bridge churn, not raw space.** Hop log (wrapped
  `bridge_stamp`): S built 5 hops (Q 1, T0 1 alongside); every S hop reverted
  on a failed `pb`, and each left its `pa` approach path stamped
  (`(51,17)`, `(43,16)`, `(55,17)` survive in the dump as orphans). Three
  local defects: failed hops don't revert `pa`; a ripped bridge leaves its
  `solid` cobble pillars forever (rip-up dels `wires`+`sup` only —
  `bridge_stamp` put supports in `solid`); `bridged` never-retries a ripped
  hop. Final pocket (W north, tile cobble east, S-rings) is real, but the
  router dug it deeper itself.
- **micro1 seed 2 — first fully-routed micro1, SIM-FAIL Y ×2, two species.**
  (a) S-row repeater `(80,19)` + routed dust close a **non-inverting loop**
  (`(81,19)→(81,20)→(80,20)→(79,20)→(79,19)→back`). Tick-trace
  (`_run_vec(until=)`): dark at tick 6, latched hot by tick 10 — a
  booster-settling transient (west row `(77,15)=3` at tick 2) kicks it once
  and it holds. Bistable in vanilla too: **true red, sim correct.** The
  router may no longer step ON repeater cells (`32c54b6`) but may still join
  front-arm to back-arm around one. (b) nOP sustained hot (15-peaks at
  164/170/181/190,20) with OP=1: boosters can't latch (no feedback), so the
  NOT tile genuinely drives — OP arrives dark at its port (arrival decay) or
  the tile misfires. **Port-level check open.** Vector 1 in the same build is
  consistent (Q=15 correct, T1 dark = Q→T1 leg dark).
- **Corridor verdict unchanged** (alu1 41/19/1; cpu4 triage same mode) — but
  it is now one wall of four, and the last to work on: items 1–3 below are
  correctness fixes in the 0-block tradition, and micro1's routing wall is
  churn it inflicts on itself.

### Tile inputs resolved (2026-09-27, `32c54b6` — D-latch 4/7 → 7/7)

- **Root cause, one level up from both fixes:** a tile repeater cell is not
  dust, but the search treated it as free space and the emitter treated it as
  a wire slot. The tile `del`s the wire label, the router stepped onto the
  cell and re-added it. Dup cells discriminate perfectly: present in exactly
  seeds 1/4/5, absent in None/0/2/3. Seeds 4/5: wire+repeater double-stamp at
  `(78,1,17)` — the sim modelled both as a self-sustaining loop
  (77→rep→79→dust78→77), holding SET across hold; the world gets one block.
  Seed 1: the S path crossed the east-facing repeater north-south, dead-ending
  at `(78,16)=5` one cell from the back — the load behind it never fed.
- **Two guards in the two shared funnels:** `astar.ok()` refuses repeater
  cells (flat/3D/bridge all funnel through it; `reps` was already plumbed in
  for `_support`; XCHECK reference mirrored, green) and materialization emits
  the repeater only (also excluded from the `wire_bid` dust set). Verified
  surgical: pre/post block diff on seeds 4/5 is exactly minus the phantom
  wire; and/2gates/latch_sr hashes unchanged; XCHECK green.
- **Same commit:** `dlatch` canary in `sim.py __main__` (7 seeds, 5-phase
  sequence + no-dup assert) — the standing decision from the open item 1.
- **Honest movement:** xor@s7g1 332→344 blocks, y>=2 47→0 (its old route is
  now illegal; `8de8a1ef`→`59638d5c`). Bridge splice still fires 1× on every
  D-latch seed — the new canary locks that coverage.
- **Census re-run** (alu1, cap 700, seeds 0–5): 41 NO-ATTEMPT / 19 no-search /
  1 solid (was 41/26/0/0; total 67→61). Same cast (A/B/OP0/CIN 94–501 tries),
  gate nets still starved. **Corridor conclusion survives.** The 1 solid is
  bridge-cobble-on-load cap-order fallout (seed 2, B), not a finding.

### Tile inputs + panel session (2026-09-27, five commits, in this order)

- `1d42c7b` **latch: buffer the S port row so the tile can set at all.** The S
  row is 9 cells of the tile's *own* dust from the block it must power, so it
  needs level ~10 at the port — and the load *is* the port, so no bus budget can
  reach past it. A repeater at `(ox+1,gz+4)`, the only cell that still sees
  power at the guaranteed minimum. Free: it replaces a dust cell inside the
  tile's own row, so `latch_sr` is 292 blocks before and after (hash
  `03542c34`→`40730f4c`, composition only).
- `701ea5b` **routing: splice a bridge hop into one path so the cover sees the
  run.** `try_bridge` made **two** routes and the bridge's dust belonged to
  neither, so the cover never counted or boosted it — the electrical run across
  the hop was longer than anything `_cover_gap` had promised. Root cause of the
  dark-gate-input class, and invisible from the index budget because the cells
  are in no path. Free: same cells, re-partitioned (`example_xor` 332 blocks
  either way, one elevated cell fewer). Together with `1d42c7b` the D-latch repro
  goes **0/7 → 4/7**; neither is sufficient alone.
- `fb01d01` handoff for the above.
- `c1fe1c5` **canary: prove the single-lever panel electrically, not just by
  label.** `panel ok` and `xor-lever ok` both count labels, which cannot see (a)
  a lever beside wire of a *second* net — the sim powers any same-level cell
  next to an ON lever, so "one lever" and "one net" are different claims — or
  (b) loads that are not reachable from that one lever at all. The new
  `panel-wire` check walks the real net graph, crossing repeaters and the sim's
  slope links, on the AND fanout **and** on XOR (whose side feed runs elevated).
  **Two negative controls, both firing**: a lever shorting a second net, and an
  input with no lever. No product code touched; all four hashes unchanged.
- `c474ad3` **routing: assert a bridge splice is a chain before covering it.**
  `place_rep` takes a repeater's facing from the step *into* its cell, so a
  non-adjacent pair in the merged hop path would aim one the wrong way. The
  cover assumes a chain everywhere else; the splice was the one place that did
  not check. Cheap, and a wrong `_dst` order would otherwise be a silently
  wrong circuit.

### Steps 1–4, the 100%-vanilla gate (landed, in this order)

- `0421c54` **export: bake wire blockstates + round-trip check.** The exporter
  wrote a bare `minecraft:redstone_wire` for every wire cell, so pasted builds
  received dots that power nothing sideways — wire state *is* its pointing.
  `wire_bid()` formats `east/north/south/west` side/none from the one shared
  `dust_points()` table; power is never baked (game-owned). New `export-rt`
  self-check exports a real AND build, reads the `.schem` back, and asserts
  every wire's baked states equal `wire_bid`. Negative control: 66/66 bare-id
  cells fail it, so it would have caught the shipped defect.
  `ponytail:` ceiling — flat dirs only; an elevated slope link bakes as `none`
  until the game updates it. Needs a shared slope predicate if 3D ever ships.
- `48824d9` **sim: land pointing `cob_state`; tile: aim NOT input stub at host.**
  `cob_state` powered a block from any side-adjacent live dust (every cell a
  cross); it now requires `dust_points` to contain the direction. Dust on top
  still counts unconditionally. The NOT port was a bare cell the router could
  approach from the north, leaving an end cell pointing N/S that never powered
  the host (measured `cobble True->False on a=1`); the tile now stamps its own
  E-W input stub ending at `(bx-1,bz)`, which points east at the host whatever
  side the router reaches the open load `(bx-2,bz)` from. Guard change was
  **skipped**: the cheap kill took `probe_not` to 0 flips, so no `_support`
  exemption was ever needed and `layout.py:81` stays load-bearing.
- `32b6fc6` **tile: feed XOR comparator sides from repeaters, one lever per
  input.** Wiki (`Redstone Comparator`): *"Side inputs are accepted only if the
  signal received is strongly powering either side of the redstone comparator."*
  Dust never counts, so the old tile levers ringed their neighbours shut and
  every XOR input cost a second lever. One repeater per side now faces into the
  comparator with its back reading the input net (a-side via a 3-cell tile stub
  off `Adust`, b-side via one extra routed load at `(ox,gz-2)`, placed north
  because the first attempt at `(ox,gz+6)` died as `lamp-spot-taken`). Outputs
  are 15, exactly like the levers were. The `xor-lever MISSED` print is now an
  assert.
- `09e6c3b` handoff: Current-state table only.

### Earlier (unchanged)

- `812c464`/`7626779`/`c3db58a` — three perf hoists. The coupling predicate
  re-probed ~12 neighbours **per candidate** (10.1M calls, 63M `dict.get` on
  `alu1`, i.e. the whole layout cost) though it depends only on the cell and
  the wires, so it is now one set per search built from the foreign side;
  `ok()`'s three static-obstacle lookups merged into one; the build windowed to
  the search's own margin box. **`alu1` 18.3s→10.65s, micro1 1.10s→0.63s,
  end-to-end 1.56x.** One hoist tried and **reverted** (per-route forb: no gain).
- `9980750` — the lever canary now covers XOR. It had only ever exercised
  AND/OR, so **XOR was never counted** — that blindness is how
  2-levers-per-input hid inside a gate that read "single lever per input".
- `9512d23` — `dust_points()`, the one missing rule, in `layout.py` so the sim
  and the exporter will share it and cannot drift apart.
- `67987b0` — the AND tile's `~a` stub reshaped N-S→E-W so it points at its NOR
  host. Verified **both ways**: with a pointing-aware sim all four small builds
  go green; without it two of them fail.
- `76d5233`/`8c67e77`/`ee1ba3f` — handoff: perf results, the single-lever
  exemption struck, the export defect recorded.

## What failed (with evidence, no theory)

### The one-circuit-per-net check — REJECTED by its own validation (new)

**The idea is right and the implementation is wrong. Do not ship the probe.**
The hypothesis was that no net label ever spans more than one electrical
circuit — a property nothing in the project checks, and the species of both
bugs fixed this session. Built in `scratch/probe_onecircuit.py`, then run
against a **known-answer** case first:

```
KNOWN ANSWER: seed 0 PASSES the canary, seeds 1 and 4 FAIL it
  seed 0: 1 net with >1 circuit   <- passes anyway
  seed 1: 1 net with >1 circuit
  seed 4: 1 net with >1 circuit
small builds, all green in the suite:
  example_and     0 nets with >1 circuit
  example_2gates  0
  latch_sr        0
  example_xor     a -> 8 circuits   <- green in the suite, worst score of all
```

**It does not discriminate.** It flags `example_xor`, which the suite accepts,
more heavily than the failing seeds. Shipping it would have condemned good
builds while looking like coverage — the exact failure `9980750` records.

**Why it is wrong:** the false positives are all the same shape and they are
informative — `[(46,2,10),(47,3,10)]`, `[(39,2,11),(39,3,12)]`, `[(3,1,6)]`.
**y=2 and y=3 cells, i.e. 3D bridge dust.** The probe's slope-link predicate
fails to join them to the run, so every bridged net looks like it has orphan
islands. The sim connects them; the transcription of `dust_lvl` does not.

**The lesson, which is worth more than the check:** the invariant must be
written **in `sim.py`, beside `dust_lvl`, in terms of that function** — so the
coupling rule is stated once and cannot drift. A probe that re-derives the
rules is the same mistake as the four instrument bugs below, and it is the fifth
time this session that re-implementing something the codebase already
implements once has cost more than reading it.

**Validation was the only reason this was caught**, and it cost one run. Keep
doing it before shipping any new check.

### Tile inputs — RESOLVED 7/7 (`32c54b6`; the "STILL RED" below is the
pre-fix record, kept for the evidence)

This was handoff item 3 ("micro1's newly-exposed sim failure — the `LATCH(S,R)`
port convention") and it is **not** a port-convention question. `latch_sr` proves
the tile is a correct SR latch (set/hold/reset/hold, green) and `eval_net`'s
`LATCH` is a correct SR latch too. The convention is fine; the *signal* was not.

**Repro** (`scratch/probe_seeds.py`, 7 seeds, grow 0 — the minimal shape, no
dense-build routing pressure):

```
IN D, W
OUT Q
nD = NOT D
S = D AND W
R = nD AND W
Q = LATCH S R
```

**Went 0/7 → 4/7** across two commits. `latch_sr` with levers on S/R was green
throughout — that was the only difference, and it is not the tile.

**ROOT CAUSE (found, and it is not where the symptoms pointed):**
`bridge_stamp` wrote a bridge hop's dust into `wires` but never into `paths`.
`try_bridge` made **two** separate routes, so the hop's cells belonged to
neither — the booster cover never counted them and never boosted them, and the
electrical run across the hop was longer than anything `_cover_gap` had
promised. A load past a bridge then got whatever level was left over.

This is why the **cover's index budget is not the lever**, which is what
attempts 2 and 3 measured: the cells are in no path at all, so no window value
can see them. Sim ground truth on one build, before the fix: the `nD` load
(the R AND tile's input port) sat at **level 0** — a gate input simply dark, so
that AND computed `R=0` forever and the latch could never reset.

**The two fixes, and why both were needed** (neither is sufficient alone):

| commit | fix | alone | with the other |
|---|---|---|---|
| `1d42c7b` | LATCH S row gets a repeater at `(ox+1,gz+4)` | 0/7 | **4/7** |
| `701ea5b` | splice a bridge hop into one `paths` entry | 0/7 | **4/7** |

The S row is a separate, genuine tile defect: it is 9 cells of the tile's *own*
dust from the block it must power, so it needs level ~10 at the port, and the
load *is* the port — no bus budget can reach past it. Measured before the fix:
the port arrived at 2 and the row died 4 cells short, so the latch could never
set. `(ox+1,gz+4)` is forced: it is the only cell that still sees power at the
guaranteed minimum. A repeater on the set input is the textbook shape and costs
no race (only set is delayed, reset is not; the cross-coupled Q/Qb loop is
untouched — the exemption the tile comment asks for, satisfied by construction).

**Both fixes are free.** Block counts are identical before and after on all four
small builds (238 / 366 / 292 / 332): the S-row repeater *replaces* a dust cell
inside the tile's own row, and the splice only re-partitions two existing paths.
Determinism re-checked across 3 processes. Suite green; `export-rt` green.

**STILL RED — 3 of 7 seeds, and do not assume the fixes above generalise:**

| seed | failure |
|---|---|
| 1 | `SEQ MISMATCH {'D': 1, 'W': 1}` — cannot **set** (the S-row case, so a residual arrival-level path remains) |
| 4, 5 | `SEQ MISMATCH {'D': 0, 'W': 0}` — wants `Q=0`, gets `Q=1`, i.e. the latch **spontaneously set while both inputs are 0** |

**A/B'd, so this is not a regression from the fixes:** at `1d42c7b` (no bridge
splice) seed 4 never sets *at all* — Q stays 0 and S never arrives, the old
failure. The splice fixed the set path. The failure only *moved*.

**NARROWED (seed 4, sim ground truth, per phase) — a lead, not yet a cause.**
The discriminator is the *shape* of the S net, not whether it is hot — S is hot
in the hold phase in **every** seed, including the passing one:

| seed | verdict | S-net lit cells, hold phase | shape |
|---|---|---|---|
| 0 | **passes** | 60 | one clean monotone decay chain from the driver |
| 1 | fails | 58 | **forked** — two runs both at 15 from `x=34` |
| 4 | fails | 88 | **forked + a 3D elevated run** at `(39,2,11)`, `(39,3,12)` |

In the hold phase the S AND tile's inputs are dark *and its output stub reads
0*, yet 16 cells of the S net are still hot in a cluster at `(76-86, 14-17)`.
So in the failing seeds the S label spans cells no decay chain from its driver
explains. The sim raises no `SHORT` and no `OPEN`, because both static checkers
reason about **labels** — the same species as both bugs fixed this session.
**Which cell is the foreign source is not yet isolated.**

Seed 4/5's mechanism is also a genuinely hard one, not just sloppiness: a
cross-coupled NOR latch is **bistable** with both inputs low, so during the hold
both `Q=0` and `Q=1` are legal and the expectation is not determined by the
circuit — something has to perturb it, and the sim's latch-carry semantics are
part of the question.

**Do not attempt a fix for 4/5 by touching the latch inputs again** — attempt 4
(a repeater before every load) was measured to make **7/7** seeds oscillate,
which is the tile comment's power-on race. Input-side buffering is the wrong
lever for a hold-phase glitch.

**Four fixes tried and rejected on measurement** (full diff:
`scratch/tile_arrival_level_attempts.diff`; attempts 1 and 5 became the two
commits above):

| # | attempt | measured result |
|---|---|---|
| 2 | cover window 14 -> 12 | **no change** — the dead cells are in no path |
| 3 | cover window 14 -> 8 | **1/7 green** — margin, not a fix |
| 4 | repeater on the cell before every load | **7/7 oscillate**, loop through the latch's two torches |
| 5 | the same repeater ON the goal cell | **feeds backwards** — `place_rep` takes facing from the step *into* the cell |

**Instrument traps hit this session — five, and they cost more than the bugs:**

- **Do not re-implement a rule the codebase states once.** The fifth and worst:
  the one-circuit probe above re-derived the sim's `dust_lvl` coupling and got
  the slope links wrong. Write the check *in* `sim.py` beside the rule.
- **Validate every new instrument against a KNOWN-ANSWER case before trusting
  it.** The one-circuit check looked like exactly the coverage this project
  needs, and validation (one run against seeds 0/1/4 plus the green small
  builds) killed it. This is the single highest-leverage habit in the file.
- **The build is shrink-wrapped but the debug dump is not.** `layout.py:1635`
  shifts everything by `(minx, minz)`; `REDSTONE_DEBUG` is written in routing's
  `finally`, *before* that shift. Comparing the two silently reads the wrong
  tile — **three** probes were wrong this way. Recover the shift from a net only
  one tile has (`Q~qb` for LATCH); never assume 0.
- **A NOT tile is `cobble + east torch`, which is half the LATCH signature.**
  Identifying a tile structurally needs the north torch 4 east as well, or you
  will "find" a NOT or AND tile and read its rows.
- **Do not key captured paths by `id()` in an instrument.** The cover loop
  rebuilds its list every iteration, so ids get reused and two paths merge into
  one phantom — this cost the longest single wrong turn of the session.
- **Label your own probe output.** A row printed as "S tile row" was actually
  the AND tile's *input* area, not the latch's S row, and sent a whole
  investigation after a non-existent signal. Print the coordinates, or the
  reader cannot check you.
- **A "one layout passes" check hides this entire class.** The multi-seed
  version of the D-latch check killed attempts 3 and 4 on the spot. A canary
  that runs one layout is worse than none, because it reads as coverage.

### Phase 3 — every dense-build attempt, with the number that killed it

- **The spine plan (`docs/plans/2026-09-26-spine-fed-input-distribution.md`) —
  the central assumption is falsified.** It rests on "inputs own the alu1
  budget, so feed them cheaply." Measured on alu1 (6 seeds, grow 0, cap 700,
  the paired per-seed-load denominator): with the spine-vs-branch variant,
  **NO-ATTEMPT collapsed 41→11 and no-search rose 26→49** — total unreached
  loads only 67→60. The inputs stopped starving exactly as designed, and the
  freed budget was immediately eaten by *gate* nets that could no longer find
  ground (A 250 tries, B 183). It **relocates** the starvation rather than
  removing it. Root finding: the field has no spare ground corridor, so a
  spine consumes exactly the space the gate nets needed. **The binding
  constraint is total ground corridor, not input distribution.** Consistent with
  3D escalation measuring only 1–2% of searches: the field is not short of
  *search*, it is short of *space*.
- **Spine T2/T3/T4, three variants, all reverted** (same experiment at three
  settings, each verified, none landable — the suite went red every time):
  T2 alone (bank-connected tap starts) → the panel XOR goes dark (ripped tap
  orphan). T2+T3 (*every* input path unrippable) → panel deadlock
  `no route for y1/c` on every seed; unrippable delivery sealed corridors that
  gate nets used to rip open. T2+T4 (bridgeable spines + bridge-first) →
  routing restored, but gate detours were crowded into a 43-cell unboostable
  run decaying 15→2→0, i.e. a vanilla-correct sim verdict on a bad layout.
  The retry (spine-only unrippable) reproduced the T3 deadlock
  (`no route for y1`, 3D self-lid) and moved the xor canary. **Four data points,
  one shape: any unrippable input delivery on a tight field seals gate
  corridors. Do not attempt a fifth variant without a new hypothesis.**
- **Tap reservation (mechanism A) — moves the target, cannot land, NOT
  falsified.** v1 (ring the tap cell + its clearance + the lamp cell) took
  micro1 s0/s1 from a hard layout wall to a **sim** failure — the first time
  those seeds have ever fully routed — but the suite went red with
  `SHORT3D: b slope-links y at (6,2,18)->(5,1,18)`. v2 (also pre-seed the tap
  cell into `wires`, which is what the coupling check reads for the slope rule)
  fixed the slope hole but the panel self-check then failed
  `SIM MISMATCH` and **all four canary hashes moved** (xor 332→246 blocks,
  y>=2 48→7). Two corrections that survive: the reservation must cover the tap
  cell's *clearance*, not the cell (a transient probe showed the tap cells were
  still empty and the real blockers were two `nOP` wires *beside* the tap, which
  the stamp loop's adjacency guard rejects); and a y=1 ring cannot close a
  slope hole, so a reservation must also reserve through the wire channel.
- **"2 ringed load cells in the alu1 census" — cancelled, no target.** The cause
  check tests `ringed` *before* attempt-count, so a cap cannot mask it: across 6
  seeds the census reports **0 ringed, 0 solid**. The mechanism has nothing to
  fix. Do not build it.
- **alu4 is NOT a search problem, and the earlier placement read was
  incomplete.** `AND blocked for A0B0` dies in phase 1, pre-routing, with
  **0 candidate slots ever attempted** (`tried=0`): full-width bus lanes kill
  the grid rows (OP0 z=16 kills row 12; B0/A3/A2/A1 z=26–32 kill row 26) and
  bounds kill the rest (chained z=36 needs D>42, row 40 needs D>46). But
  `grows=2` *does* pass placement, so it is grow-fragile cost-scale work, not a
  structural tile defect. Verbatim identical on a `1004f53` control, so Steps
  1–4 are neutral on it.
- **micro1's S wall is seed-fragile (1 of 7), and the real wall is elsewhere.**
  Seed sweep (tries=1/grows=1, with verify): s0/s1 `lamp spot taken for Y at
  (222,12)` (a deterministic repeat, and the only seeds that route completely);
  s2 Q-wall, s3 T0-wall (3D self-lid), s4 R-wall, s5 B-wall (123 unroutable),
  seed-None S-wall. No seed reaches green. Per the standing rule no fifth
  router constraint was attempted without a named hypothesis. Both previously
  known micro1 items (the latch `Sdust` stub, the output tap) sit *downstream*
  of these walls and remain unreached — do not re-derive them.
- **cpu4 is alu1's failure mode at ~4× scale, now measured.** 6 seeds, cap 700:
  **263 NO-ATTEMPT + 5 no-search** (each failing net ≤7 tries), 0 solid/ringed.
  Most-searched nets are `OPC1`/`D0`/`D3` (122–380). No mechanism until the
  reframing above is acted on.
- **`ctrl_decode` is a routing wall, not a ~2s control** (uncapped, ~20 min):
  `no route for n2: (57,9)->(59,11)`, 668 tasks unroutable.
- **`99 unrouted` vs `41 NO-ATTEMPT + 26 no-search` reconciled** — different
  runs *and* different units: 99 is the live pending-task queue length
  (re-queued retries included) at cap-hit on seed None; 41+26 is static
  unreached *loads* summed over seeds 0–5. The denominator for any future
  census delta is **paired per-seed loads, same 6 seeds, same cap**.
- **No debug dump lands on a placement failure** (the dump lives in routing's
  `finally`). Two transient instruments were used to read alu4 and both were
  reverted; the tree is verified clean after each. Anything diagnosing a
  phase-1 failure must instrument, not look for a dump.

### Older (unchanged)

- **My OR-diode adjacency hypothesis — falsified by my own measurement.** Every
  OR load cell has **3 router-legal approaches, 0 ringed**, so a "≥2 free
  approaches" guard is a no-op.
- **The OR-cluster wall theory — wrong, and it dates from the first handoff of
  this project.** The cause column proves the failing OR drivers were
  **NO-ATTEMPT**: never searched, because `A`/`B`/`OP0` were searched 200–360x
  each at 40–75% failure and ate the whole budget. Positional downstream
  damage, not a junction defect. The junctions are real and fine.
- **"Connected vs cross" as the pointing rule — wrong.** I asserted it with the
  wiki open; the rule is **pointing**, from the connection shape. The owner's
  in-game test is what caught it.
- **"The `~a` reshape is byte-neutral" — false.** Counts unchanged, but the
  canary moved for both AND builds. The canary was right, the claim wrong.
- **"`(ox+1,gz+1)` isn't ring-covered" — false.** It already was; no ring edit
  was needed.
- **The step-1 OR clamp — net negative, reverted.** Correct physics (a repeater
  only reaches its junction at step 1) but 1.7x slower for identical routing,
  because it turns placements into failures. It also revealed that the
  project's own `y = a OR b` self-check hits a step-3 repeater on **attempt 1**,
  so `layout_retry` has been silently burning attempts on broken ORs.
- **"Single lever per input" — never verified where it was claimed.** XOR was
  never counted.
- **Every capped `alu1` number is a lower bound, not a diagnosis** — capped
  results are order-dependent.

## Files touched

### Committed

- `layout.py` — perf hoists (`_coupling_forb`, the `hard` set, the inlined
  coupling test, the windowed build); `dust_points()` + wiki self-check; the
  AND `~a` reshape; **`wire_bid()` + the `export-rt` round-trip check
  (`0421c54`)**; **the NOT input stub + bus load move (`48824d9`)**; **the XOR
  repeater side-feeds, the extra routed load, and the lever assert
  (`32b6fc6`)**.
- `sim.py` — **changed once, in `48824d9`**: the `dust_points` import and the
  pointing condition in `cob_state`. Everything else in it is deliberately
  untouched (a settling verify is 0.03s, so `dust_lvl` was measured and
  declined; verify timings re-measured after the pointing change and unchanged
  at 6–16 ms).
- `sim.py` — **`d506b74` vanilla gaps (this session):** `_lit` gains dust-on-top,
  powered-block, free-torch, rblk, lever branches + canaries; `comp_in` side
  dust branch + canary; torch-burnout counter + loud raise + canary. Deliberately
  NOT built: repeater locking/delays, comp delay-2, containers, side torch.
- `layout.py` — **`8da0cb1` cmpside wall (this session):** the four comparator
  side cells per XOR tile stamp `("cmpside", o)` in `solid` (new kind, inert
  everywhere except the wall set). Exact cells, no halo (halo would starve the
  rear feed).
- `layout.py` — **`1d42c7b` the LATCH S-row repeater**, **`701ea5b` the bridge-hop
  splice**, **`c474ad3` its chain assert**, and **`c1fe1c5` the `panel-wire`
  canary** (this session). The first three are product changes; all three are
  free — 0 extra blocks on all four small builds, determinism re-checked across
  3 processes. `c1fe1c5` is check-only and moved no hash.
- `handoff.md` — this file.
- Untouched throughout: `recipe.py`, `serve.py`, `export.py`, `core.py`,
  `debug.py`, `sim.py`, all `.txt` recipes.

### Untracked by design (`scratch/`, gitignored — never merge)

- `scratch/census_cause.py` — the census **with a cause column** (`solid` /
  `ringed` / `NO-ATTEMPT` / `no-search`). Now takes `cap`, recipe and a seed
  list so the same harness serves alu1/cpu4 with a fixed denominator. Use this
  for any diagnosis, **never `census_capped.py`**.
- `scratch/stage1.py`, `scratch/sweep_micro1.py` — one-sample-per-seed stage-1
  triage and the micro1 seed sweep. Both honour `REDSTONE_SEARCH_CAP` and take
  `tries=1, grows=1`; background them, never foreground a dense build.
- `scratch/redstone-mechanics-report.md` — wiki-grounded mechanics; carries the
  pointing table and the unresolved `[GAP]`s.
- `scratch/flat_hash.py`, `prof_all.py`, `not_approach.py`, `pointing_impact.py`,
  `probe_not.py`, `probe_pointing.py`, `probe_lit_vs_table.py`,
  `probe_c_and_micro1.py` — A/B and probe harnesses.
- **`scratch/probe_seeds.py` — the tile-input repro. 7 seeds, grow 0, the
  D-latch shape. This is the one to run first for the arrival-level bug; it needs
  no cap and no dense build.** `scratch/probe_phases2.py` prints the latch's four
  rows level by level per phase (locates the tile via the `Q~qb` row and applies
  the shrink-wrap shift — see the instrument traps). `scratch/probe_gt.py` reads
  the sim's own level at every cell of one net. `scratch/probe_cover2.py` /
  `probe_cover3.py` log what the booster cover did, per path.
  **`scratch/tile_arrival_level_attempts.diff` — all 5 reverted fixes**, so no
  attempt has to be retyped to be re-measured.
- **Panel probes.** `scratch/probe_one_lever.py` answers "does one input feeding
  N gates cost one lever" three ways (label / no-short / fanout reachability),
  and prints the naive-vs-panel lever table for all 9 recipes. `probe_panel.py`
  is the generate-every-recipe sweep (4/9 build; the other 5 are the known
  routing walls). Both are superseded by the landed `panel-wire` canary.
- **`scratch/probe_onecircuit.py` — the REJECTED one-circuit check.** Keep it as
  the negative example: it flags `example_xor`, which the suite accepts. Read it
  as the worked example of "validate the instrument first".
- D-latch probes: `probe_seeds.py` (the 7-seed repro — run this first),
  `probe_hold.py` (per-tick trace, transitions only; prints the S/R mutual
  exclusion), `probe_leak.py <seed>` (per-phase net breakdown; note two of its
  own labels are wrong, see the instrument traps).
- **Vanilla-gap probes (this session).** `scratch/vanilla_audit.py` — the nine
  known-answer cases (all pass now; keep as the oracle checklist).
  `scratch/compdiag.py` + `scratch/compmap.py` — comparator side/rear anatomy
  dumps. `scratch/xorscope.py` — XOR seeds × sim verdicts + b-pergola trace.
  `scratch/burnphase.py`, `scratch/fliptime.py`, `scratch/fliptime2.py` —
  torch flip timelines (until-stepped; no product edits needed for traces).
  `scratch/lampaudit.py` — lamp-vs-dust audit on the shipped XOR layout.

### Environment notes (cost me real time; do not relearn)

- `Start-Process` in this shell gets **reaped** — the launch command errors with
  `ChildProcess.kill` yet the child survives and writes its log. Children do
  complete; poll the log files rather than trusting the launch's return code.
- Because of that, dense work is best run **serialized in the foreground with a
  generous timeout**, one build at a time, so a verdict is never taken from a
  disturbed or parallel run.

## What next (in order)

Phase 3's premise has changed. The old list is retired; these are measured.

**Owner decision pending** on item 0 — it is a fork, not a task, and the two
branches cost very differently. Items 1+ do not depend on the answer.

0. **The one-circuit invariant: build it in `sim.py`, or skip it.** The idea is
   right (a net label must be one circuit; nothing checks it; it is the species
   of both bugs fixed this session) and the probe implementation of it is
   **rejected** — it flags `example_xor`, which the suite accepts. The correct
   home is beside `dust_lvl`, written in terms of that function, so coupling is
   stated once. **Cost:** a real refactor of the shipping verifier's rules, so
   it is the owner's call whether that is worth doing now. **Validation, if
   built:** it must come out clean on all four green small builds and flag
   seeds 0/1/4 differently — if it does not discriminate, it is worthless
   regardless of how good it looks.
1. **DONE — the 7 D-latch seeds are green (`32c54b6`) + `dlatch` canary in
   `sim.py __main__`.** Seeds 4/5 were a phantom wire+repeater double-stamp
   (emission now repeater-wins); seed 1 routed through the repeater cell
   (`astar.ok()` now refuses repeater cells). The old item-1 split (seed 1 =
   arrival, 4/5 = hold) turned out to be one root cause with two faces.
2. **DONE — census re-run: corridor conclusion survives (67→61, NO-ATTEMPT
   pinned at 41).** The arrival fixes cost 0 corridor and moved no dense
   needle, as predicted.
3. **DONE — s3 FULL BAR CLOSED (first green dense build).** Layout green +
   verify green (ticks=42, 8 vectors) + export-rt green (1026/1026,
   `scratch/s3export.py`). s5 1-mismatch and s4 OPEN T0 fragment remain.
3b. **s5 1-mismatch (D1W1B1OP1, Y False want True)** and **s4 OPEN T0
   2-cell fragment ((173,12),(171,12))**: both new post-mirror, both small.
   Do these before any corridor work.
3c. **Re-validate dense verdicts under the new sim.** Every SIM-FAIL below
   predates this session (old sim ignored side dust and never burned):
   s5/s4/s0/s1/s2 walls, micro1 seed sweep. Routing verdicts (census,
   NO-ATTEMPT counts) are unaffected (search untouched). s3's bar was closed
   pre-change; re-run `scratch/s3export.py` if touching export.
3d. **alu4 at grows=2: 222 pending at 3k searches (measured pre-mirror).**
   Budget class; grows=3 not worth trying. Re-run post-mirror only if cheap.
4. **DONE (hygiene) — all-or-nothing hops landed; S wall reclassified.**
   Feet guard tried and reverted (no effect). The pocket is real.
5. **DONE — repeater-loop reject landed (`_loop_rep`, fires only s2).**
   Remaining half: *search avoidance* (end-reject burns layouts; s2 needs the
   router to not close the loop in the first place).
6. **DONE (converter) — cover floor landed; s2 SIM-FAIL → LAYOUT-FAIL.**
   Remaining: nOP segment with a boostable head (router retry luck) + item 5.
7. **DONE (scoped) — tap reservation v3.** Always-on rejected twice
   (suite SHORT3D, verbatim v1); retry-round only. s0/s1 route past taps but
   SIM-FAIL on oscillators (churn-trace needed) with +1700 detour bloat.
7b. **micro1-s0 R-wall: `R (60,13)->(76,12)`, 3D self-lid.** Flat full, 3D
   flies its own pillar into its slope. One-pass limitation — session-sized,
   do after tap v3 or before, whichever is nearer.
8. **ctrl_decode `n2` wall** — undiagnosed; needs the micro1 treatment (dump
   read: `(57,9)->(59,11)`, 668 unroutable uncapped), not theory.
9. **Corridor mechanism — last, not first.** Only for the alu1/cpu4 wall, and
   only a mechanism that *creates* space. Discriminator unchanged: NO-ATTEMPT
   drops without no-search rising 1:1. Do **not** re-run any
   input-distribution variant — measured to relocate the starvation.
10. **Housekeeping**: `origin` sync is **73 ahead / 1 behind** and still needs
explicit approval. The checked-in demo artifacts have been regenerated with
   wire states (`build.mcfunction` 1317/1317, sampled `.schem` 49/49, 0 bare);
   `32c54b6` leaves them byte-identical (no repeater-cell routes in the demo).

**Do not** re-litigate the OR junctions, the ringed-cell mechanism (cancelled —
0 targets), a fifth micro1 router constraint, or any spine variant. And do not
read a symptom table as a diagnosis: four wrong inferences came from doing that
in this project, and the spine plan was the most expensive one yet.

**And do not ship a check you have not seen fail.** Two things this session were
caught only by validation, not by reasoning: the cover-window "fixes" (which a
multi-seed probe killed on the spot) and the one-circuit check (which flags a
build the suite accepts). Both looked exactly like the coverage this project
needs. A green check that has never been seen red is a press release, not
evidence.

## History (details and evidence behind the summary above)

> Everything below this line is a **point-in-time record**. Where it disagrees
> with the summary above — branch counts, HEAD, verdicts, the "Current state"
> and "What next" sub-sections in particular — **the summary wins.** The 3D
> Attempt 1 session is preserved verbatim because its retracted findings are the
> ones most likely to tempt a re-derivation.

### Phase 3 session (2026-09-27, steps 1–4 → dense triage)

Raw verdicts, for the record. The *conclusions* are in the summary above; these
are the measurements they came from.

| build | setting | verdict |
|---|---|---|
| `micro1` | uncapped, seed None | `no route for S: (47,16)->(47,17)`, 2 unroutable — **verbatim identical on a `1004f53` control** |
| `alu1` | cap 700, seed None | cap exhausted, 99 pending tasks (lower bound) |
| `alu4` | cap 700, seed None | `AND blocked for A0B0`, `tried=0` — **verbatim identical on a `1004f53` control** |
| `cpu4` | cap 700, seed None | cap exhausted, 416 pending tasks (lower bound) |
| `ctrl_decode` | uncapped | `no route for n2: (57,9)->(59,11)`, 668 unroutable, ~20 min |

Census, 6 seeds, grow 0, cap 700, cause column (the D4 denominator — paired
per-seed loads):

| build | NO-ATTEMPT | no-search | solid | ringed | most-searched |
|---|---|---|---|---|---|
| `alu1` | 41 | 26 | 0 | 0 | `A`/`B`/`CIN` 208–346 |
| `cpu4` | 263 | 5 | 0 | 0 | `OPC1`/`D0`/`D3` 122–380 |
| `alu1` *with spine* | **11** | **49** | 0 | 0 | `A` 250, `B` 183 |

micro1 seed sweep (`tries=1, grows=1`, verify on):

| seed | verdict |
|---|---|
| None | `no route for S: (47,16)->(47,17)` |
| 0 | `lamp spot taken for Y at (222,12)` — **routing complete**, fails at the tap |
| 1 | `lamp spot taken for Y at (222,12)` — deterministic repeat of seed 0 |
| 2 | `no route for Q: (73,14)->(124,12)`, 9 unroutable |
| 3 | `no route for T0: (113,4)->(118,4)`, 3D self-lid, 16 unroutable |
| 4 | `no route for R: (60,13)->(76,12)`, 3 unroutable |
| 5 | `no route for B: (127,55)->(126,14)`, 123 unroutable |

Mechanism log (all reverted; the tree was verified clean after each):

| # | mechanism | target result | why it was dropped |
|---|---|---|---|
| T2 | tap starts only | XOR `y` dark | ripped tap orphan |
| T2+T3 | all input paths unrippable | — | panel deadlock, `no route for y1/c` every seed |
| T2+T4 | + bridge-first inputs | — | gate detour decayed 15→2→0 over 43 cells |
| B | spine-only unrippable | census 67→60, inverted | panel `no route for y1` self-lid; xor canary moved |
| A v1 | ring tap + clearance + lamp | **s0/s1: layout wall → sim failure** | suite `SHORT3D: b slope-links y` |
| A v2 | + pre-seed tap into `wires` | s0/s1 held at sim failure | suite panel `SIM MISMATCH`; all 4 canary hashes moved |

Steps 1–4 measured results: `export-rt ok: 66 wire states round-trip` (negative
control 66/66 bare-id cells fail); `example_and` 104/104 wire lines with
blockstate; `probe_not` 0 flips on NOT/AND/2gates (2/4/8 vectors), `latch_sr`
(3), `example_xor` (4); `example_xor` levers `{a:1, b:1}`; verify timings
unchanged at 6–16 ms after the pointing change; bounded micro1 RED in 2.2 s
throughout Steps 1–4 (Steps 1–4 are neutral on dense builds).

### Goal (evolved)
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

### Current state *(3D Attempt 1 session — superseded by the summary above)*
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
- **KNOWN DEFECT (shipping-blocking, confirmed, NOT fixed): the export writes
  no redstone-wire blockstate.** Measured on the shipped demo:
  `build.mcfunction` has **106 `redstone_wire` lines, 0 with a blockstate**,
  and the `.schem` palette holds the bare string `minecraft:redstone_wire` for
  every one of them. Repeaters and comparators DO carry theirs
  (`facing=north,delay=1`, `mode=subtract`), so the exporter passes state
  through correctly — the defect is upstream, at `layout.py:1548`, which emits
  a bare id while `layout.py:1550` gives repeaters `facing`/`delay`.
  - **Why it matters:** wire's state IS its pointing
    (`east/north/south/west ∈ {none, side, up}` + `power`). A schematic entry
    with no properties loads the block's defaults — all-`none`, `power=0` —
    which is a **dot that powers nothing sideways**. So the connection shape
    never reaches the world, and it is the same concept the sim is missing
    (see `dust_points` below). One fix, two consumers.
  - **Why the sim cannot catch it:** the sim verifies `layout.py`'s internal
    `wires` dict and never reads the exported file, so the whole
    `layout -> sim -> green` chain is blind to what the world receives. A
    pasted dot may or may not re-configure on load depending on whether the
    game fires wire updates for those cells; the FILE does not encode it, and
    the standing requirement is 100% vanilla compatibility.
  - **The check that would have caught it:** an export round-trip — export,
    read the `.schem` back, assert every wire cell's states match the shape
    `dust_points` says it should have. Add it with the fix.
- **ROOT CAUSE of "not 100% vanilla": there was no external oracle.** The sim
  and the layout encode no pointing rule *at all*, so they agreed with each
  other: layout stamps an end cell beside a block, `cob_state` says "adjacent
  dust powers it", the tile verifies green, and both are wrong the same way.
  Note the asymmetry — the **sim has a wrong model** (assumes every cell is a
  cross), the **layout has no model**, so the sim needs a rule ADDED while the
  layout needs a GEOMETRY change. `dust_points()` (`9512d23`) is the shared
  table, asserted against the wiki for all five shapes, and is deliberately
  NOT yet consumed by either side.
- **GATE on the pointing work: the in-game end-cell test, not yet run.** Run a
  north–south 2-dust wire that ENDS due west of a block, torch on that block,
  lever on the wire. Torch off ⇒ dust does power a side-adjacent block, the
  sim is right, the AND tile is fine. Torch stays on ⇒ the pointing model is
  right, and the AND tile's `~a` stub (ends at `(9,1,4)`, whose only dust
  neighbour is north, so it points north/south and never east at the NOR
  cobble `(10,1,4)`) is broken in vanilla — `example_and` and
  `example_2gates` currently pass only because `cob_state` over-powers.
  Measured consequence of the pointing model: both flip to `SIM MISMATCH` on
  `a=0,b=1`. Do not change the sim or the tiles before this test.
- **CENSUS DISCIPLINE (learned the hard way this session): the census records
  WHICH nets fail, never WHY.** A symptom table got read as a diagnosis three
  times — twice by me, once by the owner, and the OR-cluster "wall" theory
  traced back to the very first handoff of this project was simply wrong. The
  measured truth: micro1 is TILE GEOMETRY (the latch's own `Sdust` stub at
  `(81,16)` beside its Q-side torch attach — no router constraint can refuse
  it), while alu1/alu4/cpu4 are SEARCH-BUDGET EXHAUSTION (A, B, OP0 searched
  200–360x each at 40–75% failure eat the budget, so later nets are never
  placed — the "OR drivers fail" pattern is POSITIONAL downstream damage, not
  a junction defect; the junctions are real and fine). `scratch/census_cause.py`
  now prints a CAUSE per unreached net (solid / ringed / never-attempted /
  exhausted-searches). Run that, not `census_capped.py`, for any diagnosis.
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

### Method note
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


### Method note (continued)
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

### What changed (newest last)
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

### What changed (newest last) (continued)
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

### What failed (with evidence, no theory)
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

### Files touched
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

### What next (in order) *(RETIRED — kept only as a record; use the summary's
"What next" at the top of this file)*

1. ~~**Re-census alu1 under the deferral** (`12dd3c9`).~~ **DONE**, and the
   answer was no: the deferral did not change the failure set. Superseded by the
   6-seed cause census in the Phase 3 record above.
2. ~~**Settle the sim budget question on dense builds.**~~ **DONE** — caps were
   raised to 5000 ticks / 300000 steps; the dense builds now fail on *routing*,
   not on the sim budget, so this no longer gates anything.
3. ~~**micro1's three residual failures under the deferral.**~~ Partly done:
   item 3's first sub-point (reserve the output tap in phase 1) is now the
   top remaining item, and it **works** — see Mechanism A in the summary. Items
   2 and 3 of that list (`SIM MISMATCH`, `no route for Q`) remain, and the
   SIM MISMATCH is now *diagnosed* (the `LATCH(S,R)` port convention), not just
   observed.
4. ~~**Stage-1 reads for alu4 / ctrl_decode / cpu4** (~2s each).~~ **DONE**:
   all three read, none passes, and the "~2s each" estimate was wrong —
   `ctrl_decode` alone takes ~20 min uncapped.
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


