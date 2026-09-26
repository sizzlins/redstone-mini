# Handoff — redstone-mini (2026-09-26 night)

## Goal (evolved)
1. Phase 1 port grid → DONE, PR #1 merged.
2. Phase 2 routing → lanes/trunks/relays walled → shipped maze per-hop +
   master boosters + bridges + astar cap + two-tier rip-up. PR #2 MERGED
   (`0e686a5`).
3. Single-lever panel (DECIDED: ship with ceiling) → MERGED in PR #2.
   Small builds green and cheaper (demo 270→246); dense builds red (see
   What failed).
4. CPU builds (all 9 .txt green, single lever everywhere) → flat family
   exhausted with data (see What failed). Owner DECIDED: implement 3D
   (item 7). No more flat mechanisms.
5. Sim correctness (shipped): lamp pointing rule + `sim_pulse`
   timeline proofs. Suite green.
6. Mechanics research (done): `scratch/redstone-mechanics-report.md`
   (Wiki-sourced, sim cross-checked, video-triangulated).
7. 3D router (DECIDED 2026-09-26, NEW): volumetric tiles, 6-dir A* with
   priced level changes, sim verticals past slope-links, placement using
   height. Design round first, micro1-first ladder, background-only dense
   attempts. Only un-disproven direction; corroborated by RedstoneBuilder
   comparison (3D P&R scales to a 242-gate ALU, nothing flat does).

## Current state
- **Master:** PR #2 merged. Phase-2 router + panel + hardening all in.
- **Branch `phase2-design`** (ahead 16 + this handoff, behind 1 — push
  needs a force decision): Task-1 lanes (`e5afcb5`), dense-green spec +
  plan (`9e4f803`, `1bf6e4b`), staircase spec as history (`fd5a428`),
  XOR tile fix (`2fb620d`). Worktree clean (trunk/relay/bridge/BAND work
  all reverted, suite green after each).
- **Green (verified, re-run this session):** full suite — `recipe.py`,
  `sim.py`, `serve.py --check` (demo 246), `layout.py` (ports, or-lever,
  panel, bridge); `example_and/2gates`, `latch_sr`, `example_xor` (fixed
  this session) verify green. Acceptance bar per owner: all 9 `.txt`
  (`micro1, alu1, alu4, cpu4, ctrl_decode, example_and/2gates/xor,
  latch_sr`) verify green + single lever per input (XOR keeps tile side-
  levers by strong-side geometry; bank stays single).
- **Red (standing):** micro1/alu1/alu4/cpu4 + ctrl_decode with panel.
  Pre-panel micro1 was green (2s/1960) — panel inputs are the entire
  delta. `example_xor` was red since the panel merged (never pinned by
  suite) — FIXED this session, see What changed.
- **Backlog (ponytail-sorted):** (1) 3D router — DECIDED, design round is
  the next work; (2) timed sources — sim_pulse SHIPPED, plates/observers
  open; (3) locking/burnout/containers/pistons-QC — YAGNI deferred, no
  consumer; (4) remote sync — force approval pending.

## What changed (newest last)
1. 3D DECIDED + field survey: shallow-cloned RedstoneBuilder to temp
   (outside repo) and mapped its P&R vs ours — 3D grid + volumetric
   cells, negotiated-congestion PathFinder, SA placement, Steiner fanout;
   no CPU anywhere (biggest proof: 8-bit ALU ~242 gates, slow/ignored;
   biggest non-ignored green: 5-gate adder). Portable lesson:
   history-kept congestion only (taps/diodes already mirror the rest);
   the load-bearing gap is 3D. Their pipeline gaps noted too (placement
   cost ignores Y; slab/glass crossing helpers test-only).
2. micro1 BAND attempt (reverted): hand-banded `micro1.txt` datapath
   order (6 bands, existing machinery, zero code change). Single-shot
   died on a short hop (`R (36,27)->(52,12)`, goal enterable, tile mass
   seals mid-path); background full-retry 600s silent, killed on bound.
   Bands shorten distance, seals aren't distance. File reverted.
