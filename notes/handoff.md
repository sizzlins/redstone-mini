# handoff — 2026-10-03 session (single input-lever column, three engine bugs, cpu4 diagnosis)

Repo: `D:\redstone-mini`, branch `phase2-design`.
Session commits: `49dc51c..ecf651b` (7 commits, `compose.py` +439/-…, docs).
Working tree clean apart from the two pre-existing `build.mcfunction.bak` /
`build.schem.bak`, which nobody may delete or commit.

---

## ⚠ Read this first: the working tree is SHARED

Another agent was editing this repo during the previous session. **What went
wrong then, so it is not repeated:** I ran `git stash push -- export.py` and
`git checkout -- export.py` to isolate a file I was verifying. Both were meant
to be temporary and I did not put it back, so another agent's bug fix sat in a
stash while their tree showed HEAD. Nothing was lost, but it is exactly the
"you reverted a fix" outcome. Recorded in LOG.md under "export.py: a
concurrent agent's fix".

**Rules:**
- **DO NOT DELETE FILES.** Not tracked, not untracked, not ones that look dead.
  Cut code *inside* a file all you like; the file itself stays. If something
  must go, comment it out and say so in LOG.md — that leaves it recoverable.
- **Another process may be editing any file here. `git status` is not evidence
  that a file is yours.**
- To isolate someone else's in-flight work, use a **copy** (or a git
  worktree), never `checkout --` / `stash push` on a path you did not write.
- Never `rm` / `git clean` anything you did not create.
- `git add <file>` then `git commit` sweeps up *whatever else is staged*. Use
  `git commit -- <paths>`, and `git status` first.
- Before assuming a file is stale, check `LastWriteTime` and `git diff` again.

---

## Goal

**Asked for this session:** the input levers had to be in **one cluster**, so
an input can be flipped from one place. They were not — see "what changed".

**Reached:** one lever column, `alu4` green 16/16 with it, reproducible from
scratch, exported and installed.

**Still the standing goal:** every recipe in `recipes/` generates, verifies and
exports. `alu4` is done, `cpu4` is not (see below). The remaining
*architectural* goal is still true 3D tile stacking (scoped, not built).

---

## Current state

| build | verdict | evidence |
|---|---|---|
| **alu4** (10 inputs, 1024 vectors) | **GREEN, 10 levers in one column** | `scratch/alu4bank.pkl`, `VERIFY OK: 1024 vectors, 16 chunks green`, 60,724 blocks, size (1980, 285) |
| alu4 reproducibility | **byte identical from scratch** | `scratch/alu4bandsBANK.pkl` all 6 bands == `alu4bands.pkl`; `alu4fresh.pkl` == `alu4bank.pkl` |
| alu4 control (`REDSTONE_INPUT_BANK=0`) | **byte identical to shipped** | `alu4merge.pkl` = 35,082 blocks, `io["levers"]` equal, 4/4 smoke |
| **cpu4** (7 inputs, 128 vectors) | **RED — and NOT the bank** | fresh bands green per-band (203 s), merge succeeds, `SMOKE 1111111 MISMATCH ['Y2']` **identically with the bank off** |
| alu1 | GREEN, 13,300 blocks (**unchanged**) | `scratch/nonhier_suite.py` |
| ctrl_decode | GREEN, 5,499 blocks (**unchanged**) | same |
| example_and / 2gates / latch_sr / xor / micro1 | GREEN | same (144 / 322 / 224 / 214 / 2925 blocks) |
| suites | GREEN | `python compose.py` self-test passes |

**The lever cluster (the thing that was asked for):**

```
LEVERS: 10    x 3..3  (span 0)    z 3..93
   B0(3,3)  A0(3,13)  B1(3,23)  A1(3,33)  B2(3,43)
   A2(3,53) OP1(3,63) OP0(3,73) B3(3,83)  A3(3,93)
```

Was 21 levers over 1757 cells of x: for `A3` you had to walk to x=1484 *or*
x=1760, and `OP1` had five levers at x = 7 / 431 / 826 / 1468 / 1752.

**Exported and installed:**

| file | size | notes |
|---|---|---|
| `build_alu4bank.schem` | 17,390 B | 60,724 placed cells, 22 palette entries, read back and confirmed |
| `build_alu4bank.mcfunction` | 3,999,496 B | |
| `build_alu4bank.html` | 25,100,239 B | 1024 vectors, **full** states (the old `build_alu4.html` was a *partial* set: ~29 bytes/vector) |

