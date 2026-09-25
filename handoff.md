# Handoff — redstone-mini bus routing (2026-09-25 evening)

## Goal (evolved)
1. Phase 1 port grid → DONE, PR #1 open (`phase1-tiles`, unmerged).
2. Replace maze A\* so dense datapaths route → v1 horizontal lanes hit a
   structural wall (below) → v2 (relays + N-S trunks) specced, relay core
   proven by spike, v2 implementation plan NOT yet written.

## Current state
- **Master + suite green** (untouched all session: `sim/recipe/export/serve`
  green, demo 114 blocks maze-era).
- **Branch `phase1-tiles`** (pushed): lamp east-first (1 line) + lamp-anchored
  port-grid asserts in `layout.py.__main__`. PR #1 OPEN, unmerged.
- **Branch `phase2-design`** (local only, 8 commits on master): v1 bus router
  (planner + stamp + order search), v1+v2 plans, v2 spec. Worktree clean.
- **Green under v1 bus (verified):** `example_and` (42 blocks/0 reps),
  `example_2gates` (90/3), `latch_sr` (77/0), demo (90 blocks, was 114),
  `python layout.py` ports ok. `build.html` currently holds the DEMO
  (overwritten by the Task-3 demo run; gitignored, no repo impact).
- **Proven by spike (temp-only, NOT committed):** relay-split expansion —
  every hop spans ≤1 band gap (asserted) + truth tables identical pre/post
  on 4-gate (4→13 gates, 4 vectors), micro1 (10→36, 16), alu1 (21→40, 32),
  alu4 (72→648, 1024).
- **Red:** v1 lanes fail 4-gate 6/6, micro1 (net S skipper); alu4/cpu4 never
  routed under any router (maze ceiling stands).

## What changed (newest last)
1. v2 brainstorm (trunks + relays, §§1–3 approved) → v2 spec committed
   (`docs/superpowers/specs/2026-09-25-bus-v2-design.md`).
2. STOPPED v1 implementation per debugging rule (8 root-cause fixes, wall
   just moved): committed progress on `phase2-design`, reverted temp hacks.
3. v1 order search (25 shuffles/call) + decay budgets + station shift +
   OPEN-trace solid repeaters + driver jogs + stub L-shapes + pitch-2 +
   ring-awareness. Each verified; each revealed the next wall.
4. v1 Tasks 1–2 done (planner+probe, stamp, small builds green).
5. Phase-2 v1 plan written; brainstorm (big-bang, every-net-lane) before it.
6. Phase-1 plan executed; handoff updated; PR #1 created.
7. Older (from prior session): 4-gate latch maze fix, alu1 logic proof 32/32,
   phase specs + Phase-1 plan docs, ~20 reverted maze heuristics.

## What failed (with evidence, no theory)
- **v1 lanes vs 4-gate:** mutual walling — D@10 walls nD south (pitch),
  W@17 walls east rows, S-AND tiles wall center. 0/200 seeds (≈5000 order
  samples) + forced-order probe (wall moves, never falls). Structural:
  rigid straight lanes + pitch-2 cannot pack interleaved port rows.
- **v1 vs micro1:** net S (band 1→3 skipper), no lane row. Same class.
- **alu4 relay blowup (spike datum):** per-column chaining on unbanded
  auto-columns = 576 bufs for 72 gates. Structurally sound, needs cost
  control (share? limit? accept?) before layout.
- **Plan bugs fixed en route:** OUT/gate mismatch, easternmost anchor
  (shrink-wrap translates coords), tap-coord typo, tuple seeds,
  probe lane-7/stations, unconditional "sequence ok" print, task-reviewer
  pre-judgment traps. Process calibration: hand-simming tile geometry
  failed repeatedly — instrument (`dbgrows` pattern) or replicate in
  probes; never trust mental coordinates.

## Files touched
- **Tracked, on `phase2-design`:** `layout.py` (v1 bus router: plan_bus +
  order search + stamp + trace fix); `docs/plans/2026-09-25-phase2-bus.md`
  (v1 plan, in sync — mechanical parity check 0 diffs);
  `docs/superpowers/specs/2026-09-25-bus-routing-design.md` (v1 spec);
  `docs/superpowers/specs/2026-09-25-bus-v2-design.md` (v2 spec).
- **Tracked, on `phase1-tiles`:** `layout.py` (lamp line + `__main__`
  asserts), `handoff.md` (phase-1 section).
- **Gitignored (never merge):** `scratch/countrep.py`, `scratch/check4gate.py`
  (honest skip print), `scratch/exportmicro.py` runs.
- **Temp only (prove, don't merge):** `probe_bus.py`, `relayspike.py`,
  `parity*.py`, `sweepfour.py`, `dbg*.py`.
- **Untouched:** `sim.py`, `recipe.py`, `export.py`, `serve.py`, `core.py`.

## What next (in order)
1. **Write the v2 implementation plan** (`docs/plans/2026-09-25-phase2-bus-v2.md`):
   Task 1 crossing-relays in `expand_gates` (+ `__main__` asserts, transcribe
   the proven spike) + retire-vs-keep call on old fanout/replication;
   Task 2 trunk planner (transpose v1 legality core) + probe; Task 3 stamp +
   small builds; Task 4 ladder with 4-gate FIRST + repeater ratio; Task 5
   self-check + suite + retire dead code (v1 orphans: astar/route/firstport/
   NOR/heapq/TORCH_BACK/paths + old expander mechanisms) + push.
   Base: `phase2-design` as-is. Pre-decided in spec: no minimize guard needed
   (expansion runs post-minimize — verify by reading, not memory).
2. **Decide the alu4 buf question before layout:** accept 8× tiles, share
   chains, or limit relay depth (spec gate counts repeaters, not blocks —
   but 648 placements must still fit/verify).
3. **Execute v2 plan** (subagent-driven vs inline — ask then).
4. **Land:** merge PR #1 first (v2 base assumes it), then v2 PR.
5. **Do NOT:** add maze heuristics (~20 reverted for migrating failures);
   trust mental tile coordinates (instrument instead); merge `scratch/`.
