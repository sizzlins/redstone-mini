# Phase 2 — Bus routing

Status: planned. Predecessor: Phase 1 (port grid). Successor: Phase 3 (clock).

## Goal
Replace maze A\* with Manhattan bus routing: inputs enter on parallel bus
lanes, vertical stubs drop to the Phase-1-aligned tile ports, repeaters at
fixed stations. Kills maze sprawl, repeater scatter, and multi-lever
(one lever per input driving the bus head).

## Design
- **Bus lanes**: straight parallel runs, 2 cells apart (touch-safe by
  construction), spanning the field east-west.
- **Stubs**: north/south jogs from lane to tile port (ports sit on grid
  rows per Phase 1 spec; exceptions documented there).
- **Repeater stations**: boosters at fixed intervals (every 14) on bus
  lanes only — never scattered, never on tile dust.
- **Taps**: branch wires may tap a bus ONLY at repeater outputs
  (always full-strength). Rationale, load-bearing: tapping mid-decay dust
  caused decayed weak taps; connected-tap + shortest-first retries broke
  xor (2026-09). The repeater-output rule is what makes taps sound.
- **Levers**: exactly one per input, at its bus head. Multi-lever
  (per-load taps) is deleted with the maze router that required it.

## Non-goals
No layers/bridges (still flat single-layer). No clock (still
combinational + level latches). No new tile types. No sim physics changes.

## Verification gate
- Suite green (same list as Phase 1).
- micro1 + alu4 route with an order of magnitude fewer repeaters than
  maze routing produced.
- 4-gate latch + sequence still green.
- Sim remains the selector: `layout_retry(verify=True)` must pass.

## Risks
- Dense bands may still need `grow` retries where lanes saturate; the
  retry/grow machinery is unchanged and stays the backstop.
- The tap rule is the load-bearing invariant: any future tap relaxation
  must re-prove the xor case first.
