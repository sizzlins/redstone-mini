# MORNING-REPORT — 2026-10-02 night session

Headline: **alu4 is green — 1024/1024 vectors verified — and the build is
exported to your WorldEdit folder.** Two more real defects were found and
fixed along the way, both of which had been silently shipping green builds.

## Where your build is

| what | where |
|---|---|
| **`.schem` (WorldEdit)** | `…\FreesmLauncher\instances\26.3\minecraft\config\worldedit\schematics\build.schem` (12,356 bytes) |
| previous one, not overwritten blind | same folder, `build.schem.bak-20261002-210028` |
| `.mcfunction` | `D:\redstone-mini\build_alu4.mcfunction` (2.28 MB) |
| `.html` preview | `D:\redstone-mini\build_alu4.html` (4.5 MB, interactive — 4 smoke vectors have real per-wire state) |

Paste at y=64 (WorldEdit's default anchor is the player, so paste where you
want it). 35,082 blocks: 14,634 wire, 13,821 stone, 4,386 cobblestone, 2,059
repeaters, 138 torches, 21 levers, 18 comparators, 5 lamps.

Verified by reading the *written file* back, not the build list: all 35,082
blocks carry the state they were written with, plus a 500-block random re-read
of the installed `.schem` (0 mismatches).

## What now builds

| build | verdict | evidence |
|---|---|---|
| **alu4** (10 inputs) | **GREEN, 1024/1024** | `VERIFY OK: 1024 vectors, 16 chunks green`, fp `6bd0cbfd80fe` |
| cpu4 (7 inputs) | GREEN, 128/128 | re-verified from scratch under the new engine |
| alu1 | GREEN, 12,294 blocks | after every fix |
| ctrl_decode | GREEN, 4,923 blocks | after every fix |
| example_and / 2gates / latch_sr / xor | GREEN | `compose_check.py` |
| suites | GREEN | `sim.py`, `layout.py`, `diff_engine` ALL IDENTICAL |

## The three bugs of the night

1. **alu4's old "64/64 green" was a ghost** — written 10/1 23:19, before the
   diode-facing flip landed 10/2 10:56. Re-verified today it was RED on all 16
   chunks. Kept as `alu4merge.preflip.pkl`.
2. **A booster that fed a tile torch which fed it back.** 6-node ring on
   `OP1x_3` latched the band-3 handoff (15 of 24 sampled vectors hunting,
   18,059 churn cells). `_closes_loop`/`_loop_rep`/`_ends_ok` all miss it: they
   reason about dust, and this ring leaves the dust *through a torch*. Fixed in
   `compose._ends_ok` + layout's booster loop + a loud `finish_assembly` check.
3. **Dust stacked on dust — invisible to the sim, fatal on paste.** The export
   round-trip (the only check that sees the paste) caught 24 cells holding both
   cobblestone and wire, each with a dust cell above resting on what became a
   wire. Two causes: my duplicate guard ran *before* wires were appended, so it
   was blind to the whole wire class; and compose's bridge/hop sites stamped
   supports without asking whether the cell was occupied. Both fixed; the sim
   now refuses a component resting on a wire. The rebuilt alu4 is also
   **smaller** (35,082 vs 41,031 blocks) and verifies **4.7× faster** (245 s vs
   1,150 s).

## The stitch item I offered — solved at the root

No seed/spread knob was added: the failures were placement *rules*, not bad
luck, so fixing the rule makes the first attempt green instead of burning
retries. What the pipeline did lack was the link from stitch to verifier —
`hier_stitch.py` now takes an optional 4th argument that saves the merge pkl,
because `verify_par` reads a pkl and nothing could hand it one.

## Still not done (nothing blocking)

- **True 3D tile stacking** — physics proven, compiler migration (~140
  `y==1` assumptions) still not built.
- **Band caches are not fingerprinted** — only verify caches are; the cpu4
  stale-input lesson is still enforced by hand.
- **Never pasted into a real client.** Every verdict here is the sim agreeing
  with itself plus wiki rules. This is the first build exported for real use,
  so the paste itself is the next unproven step — the 24 popping cells were
  caught by a file round-trip, not by the game.
- **Layout facing trap** — layout's booster helpers read `front` as the output
  cell while sim reads the opposite; harmless only because those helpers are
  direction-agnostic. `_booster_out_cell` encodes sim's rule now.