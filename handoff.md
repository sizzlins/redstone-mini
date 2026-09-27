# Handoff — redstone-mini (2026-09-26, 3D Attempt 1)

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

Branch `phase2-design`, **47 ahead / 1 behind** `origin` (remote sync needs
explicit approval). Tree clean apart from untracked plan docs. HEAD `67987b0`.
Suite green: `recipe.py`, `sim.py`, `layout.py`, `serve.py --check`.

**The governing discovery: this project had no external oracle.** The sim and
the layout encode no redstone *pointing* rule at all, so they agreed with each
other — layout stamped a wire end-cell beside a block, `cob_state` said
"adjacent dust powers it", the tile verified green, and both were wrong the
same way. Everything below follows from that.

| item | state |
|---|---|
| Router performance | **1.7x faster**, A/B'd, with a biconditional `REDSTONE_XCHECK=1` |
| `dust_points()` pointing table | landed `9512d23`, wiki-asserted for all 5 shapes, **consumed**: sim `cob_state` (`48824d9`) + exporter `wire_bid`/`export-rt` (`0421c54`) |
| AND tile `~a` stub | **fixed and verified** `67987b0` (was dead under the wiki rule) |
| NOT tile input port | **fixed** `48824d9` (own E-W stub ends at `(bx-1,bz)`, points east at host; guard change skipped — cheap kill took `probe_not` to 0 flips) + pointing sim **landed** same commit |
| XOR levers | **1 per input, asserted** `32b6fc6` (side feeds are repeaters; wiki strong-side rule quoted in message) |
| Export blockstates | **fixed** `0421c54` (every wire line carries side/none states) + `.schem` round-trip check; negative control 66/66 bare-id cells fail it |
| Dense builds | `micro1` = tile geometry; `alu1/alu4/cpu4` = input-route budget starvation |
| Byte-identity canary | re-baselined: `e79bfa6d` / `b4a9cc9b` / `03542c34` (wire states only, geometry proven identical) + xor `3449ff76` (tile + routes moved) |

## What changed

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

- `layout.py` — perf hoists (`_coupling_forb`, the `hard` set, the inlined
  coupling test, the windowed build); `dust_points()` + wiki self-check; the
  AND `~a` reshape.
- `sim.py` — measured and **deliberately unchanged**: a settling verify is
  0.03s, so `dust_lvl` was not worth touching, and the pointing-aware
  `cob_state` was measured, found to break the NOT tile, and reverted.
- `handoff.md` — this file.
- `scratch/census_cause.py` — the census **with a cause column** (`solid` /
  `ringed` / `NO-ATTEMPT` / `no-search`). Use this for any diagnosis, never
  `census_capped.py`.
- `scratch/redstone-mechanics-report.md` — wiki-grounded mechanics; now carries
  the pointing table and the unresolved `[GAP]`.
- `scratch/flat_hash.py`, `prof_all.py`, `not_approach.py`,
  `pointing_impact.py` — A/B and probe harnesses (untracked by design).
- Untouched: `recipe.py`, `serve.py`, `export.py`, `core.py`.

## What next (in order)

1. **In-game end-cell test — the only true gate, and the owner must run it.** A
   north–south 2-dust wire that ENDS due west of a block, torch on that block,
   lever on the wire. Torch off ⇒ the sim is right. Torch stays on ⇒ the
   pointing model is right. Everything below is downstream of this.
2. **Feed tile input ports from ON TOP of the host.** "On top" carries no shape
   condition at all, so it is pointing-proof *by construction* — tile-local and
   canary-safe. This generalises the `~a` fix and is the lazy answer: the NOT's
   port is fed from the side, so its correctness depends on *where the router
   approached*. Check the AND's external `A`/`B` ports too — they are
   router-fed and exposed to the same class. The alternative is a router
   approach constraint (new machinery, costs the canary).
3. **Then land the pointing sim** (`cob_state` → `dust_points`) once the NOT and
   the ports are fixed. Unblocked by 1+2, not before.
4. **Export the wire blockstates** from the net map, plus an **export round-trip
   check** (export → read the `.schem` back → assert every wire's states match
   `dust_points`). Required by the 100%-vanilla goal regardless of how 1
   resolves; the round-trip would have caught this today.
5. **XOR input corridor** — ungate one approach cell so a routed wire can reach
   the port and the second lever per input goes away. Hypothesis-independent: a
   comparator reads its rear's *level*, and pointing is not involved in
   comparator input.
6. **Input distribution** (`spine-on-top` for `A`/`B`/`OP0`) — the census says
   inputs are **15/15** of the genuine search failures. This is what actually
   unblocks `alu1/alu4/cpu4`, and the only step that spends the canary.
7. **micro1's latch `Sdust` stub** at `(81,16)` beside its Q-side torch attach —
   tile geometry, and no router constraint can refuse the tile's own wire.
8. **The 2 ringed load cells** in the `alu1` census — the only structural
   failures left; no amount of budget fixes a reserved cell.

**Do not** re-litigate the OR junctions, and do not read a symptom table as a
diagnosis: three wrong inferences this session all came from doing that.

## History (details and evidence behind the summary above)

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

### Current state
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

### What next (in order)
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


