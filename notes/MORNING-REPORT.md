# Morning report — cpu4 session (autonomous, 2026-10-01)

**DONE = cpu4 green. NOT DONE.** cpu4 is at *merge reaches the simulator,
3 of 5 outputs correct* (was: torch burnout, then all-dark). Two real root
causes were found and fixed; a third is now the wall.

Repo `D:\redstone-mini`, branch `phase2-design`. Commits this session:
`7fdbd72`, `c8fb1d2`, `0b773eb`, `a893b82`, `e8cd0c8`. Working tree clean
except `notes/MORNING-REPORT.md`.

## What is green now (authoritative, re-run this session)

| gate | result |
|---|---|
| `python recipe.py` | pass |
| `python sim.py` | pass (2 new oracles added) |
| `scratch/compose_check.py` | bit-identical 144 / 322 / 224 / 214 |
| `scratch/dense_status.py` | OK: example_and, latch_sr, mux2, sub2, micro1, decode3, cmp2 |
| `scratch/verify_par.py scratch/alu4merge.pkl recipes/alu4.txt` | **VERIFY OK 1024/1024** (re-composed *and* re-verified with the new physics) |

alu4 was re-stitched from scratch (35516 blocks, was 34734) and re-verified
all 1024 vectors — the physics and router both changed this session, so the
old cache proved nothing.

## What still fails

```
$ python scratch/hier_stitch.py scratch/cpu4bands2.pkl scratch/cand_cpu4hier.txt 300
STITCH RED: repeater loop on R1Q3 at (2850, 1, 43): front joins back
```

**cpu4 is blocked by a pre-existing repeater ring in a band tile**, not by
the stitch. `finish_assembly` rejects the whole merge on any
front-joins-back diode pair. The gate added this session
(`_try` → `layout._loop_rep`, new-loop-only) correctly does *not* blame the
stitch for it, so the merge still dies at the end.

`place_xor` builds its XOR from two subtract comparators whose tails merge
through **two facing diodes** at `(ox-2, gz+3)` and `(ox-2, gz+5)`. When
those two end up facing each other across one cell, `_loop_rep` sees a
front joining a back. The band sims green (the sim does not model the
bistable pair the same way), so the band cache accepts it.

### Next step (not attempted — out of context budget)

Reject a *band rung* whose own output contains a diode ring, at the point the
band cache is built (`scratch/hier_bands.py` already runs `sim_verify` and
`check_hier_ports` per rung; add `layout._loop_rep` there). That is ~5 lines
and turns this from a merge-time wall into a rung-selection problem, which
the existing ladder already knows how to answer. It is the same shape as the
`AL_X2` fix that unblocked Y2: **a tile's own dust is a fixed shape, and
`_loop_rep` is the authority on whether that shape is buildable.**

## Root causes found and fixed (all measured)

1. **Undriven SR latch hunted forever** (`sim.py`, `7fdbd72`). A NOR latch
   released from a dark start is symmetric in this model: both torches fire,
   hunt, burn out. Vanilla breaks it with update-order skew; `eval_net`
   already assumed hold-0. `_latch_hold_seed` presets `~qb` dust **and** its
   driver torch (each alone was measured to fail), and a power-on pre-roll
   (`_solve`) removes the tick-1 output pulse that reached idle latches at
   T~9 and broke the seeded hold. Latch-free builds take a byte-identical path.
2. **A lever powered every block beside it** (`sim.py`, `7fdbd72`). D3's floor
   lever drove cpu4's R0Q0 stitch run to 15, forcing R0Q2 high whenever D3=1
   — bit-0 AND/XOR wrong. Wiki: a lever powers its *attachment* only.
3. **A booster planted on a tile's own output run** (`compose.py`, `a893b82`).
   `place_xor` merges two comparator tails through two facing diodes, so a
   booster between them faces the wrong way and cuts the merge. This is why
   **Y2 was wrong**: AL_X2 went dark in the merged build while band 6 simmed
   green standalone — a band sim runs on `out`, and boosting happens *after*.
   Guard: `own=` is the placement-end wire snapshot, so only routed cells can
   be boosted. This is the fix that took cpu4 from 3/5 to a single wrong net.

Three more guards landed with it, each from a measured failure: relay
stations only on straight runs; every stitch must **deliver** onto its stub
by sim-conducting links; every consecutive pair of *fresh* path cells must be
a sim link (check_opens floods the whole field, so one break orphans
everything past it while the stub flood — seeded at the path — reported 0).

## Assumptions

- Work target is `D:\redstone-mini` (DONE says so; `D:\redstone-compiler` is
  a separate Rust project with no recipes).
- `recipes/cpu4.txt` stays the original unbanded recipe until cpu4 verifies
  128/128. `scratch/cand_cpu4hier.txt` (10-band, 128-vector equivalent) is
  the candidate.
- Band caches are built with `REDSTONE_ASTAR_CAP` **unset**. Setting it to
  6000 makes bands 5 and 6 lose their only green rung (`no ground for
  AL_n0_5`) — measured, and reproducible in a single process.

## Notes / traps found

- Comparing a band's `out` (finish_assembly'd on its own) against the merged
  block list is a **frame error** — every count comes out as "3388 cobble
  deleted". The correct map is `ctx.blocks + OFFS[band] + (2, 26)`. Two hours
  of the session went into that false lead; the real deletion set is 17
  boundary-input levers, which is by design.
- `scratch/hier_bands.py` picks the **smallest** green rung, so
  `HIER_SKIP` rarely moves a band. Force a rung with
  `REDSTONE_HIER_RUNGS` instead.

## What I need from you

Nothing blocking. Two decisions worth a word, both cheap either way:

1. The glass feature (non-conductive support; `_parse_build` still rejects
   it) is still queued after cpu4, per your earlier call. It would delete most
   of the lid/slope-coupling machinery this repo fights — worth doing right
   after cpu4.
2. `scratch/` has 539 files of probes. Most are single-purpose forensics with
   the finding already in a `ponytail:` comment. Pruning them would make the
   next session's forensics much faster to navigate.