3. XOR tile fixed (SIM-dark → green): routed rears arrive decayed (~4),
   8-cell merge ate it; two south-facing merge diodes + 1-cell drv
   extension (lamp feed is a tip again — C2's output cell sat beside it,
   failing the pointing rule all 36 tries). `example_xor` verify green
   (164 blocks); suite green.
4. Bridge-primary disproven, PARKED (`layout.py` reverted): bridge-first +
   try-all-candidates with rollback; single-shot still `no route for Q`
   (dump: goal ringed by tile solids `T0` cobble + `T1` repeater, zero
   foreign wire — no hoppable seal exists); background full-retry hit the
   600s-silence bound with empty log. Suite green after revert.
5. Staircase spec SUPERSEDED (`fd5a428` stands as history): lane→port leg
   unfillable flat for 2-load inputs (order-isomorphism argument).
6. Input relay disproven (`recipe.py` reverted): 2+-load inputs chained
   via installed `buf_of` (census x2 + `outidx` guard); micro1 full-retry
   exceeded 600s silent (baseline completes red) — 10→18 gates adds
   obstacles + marathons. Suite green after revert.
7. Bus trunk disproven (`layout.py` reverted to `e5afcb5`): full-width E-W
   trunk wire is itself a wall — suite broke (`sim.py`: `no route for S
   (7,81)->(5,16)`, `no route for a (7,81)->(4,12)`); stations don't open
   crossings (solid cell + neighbour touch). Fixes tried inside the task:
   bank→trunk jogs bridge sibling lanes (`W bridges D at (55,1,34)`),
   levers-on-lanes hit own-lever solid. Suite green after revert.
8. Task 1 shipped (`e5afcb5`): bus lanes pre-claim (`z=(D-4)-idx*2`,
   E-W `1..W-1`) + `spot_free` dodge; suite green, micro1 still red
   (`T1 (126,12)->(196,12)`, then `Q (73,14)->(124,12)` full-retry).
9. Plan + spec committed (`1bf6e4b`, `9e4f803`): dense-green B+C
   (lanes/trunk/taps/OR-dodge/acceptance); spine-first survey via 3
   subagents; owner scope: all `.txt`, `layout.py`-first.
10. `sim_pulse` + dwell guard (`e8c6880`): timed-press timeline proofs
   (press-20 lights, holds 1, drops by 5). Buttons need no new blocks.
11. Lamp pointing rule (`3077d1b`): lamps need pointing-at dust; exposed a
   real layout bug (4 placement guards compared 2D cells to the 3D wire
   map — always false): fixed lamp/OR-junction/OR-diode/bank overlap
   checks, one line each. Suite green throughout after fix.
12. Mechanics report: dust→pistons, Wiki + video sources, per-section
   `[SIM OK]`/`[GAP]` vs `sim.py`. New gaps named, all out of build scope.
13. Lanes round (reverted via `6dc34c2`): trunks + E-W + stubs delivered
   inputs green (probes), but gate marathons lost the row; arbitration
   trio (unrippable/placed-victims/bridge-first) fixed S, died on R.
14. West-bank spike (reverted same turn): even 25-cell parallel runs seal —
   the row itself is airtight.
15. Corridor round (reverted): reservations self-seal (west rays cross
   sibling lanes; bank-ward rays die in tiles; 1-gate AND went dark).
16. Spine round (reverted): taps decay dark (sim-proven), rip orphans
   branches, bridge arbitration exceeds budget (single-shot under-delivers,
   chaining thrashes >300s).
17. Panel shipped (median-band bank + inputs-first + Task-3 cleanup,
   `6dd2b78`); PR #2 merged; handoff + debt updated.

## What failed (with evidence, no theory)
- **Dense delivery (flat, exhausted):** star (>290s), taps (sim-dark),
  orderings (wall moves), grow (78s, local entombment), pitch (no
  effect), bridges last-resort (feet inside walls), bridge-primary
  (tile-solid seals hold no hoppable wire; full-retry 600s silent),
  corridors (self-seal), west bank (airtight), lanes (gates xor
  delivery), bus trunks (wall the suite), input relay (10→18 gates,
  >600s silent), hand-BAND datapath order (short hops seal like
  marathons; full-retry 600s silent). Dump-proven per goal
  (foreign/ring/solid on all sides). Verdict: flat holds no mechanism;
  3D is the only un-disproven direction.
