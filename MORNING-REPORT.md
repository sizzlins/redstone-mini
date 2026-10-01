# MORNING-REPORT — redstone-mini, cpu4 session

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
