# handoff — 2026-10-04 overnight session (band 0 → alu4 FULL GREEN 1024/1024)

Repo: `D:\redstone-mini`, branch `phase2-design`.
Session commits (engine + docs, all `git commit -- <paths>`):
`80e0d88` input-blame → `1be2186` stall guard → `ee61873` corridor blame +
pull-early → `f462f6f` hop-cond2 + diode-drop → `325eac7` full-green report.
Working tree clean apart from the GA agent's `scratch/rig_verify.py`
(modified, theirs) and the two pre-existing `build.mcfunction.bak` /
`build.schem.bak`, which nobody may delete or commit.

---

## ⚠ Read this first: the working tree is SHARED

A GA agent worked this tree concurrently all session (commits `c439751`,
`557f9c7`, `cec16ac`, RCON rig + cmc cross-check harness). **No conflicts:**
they own `scratch/evo_*`, `scratch/rig_*`, `scratch/compact.py`,
`memo.json`, RCON files; I owned `compose.py` + docs. Their
`scratch/evo_blocks.py` edit landed while I worked — left alone, they
committed it themselves.

**Rules (still in force):**
- **DO NOT DELETE FILES.** Not tracked, not untracked, not ones that look dead.
- **Another process may be editing any file here. `git status` is not evidence
  that a file is yours.** Use a copy/worktree to isolate, never `checkout --` /
  `stash push` on a path you did not write (see 2026-10-03 lesson in LOG.md).
- `git commit -- <paths>` only, `git status` first. Never `rm` / `git clean`
  anything you did not create. No checkout/stash of others' work.
- Rule 7: every test/script hard-bounded, killable children, `__main__`
  guards (spawn re-import = fork bomb). `Start-Process` detached launches
  proved flaky under load — foreground runs with timeouts worked.

---

## Goal

**Operator AFK instruction:** work fully autonomously until DONE, where
DONE = "whatever ur doing" = the band-0 campaign (alu4 band 0 was the only
red band blocking a full alu4 merge; Y0 lives in b0). No questions, no
approval, best guess + LOG note, loop until DONE, switch approach after
3 failed tries, verify after every change, commit frequently + LOG.md,
MORNING-REPORT.md when done. **Reached: DONE.**

**Standing goal (unchanged):** every recipe in `recipes/` generates, verifies
and exports. `alu4` is now done end-to-end (was: all but b0). `cpu4` untouched
this session. True 3D tile stacking still scoped, unbuilt.

---

## Current state

| build | verdict | evidence |
|---|---|---|
| **alu4** (10 inputs, 1024 vectors) | **GREEN 1024/1024, Y0 included** | `scratch/alu4merge_g.pkl`, `VERIFY OK: 1024 vectors, 16 chunks green`, 71,560 blocks, size (2198, 353), 10 levers |
| bands (fresh, engine `f462f6f`) | **6/6 green** | b0 13304 (`3,inputs_first,short`+long) · b1 7518 · b2 6957 · b3 571 · b4 2414 · b5 4878 |
| Y2 stitch coupling | **fixed, re-derived** | `y2trace` → 3 glass swaps (868,2,221 + 868,2,224 + 1170,2,218); old 5-pillar coords stale (layout reshuffled); smoke 4/4 then 1024/1024 |
| alu1 (hier gate) | GREEN 32/32 | `hier_verify.py recipes/alu1.txt` VERIFY OK |
| alu1 flat (nonhier suite) | **RED by design since `124d179`** | 22-gate banded recipe, `22 < _TERR_MIN_GATES=40`; suite `EXPECT 13300` is a stale pre-promotion number |
| ctrl_decode / micro1 / examples | GREEN, bit-identical | 5499 / 2925 / 144 / 322 / 224 / 214 |
| suites | GREEN | `python compose.py` self-test, `compose_check.py` |

**Exported and installed:**

