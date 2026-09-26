# Handoff — redstone-mini (2026-09-26 night)

## Goal (evolved)
1. Phase 1 port grid → DONE, PR #1 merged.
2. Phase 2 routing → lanes/trunks/relays walled → shipped maze per-hop +
   master boosters + bridges + astar cap + two-tier rip-up. PR #2 MERGED
   (`0e686a5`).
3. Single-lever panel (DECIDED: ship with ceiling) → MERGED in PR #2.
   Small builds green and cheaper (demo 270→246); dense builds red (see
   What failed).
4. CPU builds (all 8 .txt green, single lever everywhere) → design round
   DONE (spec + plan committed), two mechanisms disproven (see What
   failed). Parked with narrowed options, no blind patches.
5. Sim correctness (shipped): lamp pointing rule + `sim_pulse`
   timeline proofs. Suite green.
6. Mechanics research (NEW, done): `scratch/redstone-mechanics-report.md`
   (Wiki-sourced, sim cross-checked, video-triangulated).

## Current state
- **Master:** PR #2 merged. Phase-2 router + panel + hardening all in.
- **Branch `phase2-design`** (ahead 11, behind 1 — push needs a force
  decision): prior 8 + `9e4f803` dense-green spec (bus lanes + repeater
  taps), `1bf6e4b` implementation plan (tasks 1-5), `e5afcb5` Task 1 bus
  lanes pre-claim (tiles dodge via `spot_free`). Worktree clean
  (Task-2 trunk + recipe-relay work reverted, verified green after each).
- **Green (verified, re-run this session):** full suite — `recipe.py`,
  `sim.py`, `serve.py --check` (demo 246), `layout.py` (ports, or-lever,
  panel, bridge). Acceptance bar per owner: all 8 `.txt` recipes
  (`micro1, alu1, alu4, cpu4, ctrl_decode, example_and/2gates/xor,
  latch_sr`) verify green + one lever per used input.
- **Red (standing ceilings):** micro1/alu1/alu4/cpu4 with panel (single
  south-bank driver can't enter dense tile rows; row fits gates xor
  delivery). Pre-panel micro1 was green (2s/1960) — panel inputs are the
  entire delta. NEW: full-width bus trunks wall the suite; input relay
  thrashes past 600s (both reverted, see What failed).
- **Backlog (ponytail-sorted):** (1) timed sources — sim_pulse SHIPPED,
  plates/observers open; (2) CPU dense-green — spec+plan done, Task 1
  shipped, open choice: interleaved lanes / routine bridges / park;
  (3) locking/burnout/containers/pistons-QC — YAGNI deferred, no consumer;
  (4) remote sync — force approval pending.

## What changed (newest last)
1. Bridge-primary disproven, PARKED (`layout.py` reverted): bridge-first +
   try-all-candidates with rollback; single-shot still `no route for Q`
   (dump: goal ringed by tile solids `T0` cobble + `T1` repeater, zero
   foreign wire — no hoppable seal exists); background full-retry hit the
   600s-silence bound with empty log. Suite green after revert.
2. Staircase spec SUPERSEDED (`fd5a428` stands as history): lane→port leg
   unfillable flat for 2-load inputs (order-isomorphism).
   via installed `buf_of` (census x2 + `outidx` guard); micro1 full-retry
   exceeded 600s silent (baseline completes red) — 10→18 gates adds
   obstacles + marathons. Suite green after revert.
2. Bus trunk disproven (`layout.py` reverted to `e5afcb5`): full-width E-W
   trunk wire is itself a wall — suite broke (`sim.py`: `no route for S
   (7,81)->(5,16)`, `no route for a (7,81)->(4,12)`); stations don't open
   crossings (solid cell + neighbour touch). Fixes tried inside the task:
   bank→trunk jogs bridge sibling lanes (`W bridges D at (55,1,34)`),
   levers-on-lanes hit own-lever solid. Suite green after revert.
3. Task 1 shipped (`e5afcb5`): bus lanes pre-claim (`z=(D-4)-idx*2`,
   E-W `1..W-1`) + `spot_free` dodge; suite green, micro1 still red
   (`T1 (126,12)->(196,12)`, then `Q (73,14)->(124,12)` full-retry).
4. Plan + spec committed (`1bf6e4b`, `9e4f803`): dense-green B+C
   (lanes/trunk/taps/OR-dodge/acceptance); spine-first survey via 3
   subagents; owner scope: all 8 `.txt`, `layout.py`-first.
5. `sim_pulse` + dwell guard (`e8c6880`): timed-press timeline proofs
   (press-20 lights, holds 1, drops by 5). Buttons need no new blocks.
6. Lamp pointing rule (`3077d1b`): lamps need pointing-at dust; exposed a
   real layout bug (4 placement guards compared 2D cells to the 3D wire
   map — always false): fixed lamp/OR-junction/OR-diode/bank overlap
   checks, one line each. Suite green throughout after fix.
