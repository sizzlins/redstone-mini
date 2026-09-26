# Single-lever input panel (2026-09-26)

Status: design (approved). One lever per used input in a south-edge row,
inputs route as ordinary maze nets. Replaces one-lever-per-load taps.

## Problem

Today each input fans out via one lever per load (`layout.py`, per-load
loop), scattered at its gates. In a real Minecraft build the player runs
around the field flipping the same logical input in N places.

## Decisions (from brainstorming)

- Panel lives on the front/south edge, control-panel style near the lamps.
- Dense-build failure mode: loud fail (repo philosophy, no fallback paths).
- Unused inputs stay lever-less (unchanged).

## Design

1. **Bank placement.** Phase 0 stamps one lever per used input in a single
   south-edge row (`x = 2 + idx*3`, fixed south `z`, 3-pitch — same pattern
   as today's OR batch levers). Each bank lever gets `pos[name]` + feed
   wire. OR-feeding inputs join this row; their separate batch spot goes
   away. Tiles and everything downstream untouched.
2. **Routing.** Delete the per-load lever loop (stamp-wire + adjacent lever
   per load, plus the `feeds` skip in task building). Every input load
   becomes a normal `drv -> load` maze task from the bank, flowing through
   rip-up (both tiers), boosters, last-resort bridges, and the pop cap
   untouched. OR diode-backs (`orbbs`) already read a bank lever via the
   junction — no changes there. Accepted cost: input nets now consume
   routing space and boosters, so fanout-heavy block counts rise.
3. **Checkers/sim.** No `sim.py` changes (levers drive by input name; slope
   physics already cover bank-to-field routes). The open-checker already
   seeds every lever island plus `pos` — bank feeds trace with no edits.
   Extend the `layout.py` `__main__` or-lever check with a fanout
   assertion: shared-input recipe builds green with exactly one lever per
   input in `io["levers"]`. That one check pins the feature.
4. **Failure/scope.** Unroutable input raises like any gate net — no
   fallback, no silent multi-lever. Out of scope: lever facing flourishes,
   panel labeling, unused inputs, OR-junction aiming changes.

## Budget

~15 lines changed in `layout.py` plus ~10 lines of self-check. No new
files, no new deps, no sim/export/serve changes.

## Alternatives cut

- Per-input multi-lever fallback: two lever systems forever (dual paths in
  placement, checker, `io`). Cut — complexity without a paying customer.
- Status quo: zero diff, player keeps running around. Cut — the ask.
