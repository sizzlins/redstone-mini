# Handoff — redstone-mini (2026-09-27, session 2: two router fixes; micro1 1/12 → 2/12 and 10× faster)

> **Read this section first.** It is the state of play; everything below
> `## History` is the detailed evidence, kept but no longer current.

## Goal

Ship a generator whose output is **100% vanilla Minecraft compatible** — every
build is exported to `.schem` and pasted into a real world, so the simulator is
a *shipping* gate, not a design aid. A false green is a broken build in
someone's world.

Order: (1) make the sim trustworthy against the wiki, (2) make the tiles
correct under those rules, (3) make the dense builds generate.

## Current state

Branch `phase2-design`, **0 ahead / 0 behind** `origin` — everything is committed
and pushed through `4d55c6e`, HEAD there. Tracked tree clean; the only untracked
files are the five `docs/plans/*.md` (policy-excluded) and gitignored scratch.
Landed this session and pushed: per-net retry cap + booster-side guard
(`layout.py`), `layout_retry` rewrite (`sim.py`), field-depth fix (`layout.py`),
three handoff records. Reverted before commit, tree byte-identical: port
corridors, per-input bank, input fanout chaining (each with mechanism + numbers
in What failed).

Suite green: `recipe.py`, `sim.py` (all canaries), `layout.py` (incl. the new
`booster-side` canary), `serve.py --check`, `REDSTONE_XCHECK=1` on both green
micro1 builds, and **`example_and` / `example_2gates` / `latch_sr` /
`example_xor` byte-identical to HEAD (4/4 hashes)**.

| recipe | status | measured |
|---|---|---|
| **micro1** | **GENERATES** | **2/12 seeds green** (s3, s5) at grow=1. Ladder 30s; `layout_retry` 26s (was 235s). Unchanged by chaining (its inputs feed <3 gates). |
| alu1 | shared corridor wall | 0/12 at grow=1 (~7 min); 0/12 with chaining (~38 min, 5× slower, same wall). NOT space-bound (0/4 at grow=2, same nets). |
| alu4 | placement wall **CLEARED** | placement passes since `2db73c9`; shares alu1's wall (`no route for OP0`, 78 unroutable; 0/2 with chaining at 635s/672s). Was `AND blocked for A0B0`, 0.0s. |
| cpu4 | budget wall, largest, **holdout** | 402s/seed, 376 unrouted. Frozen for generality proof; never tuned to. |
| ctrl_decode | shared corridor wall | 15 gates, 65 unrouted at cap 150; 0/2 with chaining, failing on the buffer nets themselves (`_bf6`, `_bf5`). |

micro1's 12-seed breakdown after the fixes: 2 green, 5 `no route` (corridor),
2 `SIM MISMATCH` (**the same named defect, see What next**), 1 `OPEN`,
2 `repeater loop ... every triple closes it` (new *loud* failure, not a false
green — both seeds failed before too).

