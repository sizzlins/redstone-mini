# MORNING REPORT — overnight autonomous session 2026-10-03/04
(evening addendum: glass ladder + repeater lock)

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

## DONE (evening): glass ladder canary + repeater side-lock in sim

Two lessons from you, both verified before coding, both gated:

1. **Glass ladder (up yes, down no):** sim already models exactly
   this (DN term climbs over glass, UP term needs opaque cobble).
   Measured: glass UP 10 / DOWN 0, cobble UP+DOWN 10. No physics
   change; encoded as a canary. Our shafts already ride it.
2. **Repeater side-lock (user-measured in game):** sim did NOT model
   it (fresh A=1,B=1 read 1, vanilla locks 0) — real vanilla-parity
   gap, now closed: `sim.rep_locked` + hold-last + wake on
   behind-or-beside, mirrored in `simvec` (`r_side`, hold, side wake
   edges). Canaries: fresh-1,1 freezes off; output→own-side latches
   on permanently across `sim_sequence` phases.

**Regression proof (lock changes nothing green):** sim suite green,
`diff_engine` ALL IDENTICAL, compose_check 144/322/224/214, nonhier
6/7 bit-identical (144/322/224/214/2925/5499; alu1 RED is the known
pillar fault, stash A/B identical: same 4 Y vectors), chainmix 11497
+ mux4 20239 fresh recompose+verify green, stack3d re-verified 8/8
identical geometry. NOT re-run (needs quiet machine; GA grinding):
alu4glass7 1024v, cpu4retry 128v — queued in LOG, not skipped.

**What still fails / needs hands:**
1. **Paste test** (nothing here can replace the client):
   `schematics/build_stack3d.schem` is staged (alongside — not over
   — your glass7 `build.schem`). `//schem load build_stack3d` →
   `//paste` somewhere with ~60×40 room → tell me B0 and I'll regen
   a `stack3d` datapack suite in 30 s — or hand-test: levers a/b/c on
   deck0, lamps t/c2 deck0 + y deck1, all 8 combos
   (`y = (a AND b) OR c`).
2. `evo_add2` (add2fat 100-eval) still grinding (eval ~40/100 when
   checked) — check its `done best=`; sim now locks, which only
   ever rejects un-vanilla mutants.

**What I need:** the paste-test table (or B0 for the datapack), and
one decision for next session: generalize `stack3d` to BAND
partitions (alu1 4-deck stack) vs full `tiles.new_ctx` 2D→3D map
migration. Tree is clean apart from gitignored scratch/outputs.

## Commits (branch `phase2-design`)

- `d3ba831` stack3d v1 + overnight LOG entry
- `26754fd` repeater side-lock in sim+simvec, glass canary + log (this)
