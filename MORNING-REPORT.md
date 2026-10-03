# MORNING REPORT — 2026-10-03 night session

## DONE: the levers are in one column, and alu4 is green with it

```
LEVERS: 10    x 3..3  (span 0)    z 3..93

   B0(3,3)   A0(3,13)   B1(3,23)   A1(3,33)   B2(3,43)
   A2(3,53)  OP1(3,63)  OP0(3,73)  B3(3,83)   A3(3,93)

VERIFY OK: 1024 vectors, 16 chunks green
60724 blocks (was 35082), size (1980, 285)
```

One cell of x. Every input flips from one spot. Was **21 levers spread over
1757 blocks** — for `A3` you had to walk to x=1484 *or* x=1760, and `OP1` had
five levers at x=7/431/826/1468/1752.

Reproducible from scratch, not from a stale cache:

```
python scratch/hier_bands.py  scratch/cand_alu4hier.txt scratch/alu4bandsBANK 150
python scratch/hier_stitch.py scratch/alu4bandsBANK.pkl scratch/cand_alu4hier.txt 900 scratch/alu4fresh.pkl
python scratch/verify_par.py  scratch/alu4fresh.pkl scratch/cand_alu4hier.txt 16 2400 16 16
```

All 6 bands rebuild **byte identical** to the cache, and the fresh-bands merge
is byte identical to the cached-bands merge. The three engine fixes below are
geometry-neutral for band composition.

## Exported and installed

| file | size | notes |
|---|---|---|
| `build_alu4bank.schem` | 17,390 B | 60,724 placed cells, 22 palette entries, verified by reading it back |
| `build_alu4bank.mcfunction` | 3,999,496 B | |
| `build_alu4bank.html` | 25,100,239 B | 1024 vectors, **full** states |

The schematic is installed at
`…\FreesmLauncher\instances\26.3\minecraft\config\worldedit\schematics\build.schem`
(last night's 35,082-block build preserved beside it as
`build.schem.bak-20261003-063141`).

**You can paste this one.** The 10 levers are the column at x=3, z=3..93,
north-west of the machine. Nothing else in the build is interactive.

Note: `//paste` anchors on your position, and this build is 1,974 x 285. Stand
somewhere with room. The old `build_*.html` (4.0 MB) turns out to have been
exported from a *partial* states set — its wire blob was ~29 bytes per vector
(~58 wire instances, not a whole build). The new page is the real thing.

## Three engine bugs found and fixed

All three are committed, all three are no-ops on a field that was already
valid (`REDSTONE_INPUT_BANK=0` still merges byte identical to the shipped
`alu4merge.pkl`), and all three were found by the bank walking into them.

1. **`lwire`'s 3D flight could put dust and cobblestone in one cell.** A
   one-cell descent makes the lower step the support for the cell above it.
   The existing self-lid test cannot see it: it asks whether the cell above
   the lower step is a support, and that cell is only a support *because* it
   is about to become dust too. `finish_assembly` killed the whole merge with
   `duplicate block`.
2. **`_support()` reports an already-recorded pillar as reusable** (returns
   `None` for a cell in `sup`), so a later leg of the same net laid dust on a
   cell that already owed a cobblestone. `_support` is about support, not
   occupancy, and nothing else checked.
3. **`_landed`'s contiguity checker had repeaters backwards** — *both* halves,
   against `sim.py:835` (which stores `rep[c] = -parsed_facing`, i.e. travel).
   Every correctly-oriented booster counted as a break. The error walked along
   the row one cell at a time as each half was corrected, which is how it was
   identified: `broken link (-4) -> (-3)`, then `(-3) -> (-2)`, then
   `(813) -> (814)`. The third hop needed one more fix — the two every-8
   passes can leave two boosters one cell apart where they meet, and sim reads
   that fine.

## cpu4 is red, and it is NOT the bank

Rebuilt from scratch with the fixed engine: all 10 bands compose green per-band
(203 s), the merge succeeds structurally (101,031 blocks), and then:

```
SMOKE 1111111 MISMATCH ['Y2']
```

**Identical with the bank off** (73,589 blocks, same `Y2` mismatch). So this is
pre-existing and independent of everything above.

The old `cpu4merge3.pkl` is not trustworthy either: it contains **8 conflicting
duplicate cells** (e.g. `(1854,1,108)` cobblestone+wire), so it predates the
one-cell-one-block gate and its 16/16 green was scored by a sim reading two
blocks in one cell. It also cannot be re-stitched at all — it dies
`duplicate block at (1854,2,87)`.

**The likely cause, and it is a design gap rather than a bug:** the band
ladder picks the *first* rung that makes that band green **standalone**. Each
band sims green alone, but correctness is a property of the *combination* — the
cross-band handoff. The old cache happened to be a combination that worked
(under a sim that let it); a fresh climb is free to pick a different
combination, and `Y2` is wrong on the all-ones vector. `hier_bands.py` has no
notion of a merge-level retry.

**Next step for cpu4:** make the ladder combination-aware — when the merged
smoke disagrees, re-pick a rung for the bands feeding the wrong output and
re-stitch (the stitch is ~9 min, the bands are cached, so this is a loop over
cached bands). Cheap version: pin the bands that produce `Y2` and re-climb only
those. Do **not** spend time on the bank for cpu4; it is already correct there.

## Two dead ends, recorded so they are not retried

- **Straight-line one-level fan-out cannot work, and it is worth not
  re-deriving.** Every band's stub sits at z 2..8 while every field reaches
  north past z −19, so a per-input row must be north of the field, and every
  drop from a row runs south — so every drop crosses every row south of it.
  Crossings are structural.
- **`_relay` does not help the bank.** Its waypoints are already at
  `(x, drv[1])` and `drv[1]` already *is* the trunk row, so it was the obvious
  missing piece. Measured: identical failure. The east run was never the
  problem; the descent into the band at the stub's latitude was, and that is
  now solved by pre-stamping the rows and dropping down the stub's own column.

## Commits (branch `phase2-design`)

- `8d8ff53` input bank behind a flag + the two `lwire` flight fixes
- `1d304af` cluster onto its own trunk rows, rows ordered by reach, stitch-failure dump
- `3d34e9a` 6-apart rows, gapped drop waypoints, street-split east run
- `abcda2f` `_relay` tried and ruled out
- `eb50f55` **default ON** — alu4 green 16/16 with 10 levers in one column
- `a31c91a` verified end to end; exports and installed schematic

Working tree clean apart from the two pre-existing
`build.mcfunction.bak` / `build.schem.bak` (untouched, untracked). No files
deleted. `scratch/` gained only new probe outputs.

## Diagnostics added along the way

- `REDSTONE_HIERDUMP_FAIL` now fires on a **stitch** failure, not just on
  `check_opens`/`finish_assembly` — the banked fan-out is the first thing that
  can fail before either of those, which is why several iterations had no field
  to inspect.
- Leg failure messages are no longer truncated to 60 characters. That one line
  was hiding every bank error behind the last generic strategy's message.
- `_streets` is the midpoint of two band **start** offsets, i.e. *inside* the
  earlier band, not in the reserved `_HIER_GAP`. Harmless for a gate net with
  short relay legs, fatal for a trunk crossing the whole build. Left untouched
  (it is load-bearing for green geometry) and worked around with a separate
  `_bankstreets`; worth fixing properly one day.
- `_loop_near` floods a ±25 box around every path cell, so a long path sees
  the whole consumer field and reports rings that were already there. Skipped
  for the bank, where `_try`'s before/after `_lr` diff is the check that can
  actually tell a new ring from an old one.