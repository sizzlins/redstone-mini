# MORNING REPORT — autonomous session 2026-10-04 (alu4 bands 1/2 green, 0 parked)

## Status: 2 of 3 red bands green, no merge yet (band 0 blocks)

- **Band 1 GREEN** (7518 blocks, `1,inputs_first,short`): SIM MISMATCH
  (Y1 True-when-False) traced to A0B0 boundary input stuck lit (X1 dark,
  XOR correct; S1 cone inherits) via a y=3 flight over a torch zone.
  DODGED, not fixed: `inputs_first` order routes lanes in open ground.
- **Band 2 GREEN** (6957 blocks, `1,inputs_first,long`): long jogs dodge
  its wall. Both wins came from existing ladder diversity, not new code.
- **Band 0 RED**: OP1's lane cannot reach m20's west port (4,12) -- pocket
  sealed W (lane wall) / N,S (B0-adjacency + funnel cobble) / E (own
  tile). All starts fail incl. astar+3D. 8 approaches exhausted
  (sidestep-probe, reorder, order-seeds x6, NOFLAT, maze x4, TERR,
  IN-order, arg-swap-proven-useless). PARKED with precise TODO:
  disambiguate tile-seal vs lane-seal timing, then port-approach
  reachability gate in placer OR lane keep-out around west-fed ports.
  Partial merge impossible (Y0 lives in band 0).
- **No stitch attempted** (needs all bands). No engine changes this
  session (all findings are recipe/ladder/probe-level).

## Methods banked (probes force-added to git)

`sidestep.py` (lwire from N starts), `banddiag.py` (settled DIFF incl.
non-lamp nets), `jmap.py` (junction diodes), `boxmap.py` (3D region map),
`srcmax.py` (power maxima), `maze_one.py`, `one_ladder_ext.py`
(spreads 1-10). Rule learned: `PYTHONHASHSEED=0` makes compose
bit-identical across runs (hash-proven); unseeded probes chase different
geometries. `banddump.py` output name now takes the recipe prefix.

## Still open (ranked)

1. Band 0 port wall (TODO above; biggest remaining red).
2. `_streets` flip (parked; needs alu4 bands climbing -- this session
   unblocked the prerequisite everywhere except band 0).
3. Paste tests (your hands); SWAR delete (your call); LOG sharing (stable
   since the merge; GA acked append-only).

## GA agent status (observed, not touched)

Still grinding (`evo_blocks.py` modified in worktree, left alone).
`recipes/fa1.txt` is theirs (untouched). No file overlap (my paths:
probes + LOG + this report). No collisions. Tree clean except the two
protected `.bak` files.
