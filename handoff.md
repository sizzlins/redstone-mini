# Handoff — redstone-mini routing (2026-09-26 morning)

## Goal (evolved)
1. Phase 1 port grid → DONE, PR #1 merged.
2. Route dense datapaths → v1 lanes walled (below) → v2 trunks+relays tried,
   both hit walls → shipped maze per-hop + master boosters. 4-gate + micro1
   green (new). alu1/alu4 ceiling stands under every router tried.

## Current state
- **Master:** PR #1 merged (phase-1 tiles). Suite green.
- **Branch `phase2-design`** (uncommitted bridge fold-in pending push, PR #2 OPEN): maze per-hop routing +
  master boosters + rip-up restore + batch-1 OR levers + multi-lever inputs
  + `debug.py` instrument + or-lever self-check + NEW: crossover bridges,
  astar cap, driver-side ripup; firstport/NOR/io-bus dead
  code deleted; bus-plan docs removed from branch (attic'd, never merge); `recipe.py` == master (relay expansion reverted — sealed
  pockets). Audit cuts applied (minimize, adder8, bridges, `_free`, NOR
  branch, info loops → `scratch/attic.md`; bus plans → `scratch/attic-plans/`).
  Debt ledger `PONYTAIL-DEBT.md` (25 markers, 4 real ceilings). Worktree has
  scratch experiment copies (untracked there).
- **Green (verified):** suite (recipe/serve/sim/layout incl. new or-lever
  check); `example_and` (42/0), `example_2gates` (110/3), `latch_sr`
  (77/0), demo (110 blocks), 4-gate `0/6` + sequence, micro1 (1960/73).
- **Red:** alu1 (master reds identically — 86s thrash); alu4/cpu4 never
  routed under any router (maze/banded-maze/lanes/trunks/relays).
- **Honesty:** micro1 repeaters 73 vs master 46 — no economy won, only 4-gate.

## What changed (newest last)
1. Bridges + antifreeze + driver ripup (uncommitted, for PR #2 fold-in):
   single pre-proven crossover hop (last-resort, slope-aware open-check +
   `__main__` live-fire check); astar pop cap 100k (`REDSTONE_ASTAR_CAP`,
   micro1 green down to 5k); rip-up scans driver-side pre-raise (AB
   entombment fixed). Suite green, micro1 1960/2gates 110 identical.
   alu1 still red (fast-red; walls move per seed: AB/n0/t1 — standing wall
   is OR-bb delivery vs own-exit cluster, needs design talk). Bus-plan
   docs removed from branch (attic holds substance). bb-first ordering
   tried, reverted (micro1 >290s thrash).
2. Audit cuts to scratch (-190/+17): minimize, adder8, bridges, `_free`,
   NOR branch, info loops — all attic'd, suite + ladder re-verified green.
   Debt ledger written. Bus plan docs moved to `scratch/attic-plans/`.
2. v2 PR prep: or-lever self-check, suite + ladder re-verified, PR #1 merged,
   plan/handoff outcome notes. 4-gate + micro1 green on maze+boosters.
2. Rip-up loop restore (was the micro1 wall — dropped in v1, never replaced);
   micro1 green 2.1s. Batch-1 OR levers + feed-touch route filter (SHORT +
   serve-DEMO fixes, master patterns). Relay expansion reverted (3–9× tiles
   seal pockets under both routers; parity-proven but unroutable).
3. Trunk planner + debug system (`debug.py` + `REDSTONE_DEBUG` tap, kept);
   12 trunk fixes, wall moved every time → stopped per debugging rule.
4. Crossing-relays in `expand_gates` (share-per-band) + spike-fidelity proof
   (4→13, 10→36, 21→40, 72→648, all vectors) — then reverted per above.
5. (Prior session items 5–9 unchanged — see v1 plan era.)

## What failed (with evidence, no theory)
- **v2 trunks vs 4-gate/micro1:** 12 fixes (station offset, local fallback,
  own-station dodge, taken-gut, interval sort, feed-flex, ghost, grouped
  shuffle, lever search, band-None, multi-lever, port dust) — wall moved
  every time: hubs sealed (`no jog×132`), single-boost hops >28 cells,
  minefield threading. Structural: rigid geometry can't thread dense tile
  fields. STOPPED per debugging rule; planner deleted (~210 lines).
- **Relays vs maze+trunks:** 4-gate 55s+red (13 tiles), micro1 red (28
  tiles); pure master greens same logic relay-free (4-gate 0.0s, micro1
  2.3s). Tiles seal pockets. Reverted.
- **v1 lanes vs 4-gate:** mutual walling under pitch-2 (0/200 seeds).
  (Prior-session detail was in the v1 plan doc, now in `scratch/attic-plans/`.)
- **alu4 relay blowup (spike datum):** 576 bufs for 72 gates — moot after
  revert, recorded only.
- **alu1/alu4 ceiling:** red under maze (unbanded + banded, 86–260s thrash),
  lanes, trunks, relays. Shared with master; not a regression.

## Files touched
- **Tracked, on `phase2-design`:** `layout.py` (maze per-hop + boosters +
  rip-up + batch-1/multi-lever + or-lever check; firstport/NOR/io-bus
  deleted); `debug.py` (new instrument); `sim.py` (minimize call dropped);
  `recipe.py` (minimize/adder8/NOR-branch deleted); `export.py` (info loops
  merged); `redstone_mini.py` (`--alu8` path deleted); `PONYTAIL-DEBT.md`
  (new ledger); `handoff.md` (this file).
- **Tracked, on master:** PR #1 (phase-1 tiles) merged in.
- **Gitignored (never merge):** `scratch/` keepers (`countrep.py`,
  `check4gate.py`, `exportmicro.py`) + `scratch/attic.md` (cut code) +
  `scratch/attic-plans/` (bus plan docs); `build.*` outputs.
- **Worktree (scratch experiments, not for merge):**
  `C:\Users\LOQ\AppData\Local\Temp\opencode\maze-relay` (master + file copies).
- **Untouched:** `serve.py`, `core.py`.

## What next (in order)
1. **Merge v2 PR #2** (`phase2-design` → `master`, open, green).
2. **alu1/alu4 routing** — open architectural question (new design talk
   first; no blind patches; trunk+relay+maze avenues exhausted with data).
3. **Do NOT:** add maze heuristics (~20 reverted); trust mental tile
   coordinates (`debug.py` instead); merge `scratch/` or the worktree.