`…\FreesmLauncher\instances\26.3\minecraft\config\worldedit\schematics\build.schem`
is the new build. Last night's 35,082-block one is preserved beside it as
`build.schem.bak-20261003-063141` (and the older one as
`build.schem.bak-20261002-210028`). **This new one has never been pasted into
Minecraft — that is still untested.**

Reproduce alu4 from scratch (~28 min total):

    python scratch/hier_bands.py  scratch/cand_alu4hier.txt scratch/alu4bandsBANK 150
    python scratch/hier_stitch.py scratch/alu4bandsBANK.pkl scratch/cand_alu4hier.txt 900 scratch/alu4fresh.pkl
    python scratch/verify_par.py  scratch/alu4fresh.pkl scratch/cand_alu4hier.txt 16 2400 16 16

---

## What changed

`REDSTONE_INPUT_BANK` (default **ON**) replaces one lever per band per input
with **one lever column** north of the merge. Seven commits, `compose.py` only:

- Every BAND composes alone and stamped its own input bank
  (`compose.py:1055`), and the merge only deleted levers for boundary
  (`recipe["edge"]`) nets — so recipe inputs kept one lever per partition.
- The column sits north of the merge, one row per input, rows **10 apart**
  (`_hop_free`'s shape is a 5-cell staircase with back and front two cells
  either side of the wire it crosses, so a row needs 9 clear cells to be
  hoppable; at 6 apart the walk answered "compose: stitch rings for OP1").
- Rows are ordered **by how far east each input reaches, longest row
  SOUTHERNMOST**. A drop crosses exactly the rows south of it, so this makes a
  drop cross only the rows of inputs reaching *further* east than the band it
  feeds. Cut the crossings from ten to three.
