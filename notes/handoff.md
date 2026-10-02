# handoff — 2026-10-02 night session (alu4 green, target block, over-engineering audit)

Repo: `D:\redstone-mini`, branch `phase2-design`.
Last commit: `7af4caa`. Working tree clean apart from the two pre-existing
`build.mcfunction.bak` / `build.schem.bak`, which nobody may delete or commit.

---

## ⚠ Read this first: the working tree is SHARED

Another agent has been editing this repo **during** this session. Concretely:
`export.py` gained 139-169 uncommitted lines between two of my commands.

**What I got wrong, so the next session doesn't repeat it:** I ran
`git stash push -- export.py` and then `git checkout -- export.py` to isolate
that file while running my own verification. Both were meant to be temporary and
I did not put it back, so another agent's bug fix sat in a stash while their
tree showed HEAD. Nothing was lost, but it is exactly the "you reverted a fix"
outcome. Recorded in LOG.md under "export.py: a concurrent agent's fix".

**Rules:**
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

**Reached this session:** the three glass/slab holds the user rejected, a full
Target-block implementation, `alu4` green end to end and exported, and a
repo-wide over-engineering audit applied.

**Still the standing goal:** every recipe in `recipes/` generates, verifies and
exports. `alu4` and `cpu4` are done; the rest are green. The remaining
*architectural* goal is true 3D tile stacking (scoped, not built — see Next).

---

## Current state

| build | verdict | evidence |
|---|---|---|
| **alu4** (10 inputs, 1024 vectors) | **GREEN** | `scratch/alu4merge.pkl` + `verify.json` 16/16 green, fp `363f613324b5` |
| cpu4 (7 inputs, 128 vectors) | GREEN | `scratch/cpu4merge3.pkl` 16/16 green, fp `47fb2a6e0efb` |
| alu1 / ctrl_decode | GREEN | 13,300 and 5,499 blocks, `sim_verify` clean |
| example_and / 2gates / latch_sr / xor | GREEN | `scratch/compose_check.py` |
| suites | GREEN | `sim.py`, `layout.py`, `diff_engine` ALL IDENTICAL |

Canonical caches (all current-engine): `alu4bands.pkl`, `alu4merge.pkl` (+verify
json), `alu4_build.pkl` (diff_engine fixture), `cpu4bands2.pkl`,
`cpu4merge3.pkl`. Pre-flip dead geometry kept for forensics as
`alu4*.preflip.pkl`.

**Exported for the user** (verified by reading the written file back):
- `…\FreesmLauncher\instances\26.3\minecraft\config\worldedit\schematics\build.schem`
  — 35,082 blocks; their previous file preserved as `build.schem.bak-20261002-210028`.
- `D:\redstone-mini\build_alu4.mcfunction` (2.28 MB)
- `D:\redstone-mini\build_alu4.html` (4.0 MB, packed states, interactive)

Reproduce alu4 from scratch (~10 min cold, ~25 min with a cold band ladder):

    python scratch/hier_bands.py scratch/cand_alu4hier.txt scratch/alu4bandsNEW 150
    python scratch/hier_stitch.py scratch/alu4bandsNEW.pkl scratch/cand_alu4hier.txt 480 scratch/alu4mergeNEW.pkl
    python scratch/verify_par.py scratch/alu4mergeNEW.pkl scratch/cand_alu4hier.txt 16 2400 16 16

---

## What changed (16 commits, `ed4c2a7..7af4caa`)

**Glass/slab, the three rejected holds** — `bc446af`, `ed4c2a7`
- simvec stopped declining: slab is a new side code 8 (powerable like cobble,
  transparent unlike it); tri-engine probe green.
- The search reuses hand glass/slab as supports and refuses to route *into*
  them; `finish_assembly` now rejects duplicate cells.
- Auto-stamping glass measured **zero** fires on cpu4 (0 of 4709 off-ground
  pillars qualify) — deliberately not built; documented instead.
- Slab halves checked against the wiki: full-cell is correct at integer
  granularity.

**Target block** — `fd0aaeb`, `2826ed6`, `baebddf`, `37b164c`
- Opaque conductive cube; timed projectile emission at the **exact** 1..15 hit
  level (4 redstone ticks ordinary, 10 for arrow/trident = the wiki's 8/20 game
  ticks); dust redirection wired into both the sim's block-power term and
  `wire_bid`. Stimulus is an argument (`target_hits=` / third `sim_pulse`
  schedule item), never a block state — a bid with `power=5` is rejected.

**alu4: two root-cause bugs** — `f825af0`, `8c9c510`, `629f262`
1. A booster could push power into a tile torch that fed its own net back — a
   6-node ring that latched the band-3 handoff (15 of 24 vectors hunting).
   `_closes_loop`/`_loop_rep`/`_ends_ok` cannot see it: they reason about dust,
   and this ring leaves the dust *through a torch*. Fixed in `compose._ends_ok`,
   layout's booster loop, and loudly in `finish_assembly`.
2. **Dust stacked on dust** — 24 cells held cobblestone *and* wire with a dust
   cell above resting on what became a wire. The sim read both blocks and
   called it supported; vanilla refuses dust on dust, so all 24 would have
   popped on paste while every verdict stayed green. Causes: the duplicate
   guard ran *before* wires were appended (blind to the whole wire class), and
   compose's bridge/hop sites stamped supports without an occupancy check.
   Found by the export round-trip, not by the sim.

