# Recursive-locality placement (2026-09-28)

Status: design (proposed). Goal: kill the march class — 100+ cell runs
through tile bands that fail loud on signal-solids (micro1 D, alu1 C,
ctrl_decode n0, alu4 C1, all 0.0s). Supersedes nothing; builds on the
compositional-backend spec (all its machinery stays: tiles, hops, planting,
checkers, sim gate). This is a NEW hypothesis (producer-consumer locality —
every prior placement attempt was global-grid), so the standing rule against
a fifth grid variant does not cover it.

## Evidence (why this, why now)

- Composer Fase A–C works: 4/4 small builds sim-green deterministically
  (164/448/192/230 blocks, incl. sequential latch_sr — upstream cannot do
  this), ladder falls back free on loud (0.0s), suite green, hashes held.
- Dense fails ONLY on marches: consumers stack ~12/gate below producers
  (topo bands), so runs span the stack and meet torch/comp bodies the hop
  correctly refuses. Input redistribution is explicitly forbidden (four
  data points); tile redesign and detours are out of scope. What is left
  is placement that never creates long runs: children next to parents
  (upstream's actual trick — measured: their 110-gate alu4 in 0.2s —
  borrowed as discipline, not code).
- Two micro1 mutants die on the identical D-march: structural, not luck.

## §1 — Recursive placement (replaces topo bands)

Process gates in `_topo` order (producers first — the cycle guarantee rides
along). For gate g with placed drivers: gz = max driver footprint bottom +
STREET (8); ox = centroid of driver centers, bumped east (+2 steps) until
`footprint` is disjoint from all placed rects (terminates: infinite east).
Gates with no placed drivers (all-input args) seed a top row (z=12, x cursor
eastward pitch 30). Constants ("0"/"1") ignored for anchoring. Flow
invariant: signals run south+east only. `_depths` and the band cursor go
away (bump-until-disjoint subsumes depth padding); `place_*`, `footprint`,
netspec, and the maze grid code are untouched.

## §2 — Bbox buses (replaces west lanes)

After tiles: bbox of placed rects. Each input's lever row goes on the bbox
edge nearest its loads' centroid (north z=min-6, south z=max+6, tie south;
pitch 2 per edge, input-sorted). Lever x = clamped centroid x. Ties ("1")
go east of bbox at z=3 (tiles bottom out at z>=7 — always clear). Every
load wires as ONE lwire call (legs/lanes/pitch deleted); gate-first
ordering deleted (netspec order is topo-deterministic; halo already makes
order irrelevant). Candidates/rays/halo/hops/planting/flow/checkers/finish
all stay.

## §3 — Validation and kill criteria

- Gates every step: suite green, 4/4 small composer-green (block counts
  WILL move — placement changed; green/not-green is the gate, not hashes).
- Dense ladder (micro1, alu1, ctrl_decode, alu4; cpu4 stays frozen until
  these green): green-by-mechanism, sim-gated, timings recorded.
- Kill criterion (binding): if dense still fails march-class loud after
  this lands, the locality hypothesis is FALSIFIED — record, stop, no
  fifth mechanism. Next would be tile redesign or maze-search assist,
  each its own spec.
- Out of scope: tile electrical changes, sim/export/recipe changes,
  W/D bounds (unbounded-field convention stays), maze behavior changes.