**The headline, stated as a verdict:** micro1 generates; the other four share one
wall with no new hypothesis. Engineering: successful — three landed fixes that
transfer to every future recipe, 9× faster generation, placement wall cleared
for all five, full vanilla bar on micro1's build (2452 blocks, 1026 wire lines,
**0 bare**, `.schem` 1026/0), byte-identical small builds throughout, complete
evidence record including three refuted mechanisms with causes. Mission ("all
builds generated, new recipes green by default"): **not met** — alu1, alu4,
cpu4, ctrl_decode are red, and the three mechanisms tried against the shared
wall (corridors, bank-move, chaining) all died proving it is ground-*existence*,
not length, order, or placement. What remains is either a ground-creating
mechanism (nothing in the tree does this) or rescoping to pinned greens where
search finds them. See What next.

## What changed

### 1. Per-net retry cap — `layout.py`, the shared retry funnel

**Root cause:** `fails` was keyed by `(net, tuple(sorted(blockers)))`. A net
that kept meeting a *fresh* blocker set therefore reset its own retry budget
every time, and on each failure re-queued **every blocker task at the head of
`pending`**. Measured: single nets (`A`, `B`, `OP0`, `CIN`) were searching
221–290 times each while 40 loads never got a single attempt — the census's
dominant `NO-ATTEMPT` bucket, i.e. pure budget starvation, not a circuit defect.

**Fix:** a parallel `netfails` dict, and the retry condition became
`not block_tasks or fails[key] > 2 or _nf > 6`.

**Why 6:** it is exactly what the pre-existing per-blocker-set cap of 2 already
allows across 3 distinct blocker sets. So a net that keeps meeting the same
sealer is **bit-identical** to before, and only the runaway changes. That is
why all four small-build hashes held.

**Measured** (alu1 census, cap 700, seeds 0–5, grow 0 — the handoff's own
denominator):

| | NO-ATTEMPT | no-search | total unreached |
|---|---|---|---|
| HEAD | 40 | 33 | 74 |
| patched | **22** | 42 | **64** |

NO-ATTEMPT fell 18, no-search rose 9, so **10 loads newly route**. Per the
handoff's standing discriminator ("NO-ATTEMPT drops without no-search rising
1:1") this is a real gain, **not** a relocation. Ladder wall time 308s → 30s.

### 2. Booster-side guard — `place_rep` refuses to cut its own net

**Root cause, found by reading failures, not tuning.** A repeater drives
exactly one cell: its front. `place_rep` converts a wire cell into a repeater
with no check that the same net runs *through* that cell — so any same-net dust
beside it was left fed from a direction vanilla cannot feed from. **No static
check could see it:** the OPEN walk steps onto a repeater from *any* side and
out of *any* side, so the cut branch still read as "connected".

Evidence chain (all reproducible):
- micro1 **s5**: the m0 AND tile's `OP` port `(172,18)` and ~40 cells with it
  sat at level 0 in every vector. The branch met the live net at exactly one
  point, the repeater `((177,1,52),'west')` — current arrived on that
  repeater's *output* side. Hand-diagnosed from the sim's levels first, then
  confirmed mechanically.
- A temporary probe (`REDSTONE_ORPHAN`) fired on s5 and s10 and was **clean on
  all four green small builds and on s4/s7** — i.e. it discriminates.
- **Fix:** a 5-line guard in `place_rep` that raises when the candidate site has
  same-net dust outside `{back, front}`. The cover loop already iterates
  candidate triples in order and falls through on `RuntimeError`, so the cover
  backs off to the next site **with no new machinery**.
- **Result: micro1 s5 went SIM-FAIL → GREEN** (2608 blocks, ticks=45, 8
  vectors). Green rate 1/12 → 2/12.

**Canary:** `layout.py::_sidefed_repeaters(blocks, io)` + a `booster-side ok`
assert over the shipped blocks of all four small builds, plus a negative
control. It has been **seen red on the real defect** (guard disarmed, s5 names
`((177,1,52),'west',(177,1,51))`) — not merely asserted green.

Also in the same commit's worth of work: the facing→delta map was duplicated
**3×** in `layout.py`; hoisted to one module-level `_VEC` (pure deletion,
A/B-verified byte-identical).

### 3. `layout_retry` rewritten: first-verified + interleaved grows — `sim.py`

Profiling the ladder's exact walk (`scratch/prof_retry.py`: seed `None`→1..11,
uncapped, layout vs verify timed separately) found **two** things it did that
cannot pay off. Both were measured, not guessed:

1. **It kept searching after it was already green.** At grow=1 the first green
   landed at t=3 (44s in); the sweep then spent **another 48s** on t=4..11, and
   t=5 came back *worse* (ticks 45 vs 42). The old code scored every candidate
   by `(ticks, blocks)` and shipped the best, so the tail was searched to find a
   winner that lost.
2. **It swept each field size to exhaustion.** grow=0 ran all 12 seeds for
   **70s and verified 0 of them** before grow=1 was tried at all (2/12 verify
   there). A field too small to fit *always* fails, so that ordering is
   guaranteed waste.

