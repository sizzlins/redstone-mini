# Vertical routing — design

Approved: 2026-09-24. Status: spec, not yet implemented.

## Goal

Let wires climb (levels y=1..2) so shared nets cross over instead of
sealing. Tiles stay flat at y=1, placed exactly as today. Acceptance:
`ctrl_decode.txt` routes and verifies; green gate unchanged-or-better.

## 1. Bounded 3D maze

- Levels y=1..2 only (one climbing level — enough for single crossovers).
- `astar` gains vertical dust-slope neighbors: step to adjacent-level dust
  cells iff the upper cell sits on a conductive block and no lid covers
  the lower wire (the exact rules the sim proves). Small extra cost per
  climb so flat stays preferred.
- Torches, repeaters, levers, lamps stay y=1, flat-only (documented limit).

## 2. Layout changes (only these)

- Rings become vertical columns: a guarded (x, z) stays guarded above it
  (tile airspace; zero format change — the lookup ignores y).
- The router stamps bridge cobble under elevated dust itself: a climb
  without support is illegal, so placement creates its own vias.
- The short-checker goes slope-aware in 3D (two nets' slopes can genuinely
  short; the flat checker would miss it), mirroring the sim rules.
- Layout `wires` become triple-keyed; `pos`/`io` stay 2D at the boundary
  (mapped to y=1, as the sim does).

## 3. Flagged risk (unproven)

Ring-columns may forbid exactly the crossings this exists for: a wire can
only cross over unguarded gaps, and dense tile rows leave few. If the
acceptance build still seals, the fallback is narrower ring profiles per
tile (not wider fields) — decide on evidence, not here.

## 4. Out of scope

y=3+, repeaters/torches above y=1, glass-diagonal subtleties, automatic
layer assignment (levels emerge from routing), comparators/pistons.