7. Mechanics report: dust→pistons, Wiki + video sources, per-section
   `[SIM OK]`/`[GAP]` vs `sim.py`. New gaps named, all out of build scope.
8. Lanes round (reverted via `6dc34c2`): trunks + E-W + stubs delivered
   inputs green (probes), but gate marathons lost the row; arbitration
   trio (unrippable/placed-victims/bridge-first) fixed S, died on R.
9. West-bank spike (reverted same turn): even 25-cell parallel runs seal —
   the row itself is airtight.
10. Corridor round (reverted): reservations self-seal (west rays cross
   sibling lanes; bank-ward rays die in tiles; 1-gate AND went dark).
11. Spine round (reverted): taps decay dark (sim-proven), rip orphans
   branches, bridge arbitration exceeds budget (single-shot under-delivers,
   chaining thrashes >300s).
12. Panel shipped (median-band bank + inputs-first + Task-3 cleanup,
   `6dd2b78`); PR #2 merged; handoff + debt updated.

## What failed (with evidence, no theory)
- **Dense input delivery:** every variant fails — star (>290s), taps
  (sim-dark), orderings (wall moves), grow (78s, local entombment),
  pitch (no effect), bridges (feet inside walls), corridors (self-seal),
  west bank (parallel lanes airtight), lanes (row fits gates xor
  delivery), bus trunks (full-width wire walls the suite: `S/a` no-route,
  reverted), input relay (10→18 gates, >600s silent vs baseline that
  completes, reverted), bridge-primary (rollback over all candidates:
  tile-solid seals hold no hoppable wire; full-retry 600s silent,
  reverted). Dump-proven per goal (foreign/ring/solid on all sides). Verdict: only interleaved lanes / routine bridges untested —
  owner picks, no blind patches.
- **alu1 OR-cluster wall (pre-existing):** gate-fed diode-backs buried in
  their own OR cluster (seed=1: t1→(78,14)). Untouched by all rounds.
- **Attempt economics:** red attempts 55–408s capped, relay run >600s
  silent (killed per 600s rule); 36-combo retry is hours. Dense builds
  background + poll ONLY (a foreground full-retry blocked 10 min this
  session). `Start-Process` lacks `-RedirectOutput` here — use
  `cmd /c start /b ... > log 2>&1`. Single-shot `layout(r, seed=None,
  grow=0)` fails fast and suffices for mechanism proofs.
- **Probe hygiene:** dump values are JSON lists — never compare to tuples
  (silently vacuous; burned two probes). Inline `python -c` with multiline
  recipes breaks on pwsh (use `scratch/*.py`). Cancelled subagents leave
  runaways; inline execution only.

## Files touched
- **Tracked:** `sim.py` (pointing rule + probes + `sim_pulse`), `layout.py`
  (panel bank/routing/check + spine-first order + 4 overlap-guard fixes +
  Task-1 lane pre-claim/dodge); `PONYTAIL-DEBT.md` (panel-era ceiling rows;
  lane/spine/corridor/trunk/relay work reverted before ledgering — only
  shipped rows stand); specs
  `2026-09-26-{single-lever-panel,spine-fed-input-distribution,
  input-port-corridors,deterministic-input-lanes,dense-panel-green}-design.md`
  (middle three: history, do not implement); plan
  `docs/plans/2026-09-26-dense-panel-green.md` (tasks 2-5 blocked/superseded
  except Task 1 + Task 5 economics); `handoff.md` (this file).
- **Untracked (never merge):** `docs/plans/2026-09-26-{single-lever-panel,
  spine-fed-input-distribution,input-port-corridors,
  deterministic-input-lanes}.md`.
- **Gitignored (never merge):** `scratch/` probes (`probe_*.py`, lane/corridor
  dumps, `panel-micro1-report.md`, `redstone-mechanics-report.md`,
  `raymap.py`, `latchlamp.py`); `*.log`; `build.*`.
- **Untouched:** `serve.py`, `core.py`, `recipe.py`, `export.py`, `debug.py`.

## What next (in order)
1. **Sync remote** — branch diverged (ahead 11, behind 1); needs explicit
   force-with-lease approval. Nothing at risk locally either way.
2. **Timed sources, continued** — plates/observers only if a build needs
   them; locking/burnout/containers/pistons stay YAGNI until consumed.
3. **CPU dense-green** — PARKED (ponytail pick 2026-09-26: no consumer,
   flat-field family exhausted with data). Reopen only for a real build
   needing it, interleaved lanes first. Gating bar if reopened: all 8
   `.txt` verify green, one lever per input, suite green. Never a blind
   patch.
4. **Do NOT:** add maze heuristics; trust mental tile coordinates
   (`debug.py` + dump queries instead); merge `scratch/` or plans;
   foreground dense retries; unattended long subagents; tuple-compare
   JSON dump values; shared flat trunks or netlist relay without a dump
   naming the sealer first.
