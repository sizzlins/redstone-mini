# MORNING-REPORT — 2026-10-02 night session

Headline: **alu4 is green — 1024/1024 vectors verified.** The last open item
from the previous session (alu4) plus the stitch item I offered are both
closed. Nothing is blocked. Full trail in LOG.md, section "alu4 root cause".

## What now builds

| build | verdict | evidence |
|---|---|---|
| **alu4** (10 inputs, 1024 vectors) | **GREEN, all 1024** | `VERIFY OK: 1024 vectors, 16 chunks green`, cache fp `327ee4a52f1b` |
| cpu4 (7 inputs) | GREEN, 128/128 | re-verified from scratch under the new engine |
| alu1 | GREEN, 12,294 blocks | `alu1_regress` after the fix |
| ctrl_decode | GREEN, 4,923 blocks | same run |
| example_and / 2gates / latch_sr / xor | GREEN | `compose_check.py` |
| suites | GREEN | `sim.py`, `layout.py`, `diff_engine` ALL IDENTICAL |

## What was actually wrong with alu4

Two independent things, found in this order.

1. **The old artifact was a ghost.** `scratch/alu4merge.pkl.verify.json`
   said 64/64 green, but it was written 10/1 23:19 and the diode-facing flip
   (`29fc565`) landed 10/2 10:56. Re-verified today, that merge is RED on all
   16 chunks — every failure `Y2`/`Y3` with `B2`/`B3` set. Nothing to salvage;
   a rebuild was mandatory. Kept as `alu4merge.preflip.pkl`.

2. **The rebuild hunted.** 6/6 bands green, MERGE 41,031 blocks, all-zero
   settled, but **15 of 24 sampled vectors never settled** (0 logic
   mismatches — a pure ring). The churn dump + the repo's own cycle finder
   (extended with repeater/lever/rblk/comparator edges) gave the shortest
   ring: 6 nodes on net `OP1x_3` —
   `torch (2044,1,34) → dust (2045,1,34) → dust (2045,1,35) → repeater
   (2044,1,35) → dust (2043,1,35) → cobble (2043,1,34) → torch`. One inverter
   plus one wire latches the band-3 handoff; twin at `(2060,1,33)` on
   `OP0x_3`.

**Fix (commits `f825af0`, `8c9c510`)**: a booster may not push power into a
tile torch that has its own net beside it. Applied in `compose._ends_ok` (the
planter's predicate, with the torch-host map cached on ctx) and in layout's
booster loop (unwind and try the next triple, like the existing loop check).
`finish_assembly` keeps a loud all-scan version so nothing hunted can ship.
Then: bands rebuilt under the new router → MERGE 41,031 → **all four smokes
OK** → **1024/1024 green** on the first attempt.

## The bug behind the bug (worth knowing)

`_closes_loop` / `_loop_rep` flood same-net **dust over blocks**, and
`_ends_ok` only checks that a booster's front/back cells carry its own net.
A ring that leaves the dust **through a torch** — a directed, inverting edge —
is invisible to both. That is the whole class, and it is now guarded at
placement *and* at assembly.

Related trap, now written down: layout's booster helpers use
`front = cell + _VEC[facing]`, but sim treats `facing` as pointing
output→input, so the real output cell is `cell - _VEC[facing]`. Measured on
this merge: **2426 of 2426 repeaters disagree** between the two readings.
Harmless so far only because those helpers are direction-agnostic.
`_booster_out_cell` is the single place that encodes sim's rule.

## The stitch item I offered — solved at the root instead

I proposed a seed/spread knob so the stitch could retry until it found a
legal geometry. Not needed and not added: the failure was a placement *rule*,
not bad luck, so fixing the rule makes the first attempt green instead of
burning retries on a ladder. What the pipeline did need was the missing link
in the chain — `hier_stitch.py` gained an optional 4th argument that saves the
merged build to a pkl, because `verify_par` reads a pkl and nothing could
hand it one.

## Still failing / not done (nothing blocking)

- **True 3D tile stacking.** Unchanged from before: physics is proven, the
  compiler migration (~140 `y==1` assumptions) is still not built.
  `tiles.new_ctx` says "migrate the maps or don't start".
- **`alu4` build time.** The bands are cached, but a cold `hier_bands` +
  `hier_stitch` + full verify is ~25 min of wall clock. Not a defect.
- **In-game paste.** Never tested on a real Minecraft client. Every verdict
  in this repo is the sim agreeing with itself plus wiki rules.
- **Band caches are not fingerprinted.** Only verify caches are. The lesson
  from cpu4 (stale band inputs) is still enforced by hand — flagged in LOG
  as future work.

## Needs you

Nothing. No password, payment or secret was required. The only judgement call
I made without asking was the assumption recorded in LOG.md: skip the retry
knob because the root-cause fix subsumes it.