**Fix:** return the **first** verified build, and iterate `for t: for grow:`
so field sizes are diversified before committing. The `best`/score bookkeeping
is deleted outright. Verified unchanged: same build out (2452 blocks,
ticks=42, 8 vectors), 1026 wires 0 bare, `.schem` 1026/0.

| | before | after |
|---|---|---|
| `layout_retry(micro1, verify=True)` | 235.4s | **26.0s** (repeats 25.0 / 26.2) |
| full `redstone_mini.py micro1.txt` | ~4 min | **<45s** |
| `example_and` | 186 blocks / 0.16s | 198 blocks / 0.02s |
| `example_2gates` | 276 / 0.31s | 288 / 0.03s |
| `latch_sr` | 228 / 0.17s | 228 / 0.01s (identical) |
| `example_xor` | 258 / 0.44s | 258 / 0.03s (identical) |

**Cost, stated plainly:** dropping best-of costs **+12 blocks** on two small
builds (`example_and`, `example_2gates`; `serve --check` now reports a
288-block demo). `tries` remains the knob if a caller ever wants to hunt for a
smaller build again.

**Scope limit, do not overclaim:** this is a large win for any recipe that
reaches green, and **neutral for alu1 / alu4 / cpu4**, which verify 0/36 — there
is no first-green to return early at, so the same 36 layouts still get built.
It reorders them (grow=2 is reached far sooner) but does not cut total work.
Making those three faster requires *finding a green configuration*, not failing
faster.
### 4. Field depth sized for the bus lanes — `layout.py`, one line (alu4's placement wall)

**How it was found:** alu4 is the cheapest of the four, so it went first. It
died in *placement*, before any search — `AND blocked for A0B0`, 0.0s, **zero
candidates tried**, identically on every seed. Nothing diagnoses a phase-1
failure (the dump lives in routing), so `spot_free`'s four reject paths were
instrumented — one line per exit, temporary, reverted after. Three calls, three
reasons: `lane:OP1` on row 12, `lane:A1` on row 26, `bounds` on row 40.

**Root cause is upstream of the placer.** Band assignment gives every gate its
own band (`g["band"] = i`), so `counts` in the D formula is all 1s and

```
D = 12 + max(counts.values()) * 14 + 12   ->   38
```

**for every build, regardless of size.** 38 admits two usable rows. The bus
lanes are stamped at the **bottom** of the field (`lz = D - 4 - idx * 2`) and
are full width, so alu4's 10 inputs put lanes on z=16..34 — straddling the grid
row at z=12, whose footprint reaches z=18. Every gate's slot is lane-blocked,
`gridrows` then falls *downward* into the next lane, and the third row (z=40)
is cut off by the bounds check. Placement could not succeed at any seed.

**Fix:** the top grid row's footprint bottoms out at z=18, so the lowest lane
must sit below it — `D - 4 - 2*(inputs-1) > 18`, i.e.
`D = max(D, 24 + 2*len(recipe["inputs"]))`. One line, and `max()` so it cannot
disturb a build that already placed: the four small builds and micro1 all have
≤4 inputs (needing ≤32), so their D stays 38.

**Result — the whole dense family now passes placement at grow=0:**

| recipe | gates / inputs | verdict |
|---|---|---|
| alu1 | 21 / 5 | routing (40 unrouted at cap 150) |
| **alu4** | 72 / 10 | **placement now PASSES** → routing (192 unrouted) |
| cpu4 | 126 / 7 | routing (394 unrouted) |
| ctrl_decode | 15 / 3 | routing (65 unrouted) |
| micro1 | 10 / 4 | routing (14 unrouted) |

4/4 small-build hashes byte-identical; micro1 still generates (2452 blocks,
8 vectors, 25s); all gates green. Probe: `scratch/placecheck.py <cap>` gives a
placement-vs-routing verdict per recipe, bounded so placement either passes or
fails fast instead of burning 600s.

**This does not make alu4 green.** It now fails at the *same* wall as alu1
(`no route for OP0`, 78 unroutable after a full uncapped attempt). What it
removes is a whole class of failure that was masking the real one — and it
means the remaining work is **one shared problem, not four**.

