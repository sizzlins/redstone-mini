# Handoff — redstone-mini routing (2026-09-26 evening)

## Goal (evolved)
1. Phase 1 port grid → DONE, PR #1 merged.
2. Phase 2 routing → v1 lanes walled → v2 trunks+relays tried, both hit
   walls → shipped maze per-hop + master boosters. 4-gate + micro1 green.
   alu1/alu4 ceiling stands under every router tried.
3. Hardening (NEW, shipped): crossover bridges, astar anti-freeze cap,
   driver-side rip-up. Suite green, greens byte-identical.
4. Single-lever panel (DECIDED 2026-09-26: ship with ceiling): south
    bank, inputs ride the router. Small builds green and cheaper
    (demo 270→246 blocks); micro1 red under every variant (see What
    failed). Panel-vs-micro1 call went to the user → ship, note ceiling.

## Current state
- **Master:** PR #1 merged (phase-1 tiles). Suite green (multi-lever).
- **Branch `phase2-design`** (PR #2 OPEN): commits through `6dd2b78`
  (Task-3 cleanup + median-band bank + inputs-first) — all committed and
  pushed pending. Panel plan doc still untracked
  (`docs/plans/2026-09-26-single-lever-panel.md`, never merge as-is).
- **Green (verified, WITH panel):** full suite — `recipe.py`, `sim.py`
  (incl. crossover), `serve.py --check`, `layout.py` (ports + or-lever +
  panel + bridge checks); `example_and`, `example_2gates` (110),
  fanout probe (534, shared input exactly 1 lever), demo (270 blocks).
- **Red/slow:** micro1 + panel (full retry >290s unfinished; pre-panel
  2s/1960 blocks). alu1 fast-red (walls move per seed: AB/n0/t1);
  alu4/cpu4 never routed under any router.
- **Honesty:** panel costs real wire — demo 110→270 blocks, fanout 534.
  micro1 repeaters 73 vs master 46 (pre-panel) — no economy won, only 4-gate.
  Debt-ledger old rows predate the bridge line-shift (grep `ponytail:`).

## What changed (newest last)
1. Panel experiment: brainstorm (4 sections approved) → spec
   (`docs/superpowers/specs/2026-09-26-single-lever-panel-design.md`,
   committed) → plan (`docs/plans/`, untracked) → subagent Tasks 1–2
   (bank commit `9980297`, routing commit `7efe42e`, both review-clean).
   Task 3 subagent cancelled mid-flight (left uncommitted edits + 3
   runaway pythons at ~800s CPU — killed); Task 3 completed inline
   (orbbs/feeds dead-code deletion, panel check, or-lever message
   batch→bank). Suite green throughout. Micro1 thrash found via timed
   probes (earlier "slow" readings were broken inline-quote probes —
   SyntaxError on stderr, fixed by moving to `scratch/*.py`).
2. Bridges + antifreeze + driver ripup (committed `2b68e72`, in PR #2):
   single pre-proven crossover hop (last-resort, slope-aware open-check +
   live-fire check); astar pop cap 100k (`REDSTONE_ASTAR_CAP`, micro1
   green down to 5k, 20× cap reproduces identical walls — cap innocent);
   two-tier rip-up (goal-side first, driver-side pre-raise; AB entombment
   fixed). Bus-plan docs removed from branch (attic holds substance).
   bb-first ordering tried, reverted (micro1 >290s thrash — ordering
   games backfire).
3. Audit cuts to scratch (-190/+17) + debt ledger + v2 PR prep + rip-up
   restore + relay revert (see prior handoff; unchanged).
4. Trunk planner deleted (~210 lines, 12-fix debug-rule stop); relays
   reverted (seal pockets); v1 lanes walled (0/200 seeds).

## What failed (with evidence, no theory)
- **Panel vs micro1 (decided: ship, note ceiling):** three fixes tried
  with timings — inputs-last (seal moved gates→OP, 26s/try), median-band
  bank (OP marathon 160→26 cells, demo 270→246, goals still sealed 11s),
  inputs-first+median (W goal sealed by S-bridge's own supports+rings).
  Grow ruled out (78s, still sealed — entombment is local). Bridges ruled
  out (23 free hops exist but feet land inside the wall; segments can't
  reach). Relay chaining ruled out (fanout 2 < 3, buffers park at bank).
  Verdict: single south-bank driver can't enter dense tile rows on the
  flat y=1 mesh. Small builds unaffected (suite green incl. panel check).
  Full data: `scratch/panel-micro1-report.md` (gitignored).
- **alu1 standing wall:** gate-fed OR diode-backs buried 1 cell inside
  their own OR's diode/exit cluster (dump-proven, seed=1: t1→(78,14)).
  Neither order, rip-up, nor 1-hop bridges dissolve it — placement
  geometry, needs design talk.
- **Attempt economics:** red attempts run 55–408s even capped; 36-combo
  retry is hours. Background + poll + per-attempt timeouts mandatory;
  never trust foreground on dense builds.
- **Subagent ops lesson:** cancelled Task-3 left edits + runaways; inline
  `python -c` with multiline recipes breaks on pwsh (use `scratch/*.py`
  with sys.path insert, capture stderr).
- **Prior:** trunks (12 fixes, wall moved each time), relays (seal
  pockets), lanes (0/200), alu4 relay blowup datum (576 bufs/72 gates).

## Files touched
- **Tracked, on `phase2-design`:** `layout.py` (bridges + cap + two-tier
  ripup + panel bank/routing/check, COMMITTED through `7efe42e` EXCEPT
  Task-3 cleanup + panel check + message fix = UNCOMMITTED);
  `PONYTAIL-DEBT.md` (+4 bridge/cap rows, +2 watch items);
  `docs/superpowers/specs/2026-09-26-single-lever-panel-design.md` (new);
  `debug.py`, `sim.py`, `recipe.py`, `export.py`, `redstone_mini.py`
  (phase-2/audit, committed); `handoff.md` (this file).
- **Untracked (never merge as-is):** `docs/plans/2026-09-26-single-lever-panel.md`.
- **Gitignored (never merge):** `scratch/` keepers + `probe_panel.py`,
  `probe_micro1.py`, `micro1.log/.err` (this session's probes);
  `scratch/attic.md`, `scratch/attic-plans/`; `build.*` outputs.
- **Untouched:** `serve.py`, `core.py`.

## What next (in order)
1. **Panel decision DONE (ship with ceiling)** — user chose ship on
    2026-09-26. No revert, no redesign this round.
2. **Merge v2 PR #2** — panel code is in the branch, committed
    (`6dd2b78`); push + merge.
3. **alu1/alu4 routing** — open architectural question (OR-cluster
   geometry first; trunk+relay+maze+bridge avenues exhausted with data).
4. **Do NOT:** add maze heuristics (~20 reverted); trust mental tile
   coordinates (`debug.py` instead); merge `scratch/` or the worktree;
   run dense retries in foreground (background + poll + timeouts);
   dispatch long subagents unattended (they leave runaways when cancelled).
