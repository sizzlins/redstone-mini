# MORNING REPORT -- optimization pass (agent 2)

Scope: make the program faster. Nothing here changes what a build *means*;
every change is proven to produce identical output (a frozen reference engine
for the physics, a block-list sha256 for the router).

## The headline: your CLI was not slow, it was doomed

`python redstone_mini.py alu4.txt` never finishes green, and never could have.

`sim_verify` simulated **all 1024 vectors before raising anything**. 12 of the 16
vectors I sampled above index 256 raise `sim not settling` with churn
**10.4k-12.6k cells**. Indices 0-255 settle in 0.4s each. So the 22-minute
"hang" was a build that could never pass, paying for the full sweep before
saying so.

It now **fails in 97s** and names the fault:

```
sim not settling / burnout on vector
  {'A0':0,'A1':0,'A2':0,'A3':0,'B0':0,'B1':1,'B2':0,'B3':0,'OP1':1,'OP0':0}
  churn=11323  loop_torches: (115,1,53) (133,1,39) (133,1,42)
                            (188,1,54) (194,1,39) (212,1,50)
  same-level=18868  slope=6558
```

That loop is the real bug. `loop_torches` at six coordinates with ~11k churning
cells is a router topology fault (same-level edges dominate, 18868 vs 6558),
not slow convergence.

## What got faster, measured

| what | before | after | how verified |
|---|---|---|---|
| report a red 1024-vector build | 22 min | **97s** | measured both ways |
| `ticktrace` (one trace) | ~2.4 h | **0.9s** | measured |
| physics per vector (`_run_vec`) | 1.499s | **0.434s** (3.45x) | bit-identical to a frozen copy of the committed engine |
| compose, alu4hier | 27.27s | **20.1s** | sha256 of all 34672 blocks unchanged |
| bit-parallel 128-lane sim | (hung) | **1.54s** | opt-in, see caveat |
| exporters (34k blocks) | — | **0.63s** | profiled, already fine, left alone |

Router numbers carry a big caveat: the same code, same recipe, same sha256,
measured **20.1s** and **59.6s** on different runs depending on what agent 1 was
doing. The 27.27 -> 20.1 pair was taken back to back under comparable load and
is the one I trust; treat single wall-clock numbers on this box as unreliable
while two agents share it.

## What I built

**`simvec.py` (new).** Two engines over tables computed once per build.

1. `run_scalar` -- the same physics as `sim._run_vec`, but the profile showed
   `_run_vec` was almost entirely re-deriving *constant* facts: 207k
   `dust_lvl` calls, 98k `wake` calls, 146k `cob_state` calls **per vector**,
   each rebuilding tuples and re-asking membership questions fixed by the
   static build, plus 219k `os.environ.get` calls for one boolean. Precomputing
   them plus Dial's bucket queue (1969) instead of a binary heap gives 3.45x.

2. `run` -- bit-parallel (SWAR) physics: one Python big-int per cell holds one
   input vector per 6-bit lane, guard bit at bit 5 so lane-wise
   max/min/dec/compare become shift+subtract with no cross-lane borrow. Flat in
   lane count: 8 lanes 1.13s, 32 lanes 1.27s, 128 lanes 1.54s.

**`compose.py`.** Bands now climb the rung ladder in lockstep (each band's
rung-N launched before any is joined), and the partition sim gate runs in the
child so an unused block list never crosses the pipe. The router profile said
the algorithm was never the problem: of 25s, only ~5s was routing; 10.3s was
the parent blocked on children and 7.3s was pickling.

## Two things I want to flag

**1. The bit-parallel path is OFF by default, and that is a measurement.**
At 256 vectors it came out **5.6% slower** than `run_scalar` alone (22.7s vs
21.5s), byte-identical results. It pays only when every lane in a shard
converges together — an all-easy 128-lane shard is ~110x — and alu4 has hard
vectors that break that (6 of 8 x 128-lane shards burn the whole step budget).
It stays, opt-in via `REDSTONE_VEC_SWAR=1`, as the only sub-linear option for
high-input-count exhaustive verification. If you would rather not carry the
code, deleting `simvec.run` + `_swar_shard` costs nothing else: `run_scalar`
and the fail-fast driver are independent of it.

**2. My absolute timings after the router work are contaminated.** Agent 1 runs
cpu4 concurrently and the box saturates all 20 cores (I observed 6096s of CPU
burned during a single benchmark). Every ratio above is a same-process A/B and
is trustworthy; wall-clock numbers taken while both agents work are not.

## Correctness

`scratch/diff_engine.py` compares every engine change against a **frozen
extraction of the committed engine** and demands identical lamps, live dust
levels, torch states, tick count, repeater states, comparator levels, and
identical exception types. It is the gate for every optimisation.
`sim._run_vec` itself is unchanged and remains the authority; `run_scalar`
refuses (raises) rather than guessing on the latch hold-seed path.

**Three real physics bugs the differential caught**, each of which would have
silently mis-verified builds:
- the comparator term in `dust_lvl` is `return con`, **not** `lv = max(lv, ...)`.
  It is an early return, so it cannot be hoisted into a max with the decay terms.
- the chip-layer `dn` test checks the block directly **below** the cell, not
  below+dx.
- a repeater must be re-evaluated when the cell **behind** it changes (its
  input). Asking "does it feed the changed cell" left every booster evaluated
  once, at tick 0, when its input is still dark — no booster fired, the boosted
  wires decayed to nothing, and the build "settled" dark and early.

## What still fails

- **alu4 does not verify.** The 6 loop torches above are the thing to fix.
- **`compose_hier_parts` is the remaining router cost** (~16.7s of the 20.1s,
  single-threaded in the parent, dominated by astar via `_try`). Not touched:
  astar is the most correctness-critical code in the repo and I had no
  bit-identity gate for it beyond the whole-block sha256.
- **astar's `ok` predicate** is called 1.37M times per compose. It is already
  tight (bound lookups hoisted); inlining it into astar's loop would remove the
  call overhead but is invasive, and I stopped short of it.
- **`export_html` / `export_mcfunction` for 34k blocks** — profiled: 0.14s +
  0.27s + 0.22s = **0.63s** total. Already fine; nothing done, nothing needed.
- **redstone_mini runs its 322-block demo on every invocation** (2.2s) even
  when a custom recipe follows, and that demo's exports are then overwritten.
  Left alone: the demo doubles as the file's self-test.

## What I need from you

Nothing is blocked. Two decisions are yours:

1. **Delete the SWAR path or keep it opt-in?** It is currently opt-in and
   costs nothing when off. Deleting `simvec.run` + `_swar_shard` is clean if you
   want less code.
2. **alu4's oscillators** — that is a routing bug (6 loop torches, 11k churn
   cells), and it is agent 1's lane, not mine. Flagging it because it is the
   reason the CLI looked hung in the first place, and it will bite anyone
   verifying a banded recipe of this size.

## Files

- `simvec.py` — new. Both engines, the sharded driver, fail-fast.
- `compose.py` — lockstep bands + child sim gate. Perf only, output sha unchanged.
- `scratch/` (force-added despite being gitignored, because it *is* the
  correctness argument): `mkref.py` regenerates the frozen reference,
  `ref_sim.py` is it, `diff_engine.py` is the gate, `router_hash.py` is the
  router gate, `bench_*.py` / `prof_*.py` / `probe_*.py` are the harnesses.
  Every one is bounded and none can hang.
- `sim.py` — **not committed by me.** Agent 1 has uncommitted work there (the
  `_presolve` worklist, 170s -> 3s on cpu4, and a daemon guard closing a real
  fork bomb). I did not touch it.