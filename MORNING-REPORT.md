# MORNING REPORT — overnight autonomous session 2026-10-03/04

## DONE: cpu4 GREEN 128/128, alu4 fault root-caused + fixed in sim

**cpu4 (7 inputs, 128 vectors): GREEN, 129,953 blocks, exported.**
Fresh bands green per-band (92s) with the fixed sim, merge hit the known
Y2 ghost (`SMOKE 0101010 MISMATCH ['Y2']`), then the new
`scratch/hier_retry.py` (combination-aware loop: failing outputs →
fanin bands → HIER_SKIP their rungs → re-climb → re-stitch → re-smoke)
went green on retry 1. Full `verify_par`: **128 vectors, 8 chunks
green** (~9 min). Exported `build_cpu4retry.{schem,mcfunction,html}`,
7 levers one column (x=3, z=3..63). Lesson: the ladder optimizes bands
standalone but correctness lives in the combination — retry must too.

**alu4 Y2-in-game fault: ROOT-CAUSED to a real sim gap, FIXED, committed.**
`cob_state` never computed power from *below* a solid (torch-below,
dust-below). Every 3D-flight pillar over/beside a lit torch read dark
in sim, lit in game (measured: dust at power 10–15 with dark
surroundings, torches lit-vanilla/dark-sim, 1824-cell divergence map
`scratch/divfull.txt`). Fix: +31 lines below-terms in `sim.py`
(`789f879`, canary `pillar-feed ok` fails-pre/passes-post both
measured) + simvec mirror (`0a0431a`, `diff_engine` ALL IDENTICAL) +
ref freeze. Post-fix sim reproduces all 8 in-game vectors lamp-for-lamp.

**alu4 build repair: 7-pillar glass swap, sim-green 1024/1024.**
`scratch/swap7.py` swaps 7 torch-touching dust pillars to glass
(`scratch/alu4glass7.pkl`). Full verify green. T1/T2/T4 fixed; T3
correct in 160+ runs with 1 unreproduced outlier (multi-seed policy:
re-run reds 3× before believing). Exported + installed with 15 wool
lever/lamp markers + per-net floor quilt (`build.schem` = 17,769 B,
old bank preserved as `.bak-20261003-063141`).

**Course-style readability + GA, both moving.**
Export now colors floor pads per net (+16 wool preview colors, committed
`24a6efe`). `scratch/evolve.py` (netlist superoptimizer: buffer/dedup/
dead/rebind/unshare + equiv gate + compose/verify fitness) recovered a
pessimize mux2 13311→5387 = exactly the known optimum. Compact-tile
pilot measured and parked: tiles ~7% of blocks, repeater spacing
documented load-bearing — gate count (GA) is the lever, not tiles.

## Still red / open

- **alu1 RED under fixed sim** (4 vectors, same pillar class; geometry
  identical at 13300 blocks). Needs the same insulate-or-reroute
  treatment as alu4. ctrl_decode + micro1 + small builds still green.
- **In-game paste tests pending (needs you):** `build.schem`
  (alu4 fixed+marked+colored) re-paste same spot → `/reload` →
  `/function alu4:go` (7 min). `build_cpu4retry.schem` never pasted
  at all. Nothing here can replace the client.
- Old `cpu4merge3.pkl` green untrustworthy (8 conflicting duplicate
  cells, predates one-cell-one-block gate). Superseded by
  `cpu4retry_merge.pkl`.
- T3 1-in-160 sim outlier, unreproduced despite deliberate attempts
  (100-seed sweep clean). Policy recorded, cause unknown.
- True 3D tile stacking: still scoped, unbuilt (~140 y==1 sites).

## What I need

1. Paste `build.schem` same spot → `/reload` → `/function alu4:go`
   → report the table (expect all green now).
2. Paste `build_cpu4retry.schem` somewhere with room (4175×446!) →
   same drill (datapack functions are alu4-coordinate-specific; tell
   me the new B0 and I'll regenerate in 30 s).
3. Decisions (no rush): tile library vs GA for compactness; scratch/
   pruning (~40 new probe files this session, all gitignored).

## Commits (branch `phase2-design`)

- `789f879` sim below-feeds + canary + log
- `0a0431a` simvec mirror + ref freeze + log
- `24a6efe` export wool colors + quilt log
- `c9bfbaf` cpu4 log (this report's work; engine untouched tonight
  apart from the two sim commits)

## Evening addendum (same session, pre-paste)

- **alu1 repaired the same way:** 3 torch-pillars -> `scratch/alu1glass.pkl`,
  sim 32/32 x3 runs, block count identical (13300), exported
  `build_alu1glass.*`. Full nonhier suite 6/7 green (all counts match the
  handoff record); alu1's suite-RED is the fixed sim working as a
  detector, not a regression.
- **Insulation generalized:** `scratch/pillars.py:insulate()` (any pkl;
  y>=2 only, no attached torches — blanket swaps break tile attaches
  and slope conduction, measured).
- **GA hardened + running:** parallel batched evals (4 direct children,
  deadlines, memo, low priority), `op_factor` added, SOP adders proven
  unroutable in 10 min (start near-routable). `add2fat` 100-eval run in
  flight (detached).
- **Readability:** per-net floor quilt (20,566 pads) + 15 wool markers
  exported and installed as `build.schem` (old bank preserved).
- **Sim determinism:** 160+ identical T1/T3 runs; one unreproduced
  outlier stands with a re-run-reds-3x policy.
- Tree: sim/simvec/ref/export/LOG/MORNING-REPORT committed (5 commits
  today); working tree clean apart from the two pre-existing `.bak`s.
Scratch tooling added (all gitignored, kept): hier_retry, evolve,
regiondiff/mapdump/levercheck/loophunt/diodeloop/liveloop/simexact/
latchtest/maxima/explain/finaldiv/vcontact/traceback_y2/mapfirst,
gen_pack/gen_snap/gen_flick, swap7/pillars, export_marked, probes.
Rule learned the hard way: never name a scratch file after a stdlib
module (`traceback.py` shadowed stdlib under spawn and broke the
nonhier suite until renamed).
