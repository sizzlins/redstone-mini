# MORNING-REPORT — overnight 2026-10-02: vertical envelope DONE

## What now builds (was red, now green)

- **alu1 COMPOSES and VERIFIES.** Was loud `no ground for CIN` on every rung;
  now 12,294 blocks, sim green on the full vector set (maxticks 86). The
  y-histogram shows `{0:5455, 1:5463, 2:744, 3:624, 4:8}` — the new y=4 tall
  hop fired in a real build, and the support gate proves it pastes correctly.
- **Underground wires work.** astar descends through a sealed y=1 wall
  (proven with ymin=-1), every y<=0 cell resolves a pillar, finish_assembly
  emits the cobble, sim greens through a hand trench circuit.
- **Unchanged greens, all re-gated:** recipe.py, sim.py, layout.py full
  __main__ suites; compose_check bit-identical 144/322/224/214.

## What changed (2 commits on phase2-design)

1. `5d93e1d` trench support: router stamps y-1 pillars for y<=0
   (astar legality, layout route(), compose lwire, _has_support,
   _plant_repeaters), finish_assembly emits the missing cubes (loud on
   stacked columns), sim fails loud on floating dust/repeater/comparator
   at y!=1 (y==1 rides the world). Same gate duplicated at the top of
   simvec.verify_par so direct callers can't bypass it.
2. `7e98176` tall bridge: 7-cell y=4 staircase, tried only after the y=3
   shape seals (maze try_bridge + compose _walk). Greens bit-identical by
   construction. Defaults unchanged: narrow band 1..3, wide -4..6 via
   REDSTONE_COMPOSE_YMIN/MAX (now trustworthy), y=4 via bridge shape.
   True 3D tile stacking still out of scope (different compiler).

## What still fails / needs you

- **cpu4 R0Q0** (handoff diagnosis) untouched — separate lane, still the live
  wall. alu4/ctrl_decode/micro1 dense re-gates not re-run overnight (engine
  fingerprint in verify_par voids their caches automatically; expect re-verify
  on next run, should be green by the bit-identity argument, but not measured).
- **Your ceiling question, answered:** wires can now use y=-4..6 (astar wide
  band) + y=4 bridge apex. Below base 120 and above 123 both paste with
  supports. Nothing structural caps it lower/higher except the validated
  envelope — widen REDSTONE_*_YMIN/YMAX if you want more, sim rules are
  y-generic.
- Probe hygiene: every probe script must be main-guarded or set
  REDSTONE_SERIES_VERIFY=1 — an unguarded script + spawn Pool = fork bomb
  (ate two of my timeouts before I saw it). Details in LOG.md.

---


## DONE: cpu4 is green

`recipes/cpu4.txt` now holds the 11-band hierarchical recipe. It composes
end to end and sim-verifies on the full input space:

- `compose(recipes/cpu4.txt)` → **98,827 blocks, ALL OK** (layout_retry,
  verify=True, ~1200 s single run)
- the cached merge `scratch/cpu4merge3.pkl` (72,055 blocks) → **VERIFY OK:
  128 vectors, 32 chunks green**, zero failures
- `scratch/alu4merge.pkl` → **VERIFY OK: 1024 vectors, 64 chunks green**

## The wall was the simulator, not the router

Two sessions of forensics chased a routing fault that never existed. `sim.py`'s
power-on pre-roll computed a **half-powered tick-0 state**: it iterated dust /
blocks / torches to a fixpoint but **froze every repeater OFF**, on the theory
that a booster's delay is a real transient. A frozen booster makes every cell
beyond it read dark. Measured: `OPC1` read 96/903 at tick 0 instead of 903/903,
so `NOT OPC1` fired a phantom 1, and `C_n2 AND C_n1` produced a ~40-tick `REGW`
glitch at T~28 that reached `R0_S1` at T~120 and latched `R0Q1`/`R0Q3` to 1 on a
no-write vector. A booster's *settled* value is a function of its input, so it
belongs in the fixpoint. Commit `2bbf873`.

Two things fell out, both real:
- The fixpoint is **ambiguous** (more than one self-consistent state). A
  whole-field sweep converged to `AL_C2` stuck lit; the same fixpoint as a
  **worklist** converges correctly *and* went 170 s → 6 s. My first version was
  both wrong and slow.
- `sim_verify` had become a **fork bomb** (routes through `simvec.verify_par`
  → `Pool`; a pool worker is daemonic, so unguarded callers re-imported
  themselves under spawn forever). Fixed with one check in `sim_verify`;
  `simvec.py` untouched (agent 2's file).

## Dead ends (do not re-run)

- Repeater rings in the merge: `_loop_rep` returned 4, then 1, then 0 as the
  cobble set varied. Both the router's view and the sim's own view say **None**.
  My first two hits were artefacts of a cobble set neither caller uses.
- Repeater backed by a `finish_assembly` stone pad: **zero** in 4245.
- Ring closed through a chip-layer y±1 link: **zero** (sim's own sets + rule).

## Tooling fixed (scratch/, gitignored)

`verify_par.py`: cache key ignored the worker count (silently green-marked
untested vectors); only printed per chunk (~700 s silence, killed twice for
looking hung); chunk size was tied to worker count. Now: key is
`nchunks:index:recipe+build+ENGINE`, child streams per vector, nchunks is its
own argument. Plus two of my own bugs caught in the same pass (unregistering a
live worker on progress → BrokenPipeError; `poll()` raising on a closing pipe).

## Still open / needs from you: nothing

Regression gate (`micro1`, `alu1`, `alu4`, `ctrl_decode` via dense_status) was
still running at handoff: `micro1` passed, `alu1 OK 13300 blocks`, alu4 in its
band ladder. Re-run `python scratch/dense_status.py` for the final numbers if
you want them in one place.

## Trail

- `LOG.md` session 3 entry: full root-cause chain, measurements, dead ends.
- Commits: `2bbf873` (sim fixpoint + fork-bomb guard), `efd01de` (promote banded
  cpu4 recipe).
- Probes worth keeping: `scratch/netdiff.py` (which nets disagree with
  eval_net), `scratch/whylit.py` (power backtrace from sim state),
  `scratch/leak.py`, `scratch/chipring.py` (both negative, both instant).
- Untouched per protocol: `simvec.py` (agent 2).
