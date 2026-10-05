# MORNING REPORT — 2026-10-05 (optimization shift 2: speed, and one red flag)

Repo `D:\redstone-mini`, branch `phase2-design`. Full trace in `LOG.md`;
my instruments are in `scratch/` and each says what it is for in its docstring.

**Read this first: the paste-ready alu4 build disagrees with `cmc` on 2286
cells, and it is not from tonight.** Details in "THE RED FLAG" below. It does
not make the build wrong, but it is the one thing here I would not ship without
your paste test.

---

## 1. What builds now

| build | verdict | evidence |
|---|---|---|
| **alu4** (10 inputs, 71,560 blocks) | **GREEN 1024/1024** | `verify_par` cold, exit 0, 35.9s. Bands 6/6: 13304 · 7518 · 6957 · 571 · 2414 · 4878 |
| **alu1 hier** | **GREEN 32/32** | `hier_verify`, exit 0, 37.2s |
| examples / latch / xor / micro1 / ctrl_decode | GREEN, bit-identical | 144 / 322 / 224 / 214 / 2925 / 5499 |
| alu1 **flat** (nonhier suite) | RED **by design** since `124d179` | 22-gate banded recipe, `22 < _TERR_MIN_GATES=40` |
| cpu4 | RED by inheritance (pre-dates this repo's sessions) | Y2 cross-band coupling |

Paste-ready: **`build_alu4full.schem`** (hash-verified copy already in
`…/worldedit/schematics/`). `build_alu4.*` and `build_alu4bank.*` are **stale**
— do not paste those.

Every gate re-run green after every change: `sim.py` 8 canaries, `simvec.py`
self-check, `compose.py`, `compose_check`, `nonhier_suite` 6/6,
`diff_engine` **ALL IDENTICAL** (3-way: frozen `HEAD:sim.py` == live
`sim._run_vec` == the new table engine), `hier_verify` alu1, alu4 1024/1024.
`mkref.py` + `refcheck.py` re-run after the `simvec.py` commits.

## 2. What I changed, with numbers

Everything below is in `simvec.py`'s table engine, `scratch/verify_par.py`, and
one env gate in `compose.py`. The engine is **~2.8x** the original per vector,
measured interleaved in one process so machine load cannot flatter it.

| # | change | measured |
|---|---|---|
| 1 | Int-indexed tables + bytearray state. Tables were 112 MB and 0.4s per worker; `wake` alone was 59 MB of `(kind,cell)` tuples and `d_dirs` 28 MB of nested tuples | **1.62x/vector, 2.8x less RAM** |
| 2 | Z-order (Morton) cell ids — pure relabelling, invisible to the physics | 1–7% under concurrency |
| 3 | Coalescing marker: fresh `set()` per bucket → one reused bytearray per ring slot | **1.05x** (268k set-adds/vector gone) |
| 4 | Sign-encoded ring items — a wake append is now a plain reference, no `<< 1` | **1.05x** (268k allocations/vector gone) |
| 5 | **Exact wake map.** `wake` was geometric; only 45% of its edges are read by any relation | **1.11x**, 54.6% of the walk provably dead |
| 6 | **Boolean edges wake only on a zero crossing.** 57.4% of edges only care *whether* a cell is lit, not how much | **1.06x**, `_cob_state_s` calls halved (149k→62k/vector) |
| 7 | `verify_par`: a worker owns a *group* of chunks, so tables are built once per worker, not once per chunk | ~1–5% (see retracted #2) |
| 8 | `REDSTONE_ASTAR_MARGIN` env gate (default **unchanged** at 64) | answers your queued question; 64 is load-bearing |
| 9 | Drop the `cid` dict from the hot tables (it existed to serve 5 lamp lookups/vector; those are now precomputed `lamp_ids`) | 40.6 → 38.1 MB |

Headline: **full 1024-vector alu4 sweep, 16 workers, cold: 108.7s → 35.7s (3.0x)**.
Per worker: tables 112.5 MB → 40.6 MB, peak heap 230.8 MB → 75.6 MB.
Python-level calls per 5 vectors: 11.52M → 1.72M (**6.7x fewer**).

**Tried, measured, not banked** (so nobody re-derives them): cyclic-GC
hypothesis (82808 tracked objects, 0 gen2 collections, `gc.disable()` = 1.00x);
`if v:` guards on the dust classes (~2%, noise); amortising the stall check
(1.00x); reading each changed cell's state once instead of twice (1.00x);
turning `_dust_lvl_s`/`_cob_state_s` into closures over `run_scalar`'s locals
(~1.01x); neighbour-locality via Morton was mostly *not* the parallelism
answer; the pre-astar flood and bound-prune ideas from the previous session.

**Where the parallelism ceiling actually is:** per-vector cost goes 0.233s
alone → 0.377s at 4 workers → 0.775s at 16. Aggregate saturates at ~4.9x on 16
workers because the box is an i7-13650HX (14 physical / 20 logical,
hyperthreaded) with a co-tenant agent and a Minecraft server resident. Parallel
tuning is bounded by the machine, not by this code.

## 3. THE RED FLAG — alu4 vs cmc

`verify2 --diff-all` on the banked build **fails**:

```
DIFF: dust 49814/1957248 cells differ, repeaters 7280/279552 differ
DUAL-ENGINE VERDICT: FAIL
```

**It predates tonight, proven:** `REDSTONE_SERIES_VERIFY=1` runs the authority
engine `sim._run_vec`, and `sim.py` is byte-identical to what I inherited
(`refcheck`: `worktree sim.py == HEAD:sim.py`). It produces the *same numbers
to the digit*.

**Shape:** 2286 distinct cells in one contiguous region — x 1082–1095, y 1–3,
z 167–183 — a decay ladder our sim reads 12–15 and cmc reads 0. So the risk
direction is *our sim being too generous*, the opposite sign to the
comparator-front bug fixed in `38b872f`.

**Update from the other agent's session (not mine, and it narrows this a lot):**
they were chasing the same class on `alu4bank_ins` and found the disagreement is
confined **entirely to dust** — no comparator, repeater or lamp inside any
disagreeing component, 14 of 18 comparator outputs identical, and the few that
differ go *both* ways. Their hypothesis is that it is not a power, comparator or
decay rule at all, but **how each engine decides which dust neighbours are
connected**: our sim reads the blockstate `east/west/north/south` params, cmc
derives connectivity itself. That is consistent with my region being decay
ladders (i.e. propagation across a connection boundary) and it lowers the alarm
somewhat — it may be neither engine being wrong about power. It is not yet
proven, and it is a narrower question than "which engine is right".

**Why it was never caught:** `verify2` had only ever been run on alu4's *lamp*
verdict, where both engines say green. Both still do — ours on all 1024 vectors
against the logical oracle. The disagreement is internal wire state that does
not move the lamps, which is precisely the sim-overfit class: green in sim,
different in the game.

**Specific to alu4:** I re-ran alu1 tonight → `0 / 204224`, DUAL-ENGINE PASS
(the GA agent measured 0/179296 on alu1glass, 0/25872 on add2opt).

Reproduce (bounded; doc is cached so a re-run is sim-only):

```
python scratch/verify2.py recipes/alu4.txt scratch/alu4merge_g.pkl --diff-all
python scratch/diffwhy.py scratch/alu4merge_g.v2doc.json --examples 8
python scratch/simwhy.py scratch/alu4merge_g.v2doc.json 35 1082 1 169
```

**I did not fix it.** It is physics forensics, it belongs to whoever owns
`sim.py` semantics, and I was not opening a semantics change at the end of a
speed shift. It is reported with commands instead.

## 4. Three numbers of mine that were wrong

I retracted these in `LOG.md` rather than leaving them to be cited:

1. **"Table build 7.78s → 8.60s, a regression."** Both numbers were measured
   under `tracemalloc`, which inflates by more than 10x. Measured clean:
   0.395s old vs 0.353s new — the new tables build *faster*.
2. **"Grouped chunks = 1.33x."** One sample each. Re-ran twice: old 82.6/119.2s,
   new 77.7/98.5s. The within-variant spread exceeds the difference. Real
   effect ~1–5%.
3. **"Engine 1.62x."** That used vector indices 0–4, the easy end. Interleaved
   over *spread* indices three times: 2.19x / 2.10x / 2.10x. The final engine
   measures 2.78–2.86x against the original on the same instrument.

**Rule this box taught me:** single-run wall clock is not a measurement here
(~36s spread on an 80s run — 14 physical cores, hyperthreaded, plus a
co-tenant agent and a Minecraft server). Only interleaved same-process ratios
mean anything. `scratch/tbl_diff.py` now takes a `REDSTONE_TBLDIFF_REF` so a
micro-opt is A/B'd against the engine it replaces, and a byte-identical
reference must read 1.00x before I trust it. Two of my own probes (`tbl_equiv`,
`wake_miss`) also had the target/reader direction inverted and reported
confident nonsense until I fixed them — the engine had the same inversion once.

**Stronger caveat, learned late:** even the interleaved ratio is biased LOW by
up to 40% on this box. Null check on byte-identical code reads 0.61x–0.96x,
never 1.00x — probably thermal throttling on the laptop CPU, with the reference
always running cooler first. So every shipped win above was measured *against*
that bias (the true wins are at least as large), every "null" rejection might
be masking a small real win (reverting was still correct — unmeasurable wins do
not ship), and fine distinctions are unmeasurable here until the null reads
1.00x. The micro-opt loop is therefore suspended; correctness gates are immune
and keep running. `REDSTONE_WAKE_EXACT=0` / `REDSTONE_WAKE_BOOL=0` /
`REDSTONE_SERIES_VERIFY=1` are the escape hatches if anyone doubts any of it.

### Tools I added (each says what it is for in its docstring)

`tbl_diff.py` old-vs-new differ over all six returned values, on *spread*
vector indices, with three deliberate fault injections so a differ that has
never gone red is visibly untested · `tbl_equiv.py` exhaustive table
equivalence · `wake_need.py` / `wake_miss.py` / `wake_split.py` the wake-map
measurements · `tbl_probe.py` / `tbl_sizes.py` / `build_prof.py` memory and
build cost · `tickdiff.py` first divergent tick · `evlog.py` event-stream diff.

## 5. What I need from you

1. **Paste `build_alu4full.schem`** — never tested, and §3 makes it matter more.
2. **Decide on alu4 vs cmc** (§3). It is a physics question, not a speed one.
3. Stale files: `build_alu4.*`, `build_alu4bank.*`, `build.*.bak`,
   `build_alu1.html` (stale). I never delete.
4. **README is materially wrong** — still not fixed (I never got to it; it says
   "doesn't model timing yet", documents only `--alu8`, never mentions hier,
   the 1024-vector alu4, or alu4bank). It is ~20 lines of work.

## 6. Also true, for whoever reads this next

- **Another agent was committing to this tree during the shift** (`fa58552`,
  `f81977c`, and a stub `f81977c`-class commit after my cold start). My
  `diff_engine` was re-earned on their HEAD and stayed green. They own
  `scratch/sweep*`, `scratch/mkref.py`, `scratch/ref*`.
- **`hier_verify.py recipes/alu4.txt` now earns the alu4 green end-to-end (FIXED,
  not by me).** It used to exit 1 at `SMOKE 1010101010` because the load-bearing
  `ins_target` 3-pillar swap was an out-of-band manual step. The co-tenant agent
  wired it in (`4d98d4c`, "hier_verify was missing the load-bearing ins_target
  step"). I verified their fix rather than duplicating it: bands 6/6 → stitch →
  advisory smoke 3/4 → swap → smoke 4/4 → **VERIFY OK 1024 vectors, 16 chunks
  green, exit 0** in 173.7s. Same family as the two gate bugs already fixed, and
  now closed the same way: the green is re-earnable from the documented command.
- The `parallax`/GA agent owns the **cpu4** Y2 coupling, which I never touched.
## Session continues (same night) -- three tools, two refutations

**`scratch/coldstart.py` -- one command, 8 gates, 4.6 minutes, all green.**
The four broken gates shared a cause: nobody ran them, and each passed
unnoticed because the *other* gates were green. `coldstart.py`,
`--quick`, `--sweep`, `--only` included. Verified `8/8 green, exit 0`.
It re-checks the freeze *after* `mkref` rewrites it, because `mkref` cannot
report its own failure -- my first version had the honest name
`mkref_then_drift` while doing exactly that.

**`scratch/notmin.py` -- the regression seam for the non-pin lever.**
A 16-block, router-free, hand-placed comparator-subtract inverter with a glass
floor, through *both* engines on A=0/A=1 in 2s. Currently exit 1 with the
predicted signature (`sim=0 cmc=15` at A=0). The fix is still not applied; now
it cannot be forgotten.

**`scratch/coverage.py` -- the sweep truly covers everything.** 98 pkls:
48 real circuit builds, **all gated**. The 50th is `stackfail.pkl`, whose
function cannot be recovered from its pins and no recipe covers -- a deliberate
non-gate, since writing the recipe would be guessing at the oracle. The other
49 are band caches and state dumps (pipeline inputs, not circuits), largest 235
MB. `scratch/` is 1.05 GB across 1496 files; three `_states.pkl` are ~550 MB
and my own sweep's cells dumps contribute. Nothing deleted.

**Open B corrected twice.** I first called `alu4bank_ins` a
"propagation/structure" gap from one probe -- wrong; it is 633 scattered
dust-only fragments, largest 17 cells, with 14/18 comparators agreeing exactly.
Then I hypothesised params-vs-geometry; **`scratch/wireconn.py` refutes it in
30s** -- both engines push 15->14 across a join whose params say unconnected,
so neither reads params over geometry. Next cheapest probe: whether the diff
*shrinks* with more cmc settle ticks (a settling artifact would; a rule gap
would not). Not yet run.

**Coordination, still live:** the optimisation agent has uncommitted
`simvec.py` edits in the worktree. Nothing of theirs staged, reverted, or
touched. Their `5e2a25a` rewrite already deleted one latent crash I was about
to log. The `coldstart --quick` gate ran green against the tree with those
uncommitted edits present -- but treat engine-sensitive numbers as provisional
until they commit.

## CORRECTION (same night) -- my "0 diff" on alu4 was a sampling artifact

The optimisation agent ran `verify2 --diff-all` on `alu4merge_g.pkl` at
**64 vectors** and found **dust 49814/1957248 cells and 7280/279552 repeaters
differing**. I reproduced it to the digit:

    DUAL-ENGINE VERDICT: FAIL   (sim=True cmc=True diff=49814/1957248 cells)

My sweep ran **4 vectors** and found 0/122328. Both numbers are true; mine
covered 4 of 1024 vectors. The divergence lives on vectors I never sampled,
in one contiguous region (their words: x 1082..1095, y 1..3, z 167..183,
a ladder sim reads 12..15 and cmc reads 0 -- the *opposite* sign to the
comparator-front bug). **Both engines still pass functionally**, so the lamps
agree and the divergence is internal wire state -- the sim-overfit class.

They proved it predates tonight (the authority engine gives identical numbers
to the digit; `sim.py` byte-identical to HEAD). I am not re-proving that; I
reproduced the headline number and it matches.

What this costs my claims above:
- "0 per-cell diff" for the 12 alu4 builds holds **only at 4 vectors**.
  The sweep rows now carry `n_vectors`, `vectors_sampled`, `engine` and
  `cmc_stage` so a sampled green cannot read as exhaustive again.
- The alu4 1024/1024 lamp claim stands (both engines pass; verified).
- The per-cell story for alu4 is OPEN, not closed.

Worth stating plainly: this is the second time tonight a "clean" result
turned out to be a coverage artifact (the first was the resumed `CACHED` rows
with no numbers). The pattern is that a gate which *looks* exhaustive but is
sampled will be read as exhaustive. Making coverage a visible field is the
durable fix.

## Status refresh -- probes, containment, corrections (same night, later)

**Probe matrix, all 2-second runs** (`coldstart --probes` runs them
informationally; gates stay green):
| probe | result | meaning |
|---|---|---|
| `wireconn.py` | AGREE 15/14 | neither engine reads params over geometry |
| `stairdown.py` | AGREE 14/13 + lamp | isolated fall on cobble fine |
| `lid.py` | AGREE 15/14/13 + lamp | horizontal flow under a lid fine |
| `stair.py` | dust AGREE, lamp SPLIT | rise fine; sim leaves riser-tip lamp dark, cmc lights it (open) |
| `stairglass.py` | **DIVERGE 0 vs 13** | down-flow onto glass: sim refuses, cmc powers |
| `notmin.py` | **DIVERGE 0 vs 15** | non-pin lever: sim blind (Finding 3) |

**Containment for Finding 3** (after a fresh-context adversarial review that
called "do nothing" survivorship bias): `verify2` now lists every lever sim
cannot power in the verdict and prints `GATE WARNING`; sweep rows surface it.
Zero physics risk. Full directional fix still deferred (other agent mid-flight
on `simvec.py`).

**Corrections to my own claims:** (1) stackfail.pkl is sim-green/cmc-red, NOT
green/green -- cmc miscomputes its AND, so the hole is upgraded to a surfaced
divergence, not closed; (2) alu4 "0 diff" was 4-of-1024 vectors, corrected to
the 64-vector 49814-cell finding with coverage fields now on every sweep row;
(3) "49 junk files" are 235 MB of legitimate band caches/state dumps.

**alu4merge_g 49k, current:** localized to vertical staircases, both
directions, narrowed past sources/locks/decay/params/settling/rise/fall to a
cobble-lidded joint; basic lid agrees so it needs staircase+lid combined.
`coldstart` runs 8 gates green in ~5 min; `--probes` reports the 3 known
divergences without touching the exit code.

## Red-build census (all 28 characterized, same night)

| class | count | builds | meaning |
|---|---|---|---|
| both red | 22 | alu4_build/bank/fresh/av, alu4ctrl1-6, alu1_current, cpu4bank/merge* etc. | stale/broken artifacts, red in both engines |
| sim red, cmc green | 3 | cpu4merge2, cpu4retry_merge (TORCH BURNOUT guard, by design); **not_full** (sim blind to constant lever, Finding 3) | sim refuses or cannot see |
| sim green, cmc red | 3 | alu4mergeNEW/NEW4 (cmc structural support refusal, closed); **stackfail** (cmc miscomputes its AND -- sim proves the recipe on all 8) | cmc refuses or miscomputes |

No uncharacterized reds. `coldstart` 12/12 green including the 3 locked-in probes
(wireconn, stair_rise with 3D lamp key, stair_fall, lid). The stair lamp "split"
was my keying error throughout -- 2-tuple keys map to y=1, a lamp at y=3 needs
its full (x,y,z); with the right key sim lights it. Fourth setup error caught
by running.

## 2026-10-05 GA night loop -- 49k CLOSED, coldstart 14/14 green
49k-cell alu4merge_g diff is CLOSED as cmc settling, not a rule gap. Single-vector ladder: vec47 2260 cells @400 ticks -> 146 @600 -> 0 @800 -> 0 @1200/@1600; vec62/vec29 0 @1600. Full 64-vector re-gate at 1200 ticks: dust 0/1957248, repeaters 0/279552, DUAL-ENGINE PASS (sim 13s, cmc 865s). Fix: verify2.py default --ticks 400->1200 (one line; tiny probes cost the same seconds). New probes, all in coldstart GATES and green: stairlid.py (dust-cobble-dust joint from 1097,1-3,182 agrees -- direct stacks never link), repchain.py (R1->7dust->R2 agrees at 400 and 1600), repface.py (all 4 facings agree -- facing convention exonerated, closes that open item). coldstart --quick 14/14 green. Still open and UNCHANGED (need operator/game, not unilateral): glass down-flow stairglass sim=0 cmc=13, non-pin lever notmin, cpu4 untouched. Red census unchanged: 28/28 characterized. Assumption: 1200 ticks covers all banked builds (largest gated is 129953-block cpu4retry_merge; re-gate on touch).

## 2026-10-05 GA night loop FINAL -- all falsifiable items closed
Full coldstart 15/15 green (hier_alu4 1024/1024 in 207s). Sweep at 1200 ticks: 21 green both / 28 red all characterized / 2 DIFFs (alu4bank_ins both-red opposite-sign; not_full Finding-3). Slab census: 0 slabs in 2,522,792 banked blocks -- slabfall refusal cannot affect any build. What builds: alu4 1024/1024 both engines + 0/1957248 per-cell (receipt: scratch/alu4merge_g.v2doc.json.verdict.json), alu1 hier 32/32, all probes agree. What still fails (unchanged, need YOU): glass down-flow needs wiki/game call (sim 0 vs cmc 13, fix mapped to sim.py:405 + simvec mirror, not applied unilaterally); non-pin lever needs directional-source physics in both engines (notmin seam ready); cpu4 untouched (other lane); paste build_alu4full.schem never tested in-game. Commits tonight: d6b74e7 4ba4214 a72e5d5 dc399cd 01ea4db + slab/coldstart close. Co-tenant live in tree (verify_par.py uncommitted, untouched).