| file | size | notes |
|---|---|---|
| `build_alu4full.schem` | 20,174 B | hash-verified copy in `…\worldedit\schematics\` — **paste this one** |
| `build_alu4full.mcfunction` | 4,723,327 B | |
| `build_alu4full.html` | 7,890,574 B | |

`build_alu4.*` / `build_alu4bank.*` are **STALE** (pre-b0, unverified under the
new engine). `build_alu1.schem` still in schematics from its session. **No
build has ever been pasted into Minecraft — still untested.**

Reproduce alu4 end-to-end now:

    python scratch/hier_bands.py recipes/alu4.txt scratch/alu4bands 90
    python scratch/hier_stitch.py scratch/alu4bands.pkl recipes/alu4.txt 200   # with REDSTONE_HIERDUMP2=scratch/alu4merge.pkl
    python scratch/ins_target.py scratch/alu4merge.pkl scratch/alu4merge_g.pkl 868,2,221 868,2,224 1170,2,218
    python scratch/verify_par.py scratch/alu4merge_g.pkl recipes/alu4.txt 16 400 2   # ×8 rounds, staged
    python scratch/export_bank.py scratch/alu4merge_g.pkl alu4full

---

## What changed (compose.py only, all green-neutral + gated)

1. **Corridor blame** (`ee61873`). Pocket blame sees endpoints only: b0's
   n1_0 blamed OP1 while B0 owned 207 near-corridor cells (5 parallel rivers
   fencing the z=19 slot). `lwire` tags `first_err` with cands[0]'s corridor;
   `_blame` counts foreign y=1 wires within 2 of it; a fence (≥10 cells, beats
   pocket count) wins. Fired in the wild (`n1_0 sealed by B0` on 3 spreads).
2. **Gate-pull-early** (`ee61873`). `_order` pulls gates-that-precede-inputs
   before the lanes (stable partition of `out`, closure under gate preds) and
   drops auto-satisfied input preds in inputs_first. A thin leg can't cross a
   fat routed fence but the fence's later march hops one thin wire fine.
3. **Hop cond2 sees committed supports** (`f462f6f`). t00's short-hop dust
   coupled n0_0's committed deck, but `_hop_free` cond2 held only the hop's
   own supports (layout's `bridge_free` takes pre-existing `cond`; the
   adaption dropped it). `_cs()` also consults `sup`/`ctx.sup`. Tile cobble
   stays invisible (under-veto = today, safe).
4. **Post-hoc diode-drop** (`f462f6f`). SHORT3D had been masking pre-existing
   input-mesh repeater loops (checker order). Compose tail catches
   `repeater loop` from checks/finish, bisects router-planted diodes with a
   `_loop_rep` mirror, drops the single closer (cap 9); the sim gate judges
   any decay. Fired 1–2× per green rung.
5. **Stall guard** (`1be2186`). A blame pair already in `precede` replays the
   death identically (same order, field same-or-worse) — raise instead of
   grinding 24 restarts. Fired on b0 rung 1 (saved ~22 restarts).
6. **Input-vs-input blame** (`80e0d88`). `_blame`/`_order` handle input faileds
   and owners (lane-vs-lane seals were invisible, zero restarts ever fired).

Verified after every change: `compose.py` self-check, `compose_check.py`
bit-identical, nonhier suite 6/6 identical, `hier_verify alu1` 32/32 —
before each commit. Precedent kept: restarts/blame/vetoes fire only
post-death, so green geometry never moves (empty precede ⇒ identical order).

### Diagnostics added (scratch/, gitignored, hard-bounded, all keepable)

- `reachmap.py` — per-corridor-cell blocker census (tile vs lane-wire by
  owner vs ring/repeater/guard) + sealers-within-2 + routed bboxes, first 2 +
  last 3 deaths. Found the B0 fence (207) and the 90%-free corridor.
- `corridor_map.py` — ASCII map of the fatal corridor vs field. Showed the
  z=19 slot between B0 rivers and the 4 pinch points.
- `shortdiag.py` — SHORT3D *and* OPEN forensics (wraps both checkers),
  9×9×y1–3 neighborhood with owners. Showed the lid orphaning t00's hop-chain.
- `stampwho.py` — who stamps elevated dust (wraps `tiles.stamp_wire` +
  tracebacks + shift correction). Proved the killer dust came from the 3D
  flight path, not hops.
- `loopdiag.py` — repeater-loop ring flood + diode list + map. Showed B0's
  670-cell mesh with ~90 diodes on 5 parallel runs.

---

## What failed, and why (so it is not re-derived)

| try | result |
|---|---|
| Lever-at-load fallback (2nd lever at sealed port) | Fired on b0 OP1 (3,12), exposed the next identical wall at (8,12)→(111,29). Placement wall, not delivery. **Reverted same session.** |
| Flight-time slope veto (reject coupling 3D flights) | Never fired in any measured run (victim cells stamp after the flight); lid-half not airtight vs upper-pass lids. **Removed.** |
| y=2 span-refusal | Never fired (killer dust was hop dust, not spans); junction-blind. **Removed.** |
| Lower-role lids (lid over own cell under foreign flight) | Dropped the lid, then the lid **orphaned t00's hop-chain** (chain needs the same slopes) → OPEN death. Lids protect flights but kill chains over decks. **Removed.** |
| 10+ pre-session b0 approaches | sidestep/astar, reorder, seeds, NOFLAT, maze, TERR, IN-order, arg-swap, pitch, funnel, blanket-insulate — all confirmed dead again by the reachability map (double rivers 2 apart are unhoppable, tile zone kills tall-hop feet). |
| `gates_first` rungs on b0 | Input-phase repeater loops (multi-diode/tile) the drop can't always clear. inputs_first covers; no campaign need. |
| One `4,inputs_first,long` attempt | Loop dropped, then **SIM MISMATCH x1** — the drop cost decay; sim gate correctly rejected. Other rungs green. Proof the drop-then-sim-gate design is sound. |
| Old Y2 5-pillar coords | Stale (only 1/5 present post-reshuffle). Re-derived, don't reuse. |

---

## Files I touched

Tracked (`git log --oneline`: `80e0d88`, `1be2186`, `ee61873`, `f462f6f`, `325eac7`):

| file | what |
|---|---|
| `compose.py` | the 6 engine changes above (+76/+72 net across the two feature commits) |
| `LOG.md` | full trail, every measurement, every removal rationale |
| `MORNING-REPORT.md` | rewritten: 1024/1024 report, paste instructions |
| `notes/handoff.md` | this file |

**No other tracked file was modified.** `sim.py`, `simvec.py`, `layout.py`,
`tiles.py`, `recipe.py`, `export.py` (see 2026-10-03 lesson — untouched),
`core.py`, every `recipes/*.txt` are byte-identical.

New, untracked (gitignored by design): the 5 probes + `g_*.log` evidence,
`scratch/alu4bands.pkl`, `scratch/alu4merge.pkl`, `scratch/alu4merge_g.pkl`,
`build_alu4full.{schem,mcfunction,html}`. Nothing in `scratch/` was deleted.

---

## What we should do next

1. **Paste `build_alu4full.schem` into the real client.** Never tested in
   Minecraft; the round-trip is how the 2026-10-02 dust-on-dust defect was
   found, not the sim. 10 levers, column x=3, z=3..93; build is 2198×353 —
   needs room.
2. **Decide stale-artifact policy.** `build_alu4.*`, `build_alu4bank.*`,
   `build.mcfunction.bak`/`build.schem.bak` predate verification. I kept
   everything (no-delete rule); say the word and the stale alu4 files go.
3. **cpu4 is untouched.** If it climbs next, the combination-awareness note
   from 2026-10-03 still applies (ladder keeps first standalone-green rung;
   correctness is per-combination). The corridor-blame + diode-drop machinery
   is combination-friendly (both fired on band 3 unprompted), so cpu4 may just
   work — or produce new walls with the same probe kit ready.
4. **blame pick-rule, if it ever matters.** Corridor wins only when it beats
   the pocket count; measured pocket counts inflate with flooding (OP1:198 vs
   B0 fence:125 on one death). A fixed ≥50 fence threshold would flip that
   death to `(n1_0,B0)` first try — untested, parked; current rule converges
   anyway (≤2 restarts).
5. **`gates_first` b0 + multi-diode loops**, only if inputs_first ever stops
   covering. Bisect finds single closers; tile-geometry or multi-diode loops
   go loud. Wholesale-drop fallback deliberately not built (decay risk).
6. **Coordination**: GA agent active (RCON rig, evo). Ownership held all
   session (they: evo/rig/RCON/memo; me: compose/docs). Re-agree if scopes
   change. `simvec.py` off-limits note is stale (released when SWAR was cut).

---

## Build notes (still true, they cost time)

- Band caches must be built with `REDSTONE_ASTAR_CAP` unset (6000 breaks them).
- Every probe hard-bounded; `__main__` guards everywhere (spawn re-import =
  fork bomb). `hier_bands`/`hier_stitch`/`verify_par` refuse daemon fan-out.
- `scratch/mkref.py` extracts the engine from **git HEAD** — re-freeze
  `ref_sim.py` *after* committing a physics change.
- `lwire` will not route a span over ~350 cells even on empty ground; long
  runs must be split (`_relay`/streets).
- Repeater stored facing is `-travel` (`sim.py:835` negates on parse,
  `_plant_repeaters` stores `-travel`). Any third repeater-rule
  implementation must match.
- `check_shorts` runs before `finish_assembly`: SHORT3D preempts loop
  detection, so loops hide behind shorts. Fix shorts first, then re-read.
- Session record, for reference: corridor blame solved n1_0 → SHORT3D wall
  (hop cond2 fixed the stamper, veto/span never engaged) → lids orphaned
  chains (removed) → loops exposed (diode-drop) → one SIM MISMATCH on an
  aggressive drop (sim gate held) → Y2 re-derivation → 1024/1024.
