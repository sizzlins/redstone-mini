# Ponytail debt ledger

Generated 2026-09-26 from `ponytail:` comment markers (`grep -rnE '(#|//) ?ponytail:'`).
Each row: location, what was simplified, the named ceiling, the trigger to
revisit. Rows tagged `no-trigger` name no ceiling or upgrade path — those
rot silently. Check-markers (`ONE runnable check`, self-checks) are the
anti-rot devices themselves, listed for completeness.

// Convention drift note: most markers below document rationale, not
// ceiling+trigger. Only four rows carry real ceilings.

## export.py

- export.py:13, textures stream from upstream asset pack, no PNGs in repo.
  ceiling: network at view time. upgrade: none named. `no-trigger`
- export.py:74, floor renders as one plane, not W*D cubes.
  ceiling: none named. upgrade: none named. `no-trigger`

## layout.py

- layout.py:79, negotiated congestion (lite).
  ceiling: lite, no full negotiation. upgrade: none named. `no-trigger`
- layout.py:84, no hugging solids mid-run (torch power/oscillator guard).
  ceiling: ports within 2 of goal/start exempt. upgrade: none named. `no-trigger`
- layout.py:138, infinite room via grow-on-demand.
  ceiling: W cap 20000 (~830 bands), D cap 4000. upgrade: none named. `no-trigger`
- layout.py:259, ~B hugs west, never touches NOR torch (oscillator guard).
  ceiling: none named. upgrade: none named. `no-trigger`
- layout.py:616, feed-touch route skip for input loads.
  ceiling: none named. upgrade: none named. `no-trigger`
- layout.py:681, permanent debug tap, one env check per layout.
  ceiling: none named. upgrade: none named. `no-trigger`
- layout.py:791, every lever island seeds the OPEN trace.
  ceiling: none named. upgrade: none named. `no-trigger`
- layout.py:827, shrink-wrap grid to content (+3 margin).
  ceiling: none named. upgrade: none named. `no-trigger`
- layout.py:847, stone only where a component sits.
  ceiling: flat worlds (breaks on uneven terrain). upgrade: none named. `no-trigger`
- layout.py:858, port-grid self-check (check-marker, not a shortcut). `no-trigger`
- layout.py:885, or-lever self-check (check-marker, not a shortcut). `no-trigger`

## recipe.py

- recipe.py:21, optional BAND datapath columns.
  ceiling: none named. upgrade: none named. `no-trigger`
- recipe.py:93, fanout chains at 3+ loads.
  ceiling: 3-load threshold. upgrade: none named. `no-trigger`
- recipe.py:109, banded fanout replication per load-band.
  ceiling: none named. upgrade: none named. `no-trigger`
- recipe.py:152, relay runs on fresh indices.
  ceiling: none named. upgrade: none named. `no-trigger`
- recipe.py:163, banded relay, one buffer per band.
  ceiling: none named. upgrade: none named. `no-trigger`
- recipe.py:203, fanout self-check (check-marker, not a shortcut). `no-trigger`

## sim.py

- sim.py:121, chip-layer dust link rule.
  ceiling: none named (researched physics). upgrade: none named. `no-trigger`
- sim.py:162, back-to-back repeater chaining.
  ceiling: none named. upgrade: none named. `no-trigger`
- sim.py:330, sim scope flat builds + chip-layer verticals, vanilla delays.
  ceiling: no full 3D. upgrade: none named. `no-trigger`
- sim.py:399, delay-4 self-check (check-marker, not a shortcut). `no-trigger`

## Watch list (real ceilings, no trigger)

1. Stone-only floor breaks on non-flat terrain. (layout.py:847)
2. Grow caps W 20000 / D 4000 bind ~(830 bands, cpu4 needs 247). (layout.py:138)
3. Sim covers flat + verticals only. (sim.py:330)
4. Preview textures need network at view time. (export.py:13)

25 markers, 25 with no trigger.