## What failed (with evidence, no theory)

- **The approved "input port corridors" spec — IMPLEMENTED, MEASURED, REVERTED.**
  This is the most valuable negative result in the file, because the spec is
  owner-approved (`docs/superpowers/specs/2026-09-26-input-port-corridors-design.md`,
  commit `09cc91a`, §§1–3 approved) and the obvious next move. It is ~10 lines,
  placement-only, router-untouched: for every **input-fed** port, ring a
  westward 8×3 ray (port row ±1) to that net, truncated at the first solid,
  from `_load()` in the netspec block — the one place that knows both the net
  and the port for every op.

  **It is red at the spec's own Gate 4 and worse than that.**

  | | result |
  |---|---|
  | `example_and` | 262 → 283 blocks, **`y>=2` 0 → 42** (pushed 3D) |
  | `example_2gates` | 390 → 419, `y>=2` 0 → 42 |
  | `example_xor` | **FAILS**: `lamp spot taken for y at (4, 18)` |
  | **micro1** | **0/12 green, DOWN from 2/12** — s3 → `unboostable gap on Q`, s5 → SIM MISMATCH |
  | micro1 failure class | shifted to `repeater loop ... every triple closes it` ×5 and `unboostable gap` ×2 |

  **Mechanism, and it is the part the spec missed:** a ring is a wall for
  every net that does not own it, and the **booster cover needs straight open
  runs** — `_cover_triples` only offers a booster site where
  `path[j-1],path[j],path[j+1]` are collinear. Reserving 24 cells per input
  port deletes exactly those runs, so routes go twisty and the cover has
  nowhere legal to put a repeater. The spec budgeted corridors as a cost to
  *transit* ("crossing cost: bounded, in free gaps") and did not price them
  against the *cover*. **Any retry must reserve space the cover can still
  boost in** — reserve the lane but leave the repeater sites, or place boosters
  before ringing. Do not re-attempt the ray as specified.

- **"alu1 is space-bound" — FALSIFIED.** The standing conclusion in every prior
  handoff was that the binding constraint is total ground corridor. grow=2
  gives alu1 a much larger field (driver at z=398 vs z=265) and the **same
  0/4, same failing nets (A, B), only slower** (52–62s vs 32–43s). The
  coordinates are the tell: net A's driver sits at `z=398` while its load is at
  `z=12` — a ~386-cell crossing. **More space lengthens the crossing, so area
  is not the constraint; the lever-to-gate distance is.** Any future mechanism
  that grows the field will make this worse, not better.


- **Making the OPEN walk directional — REJECTED, does not discriminate.** A
  repeater really is one-way, so the walk should enter only from the back and
  leave only by the front. Implemented; it went red on **`example_xor`**, a
  build `sim_verify` proves is live. Reverted. Same verdict as the
  one-circuit probe in the history below — a check that flags a build the suite
  accepts is worthless. Note the walk's *other* blind spot, which the
  permissive repeater hop was probably papering over: **it cannot enter a
  comparator at all** (comparators live in `solid`, not `wires`), though a
  comparator's output cell at `C - rear_dir` is a legitimate source. If
  directional traversal is ever revisited, that gap must be closed first, and
  the instrument must be validated against seeds 0/1/4 *and* the green small
  builds before it is trusted.
- **The first version of the new canary was VACUOUS.** `_sidefed_repeaters`
  read the repeater's net from `io["nets"]`, but `place_rep` *deletes* the cell
  from `wires`, so a repeater cell is not in `io["nets"]` — the function
  returned `[]` for every real repeater and all four asserts "passed" meaninglessly.
  Fixed by taking the net off the repeater's own back/front dust, and the
  function now carries an **assert that it is not vacuous**. This is the same
  species as the four instrument bugs already in the history: *a check that has
  never been seen red is a press release.*
- **alu4 is still a hang-equivalent at grow=1.** 481s of CPU on a single seed
  with no output. Do not measure it in the foreground. The history already has
  its numbers (grows=2: 222 pending at 3k searches) — re-measuring 6 seeds
  costs 30+ minutes to re-confirm 0/6.
