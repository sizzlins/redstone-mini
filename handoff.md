# Handoff — redstone-mini routing session (2026-09-25)

## Goal (evolved)
1. Fix the 4-gate latch that never routed → DONE, verified.
2. Full working CPU (`cpu4.txt`, 126 gates) → NOT DONE (ceiling, see failures).
3. Along the way: ALU arithmetic circuit (`alu1.txt`) → logic proven, not routed.
4. Standardize builds (tiles → buses → clock) → 3 spec `.md` + Phase 1 implementation plan written; execution choice pending.

## Current state (all pushed to `origin/master`)
- **Green, verified:** 4-gate latch (6/6 seeds + hold sequence), micro1 (full
  `layout_retry(verify=True)`, all 16 vectors, 1434 blocks), suite
  (`recipe.py`, `serve.py --check`, `redstone_mini.py` demo at 114 blocks,
  `sim.py` incl. crossover/comparator, examples, `latch_sr.txt`).
- **`build.html` holds the verified micro1 build** (re-export with
  `python -u scratch/exportmicro.py`; note `redstone_mini.py` overwrites it
  with the demo).
- **Red (documented ceiling):** `--alu8`/adder8, `alu4` (flat and banded),
  `cpu4`, `ctrl_decode`. All fail routing with dense-column seals.
- alu1 logic proven 32/32 via `eval_net`; not routed.

## What changed (commits, oldest first)
- `7247b31` 4-gate latch routes: per-column auto-band + topo-sort,
  frontier rip-up (records blocking cells in A\*), stub-tail repeater
  cover, shortest-of-3-margins.
- `f757390` phase-2 comment matches longest-first order.
- `ab52aed` zero-wire input fanout: one lever per load, redundant tasks
  skipped, first-OR lever rule.
- `b40b2d5` BAND sections in recipe language; input-relay deletion;
  banded per-band relay + driver replicas; placement guards
  (`spot_free`, row-march, W-cap fix); LATCH loop-break fix (was silently
  dropping gates!); banded XOR stays a tile.
- `fb7f625` torch-guard routing (no hugging torch cells/blocks mid-run),
  negotiated congestion lite (+5 on ripped cells), lever-island checker
  seeding, NOT/NOR port-stub stamping.
- `7b60cea` `alu1.txt` (1-bit AND/OR/ADD/XOR slice), `micro1.txt` tracked.
- `59a00ac` viewer gray no-data for unverified latch-hold combos.
- `61e0f91` banded OR uses junctions (delete NOR+NOT doubling, net −15).
- `b58da06` three standardization specs (`docs/phase{1,2,3}-*.md`).
- `79eabac` Phase 1 implementation plan (`docs/plans/2026-09-25-phase1-tiles.md`).

## What failed (and was reverted or shelved)
- Rip-up ping-pong (S↔Q, T0↔nOP…): deterministic blame cycles; fails-cap
  terminates but never converges on dense knots.
- Bend penalty, congestion halo, OR-goal priority, OR b-cell spacing,
  shortest-first ordering: each unblocked one pair and starved the next.
  All reverted (kept only what suite-verified: congestion-lite + guard).
- Depth bands / depth grid: broke 4-gate (shared-band crowding,
  spillover cascades); reverted to index bands + bandrows.
- Column pitch 24→12: breaks 15-wide LATCH adjacency (proven by
  instrumented rejection trace); reverted same session.
- Subdividing bands (per-bit → sub → sub-sub): Zeno effect, each split
  moved the seal; stopped.
- `--alu8` on master: no verdict in 15 min (never proven green anywhere).

## Files touched (tracked)
- `layout.py` (placer/router), `recipe.py` (parser/expand/minimize),
  `core.py` (`TORCH_BACK`), `export.py` (viewer no-data state).
- New recipes: `alu1.txt`, `micro1.txt`.
- Docs: `docs/phase1-standard-tiles.md`, `docs/phase2-bus-routing.md`,
  `docs/phase3-clock-discipline.md`,
  `docs/plans/2026-09-25-phase1-tiles.md`.
- Scratch (gitignored, probes/runners/annotated copies):
  `scratch/{probe,runalu,runalu1,rumicro,exportmicro,proofalu,checkhtml}.py`,
  `scratch/alu4_banded.txt`, build artifacts (`build.html/.mcfunction/.schem`).

## Environment gotchas (learned the hard way)
- PowerShell 7 wrapper: no `grep`/`head`/`tail`, no `/dev/null`, no `&&`
  with `$env:` assignments; quote inline `python -c` via files instead.
- `Start-Process` background launches glitch the wrapper and pop visible
  consoles: run foreground with `python -u` + heartbeat prints + watchdog
  (`os._exit` on timeout). Nothing ever waits for stdin.
- `__pycache__` goes stale when edit+run land in the same mtime second:
  delete it when results contradict the code on disk.
- `layout_retry(r, verify=True, tries=0|grows=0)` raises `TypeError`
  (`raise last` with `last=None`); minimum tries=1, grows=1.
- `sim_verify` SKIPS latch-hold vectors (S=R=0, undefined power-on) and
  never compares latch outputs — direct `_run_vec` + `eval_net` checks
  are required for latch circuits.

## What next (in order)
1. **Execute Phase 1 plan** (`docs/plans/2026-09-25-phase1-tiles.md`):
   lamp order (1 line), port-grid asserts, suite green. Awaiting execution
   choice: subagent-driven vs inline.
2. **Phases 2–3** need their own brainstorm→plan cycles when Phase 1 lands.
3. **Dense datapaths** (adder8/alu4/cpu4) need, ranked: congestion schedule
   (static +5 now), lane-assigned router, or bridge layers (sim physics +
   scaffolding already exist). Do NOT add more maze heuristics — ~20 were
   tried, all migrated failures.
4. **CPU path** if revived: `BAND` syntax + bit-slice annotation exist
   (`scratch/alu4_banded.txt` as template); program counter → instruction
   ROM → RAM per the researched architecture (accumulator/RISC, Harvard,
   torch-NOR cores already match community practice).

## 2026-09-25 — Phase 1 executed (branch `phase1-tiles`, PR to master)

Two commits on `phase1-tiles` (pushed):
- `2f254e6` lamp east-first (1 line in `layout.py`, char-locked `((5,9),'Q')`).
- `fc56bd9` lamp-anchored port-grid asserts in `layout.py.__main__`
  (`python layout.py` → `ports ok`).

Deviations from `docs/plans/2026-09-25-phase1-tiles.md` (plan bugs, root-caused):
- Plan recipe `OUT y,z,w` matched no gate (`KeyError: 'y'`) → isolated
  single-tile builds (`OUT n`, `OUT t`).
- Easternmost-cell anchor wrong twice: shrink-wrap (`layout.py:875-889`)
  translates all coords, and routed nets run east past the tile → relative
  offsets off the lamp (NOT out −2/port −5; AND out −2, A −10/−1, B −10/+2).
- 4-gate recipe is micro1's gated-D head (`micro1.txt:3-6`), not in the
  phase-1 doc → `scratch/check4gate.py` (gitignored): `4-gate bad: 0 /6`
  + `sequence ok`.

Verified green: `recipe.py`, `serve.py --check`, `sim.py`, `layout.py`,
demo 114 blocks, micro1 1434 blocks re-exported to `build.html`.

Next: Phase 2 (bus routing) brainstorm → spec → plan.
