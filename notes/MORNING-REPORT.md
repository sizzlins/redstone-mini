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

### RETRACTION — the "missing tile torches" finding below is WRONG

I claimed the merged `blocks` list was missing tile torches. **It is not.**
Measured over the whole build: all **230 of 230** `("torch", net)` entries in
`solid` have a matching `wall_torch` block. Nothing is missing.

The error was mine: I computed the `finish_assembly` shift as `(-2,-26)` and
so compared `solid` (merge space) against `blocks` (block space) at the wrong
offset. The **correct, build-independent rule** is:

```
block = merge + (3 - min_merge_x, 3 - min_merge_z)
```

because `finish_assembly` shrink-wraps with `minx = min(OCC_x) - 3`. For
`cpu4merge2.pkl` that is `merge + (2, 86)` — my `(-2,-26)` was off by 112 in
z. Derive it per build from the data; never hard-code it. (This is the same
frame error that produced the bogus "3388 cobble deleted" two sessions ago.
It has now cost two sessions. It is the single highest-value thing to fix
next: **make the merge dump carry the shift explicitly**, e.g. store
`{"shift": (minx, minz)}` in the pickle, so no probe can get this wrong again.)

### The real remaining symptom (needs re-diagnosis with the right frame)

On `D=0101 OPC=010` (a no-write vector: `REGW=0`, so both registers must hold
their seeded 0):

| net | lit | should be |
|---|---|---|
| `R0Q0` | **1068/1068** | 0 |
| `R1Q0` | 0/811 | 0 |
| `AL_X0` | 63/64 | 0 |
| `AL_S2` | 31/32 | 0 |
| `AL_X2` | 61/315 | 0 |

`R0Q0` — a whole register-bank output, latch *and* stitch — reads lit when it
must be dark, and the XOR tails inherit it. The net-level counts above are
frame-independent (they come from `live`/`nets`, both block space), so this
part stands. Only my *localisation* of it was wrong: the latch torch
neighbourhood I dumped was read at the wrong offset, so "the latch is absent"
was an artefact.

**Next step:** re-run the latch-neighbourhood dump for `R0Q0` at
`merge + (2, 86)` and find what actually drives it. The R0Q0 latch origin in
merge space is `(652,48)`, i.e. block `(654,134)`.


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
