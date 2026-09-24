# Tap-nearest-live-wire routing — design

Approved: 2026-09-24. Status: spec, not yet implemented.

## Goal

Let each load tap the nearest same-net wire that already conducts from its
driver (short hop), instead of running the full marathon home. Expected to
unlock moderate-span shared nets (control decode); genuine over-density
(adder/ALU/CPU marathons) may still fail — report, don't promise.

## 1. Mechanism (route() only; astar untouched)

- `route(a, b, net)` builds starts = driver `a` plus same-net wire cells
  reachable from `a` through same-net cells and junctions (connected
  component — dead islands excluded), nearest-first to the goal `b`,
  bounded to 8 taps (A* heap cost stays flat).
- Deterministic: taps sorted by distance to goal, no randomness.
- Why the connectivity guard: unbounded taps once tapped dead islands and
  broke the XOR example (unconnected dust); live-only taps keep that
  failure mode out by construction.

## 2. Acceptance

- `ctrl_decode.txt` routes and verifies (all vectors, sim-checked).
- Green gate unchanged: demo 132, and 46, xor 482, 2gates 132, latch 84
  with `latch ok: set/hold/reset/hold`, `sim.py` self-checks,
  `serve.py --check`, `python recipe.py` — counts move only per the
  (ticks, blocks) score rules.
- adder8/alu4/cpu4: report failure points before/after; no green promised.

## 3. Out of scope

Bus columns, fanout trees, placement or tile changes, vertical
construction, new block types. Each is a separate spec when a build
needs it.
