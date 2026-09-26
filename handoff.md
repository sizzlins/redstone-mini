# Handoff — redstone-mini (2026-09-26 night)

## Goal (evolved)
1. Phase 1 port grid → DONE, PR #1 merged.
2. Phase 2 routing → lanes/trunks/relays walled → shipped maze per-hop +
   master boosters + bridges + astar cap + two-tier rip-up. PR #2 MERGED
   (`0e686a5`).
3. Single-lever panel (DECIDED: ship with ceiling) → MERGED in PR #2.
   Small builds green and cheaper (demo 270→246); dense builds red (see
   What failed).
4. CPU builds (micro1/alu/cpu green, single lever everywhere) → PARKED
   after 4 failed delivery rounds (see What failed). Next thesis recorded.
5. Sim correctness (NEW, shipped): lamp pointing rule + `sim_pulse`
   timeline proofs. Suite green.
6. Mechanics research (NEW, done): `scratch/redstone-mechanics-report.md`
   (Wiki-sourced, sim cross-checked, video-triangulated).

## Current state
- **Master:** PR #2 merged. Phase-2 router + panel + hardening all in.
- **Branch `phase2-design`** (ahead 7, behind 1 — push needs a force
  decision): `92bea23` spine-first order, `6df10f8` spine spec, `09cc91a`
  corridor spec (origin tip), `963cadd` lanes spec, `3077d1b` lamp
  pointing + overlap-guard fixes, `e8c6880` sim_pulse, `c842aa5` handoff.
  Worktree clean.
- **Green (verified):** full suite — `recipe.py`, `sim.py` (tick, pulse,
  latch, verticals, pointing, crossover, comparator), `serve.py --check`
  (demo 246), `layout.py` (ports, or-lever, panel, bridge); fanout probe
  (one lever per input, unused lever-less).
- **Red (standing ceilings):** micro1/alu1/alu4/cpu4 with panel (single
  south-bank driver can't enter dense tile rows; row fits gates xor
  delivery). Pre-panel micro1 was green (2s/1960) — panel inputs are the
  entire delta.
- **Backlog (ponytail-sorted):** (1) timed sources — sim_pulse SHIPPED,
  plates/observers open; (2) CPU placement reform — parked thesis;
  (3) locking/burnout/containers/pistons-QC — YAGNI deferred, no consumer;
  (4) remote sync — force approval pending.

## What changed (newest last)
1. `sim_pulse` + dwell guard (`e8c6880`): timed-press timeline proofs
   (press-20 lights, holds 1, drops by 5). Buttons need no new blocks.
2. Lamp pointing rule (`3077d1b`): lamps need pointing-at dust; exposed a
   real layout bug (4 placement guards compared 2D cells to the 3D wire
   map — always false): fixed lamp/OR-junction/OR-diode/bank overlap
   checks, one line each. Suite green throughout after fix.
3. Mechanics report: dust→pistons, Wiki + video sources, per-section
   `[SIM OK]`/`[GAP]` vs `sim.py`. New gaps named, all out of build scope.
4. Lanes round (reverted via `6dc34c2`): trunks + E-W + stubs delivered
   inputs green (probes), but gate marathons lost the row; arbitration
   trio (unrippable/placed-victims/bridge-first) fixed S, died on R.
5. West-bank spike (reverted same turn): even 25-cell parallel runs seal —
   the row itself is airtight.
6. Corridor round (reverted): reservations self-seal (west rays cross
   sibling lanes; bank-ward rays die in tiles; 1-gate AND went dark).
7. Spine round (reverted): taps decay dark (sim-proven), rip orphans
   branches, bridge arbitration exceeds budget (single-shot under-delivers,
   chaining thrashes >300s).
8. Panel shipped (median-band bank + inputs-first + Task-3 cleanup,
   `6dd2b78`); PR #2 merged; handoff + debt updated.

## What failed (with evidence, no theory)
- **Dense input delivery:** every variant fails — star (>290s), taps
  (sim-dark), orderings (wall moves), grow (78s, local entombment),
  pitch (no effect), bridges (feet inside walls), corridors (self-seal),
  west bank (parallel lanes airtight), lanes (row fits gates xor
  delivery). Dump-proven per goal (foreign/ring/solid on all sides).
  Verdict: placement reform is the remaining thesis (reserved boxes pin
  tiles to columns — unproven, do not start without a design round).
- **alu1 OR-cluster wall (pre-existing):** gate-fed diode-backs buried in
  their own OR cluster (seed=1: t1→(78,14)). Untouched by all rounds.
- **Attempt economics:** red attempts 55–408s capped; 36-combo retry is
  hours. Background + poll + timeouts mandatory. `Start-Process` lacks
  `-RedirectOutput` here — use `cmd /c start /b ... > log 2>&1`.
- **Probe hygiene:** dump values are JSON lists — never compare to tuples
  (silently vacuous; burned two probes). Inline `python -c` with multiline
  recipes breaks on pwsh (use `scratch/*.py`). Cancelled subagents leave
  runaways; inline execution only.

## Files touched
- **Tracked:** `sim.py` (pointing rule + probes + `sim_pulse`), `layout.py`
  (panel bank/routing/check + spine-first order + 4 overlap-guard fixes);
  `PONYTAIL-DEBT.md` (panel-era ceiling rows; lane/spine/corridor work
  reverted before ledgering — only the shipped median-bank + inputs-first
  rows stand); specs
  `2026-09-26-{single-lever-panel,spine-fed-input-distribution,
  input-port-corridors,deterministic-input-lanes}-design.md` (last three:
  history, do not implement); `handoff.md` (this file).
- **Untracked (never merge):** `docs/plans/2026-09-26-{single-lever-panel,
  spine-fed-input-distribution,input-port-corridors,
  deterministic-input-lanes}.md`.
- **Gitignored (never merge):** `scratch/` probes (`probe_*.py`, lane/corridor
  dumps, `panel-micro1-report.md`, `redstone-mechanics-report.md`,
  `raymap.py`, `latchlamp.py`); `*.log`; `build.*`.
- **Untouched:** `serve.py`, `core.py`, `recipe.py`, `export.py`, `debug.py`.

## What next (in order)
1. **Sync remote** — branch diverged (ahead 7, behind 1); needs explicit
   force-with-lease approval. Nothing at risk locally either way.
2. **Timed sources, continued** — plates/observers only if a build needs
   them; locking/burnout/containers/pistons stay YAGNI until consumed.
3. **CPU placement reform** — parked; reopen with a design round (dynamic
   boxes + gate-fed spiral), never a blind patch. Gating bar stays: all
   five builds verify green, one lever per input, suite green.
4. **Do NOT:** add maze heuristics; trust mental tile coordinates
   (`debug.py` + dump queries instead); merge `scratch/` or plans;
   foreground dense retries; unattended long subagents; tuple-compare
   JSON dump values.