- **Every row run is stamped up front**, straight, in open ground; only the
  drops are routed. That puts every row/drop crossing in a drop, where the hop
  fits. The other order put them in a 1000-cell row run and the router's
  detour to hop a single drop came back through a waypoint ("path re-enters
  (332,1,-116)").
- The bank is **stitched last**, and its cluster is built after `_minz0`. A
  full-width trunk in the north margin takes away the only open margin the gate
  nets have — `A3B3` died "no ground for A3B3: (1834,50) -> (1341,1)". Routing
  the bank after every gate net gives each gate net the field it verified
  green with. `_gate + _bank` in the stitch loop is the whole of it.
- Drop columns **prefer the stub's own column**, checked clear of solids and
  repeaters. `_streets` is the midpoint of two band *start* offsets — i.e.
  *inside the earlier band*, not in the reserved `_HIER_GAP` — and a gate net's
  3D flyover roofs a whole gap with y=1 pillars, so no fixed gap column is
  reliable. `_bankstreets` was added as the gap fallback; `_streets` was left
  untouched so no gate net's geometry moves.

### Three engine bugs found and fixed

All three are no-ops on any field that was already valid, and all three were
found by the bank walking into them. Verified harmless to the old path
(`REDSTONE_INPUT_BANK=0` byte identical, and alu1/ctrl_decode block counts
unchanged) — worth stating because two of them live in `lwire`, which every
partition composition uses, not just the hier ones.

1. **`lwire`'s 3D flight could put dust and cobblestone in one cell.** A
   one-cell descent makes the lower step the support for the cell above it, so
   the same cell got both. The existing self-lid test is structurally blind to
   it: it asks whether the cell above the lower step is a support, and that
   cell is only a support *because* it is about to become dust too.
   `finish_assembly` killed the whole merge with `duplicate block`.
2. **`_support()` reports an already-recorded pillar as reusable** (returns
   `None` for a cell in `sup`), so a later leg of the same net laid dust on a
   cell that already owed a cobblestone. `_support` is about support, not
   occupancy, and nothing else checked.
3. **`_landed`'s contiguity checker had repeaters backwards — both halves** —
   against `sim.py:835`, which stores `rep[c] = -parsed_facing`, i.e. travel.
   Every correctly-oriented booster counted as a break. Identified because the
   error *walked along the row one cell at a time* as each half was corrected
   (`broken link (-4) -> (-3)`, then `(-3) -> (-2)`, then `(813) -> (814)`). A
   third fix was needed: the two every-8 passes can leave two boosters one
   cell apart where they meet, and sim reads that fine ("repeaters chain
   back-to-back").

### Diagnostics added (they are what made the rest findable)

- `REDSTONE_HIERDUMP_FAIL` now fires on a **stitch** failure, not just
  `check_opens`/`finish_assembly`. The banked fan-out is the first thing that
  can fail before either of those.
- Leg failure messages are no longer truncated to 60 characters. That one line
  was hiding every bank error behind the last generic strategy's message.
- A banked leg no longer falls through to the six generic strategies: all six
  are anchored on the driver's own cell or at the stub's latitude, which for a
  bank means running east at the trunk row through six fields. Every one was
  measured to fail on every banked leg, and running them cost ~40 s per leg
  while replacing the error that mattered.
- `_loop_near` is skipped for the bank. It floods a ±25 box around *every* path
  cell, so a 1000-cell trunk run sees the whole consumer band and reports a
  ring that was already there. `_try`'s before/after `_lr` diff is the check
  that can actually tell a new ring from an old one.

---

## What failed, and why it was wrong

- **Keeping each input's own westernmost lever is NOT one place.** It made
  **four** clusters (alu4: A0's at x=13, A1's at x=437, A2's at x=832, A3's at
  x=1482), because each input's westernmost copy lives in a different band.
  Recorded because it looks like the cheap fix and is not.
- **A straight-line one-level fan-out cannot work, and this is worth not
  re-deriving.** Every band's stub sits at z 2..8 while every field reaches
  north past z −19, so a per-input row must be north of the field, and every
  drop from a row runs south — so every drop crosses every row south of it.
  Crossings are structural, not a placement bug.
- **`_relay` does not help the bank.** Its waypoints are already at
  `(x, drv[1])` and `drv[1]` already *is* the trunk row, so it was the obvious
  missing piece for the 1657-cell east run. Measured: identical failure. The
  east run was never the problem; the descent into the band at the stub's
  latitude was.
- **`_streets` is in the wrong place.** It is the midpoint of two band *start*
  offsets, so it lands inside the earlier band, not in the gap. Harmless for a
  gate net with short relay legs, fatal for a trunk crossing the whole build
  (the first relay attempt descended band 3's middle). Not fixed — it is
  load-bearing for green geometry. Worked around with `_bankstreets`.
- **The measured progression, for reference** (same command each time):

  | change | failure |
  |---|---|
  | cluster at band-0 latitude, chain stub→stub | `OP1 band 4: path re-enters (1341,1,2)`; band 5 `no ground (825,4)->(1653,1)` |
  | fan out from the cluster, no chain | `A2 band 3: no ground for A2: (-4,2) -> (1123,1)` |
  | bank strategy first (north-margin route) | unchanged — the riser ran into the other nine stubs in the shared stub column |
  | one lever per trunk row, no risers | all ten inputs stitch; `A3B3 band 4: no ground (1834,50) -> (1341,1)` |
  | rows ordered by reach | `OP0 band 2: bridge support lands on wire at (8,1,-23)` |
  | rows 6 apart + gapped waypoints | `OP1 band 5: no ground (-4,-33) -> (1653,1)` |
  | + street waypoints on the east run | unchanged — `lwire` will not route >350 cells |
  | drop on the stub's own column, gate nets first, rows pre-stamped, `_landed` repeaters fixed | **GREEN 16/16** |

- **cpu4's cached green was not green.** `cpu4merge3.pkl` contains **8
  conflicting duplicate cells** (e.g. `(1854,1,108)` cobblestone+wire): it
  predates the one-cell-one-block gate, so its 16/16 was scored by a sim
  reading two blocks in one cell. It also cannot be re-stitched at all
  (`duplicate block at (1854,2,87)`). `cpu4bands2.pkl` bands 5/6 carry the same
  defect class.

---

## Files I touched

Tracked, this session (`git diff --stat 49dc51c..HEAD`):

| file | delta | what |
|---|---|---|
| `compose.py` | +439/−… | the input bank, the three engine fixes, the diagnostics |
| `LOG.md` | +351 | the full trail, every measurement |
| `MORNING-REPORT.md` | rewritten | this session's report |
| `notes/handoff.md` | rewritten | this file |

**No other tracked file was modified.** `sim.py`, `simvec.py`, `layout.py`,
`tiles.py`, `recipe.py`, `export.py`, `core.py` and every `recipes/*.txt` are
untouched. Verified: `python compose.py` self-test passes, and the non-hier
suite is green with alu1/ctrl_decode block counts identical to the previous
handoff's record.

New, untracked (gitignored), all hard-bounded:

- `scratch/export_bank.py` — exports a merge pkl to `.mcfunction`/`.schem`/`.html`.
  Fixed pickles in, files out; no compose, no sim, nothing that can hang.
- `scratch/export_bank_html.py` — same with a states pkl for the interactive page.
- `scratch/nonhier_suite.py` — bounded suite runner for the non-hier recipes
  (one killable child each, per-recipe cap), the evidence that the `lwire`
  fixes moved nobody else's geometry.
- `scratch/alu4bank*.pkl`, `alu4bankstates.pkl`, `alu4bandsBANK.pkl`,
  `alu4fresh.pkl`, `cpu4bandsBANK.pkl`, `cpu4bank.pkl`, `cpu4newctrl.pkl`,
  `alu4ctrl*.pkl`, `bankfail*.pkl`, `bank_trace*.txt` — this session's probes.
  Nothing in `scratch/` was deleted.

New build artifacts at the repo root: `build_alu4bank.{schem,mcfunction,html}`.

---

## What we should do next

1. **Paste `build.schem` into the real client.** It has never been tested in
   Minecraft, and nothing in this repo ever has. The 10 levers are the column
   at **x=3, z=3..93** (north-west of the machine); the build is 1,974 × 285,
   so paste somewhere with room. If it is wrong, the round-trip catches it —
   that is how the 2026-10-02 dust-on-dust defect was found, not the sim.
2. **Make `hier_bands` combination-aware (this is cpu4's whole problem).** The
   ladder keeps the first rung that makes a band green **standalone**, but
   correctness is a property of the band **combination** — `Y2` depends on the
   cross-band handoff. A fresh cpu4 climb picks a different combination and
   `SMOKE 1111111 MISMATCH ['Y2']` appears, identically with the bank off.
   The cheap version: merge, smoke, and on disagreement re-climb only the bands
   feeding the wrong output, then re-stitch (bands are cached, the stitch is
   ~9 min, so it is a loop over cached bands). Do **not** spend more redstone
   effort on cpu4's bank — it is already correct there.
3. **Fix `_streets` properly.** It is the midpoint of two band *start*
   offsets, so it sits inside the earlier band rather than in the reserved
   `_HIER_GAP`. It is load-bearing for green geometry, so it needs the A/B
   (`REDSTONE_INPUT_BANK` gives a habit for that) and a full re-verify, not a
   drive-by edit.
4. **Fingerprint the band caches** (`alu4bands.pkl`, `cpu4bands2.pkl`, and the
   new `*bandsBANK.pkl`). The engine fingerprint voids verify caches only; a
   stale band cache cost a full session on cpu4 and nearly one on alu4.
   Cheapest fix: store the same `__fp__` in the band pkl and refuse on
   mismatch. This session's alu4 result was checked by hand (all 6 bands
   byte-identical from scratch) — that check should not be manual.
5. **Decide on `scratch/` pruning.** It is now ~640 files. The six live tools
   are `hier_bands`, `hier_stitch`, `verify_par`, `collect_states`,
   `export_bank`, `nonhier_suite`. Most of the rest is evidence behind LOG.md.
6. True 3D tile stacking is still the last architectural goal, still scoped and
   unbuilt: ~140 `y==1` assumptions across `layout/compose/tiles/sim`, and
   `tiles.new_ctx` says "migrate the maps or don't start".
7. **Coordination**: if two agents are active, agree file ownership out loud
   before either starts. `simvec.py` is no longer declared off-limits (that
   note is stale — it was released when the SWAR engine was cut).

---

## Build notes (still true, they cost time)

- Band caches must be built with `REDSTONE_ASTAR_CAP` unset (6000 breaks them).
- Every probe must be hard-bounded; an unguarded script reaching a spawn path
  re-imports itself under spawn and becomes a fork bomb. `if __name__ ==
  "__main__"` everywhere, and `sim_verify`/`verify_par`/`hier_bands`/`hier_stitch`
  refuse to fan out from a daemon. Every tool added this session follows that.
- `scratch/mkref.py` extracts the engine from **git HEAD**, so re-freeze
  `ref_sim.py` *after* committing a physics change, and its header must import
  whatever constant the frozen copy uses (`TORCH_BACK`, today).
- `lwire` will not route a span over ~350 cells even on empty ground. That is
  why `_relay` and the street waypoints exist; a long run must be split.
- A repeater's stored facing string is `-travel`. `sim.py:835` negates the
  parsed facing on the way in and `_plant_repeaters` stores `-travel`, so the
  two agree. Any third implementation of the repeater rule must match that or
  it will read every booster backwards — that was bug 3 above.