- **alu1 OR-cluster wall (pre-existing):** gate-fed diode-backs buried in
  their own OR cluster (seed=1: t1→(78,14)). Untouched by all rounds.
- **Attempt economics:** red attempts 55–408s capped, three runs >600s
  silent (relay, bridge-primary, BAND — all killed per 600s rule);
  36-combo retry is hours. Dense builds background + poll ONLY (two
  foreground full-retries blocked 10 min and 7 min this session).
  `Start-Process` lacks `-RedirectOutput` here — use
  `cmd /c start /b ... > log 2>&1`. Single-shot `layout(r, seed=None,
  grow=0)` fails fast and suffices for mechanism proofs.
- **Reproducibility (NEW):** same-args builds differ across processes —
  hash-seed iteration order of bridge-candidate ties (`cands` sort is
  stable over randomized insertion). Same-process runs are identical.
  Not fixed; pin with fully-sorted candidate keys when builds must be
  compared across processes.
- **Probe hygiene:** dump values are JSON lists — never compare to tuples
  (silently vacuous; burned two probes). Inline `python -c` with multiline
  recipes breaks on pwsh (use `scratch/*.py`). Cancelled subagents leave
  runaways; inline execution only.

## Files touched
- **Tracked:** `sim.py` (pointing rule + probes + `sim_pulse`), `layout.py`
  (panel bank/routing/check + spine-first order + 4 overlap-guard fixes +
  Task-1 lane pre-claim/dodge + XOR merge diodes/drv extension);
  `PONYTAIL-DEBT.md` (panel-era ceiling rows; lane/spine/corridor/trunk/
  relay/bridge work reverted before ledgering — only shipped rows stand);
  specs `2026-09-26-{single-lever-panel,spine-fed-input-distribution,
  input-port-corridors,deterministic-input-lanes,dense-panel-green,
  staircase-lanes}-design.md` (all but panel/green: history, do not
  implement); plan `docs/plans/2026-09-26-dense-panel-green.md` (tasks 2-5
  blocked/superseded except Task 1 + Task 5 economics); `micro1.txt`
  (BAND attempt, reverted — net zero); `handoff.md` (this file).
- **Untracked (never merge):** `docs/plans/2026-09-26-{single-lever-panel,
  spine-fed-input-distribution,input-port-corridors,
  deterministic-input-lanes}.md`.
- **Gitignored (never merge):** `scratch/` probes (`probe_*.py`, lane/corridor
  dumps, `panel-micro1-report.md`, `redstone-mechanics-report.md`,
  `raymap.py`, `latchlamp.py`); `*.log`; `build.*`.
- **Outside repo (no cleanup needed):** temp clone of RedstoneBuilder +
  `pre-lanes` worktree (both under `Temp/opencode`, worktree removed).
- **Untouched:** `serve.py`, `core.py`, `recipe.py`, `export.py`, `debug.py`.

## What next (in order)
1. **3D router — design round first (DECIDED, funded by owner):** volumetric
   tile cells, 6-dir A* with priced level changes, sim verticals past
   slope-links (support/lid rules), placement using height. Micro1-first
   ladder (`micro1→alu1→alu4→cpu4`), one mechanism per attempt with
   keep-or-revert, background-only dense runs with the 600s-silence kill
   rule. Gating bar: all 9 `.txt` verify green, single lever per input
   (XOR tile sides exempt by geometry), suite green.
2. **Sync remote** — branch diverged (ahead 16 + this handoff, behind 1);
   needs explicit force-with-lease approval. Nothing at risk locally
   either way.
3. **Timed sources, continued** — plates/observers only if a build needs
   them; locking/burnout/containers/pistons stay YAGNI until consumed.
4. **Do NOT:** flat mechanisms of any kind (exhausted — needs a dump naming
   a sealer that 3D wouldn't dissolve); trust mental tile coordinates
   (`debug.py` + dump queries instead); merge `scratch/` or plans;
   foreground dense retries; unattended long subagents; tuple-compare
   JSON dump values; cross-process build diffs without pinned candidate
   order.