- **My own shell discipline cost two sessions.** `... | Out-String` buffers
  *all* output, so a streaming probe printed nothing until it exited and looked
  hung — twice, and both times the work was killed mid-flight. Also
  `Start-Process` reports `ChildProcess.kill` yet the child survives. **Working
  pattern: redirect to a log file, poll the log, never pipe through
  `Out-String`.** A streaming per-seed harness is `scratch/ladder2.py`
  (`LADDER_GROW`, cap, seed range, recipe list) and a 1-seed one is
  `scratch/seed2.py`.

## The next defect, named but NOT solved — micro1 s7 / s10

Both fail `SIM MISMATCH x2` on the **same** vectors, and the cause is
`Q` (the latch output) not propagating:

| | s7 (fails) | s3 (green) |
|---|---|---|
| `S` at the latch port | drv 14, load 13 — **arrives** | arrives |
| `Q` cells lit | **16 / 126** | **111 / 111** |
| `Q` loads | both **0** | far load **15** |
| repeaters on `Q` | **0** | **0** |

`Q`'s *driver* stub reads 6 in **both** seeds, so 6 is normal tile behaviour and
is not the defect. On s7 the run simply dies ~14 cells out. Reproduce with
`scratch/qnet.py 7 1100 0100` and `scratch/netmap.py 7 Q 1100`.

**The lead, unproven:** s3's `Q` net has **five separate level-15 islands**
(`(70,19) (70,23) (76,27) (80,27) (81,14)`) spread across the field. A single
source cannot produce that — it says the `Q` **label spans more than one
electrical circuit**. That is precisely the invariant the rejected
one-circuit-per-net probe was reaching for, and the handoff records *why* that
probe was wrong: its slope-link predicate did not match `dust_lvl`, so 3D
bridged dust read as orphan islands. **The idea may be sound and only the
transcription wrong** — and per that same record the fix belongs *in `sim.py`,
beside `dust_lvl`, written in terms of that function*, not in a probe that
re-derives the coupling rules.

Next experiment, in order:
1. Read `sim.py::dust_lvl` and write the one-circuit check **there**, in terms
   of that function. Validation is mandatory and cheap: it must come out clean
   on all four green small builds and flag s7/s10 — if it flags `example_xor`
   again, it is wrong and must be dropped, exactly as last time.
2. s4's `OPEN (unconnected dust): ((173,12),(171,12)) 'T0'` is a **different**
   mechanism — the booster-side probe was clean there. 2 cells, still open.
3. **The dense wall is one shared problem, and the placement lever is now
   exhausted — two independent moves agree.** Corridors and the per-input bank
   both died by the same mechanism (middle-field walls cost more ground than
   they save), both recorded above with numbers. Ordering was already correct
   before this session began. Growing the field is falsified for alu1. So there
   is no fourth placement/order/size variant to try; the standing rule against
   a fifth attempt without a new hypothesis now covers the whole category.
   Ordered by cost-to-first-green, what little ordering remains:
   - **alu1 — cheapest full green if the wall ever cracks.** 21 gates; lever
     distance confirmed (386-cell crossings) but unfixable by placement.
   - **ctrl_decode — fewest moving parts.** 15 gates; fails on its buffer nets
     under chaining, on OP0/OP1 crossings without it. Best proving ground for
     any future routing fix.
   - **cpu4 — most expensive, and the holdout.** 376 unrouted, 402s/seed.
     Never tune to it; it is the generality proof, background only.
