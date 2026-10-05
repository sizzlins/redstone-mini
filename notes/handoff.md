# handoff (2026-10-05 — send this to the next session)

Single entry point. Detail lives in `notes/handoff-opt2 agent.md` (this
session), `notes/handoff-opt agent.md` (previous speed session),
`MORNING-REPORT.md` (repo root, operator-facing), and the repo-root `LOG.md`
(append-only trace). Branch `phase2-design`, shared with a co-tenant agent —
see "shared tree" at the end.

## Goal

Operator's standing loop, unchanged: pick a file or function, think of an
optimization no matter how crazy, implement it, verify it, repeat. Do not stop.
Standing project goal: every recipe in `recipes/` generates, verifies,
exports. `alu4` done, `alu1` hier done, `cpu4` untouched (not this lane).

## Current state (all re-verified cold; commands under "gates" below)

| build | verdict |
|---|---|
| **alu4** (10 inputs, 71,560 blocks) | **GREEN 1024/1024**, cold 35.7s (was 108.7s) |
| **alu1 hier** | **GREEN 32/32**, ~39s |
| examples / latch / xor / micro1 / ctrl_decode | GREEN, bit-identical (144/322/224/214/2925/5499) |
| alu1 flat | RED **by design** (22-gate recipe, `_TERR_MIN_GATES=40`) |
| cpu4 | RED by inheritance (Y2 coupling; untouched) |
| `hier_verify alu4` end-to-end | GREEN, exit 0 (fixed by co-tenant `4d98d4c`; verified 173.7s) |

Engine ~2.8x per vector (interleaved same-process). Tables/worker 112.5→38.1 MB.
`diff_engine` ALL IDENTICAL; `verify2` vs cmc PASS 0/204224 on alu1.
Paste-ready: `build_alu4full.schem`. Nothing ever pasted. `build_alu4*` stale.

## What changed

`simvec.py` table engine, nine shipped items: int-indexed tables + bytearray
state (1.62x, the big one) · Morton ids (1–7%) · bytearray coalescing (1.05x) ·
sign-encoded ring items (1.05x) · exact wake map (1.11x, 55% of the walk dead) ·
boolean edges wake on crossing (~1.06x, halved solid evals) · `verify_par`
grouped chunks (~1–5%) · `REDSTONE_ASTAR_MARGIN` gate, default 64 unchanged ·
dropped `cid` from hot tables (40.6→38.1 MB). Plus `README.md` rewritten (the old
one documented a `--alu8` flag that does not exist).

New instruments in `scratch/` (all force-added; each docstring says its use):
`tbl_diff.py` (the A/B gate, with fault injection + reference selection),
`tbl_equiv.py`, `wake_need/miss/split.py`, `tbl_probe/sizes.py`, `tickdiff.py`,
`evlog.py`, `build/gc_probe.py`, `dump_cell.py`, and `simvec_old/geo/prev.py`
as A/B references.

Found and reported (not caused): **alu4 disagrees with cmc on 2286 cells**
(x 1082–1095, decay ladders our sim reads 12–15 vs cmc 0). Proven pre-existing
(untouched authority engine, identical numbers to the digit). Other agent
narrowed it to dust-connectivity derivation. Both engines still call the build
green — sim-overfit class, paste test matters more.

## What failed (measured, reverted, do not re-derive)

GC hypothesis (1.00x) · `if v:` guards (~2%, noise) · stall amortisation
(1.00x) · single-read handlers (1.00x) · closure helpers (~1.01x) · **argmax
skip (0.2% — fully implemented, verified IDENTICAL, reverted; design in LOG)**
· worker 14 vs 16 (tie at best-of-5) · astar default change (margin 16 loses
band 0; 32/48 reproduce exactly) · bit-parallel (blocked: agrees on lamps,
disagrees on settle ticks; 68dd094 precedent).

Three of my own numbers were retracted in LOG (tracemalloc-inflated build time,
single-sample 1.33x, easy-vector 1.62x). **Sequential A/B is biased low up to
40% here (thermal throttling; null on identical code reads 0.61x–0.96x), so the
micro-opt loop is suspended until the null reads 1.00x.** Shipped wins were
measured against the bias and are conservative.

## Files touched

`simvec.py`, `compose.py` (one env line), `scratch/verify_par.py`,
`README.md`, `LOG.md`, `MORNING-REPORT.md`, `notes/handoff-opt2 agent.md`,
`notes/handoff.md` (this). New tracked tools listed above. Never touched:
`evolve.py`, `compact.py`, `evo_*`, `enum_*`, `memo.json`, `rig_verify.py`,
`sweep*`, `mkref.py`, `ref*`, `verify2.py`, `diffwhy/simwhy.py`, `compdiff.py`,
`notes/to-opt-agent.md`, `notes/handoff-ga- agent.md`, `recipes/alu1.skip`,
`recipes/alu4.ins_target`. Left alone: `notes/handoff.md` was already deleted
(operator reorg) before this file restored the path; `build.*.bak` (never
delete); 400+ MB of pre-existing `scratch/*.pkl` (not mine).

## What next (priority order)

1. **Argmax-gated level edges** — fully specified in LOG with the exact skip
   rule and why both conditions are required. Proven correct, 0.2% here.
   Re-measure before believing it anywhere else; expect well under 1.1x.
2. **Bit-parallel whole-field engine** — only 10x-class idea left, documented
   blocker (lamp agreement vs tick disagreement; cannot pass the 3-way gate
   without redefining it). Additive + separately gated or not at all.
3. **alu4 vs cmc** — physics, other agent's lane, they are on it. Paste test
   adjudicates. Do not open a `sim.py` semantics change alone.
4. Operator items: paste `build_alu4full.schem`; stale-file deletions; cpu4.
5. If the box quiets (null check reads 1.00x), the micro-opt loop can resume;
   until then only large (>20%) structural wins are measurable.

## Gates (in order; first failure stops)

    python scratch/mkref.py                    # ONLY after sim.py/simvec.py commit
    python scratch/diff_engine.py              # ALL IDENTICAL
    python compose.py                          # buffers ok
    python scratch/compose_check.py            # 144/322/224/214
    python scratch/nonhier_suite.py            # 6/6
    python scratch/hier_verify.py recipes/alu1.txt   # 32/32
    python scratch/verify_par.py scratch/alu4merge_g.pkl recipes/alu4.txt 16 400 0 16  # 1024/1024

Re-freeze after any `sim.py`/`simvec.py` commit (`mkref.py`), else `diff_engine`
lies. Never `checkout --` / `stash` a file you did not write; `git commit --`
only, `git add -f` under `scratch/`. LOG append-only. A second agent commits
here — re-earn `diff_engine` on a new HEAD, expect timing noise, check
`Get-Process` before trusting any number.
