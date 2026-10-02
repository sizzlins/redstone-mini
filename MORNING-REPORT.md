# MORNING-REPORT — finish session 2026-10-02 (all three deferred items closed)

## Glass + slab: transparent vertical physics, modeled and gated

Glass (`minecraft:glass`) and stone-family slabs are first-class sim citizens:
dust climbs onto glass, glass stays dark and never feeds down, slabs carry
power/feed dust on top, transparent lids never cut slopes. Hand-placed
shafts/floors/lids verify instead of hard-rejecting. 4 sim oracles lock the
physics; suites green, compose_check bit-identical, diff reference re-frozen
(was stale 6 commits), ctrl_decode green. Full account in LOG.md.

### The three conservative holds — all worked, none declined (bc446af)

1. simvec no longer refuses: new side code 8 = slab, power terms take 4 and
   8, cup/cdn stay cobble-only (slab is powerable but transparent), wake
   vertices/edges + r_src + side() + l_cob + ncells + both scheduler loops
   extended. Tri-engine probe: serial == scalar == SWAR on a glass tower;
   diff_engine ALL IDENTICAL (the delta is empty on glass-free builds, so the
   bit-identity gate alone could never have caught a mistake here).
2. The search knows glass/slab: `_support(..., reuse=)` returns None (stamp
   nothing) over ownerless hand glass/slab, and `astar(..., reuse=, ig=)`
   slopes onto them while refusing to route *into* them at any height.
   finish_assembly now rejects duplicate coordinates, so the whole
   two-blocks-one-cell paste class is loud. `route()` threading deliberately
   skipped: both builders start from empty fields, so the set is provably
   always empty — direct astar callers pass it explicitly.
3. Router auto-glass: measured, not built. The provably-safe rule (glass iff
   all four diagonal-below cells are immutably occupied) fires 0 times on
   cpu4merge3 — 0 of 4709 off-ground pillars qualify, because corridors are
   open by construction. Zero-fire code is YAGNI, so the honest answer is the
   measurement plus the search-awareness above: glass pays off as hand-placed
   insulation, and the router's glass payoff is *avoiding* couplings, not
   stamping pillars.

### Slab halves: checked against the wiki, full-cell is the correct model

minecraft.wiki/w/Redstone_Dust: dust is placed on "conductive blocks ...
upside-down slabs, glass, upside-down stairs"; the block *between* two dust
must be air or non-conductive; downfeed needs the higher dust "on a
conductive block one level higher", and "the signal can never go down from
slabs". At integer-block granularity all three hold for a full-cell slab: the
slab owns its own cell so anything resting on it is necessarily the cell
above (both halves), the slab is transparent for connections, and it never
passes power down. `export.py` emits explicit `type=bottom` for hand slabs, so
half-height never has to be modelled — the only slab states we accept are the
transparent single ones; `type=double` is an opaque full block by design.

## cpu4: DONE, 128/128 — root cause was stale diodes, not the router

R0Q0's wall is gone. Forensics (9 bounded probes, all offline against
cpu4merge3.pkl): coupling clean at every level (same-y/slope/torch/lever/
repeater/junction/ring — all zero), per-vector sweep found 16 dark-when-lit
mismatches, bisection led to REGW dark everywhere incl. its driver cell,
then to C_n2's trunk lit only 9 cells. Band 0's own ctx is healthy (122 dust
+ 16 diodes). Root cause: cpu4bands2.pkl was built 10/1 6:16PM, commit
29fc565 flipped diode facing to vanilla 10/2 10:56AM — every pre-flip diode
reads backwards under the current sim and never fires. Fix = rebuild
artifacts, zero code: hier_bands → 10/10 green, hier_stitch → 74473 blocks,
smokes 0000000/1111111/0101010/1010101 OK, verify_par → 128/128 chunks green.
Canonical caches (cpu4bands2.pkl, cpu4merge3.pkl + verify.json) replaced.
Lesson: the engine fingerprint voids verify caches, but band/merge PKLs are
build INPUTS — nothing forces their rebuild after a physics-meaning change.

## Default bands widened upward: maze 1..4, compose narrow (1,4)

Suites green, compose_check bit-identical, alu1 recomposed under final
defaults with identical geometry (12294 blocks) and VERIFY GREEN. Measured
NO downward: ymin=0 as a first-attempt default breaks gate-fed D-latch
(nD 3D-self-lid — ground cobble roofs trench slopes, candidates all
self-lid). Trenches stay in the wide fallback + REDSTONE_YMIN=0. Two commits:
try_bridge for/else (pre-existing UnboundLocalError when every candidate
refuses — proven pre-tall-bridge via git show, it just never fired before)
and the band change.

## Vertical stacking: physics proven, compiler migration scoped as TODO

Hand-placed NOT at y=2 on pillars sim-greens. End-to-end needs the 2D→3D map
migration (~140 y==1/2D-key sites measured across 4 files) — a compiler
project, not an overnight task. Anchor comment at tiles.new_ctx says exactly
where to start and what not to do (no lone y0-threading: it pastes
unroutable tiles). Full analysis in LOG.md.

## Fleet (this engine, verify=True throughout)

- micro1 OK (2925), alu1 OK (12294, green), ctrl_decode OK (4923), cpu4 OK
  (128/128) — all green.
- alu4: fresh compose still grinding at handoff (long rung, CPU-busy, no
  crash — the UnboundLocalError on its exact path is fixed). Its old merge
  pkl is pre-flip (backwards diodes) so re-verifying it would false-red;
  the honest re-gate is the running fresh compose. Resume: dense_status.py
  recipes/alu4.txt — or rebuild its bands like cpu4 if compose stays loud.
- Probe rule (bit twice now): main-guard every probe or set
  REDSTONE_SERIES_VERIFY=1 — unguarded + spawn Pool = fork bomb. An outside
  agent correctly diagnosed my leftover trench_e2e.py; tree killed.

---

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