4. Standing rule, extended by this session: a mechanism must be costed against
   **ground existence** — not transit, not the cover, not length. Corridors
   looked free on transit and destroyed booster runs; the bank looked free on
   length and sealed gate ground; chaining looked free on length and *was*
   ground pressure (+20 tiles where 4 cells don't fit). The s8 datum
   (`n0: (8,54)→(9,51)`, 4 cells, no fit) is the shape of the wall: when 4
   cells don't fit, nothing that adds cells can help. Only a mechanism that
   creates ground, or uses strictly less of it, is in scope.

**Do not** re-run any input-distribution / spine variant (four data points say
they relocate starvation), the port-corridor ray as specified (measured, costs
micro1 two green seeds), the per-input bank (measured, 0/12 by relocation),
input fanout chaining (measured, 0/12 at 5× cost, buffers can't route), grow
the field expecting relief (falsified for alu1), a fifth micro1 router
constraint or a fourth placement variant without a new hypothesis, or the
OR-junction and ringed-cell theories (both falsified).

- **Input fanout chaining — DESIGNED, APPROVED, IMPLEMENTED, MEASURED,
  REVERTED.** Third mechanism to die, and the most instructive because it was
  the best-argued: `recipe.py` relays gate-net fanout but excluded inputs on a
  premise ("zero-wire taps") that died with the single-lever panel, so inputs
  paid 130–390-cell marathons the chains exist to end. Full brainstorming
  gate held (spec `docs/superpowers/specs/2026-09-27-input-fanout-chaining-design.md`,
  holdout cpu4 + synthetic floor), implementation plan
  (`docs/plans/2026-09-27-input-fanout-chaining.md`, inline execution),
  TDD with a failing check first. Two correctness refinements found during
  planning: line 102 keeps its exclusion (replication indexes a driving gate
  inputs don't have — deleting there crashes), and single-band inputs take the
  banded body as one shared buffer.
- **Measured: 0/12 alu1 (was 0/12, now 5× slower), 0/2 alu4, 0/2 ctrl_decode.**
  Zero near-misses anywhere — all corridor walls, no fully-routed-but-wrong
  build. Costs escalated per seed (71s → 403s on alu1) because ~20 buffer tiles
  plus their routes load an already-full field. Smoking gun on alu1 s8:
  `no route for n0: (8,54)→(9,51)` — a **4-cell** hop failing. And a new loud
  class tracing directly to the buffers: ctrl_decode fails `no route for
  _bf6`, `no route for _bf5` — the buffer routes themselves can't fit.
- **Mechanism: buffers don't relieve ground pressure, they add to it.** Each
  buffer is a tile to place plus a route to find. On a field where 4 cells
  don't fit, +20 tiles is strictly worse. Chaining helps only when the wall is
  route *length*; alu1's wall is route *existence*. Reverted per the plan's
  kill-switch (zero greens, zero near-misses, new buffer-traced failure
  class); tree byte-identical, micro1's two greens intact. The spec and plan
  docs stand as the worked example of the full gate held end to end.

- **Per-input lever bank (median-row placement) — TRIED, MEASURED, REVERTED.**
  Second placement idea to die by the *same* mechanism as corridors, which is
  the pattern. Measured first: every alu1 input crosses 127–214 cells at
  grow=0 (OP1 214, OP0 203, A/B 166, CIN 127; loads span z=12..141, levers all
  at z=176 — `scratch/bankdist.py`). Fix: park each input's lever just south
  of its own loads' median grid row (replicating placement's bandrows math),
  cutting maxdist 2.4–4×. Small-build canaries all passed — then micro1's two
  green seeds both died, and the full 12-seed ladder came back **0/12, down
  from 2/12**, with 10 of 11 failures on *gate* nets (T0/T1/S/Q/R ×2 each).
  Inputs improved; gates collapsed. Relocation by the standing discriminator.
  Mechanism: a lever plus its 4-cell ring in the middle of the field is a wall
  for gate routes — same species as corridors. So **two independent placement
  moves now agree: anything put in the middle of the field costs more ground
  than the shorter input routes save.** The lever bank stays at D-2; the tree
  is byte-identical to before the attempt.

## Files touched

### Landed and pushed (`layout.py`)

- `netfails` + the `or _nf > 6` term in the shared retry condition (per-net cap).
- the same-net-side guard in `place_rep` (booster-side refusal).
- `_sidefed_repeaters(blocks, io)` + the `booster-side ok` canary, negative
  control, and not-vacuous assert in `__main__`.
- `_VEC` module constant replacing three duplicated facing→delta dicts.
- `D = max(D, 24 + 2 * len(recipe["inputs"]))` (field depth clears the bus
  lanes; placement wall gone for all five dense recipes).

### Landed and pushed (`sim.py`)

- `layout_retry` returns the **first** verified build and interleaves the grow
  levels per seed; the best-of-`(ticks, blocks)` bookkeeping is deleted. 9×
  faster on micro1 (235.4s → 26.0s), +12 blocks on two small builds.

### Landed and pushed (docs)

- `docs/superpowers/specs/2026-09-27-input-fanout-chaining-design.md` — the
  approved generality design (holdout cpu4 + synthetic floor).
- `handoff.md` — this file, rewritten for the verdict below.

### Attempted and reverted, tree byte-identical (evidence in What failed)

- Port-corridor ray (`_corridor` in `_load`), per-input lever bank (`_bankz`),
  input fanout chaining (two `recipe.py` gates). Each reverted after its
  kill-switch fired; each left its probe and mechanism in the record.

Every gate green and 4/4 small-build hashes byte-identical throughout.
`build.html`, `build.mcfunction` and `build.schem` hold a verified micro1
(2452 blocks, 0 bare wires, schem round-trip 1026/0).

### Untracked by design (`scratch/`, gitignored — never merge)

- **`scratch/ladder2.py` — the streaming multi-recipe ladder.** Per-seed
  verdict + timing, flushed, `REDSTONE_SEARCH_CAP` bounded. `LADDER_GROW`
  env for the grow level. This is the harness to use; it cannot look hung
  because it does not block.
- **`scratch/seed2.py <seed...>`** — same, one recipe, named seeds.
- **`scratch/prof_retry.py [recipe] [grows]`** — replays `layout_retry`'s exact
  walk (seed `None`→1..11, uncapped) with **layout and verify timed separately
  per seed**. This is what found the two structural wastes in `layout_retry`;
  re-run it before optimising that loop again, and do not add a print-only
  variant (the churn lesson below applies).
- `scratch/retry_hash.py` — small builds through `layout_retry` (NOT
  `layout()`), which is the only way to measure that function. `flat_hash.py`
  calls `layout()` directly, so it proves `layout.py` edits are neutral and
  says **nothing** about `layout_retry`.
- `scratch/qnet.py <seed> <vecA> <vecB> [recipe] [grow]` — drv + every load
  level for two vectors, netspec via the pre-shift dump with layout's own
  shift recovered (the OPEN raise is **pre**-shrink-wrap; `io` is post — this
  trap has cost three wrong probes before).
- `scratch/netmap.py <seed> <net> <vec4> [recipe] [grow]` — one net, every
  cell, level + block, in one vector.
- `scratch/probe_repback.py <seed>` — any repeater whose back is powered but
  whose front is dark. **Zero on micro1 s5**, which is what proved the boosters
  are not misaimed and the branch is *orphaned* instead.
- `scratch/probe_s5.py` / `probe_s5map.py` — the s5 autopsy (net levels; an
  annotated region map). **Caveat:** `probe_s5map.py`'s level glyph table is
  inverted for 0/1 (`lev[0]` prints `1`) — it cost a wrong turn once.
- Pre-existing and still valid: `census_cause.py` (**never** `census_capped.py`),
  `flat_hash.py`, `sweep_micro1.py`, `s3export.py`, `vanilla_audit.py`,
  `probe_seeds.py` (D-latch repro), `tile_arrival_level_attempts.diff`,
  `probe_onecircuit.py` (the rejected check, kept as the worked example).

### Deliberately untouched

`sim.py`, `core.py`, `recipe.py`, `serve.py`, `export.py`, `debug.py`, all
`.txt` recipes, all demo artifacts.

## Environment notes (still true, still cost time)

- Pipe nothing through `Out-String` when watching a long run. Log + poll.
- `Start-Process` errors with `ChildProcess.kill` and the child survives.
- Dense work: serialized, foreground, one build at a time. Never compare
  timings across runs that die at different walls, and check for stray load
  first. (There is an unrelated `chess_notifier.py` python process on this
  box; it is not ours and was left alone.)

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

