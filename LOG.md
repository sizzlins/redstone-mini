# Overnight Log — redstone-mini dense builds (2026-09-30)

Operator asleep ~8h. No questions, loop until DONE, verify every change,
commit often. MORNING-REPORT.md at end.

## Assumptions
- A1 (user-confirmed): work repo = D:\redstone-mini. DONE = (1) all 5 dense
  recipes generate without error AND sim-verify: micro1, alu1, alu4, cpu4,
  ctrl_decode; (2) +3 NEW dense builds green, then stop.
- A2: verify command (user gave none; defined here): `python dense_verify.py`
  (to be created): compose-first + maze fallback with per-recipe budget,
  sim_verify every build, exit 0 iff all green. Until it exists, gates are:
  `python compose.py`, `python scratch/compose_check.py`, `python recipe.py`,
  `python sim.py`, plus per-recipe compose/sim probes below.
- A3: reference repos read-only unless needed; clones only into
  D:\put gitrepos here; nothing touched outside listed paths.
- A4: prior sessions' uncommitted tree (sim.py/recipe.py/export.py/handoff
  mods) is taken as-is; validated by gates before building on it.

## Timeline
- 00:00 state: branch phase2-design @8acf27d + working mods (incl. my prior
  ring-hop + candidate-fallback in compose.py, intact). Baseline gates ALL
  GREEN (compose AND+bridge+buffers, 4 small 158/280/226/254, recipe, sim).
- 00:10 checkpoint commit, then resume: astar-path-as-fallback-candidate
  (BFS proved y=1 violation-free len-53 path exists for alu1 AB; layout.astar
  flat_only finds one; 26 L/ray candidates all die).
