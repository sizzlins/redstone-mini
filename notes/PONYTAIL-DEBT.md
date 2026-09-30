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
- layout.py:10, astar pop cap (anti-freeze).
  ceiling: 100k pops/call. upgrade: `REDSTONE_ASTAR_CAP` if a verified build trips it.
- layout.py:126, single bridge shape (no 3D search).
  ceiling: one pre-proven hop. upgrade: full 3D search if hops dominate.
- layout.py:267, median-band bank levers (short north runs, not west marathons).
  ceiling: colliding medians run east, may go out of bounds (loud). upgrade: input fanout chaining (recipe.py still excludes inputs).
- layout.py:679, panel inputs ride first (gates detour thin input tips).
  ceiling: fanout-dense inputs may still seal (micro1: south-bank driver can't enter dense tile rows). upgrade: input fanout chaining, or wider band pitch for input corridors.
- layout.py:721, last-resort bridge hops.
  ceiling: 24 hops/build. upgrade: raise cap or 3D search if dense builds need more.
- layout.py:963, slope-link open-check (check-helper, not a shortcut). `no-trigger`
- layout.py:1041, bridge template check (check-marker, not a shortcut). `no-trigger`

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

- sim.py:16, settling budget raised 500 ticks/20000 steps -> 5000/300000.
  ceiling: a GENUINE non-settling build (a real oscillation) now costs 10-15x
  more to detect than it used to — the budget is 15x, so a true oscillator
  burns 15x the time before it is reported. Right trade (a dense build
  legitimately needs it: a 40-cell boosted run alone costs 40 ticks, and the
  old caps expired mid-convergence and misreported dense builds as
  oscillators, which reads as a router fault and is not one). upgrade: lower
  the defaults for a fast red-build signal, or detect "no new value for N
  consecutive steps" instead of a step ceiling, so a real oscillator fails
  fast while a slow converger still gets its budget.
  trigger: revisit when a build legitimately needs >500 ticks, or when an
  oscillation costs more than the layout that produced it.
- sim.py:20, stall verdict ("no value change for REDSTONE_SIM_STALL=5000
  steps"). A progress signal, not another constant: stale queued events drain
  for hundreds of steps (measured max_gap 444-662 on a real oscillator), so
  stalling and oscillating are genuinely different failures. ceiling: the
  threshold is NOT calibrated against a large *converging* build, because
  there is not one to measure — micro1 is red under the deferral, so we have
  no dense known-good build whose post-last-change backlog we could bound. A
  false STALL is possible if a converging dense build leaves >5000 stale
  queued events after its final change. upgrade: once a dense build settles,
  measure its worst backlog and set the threshold from that.
  trigger: revisit when micro1 (or any dense build) goes green again, or if a
  STALLED verdict ever appears on a build that later settles.
- sim.py:121, chip-layer dust link rule.
  ceiling: none named (researched physics). upgrade: none named. `no-trigger`
- sim.py:162, back-to-back repeater chaining.
  ceiling: none named (researched physics). upgrade: none named. `no-trigger`
- sim.py:330, sim scope flat builds + chip-layer verticals, vanilla delays.
  ceiling: no full 3D. upgrade: none named. `no-trigger`
- sim.py:399, delay-4 self-check (check-marker, not a shortcut). `no-trigger`
- sim.py:burnout, no relight path (raise aborts the run on burn).
  ceiling: vanilla relights after 160 ticks + block update and continues dark;
  we fail loud instead, so a build that burns and then settles right still
  reads red. Correct verdict, poorer trajectory info.
  trigger: revisit if a build ever burns yet settles with matching lamps
  (vanilla would pass it; we fail it loud).

## Watch list (real ceilings, no trigger)

1. Stone-only floor breaks on non-flat terrain. (layout.py:847)
2. Grow caps W 20000 / D 4000 bind ~(830 bands, cpu4 needs 247). (layout.py:138)
3. Sim covers flat + verticals only. (sim.py:330)
4. Preview textures need network at view time. (export.py:13)
5. A* pop cap 100k/call bounds search; long detours need the env knob. (layout.py:10)
6. Bridges are one fixed shape, max 24/build; denser needs full 3D. (layout.py:126,721)
7. Panel inputs ride first from a median-band bank; dense tile rows still
   seal (micro1 red). Upgrade is input fanout chaining or wider band
   pitch. (layout.py:267,679)

33 markers, 23 with no trigger.

## Addendum 2026-09-28 (Phase C: budget, eval gate, snapshots)

> The body above is the 2026-09-26 generated snapshot and its line numbers are
> now stale (layout.py alone has ~40 markers, ~20 listed). Regenerating the
> whole file is a mechanical chore nobody has done in three sessions; these are
> the rows Phase C adds, with current line numbers. Line numbers for the
> pre-existing rows are NOT updated here — do not trust them, re-grep.

### recipe.py

- recipe.py:260, eval gate runs 3 vectors (0^n, 1^n, alternating), not the
  exhaustive set. Speed bound, not a correctness one: anything missed still
  fails in sim_verify, later. ceiling: a defect reachable only off those three
  vectors is not caught pre-layout. upgrade: mirror sim_verify's `2**n <= 4096`
  rule. trigger: none, widening is free.

### sim.py

- sim.py:27, `REDSTONE_MAX_SECS` wall clock, checked at the SEED boundary only.
  ceiling: one seed always runs to completion (grows layouts), and `tries=1` is
  never bounded. upgrade: `layout()` already polls a search cap mid-search —
  thread the same deadline through it for per-A*-call granularity.
  trigger: one seed overrunning the budget by more than the budget itself
  (measured: 80.6s for two cpu4 seeds at grow=0, `REDSTONE_SEARCH_CAP=700`).

### snapshot.py

- snapshot.py, whole build as one unpruned JSON. Bounded only by content-hash
  dedup, so N distinct builds is N files forever. ceiling: no eviction; alu4 at
  24k blocks is ~2MB. upgrade: prune by count/mtime in `target()`, or gzip.
  trigger: `.snapshots/` past ~100MB or a few hundred files.
