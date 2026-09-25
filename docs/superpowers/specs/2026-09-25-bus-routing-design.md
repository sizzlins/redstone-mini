# Bus routing design (2026-09-25)

Status: design (approved §1–3 in brainstorm). Predecessor: Phase 1
(port grid, PR #1). Refines `docs/phase2-bus-routing.md` — that file is
the goal, this file is the buildable design.

## Decisions (locked in brainstorm)

- **Big-bang replacement.** The maze router is deleted, not kept. No
  bus↔maze seam, no throwaway spike. De-risked by climbing
  smallest-first and deleting maze code last.
- **Every net gets a lane.** One uniform rule, no input/internal split.
  Carve-outs (existing behavior, not new scope): const `"0"` never
  routes, const `"1"` keeps its block feed; LATCH cross-coupling stays
  internal to the tile; OR diode aiming re-targets lane taps.

## Architecture

`layout()` placement stays byte-identical (Phase 1 tiles locked).
Only the phase-2 routing block is replaced. Per net: assign lane →
stamp lane wire + repeater stations every 14 cells → driver feed at the
west end → N/S stubs to load ports → lamps/lever as today (lamp
east-first unchanged; levers move to bus heads, both lever phases
replaced by one lever per input).

Untouched: `layout_retry` tries/grows/verify-as-selector, `sim.py`
physics, tile stamps, `export.py`/`serve.py`. Deleted with the maze:
`astar`, frontier rip-up records, congestion lite, torch-guard,
task ordering — plus any ring checks that only served maze routing
(stub checks stay; lanes are exempt by 2-pitch construction).

## Geometry + invariants

- Lanes run east-west at pitch 2 (one empty row between adjacent
  lanes — dust is not cardinally adjacent across the gap, hence
  touch-safe). Lane z = driver port row (producers sit west of
  consumers, flow runs west→east).
- Repeater stations every 14 cells on lanes only — never on tile
  dust or stubs.
- **Tap rule (load-bearing):** a branch taps a lane ONLY at a repeater
  output (full-strength). Any relaxation must re-prove the xor case.
- Stubs keep ring-guard checks (they thread past tiles).

## Errors

Loud `RuntimeError` on lane saturation, unreachable port, or station
collision, into the existing tries/grow retry. No new recovery
machinery, never silent wrong.

## Verification

Existing harness only: `recipe.py`, `serve.py --check`, `sim.py`,
`layout.py` asserts stay green; 4-gate `0/6` + sequence; demo 114.
micro1 + alu4 must route with ~10× fewer repeater blocks than maze
(counted from the block list). New check (assert-based, repo
convention): every tap sits at a repeater output, stations exactly 14
apart. cpu4/ctrl_decode/adder8 are attempted (red today) but not gates.

## Migration order (deletion gate)

demo → latch_sr → 4-gate → micro1 → alu1 → alu4. Maze code is deleted
when the bus covers every previously-green recipe plus alu4. Each rung
holds `layout_retry(verify=True)` green before moving up.

## Non-goals

No layers/bridges (flat), no clock, no new tile types, no sim changes,
no per-recipe tuning, no config for the 14-cell station interval.
