# MORNING REPORT — overnight autonomous session 2026-10-03/04

## DONE: true 3D tile stacking v1 (`stack3d.py`, sim-green 8/8)

**What now builds:** a 2-deck stacked demo — AND gate + c-buffer on
deck0 (y=1..4), OR gate on deck1 (y=6+, same x,z footprint, 122 shared
columns), joined by two staircase vias (t, c2) with glass pillars,
glass floor plate between decks, repeater boosters. 2464 blocks.
`sim_verify` on the full recipe: **8/8 vectors green**.
Regenerate deterministically: `PYTHONHASHSEED=0 python stack3d.py`.

**Design (no engine edits — one new file):** decks compose flat via
`layout_retry(verify=True)`, deck1 translates +5y over deck0, glass
plate at y=5 (inert: conducts/cuts nothing), vias climb fixed
diagonals with driver-region taps (sim-measured 15s), port-aligned
translation, top/periodic/end-diode boosters (decay budget ~1/cell),
air-only paths, slope + lamp-arm clearance, order retries + avoid
columns. Full reasoning + 8 measured failure→rule pairs in LOG.md.

**Also done:** course check you asked for (`redstone-university` 09
ALU, read not guessed): our BANDs = their bit-slices, our
comparator-XOR = theirs, glass insulation = same idiom as our towers,
dust staircases = our shafts. Through-floor reads can't span our
pitch-5 passively (documented v2 direction). Assumption I made while
you slept: stacking tonight, wool color-coding stays out (sim still
rejects wool — one-liner open at `sim.py:865`).

**What still fails / needs hands:**
1. **Paste test** (nothing here can replace the client):
   `schematics/build_stack3d.schem` is staged (hash `786FCE48…`,
   alongside — not over — your glass7 `build.schem`). `//schem load
   build_stack3d` → `//paste` somewhere with ~60×40 room → tell me B0
   and I'll regen a `stack3d` datapack suite in 30 s — or hand-test:
   levers a/b/c on deck0, lamps t/c2 deck0 + y deck1, all 8 combos
   (`y = (a AND b) OR c`).
2. Engine suites all green (compose/recipe/sim/export self-checks);
   the 21-recipe suite untouched by construction (zero engine edits).
3. `evo_add2` (add2fat 100-eval) was mid-run when I started — check
   its `done best=`; my session didn't touch it.

**What I need:** the paste-test table (or B0 for the datapack), and
one decision for next session: generalize `stack3d` to BAND
partitions (alu1 4-deck stack) vs full `tiles.new_ctx` 2D→3D map
migration. Tree is clean apart from gitignored scratch/outputs;
commit `d3ba831` holds code+log.

## Commits (branch `phase2-design`)

- `d3ba831` stack3d v1 + overnight LOG entry (this report's work)
