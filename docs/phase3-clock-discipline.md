# Phase 3 — Clock discipline

Status: planned. Predecessor: Phase 2 (stable combinational behavior).

## Goal
Make the builds synchronous: a global clock net plus edge-triggered
registers instead of bare level-sensitive latches. Kills the
transparent-latch glitch class (races on simultaneous input changes)
permanently, and matches how real redstone CPUs are built.

## Design
- **D-flop tile**: master-slave pair of gated latches (wiki design H),
  built from the existing proven latch geometry. One new tile type,
  hand-verified like the others.
- **Clock tree**: single clock net distributed with balanced delays so
  every flop sees the edge together (matched wire lengths ± repeater
  staging; the repeater-station machinery from Phase 2 is reused).
- **Recipes gain edge semantics**: `Q = DFF D CLK` (new primitive,
  parsed like `LATCH`). No sim physics changes needed — two latches
  already simulate; edge behavior falls out of the master-slave
  arrangement.
- **Sequences move to edges**: set/hold/reset/hold proofs assert on
  clock edges instead of level windows.

## Non-goals
No new sim physics. No pipelining. No multi-phase clocks (single edge).
No changes to combinational tiles or the bus router.

## Verification gate
- New D-flop tile: truth table + setup/hold behavior asserted in sim.
- Latch sequence proofs re-expressed on clock edges, green.
- Suite green (same list as Phase 1).
- micro1-equivalent demo circuit converted to clocked form, verified.

## Risks
- Clock skew across large builds is the classic failure; the balanced
  tree + repeater staging is the mitigation, verified by edge sequences.
- Recipes using bare `LATCH` keep working (no forced migration).
