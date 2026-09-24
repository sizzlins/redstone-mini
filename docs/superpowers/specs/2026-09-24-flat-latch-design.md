# Flat SR latch — design

Approved: 2026-09-24. Status: spec, not yet implemented.

## Goal

Give recipes memory: `Q = LATCH S R` (set/reset, holds when quiet), built
flat from existing block types, proven by simulation. Unlocks registers;
deliberately not compact (vertical stacking stays a later project).

## 1. Language and evaluator

- New primitive in `recipe.py`: `Q = LATCH S R` (two args, like AND).
  `OPS` extended; single output Q, no Qbar.
- `eval_net` iterates the whole net to a fixed point (at most 20 passes)
  instead of assuming feedforward order. Acyclic recipes evaluate
  identically to today; cyclic (latch) nets settle or raise
  `ValueError("no stable state")` on oscillation.
- `expand_gates` keeps LATCH as a primitive end to end (no expansion into
  NORs). Banded recipes: LATCH carries its band like any gate; banded
  placement treats it as a tile (same code path as AND/NOR/NOT).

## 2. Tile (flat, existing block types only)

- Same construction pattern as the AND compound: hand-stamped cobble +
  wall torches + dust stubs, guard rings over the family of nets, S/R
  in-ports, Q out-port, footprint box for the reservation system.
- S/R lever taps follow the existing first-port pattern (batch-2 levers).
- No exporter changes (cobble/torch/dust/lever/lamp only).
- No `sim_verify` physics changes (it simulates placed blocks, and already
  settles feedback loops). Forbidden input S=R=1 documented as garbage-in
  (matches real hardware: both outputs drop, release races).

## 3. Proving memory: sequence harness

- Truth tables cannot express "still on after input goes quiet", so add a
  small sequence driver: it runs the existing tick engine through input
  phases within one settled run (S pulse → Q=1 → release → Q stays 1 →
  R pulse → Q=0 → release → Q stays 0).
- New test code in `sim.py` (`__main__` assert block, repo convention);
  not a simulator rewrite.
- Green gate unchanged: demo/and/xor/2gates counts, `sim.py` self-checks,
  `serve.py --check` — plus the latch sequence asserts.

## 4. Out of scope

Qbar output, edge-triggered/clocked latches, vertical (multi-level)
construction, comparator/piston/hopper parts, adder8 routing. Each is a
separate spec when a build needs it.
