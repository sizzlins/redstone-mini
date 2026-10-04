# MORNING REPORT — 2026-10-04/05 (band 0 DONE, then the speed shift)

Repo `D:\redstone-mini`, branch `phase2-design`. Full detail in
`notes/handoff-opt agent.md` (mine, current) and `LOG.md`.

## Builds that work now

| build | verdict | evidence |
|---|---|---|
| **alu4** (10 inputs, 1024 vectors) | **GREEN 1024/1024** | `VERIFY OK: 1024 vectors, 16 chunks green`, 71,560 blocks (2198×353), 10 levers. Bands 6/6: b0 13304 · b1 7518 · b2 6957 · b3 571 · b4 2414 · b5 4878 |
| **alu1 hier** | **GREEN 32/32** | band 0 pinned via `recipes/alu1.skip` (10124) · band 1 494 · MERGE 15104 |
| examples / latch / xor / micro1 / ctrl_decode | GREEN, bit-identical | 144 / 322 / 224 / 214 / 2925 / 5499 |
| alu1 **flat** (nonhier suite) | RED **by design** since `124d179` | 22-gate banded recipe, `22 < _TERR_MIN_GATES=40`; the suite's `EXPECT 13300` is a stale number, not a failure |
| cpu4 | RED by inheritance (pre-dates tonight) | Y2 cross-band coupling class |

Paste-ready: **`build_alu4full.schem`** (hash-verified copy already in
`…/worldedit/schematics/`), plus `.mcfunction` / `.html` in the repo root
(gitignored). `build_alu4.*` and `build_alu4bank.*` are **stale** — do not
paste those.

## Still failing, with the log

1. **No build has ever been pasted into Minecraft.** sim + cmc (second engine)
   are the verification pair; the RCON rig is not an oracle (GA's finding).
   A real paste is the only missing proof.
2. **cpu4** — not attempted tonight.
3. **`gates_first` band-0 rungs** — input-phase repeater loops the diode-drop
   can't clear (multi-diode/tile geometry). `inputs_first` covers it.

## What changed tonight (measured, all gates green)

- **Band 0 unblocked** → first-ever full alu4: corridor blame (pocket blame
  ordered around the wrong net while B0 owned 207 near-corridor cells),
  gate-pull-early, hop-guard seeing committed supports, post-hoc diode-drop,
  stall guard.
- **verify_par ran the slow engine**: `_vec_child` called `sim._run_vec`
  everywhere → **104s → 47s per 64-vector chunk (2.2x)**.
- **`_run_vec` delegates to the table engine** when eligible →
  **1.311s → 0.678s per vector (1.93x)** for every direct caller (incl. the
  GA agent's evals).
- **Router**: `ok()` tuple hoist, `_support` memo, stale-pop guard, dead code
  deleted — bit-identical, band 1 4.4s → 4.2s.
- **Two gate bugs fixed** (both made "green" a lie): `hier_verify` swallowed
  stage exit codes (a RED stitch then "VERIFIED" a stale merge), and
  `diff_engine`'s frozen reference was stale + missing helpers (`mkref` now
  freezes `HEAD:sim.py` verbatim).
- **alu1 hier re-greened** with a durable pin (`recipes/alu1.skip`), because
  the GA agent's comparator-front physics fix re-greened band 0 at a spread
  whose compact shape walled the stitch.

## What I need from you

1. Paste `build_alu4full.schem` in-game (never tested).
2. Decide whether the stale `build_alu4.*` / `build_alu4bank.*` /
   `build.*.bak` files get deleted (I never delete).
3. `README.md` is materially wrong (timing, `--alu8`-only, no hier/alu4 story)
   — left for the next optimization agent.
4. Unstaged in the tree: `notes/handoff.md` deleted (your reorganization),
   `build.*.bak`. The GA agent's `scratch/` files are theirs.
