# MORNING REPORT — 2026-10-03 night session

## What I was asked to do

"the levers need to change. they need to be in only one cluster." — the hier
builds ship one input lever per band, so `alu4` had **21 levers spread over
1757 blocks** and flipping an input meant walking to whichever band's copy was
nearest.

## The answer to your question, measured

**It is now one column, and I have the numbers off the merged field:**

```
REDSTONE_INPUT_BANK=1  python scratch/hier_stitch.py scratch/alu4bands.pkl \
    scratch/cand_alu4hier.txt 900 scratch/alu4bank.pkl

LEVERS IN MERGED FIELD: 10
x -5..-5   (span 0)        z -51..-15  (span 36)
   OP1(-5,-51)  OP0(-5,-47)  B3(-5,-43)  B2(-5,-39)  B1(-5,-35)
   B0(-5,-31)  A3(-5,-27)  A2(-5,-23)  A1(-5,-19)  A0(-5,-15)
```

One cell of x. 36 cells of z. Every input flips from one spot. Was 21 levers
over 1757 cells of x.

## What is NOT done

**The build is still red, and it is not the levers.** Carrying the value from
that column to each band's stub needs a distribution trunk, and the trunk is
what is not finished.

Last measured failure, `REDSTONE_INPUT_BANK=1`:

    STITCH RED: hier stitch OP1: band 5 stub (1751, 4):
                compose: no ground for OP1: (-4, -33) -> (1653, 1)

**So the flag is `REDSTONE_INPUT_BANK`, default OFF**, and with it off
`alu4` merges **byte identical** to the shipped `alu4merge.pkl` (35082 blocks,
`io["levers"]` equal, 4/4 smoke vectors OK). Your ten green builds are
untouched. Do not paste anything new tonight — the build in
`…\worldedit\schematics\build.schem` is last night's, unchanged, and still has
21 levers.

## Two real engine bugs found and fixed (both committed, both narrow)

Both are in `lwire`'s 3D-flight branch, both are no-ops on any field that was
already valid, and both were confirmed by the control staying byte identical.

1. **One cell got both dust and cobblestone.** A one-cell descent makes the
   lower step the support for the cell above it. The existing self-lid test
   cannot see it — it asks whether the cell above the lower step is a support,
   and that cell is only a support because it is about to become dust too.
   `finish_assembly` then killed the whole merge with
   `duplicate block at (1854,2,139)`.
2. **`_support()` calls an already-recorded pillar "reusable".** It returns
   `None` for a cell in `sup`, so a later leg of the same net laid dust on a
   cell that already owed a cobblestone. `_support` is about support, not
   occupancy, and nothing else checked. Same `duplicate block` death.

Also added: `REDSTONE_HIERDUMP_FAIL` now fires on a **stitch** failure, not
just on `check_opens`/`finish_assembly`. The banked fan-out is the first thing
that can fail before either of those, which is why several iterations tonight
had no field to inspect.

## cpu4 is red independently of any of this — do not trust its cache

- `cpu4bands2.pkl` bands 5 and 6 each contain **3 cells that are in `sup` at
  y>=2 and also in `wires`** — the exact defect class of bug 1 above, baked
  into the cached partitions.
- `scratch/cpu4merge3.pkl` (the "green" cpu4 merge, fp `47fb2a6e0efb`)
  **itself contains 8 conflicting duplicate cells**, e.g. `(1854,1,108)`
  cobblestone+wire. It predates the one-cell-one-block gate added 2026-10-02, so
  its 16/16 green was scored by a sim that read both blocks in one cell.
- `hier_stitch cpu4bands2.pkl` now dies **with and without** the bank:
  `duplicate block at (1854,2,87)`.

**cpu4 needs its bands rebuilt from scratch, not re-stitched.** Its band ladder
has to run again on the current engine.

## The next step (each is a measured failure, not a guess)

**What is now known precisely:** the east run along the trunk row is solved —
it splits at the streets, and `_relay` gives it repeater stations. The part
that does not route is the **descent into the band at the stub's own
latitude**. Every band's stub is at `minx - 1`, the westernmost cell of that
band's margin, and the lever rows march east from it at 2 cells of z pitch, so
a run at the stub's latitude walks straight into them.

1. ~~Give `_relay` a row argument.~~ **TRIED, FAILED — do not repeat.**
   `_relay`'s waypoints are already at `(x, drv[1])` and `drv[1]` already *is*
   the trunk row, so I routed the bank through `_relay` directly instead of
   `_legs`. Result: identical failure, `hier stitch OP1: band 5 stub
   (1751,4)`. Its last leg is the suspect: `(1577,4) -> (1751,4)`, a 174-cell
   run at z=4 — exactly the lever-bank latitude.
2. **Drop down the street instead of down the stub's column.** `_HIER_GAP=160`
   leaves a 160-wide empty column between every band pair, empty top to
   bottom. East along the row to the street immediately west of the band, down
   the street, then east at the stub's latitude. Same last-leg problem, but
   from a guaranteed-clear column and with 160 cells of approach instead of
   one. **Most promising.** Check `A3B3` first: its stub is at z=63, far
   inside band 4, so its latitude may not be reachable from a street either.
3. **Reach the stub from the north down its own column.** `_bank_pts` already
   tries this; it keeps dying. Add the band's `minx` column as an explicit
   waypoint *before* the latitude change, so the descent is split into
   "down the column in the north margin" and "one cell east into the stub".
4. **Trunk in the gap between y.** Stack rows at y=1,3,5,… over z rows 6
   apart. Needs a narrow exemption for the cell directly above a row, which
   bug 2's fix just made fatal.

**Do not try a straight-line one-level fan-out.** I proved it cannot work and
the proof is in LOG.md: every band's stub sits at z 2..8 while every field
reaches north to z −19, so a per-input row must be north of the field, and
every drop from a row goes south, so every drop crosses every row south of it.
Crossings are structural. Ordering the rows by how far east each input reaches
(longest row southernmost) cut the crossings from ten to three and the failure
moved from `A3B3` to `OP0` — three is past what `lwire`'s single hop absorbs.
Rows are now 6 apart with a waypoint in each gap so each leg crosses exactly
one row; that got the bank legs furthest of anything tried, and OP1's band-5
leg still does not land.

## Commits (branch `phase2-design`)

- `8d8ff53` input bank: one lever column for hier builds (flag, default off) + the two `lwire` fixes
- `1d304af` cluster moved onto its own trunk rows, rows ordered by reach, stitch-failure dump

Working tree: only `compose.py` and `LOG.md` touched. No files deleted. The two
pre-existing `build.mcfunction.bak` / `build.schem.bak` are untouched and
untracked. `scratch/` gained only new probe outputs (`alu4bank.pkl`,
`alu4ctrl*.pkl`, `bankfail*.pkl`, `bank_trace*.txt`) and deleted nothing.

## Reproduce

    # control: must print 35082 blocks, byte identical to alu4merge.pkl
    set REDSTONE_INPUT_BANK=0
    python scratch/hier_stitch.py scratch/alu4bands.pkl scratch/cand_alu4hier.txt 900 scratch/alu4ctrl.pkl

    # the bank (currently red on a gate net)
    set REDSTONE_INPUT_BANK=1
    python scratch/hier_stitch.py scratch/alu4bands.pkl scratch/cand_alu4hier.txt 900 scratch/alu4bank.pkl

Both are hard-bounded: the stitch child is killed at the timeout you pass, and
the outer shell timeout is a second bound.