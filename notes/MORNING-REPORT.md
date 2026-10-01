# Morning report — cpu4 session 2 (autonomous, continued)

**DONE = cpu4 green. NOT DONE — but the merge now completes and two of four
smoke vectors are correct.** Previous report's wall (a pre-existing diode ring
killing the merge in `finish_assembly`) is fixed.

Repo `D:\redstone-mini`, branch `phase2-design`. New commits this session:
`e8cd0c8` (previous session), `6540a3a`. Working tree clean.

## Progress

```
$ python scratch/hier_stitch.py scratch/cpu4bands2.pkl scratch/cand_cpu4hier.txt 300
MERGE 72055 blocks (3376, 287)
SMOKE 0000000 OK
SMOKE 1111111 OK
SMOKE 0101010 MISMATCH ['Y1']
```

That is a real step: the merge used to die in `finish_assembly` or in the sim.

## The wall this session (previous report's item) — FIXED

`finish_assembly` rejected the merge on `repeater loop on R1Q3 at (2850,1,43)`.
The cause was **ordering**, not geometry: the ring gate inside `_try` ran
*before* `_plant_repeaters`, so a booster landing where a leg doubles back on
an **earlier leg of the same net** (R1Q3 is consumed by two bands and the legs
chain stub-to-stub) closed a ring nobody was watching.

Fix: boosters are planted **inside `_try`**, after the pre-boost ring check and
followed by a post-boost one. Inside `_try` a failure rolls back and the *next
strategy* runs; outside it the whole net failed. Also added: a run must be a
*simple* path (an adjacent repeat at a leg joint is the only legal one), and
the stub-connect pass got the same post-boost ring gate it never had.

## What still fails, precisely

On `D=0101 OPC=010` (a no-write vector: `REGW=0`, so both registers must hold
their seeded 0):

| net | lit | should be |
|---|---|---|
| `R0Q0` | **1068/1068** | 0 |
| `R1Q0` | 0/811 | 0 |
| `AL_X0` | 63/64 | 0 |
| `AL_S2` | 31/32 | 0 |
| `AL_X2` | 61/315 | 0 |

So `R0Q0` — an entire register-bank output, latch *and* stitch — is lit when it
must be dark, and the XOR tails inherit it.

### The finding to chase next (frame mapping is now certain)

**The merged `blocks` list is missing tile torches that `solid` still
declares.** In `scratch/cpu4merge2.pkl`:

- `solid` says the R0Q0 latch torches are at merge `(653,48)` and `(656,47)`
- `finish_assembly` shifted blocks by `(-2,-26)`, so those are **block
  `(655,74)` and `(658,73)`**
- `blocks` contains **no** torch anywhere in x 640-680, z 60-95; in fact
  **all 230 torches in the build sit at z 98..170**

`check_shorts`/`check_opens` read `wires` + `solid` and pass; the **sim** reads
`blocks` and therefore cannot see those torches at all. That is why a run with
no visible driver still reads high, and it is a merge-integrity bug, not a
routing one.

**Frame rule, stated once so it stops costing time:** `solid`, `wires`,
`repeaters`, `rings` and `stitched` in a merge dump are **merge space**;
`blocks` (and therefore `io`) are **block space**; `block = merge - (-2,-26) =
merge + (2,26)`. Comparing a band's `out` (finish_assembly'd on its own)
against the merged `blocks` is a *different* frame error and manufactures a
bogus "3388 cobble deleted" (it is 17 boundary-input levers, by design).

## Next step

Find where the merge drops those torch blocks. Prime suspects, in order:

1. `compose_hier_parts`'s band copy loop — it appends `pctx.blocks` verbatim
   and separately copies `pctx.solid`, so the two can diverge if a band ctx's
   `blocks` is short. Compare `len(solid torch entries)` against
   `len(wall_torch blocks)` **per band, in one frame**, right after the merge
   loop and again after `finish_assembly`.
2. `finish_assembly`'s shrink-wrap: it shifts `blocks`, `solid`, `wires`,
   `rings`, `junctions`, `pos`, `repeaters` — but **not** the copies embedded
   in `io`, and it rebuilds dust/repeater blocks from `wires`/`repeaters`
   only. A tile torch lives in `blocks` and nowhere else, so if the band
   `blocks` list lost it, nothing restores it.

Add a fail-loud assertion at the merge boundary: every `("torch", net)` in
`solid` must have a `wall_torch` block at the corresponding cell. That turns
this whole class loud at compose time.

## Re-gated

`recipe.py`, `sim.py` pass. `compose_check.py` bit-identical
(144/322/224/214). `dense_status.py` OK for example_and, latch_sr, mux2, sub2,
micro1, decode3, cmp2. alu4 re-stitched 35516 blocks and re-verified **1024/1024**
with the new physics.

## Traps (carried forward, both cost real time)

- Frame rule above. Two separate sessions lost hours to it.
- `REDSTONE_ASTAR_CAP` must be **unset** when building band caches; at 6000,
  bands 5 and 6 lose their only green rung.
- `scratch/hier_bands.py` picks the **smallest** green rung, so `HIER_SKIP`
  rarely moves a band — use `REDSTONE_HIER_RUNGS` to force one.
- `scratch/` now holds ~560 probe files. Pruning them (the finding is already
  in a `ponytail:` comment next to the code) would make the next session's
  forensics much faster.