**Over-engineering audit** — `68dd094`, `a197c86`, `17adc59`, `d70ed89`, `5077f6d`
- Cut the bit-parallel SWAR engine (simvec 1456 → 927 lines): measured 5.6%
  *slower* than the table engine on alu4, default-off, enabled by nobody, and
  unable to terminate on a hunting vector.
- Cut `reuse=`/`ig=` params no caller ever passed, `_ig3`, and 70 lines of
  `REDSTONE_XCHECK` reference predicates.
- Consolidated three inline torch-attach dicts onto `core.TORCH_BACK`.
- Dropped `lampat` (collected, never read) — parse tuple is now 14 fields.
- Net **-591 lines**, zero behaviour change, alu1 geometry identical.

**Concurrent agent's fix, adopted** — `9be02f8`, `7af4caa`
- `export.py`: preview states packed as base64 nibble/bit rows indexed by
  instance number (a 1024-vector preview was ~1.6GB of raw JSON). Their code was
  correct; the red was sim.py's fixture missing the comparator field.

---

## What failed, and why it was wrong

- **alu4's "64/64 green" was a ghost.** The verify json predated the
  diode-facing flip (`29fc565`); re-verified under current physics that merge is
  RED on all 16 chunks (`Y2`/`Y3` with `B2`/`B3` set). Band/merge caches are
  build *inputs* and nothing enforces rebuilding them — only verify caches are
  fingerprinted.
- **Adding the dust-on-dust guard alone broke the build** (bands 0 and 1 went
  NO GREEN RUNG). Measuring first is what made the second cause findable: the
  guard proved the class was systematic, which pointed at the router.
- **The stuck `dense3.log` process** (PID 16976) burned a core for hours with no
  output after 4 sealed restarts. Killed. `hier_stitch` and `hier_bands` are
  hard-bounded; ad-hoc loops are not.
- **`_booster_out_cell` facing trap.** layout's booster helpers read `front` as
  `cell + _VEC[facing]` while sim reads `cell - _VEC[facing]`; measured 2426 of
  2426 repeaters disagree. Harmless only because those helpers are
  direction-agnostic. Any new direction-aware check must use sim's rule.
- **My error:** stashing/checking out another agent's `export.py`. See the
  warning at the top.

---

## Files I touched

Tracked, this session (`git diff --stat ed4c2a7..HEAD`):

| file | delta | what |
|---|---|---|
| `sim.py` | +262/-… | target physics + `_target_shots`, dust-on-dust support gate, `TORCH_BACK`, `lampat` out, fixture field |
| `layout.py` | +302/-… | `_torch_hosts`/`_inverter_ring_at`/`_booster_inverter_ring`, post-assembly one-cell check, dust-on-dust guard, audit cuts |
| `compose.py` | +41 | `_ends_ok` ring filter, `_supports_free` on bridge/hop supports |
| `simvec.py` | -675/+… | slab side code, SWAR engine removed, shard tuple slimmed |
| `export.py` | +176/-… | target colour/props/mount; **the other agent's packed-state preview** |
| `scratch/ref_sim.py`, `scratch/mkref.py` | re-frozen | reference engine + generator header |
| `LOG.md`, `MORNING-REPORT.md`, `notes/handoff.md` | docs | trail, report, this file |

Untracked (gitignored) but load-bearing: `scratch/` holds 299 probe files /
28,036 lines — the alu4 and cpu4 pipelines (`hier_bands`, `hier_stitch`,
`verify_par`, `mkref`, `diff_engine`, `dense_status`) plus every forensic probe
cited in LOG.md. **Do not prune it casually.**

---

## What we should do next

1. **Paste `build.schem` into the real client.** It is the first build exported
   for actual use and the 24 popping cells were caught by a file round-trip, not
   by the game. Nothing in this repo has ever been tested in Minecraft.
2. **Fingerprint the band caches** (`alu4bands.pkl`, `cpu4bands2.pkl`). The
   engine fingerprint voids verify caches only; a stale band cache cost a full
   session on cpu4 and nearly cost one on alu4. Cheapest fix: store the same
   `__fp__` in the band pkl and refuse on mismatch.
3. **True 3D tile stacking** — the last architectural goal. Physics is proven;
   the compiler migration is ~140 `y==1` assumptions across
   `layout/compose/tiles/sim`. `tiles.new_ctx` says "migrate the maps or don't
   start": key `solid`/`rings`/`pos` by level, or give each deck its own 2D
   namespace. Do not thread a `y0` through the placers alone.
4. **Decide on `scratch/` pruning** — ~290 of the 299 files are dead, but they
   are also the evidence behind LOG.md's forensics. Keep the six live tools.
5. **Coordination**: if two agents are active, agree file ownership out loud
   before either starts. `simvec.py` was previously declared off-limits to me;
   that is now stale (I own it again after the SWAR cut).

## Build notes (still true, they cost time)

- Band caches must be built with `REDSTONE_ASTAR_CAP` unset (6000 breaks them).
- Every probe must be hard-bounded; an unguarded script reaching a spawn path
  re-imports itself under spawn and becomes a fork bomb. `if __name__ == "__main__"`
  everywhere, and `sim_verify`/`verify_par` refuse to fan out from a daemon.
- `scratch/mkref.py` extracts the engine from **git HEAD**, so re-freeze
  `ref_sim.py` *after* committing a physics change, and its header must import
  whatever constant the frozen copy uses (`TORCH_BACK`, today).