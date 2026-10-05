# handoff — speed session 2 (2026-10-05, engine 2.8x, all gates green)

**If you are the next session, read in this order and stop when the questions
are answered:** this file → `MORNING-REPORT.md` (repo root, current — the
operator reads this too) → `LOG.md` in the repo root, last ~150 lines (the
overnight trace; append-only, never rewrite) → `notes/to-ga-agent.md` +
`notes/to-opt-agent.md` (who owns what; the co-tenant agent is live in this
tree) → `notes/PONYTAIL-DEBT.md` (conventions). Do NOT read
`notes/handoff-ga- agent.md` (theirs, they maintain it) or `notes/LOG.md`
(untracked stray copy).

Repo `D:\redstone-mini`, branch `phase2-design` (shared with the co-tenant
agent — commits interleave; see "shared tree" below). HEAD at handoff:
`a9e9b61` plus doc commits after it; check `git log --oneline -5` on arrival
because they commit while you work.

---

## Goal (unchanged from the operator)

Loop: find an optimization, implement it, verify it, repeat. Do not stop.
Standing project goal: every recipe in `recipes/` generates, verifies,
exports. `alu4` done, `alu1` hier done, `cpu4` untouched (not mine, not
attempted).

## Current state (all re-verified cold on the final HEAD)

| build | verdict | evidence |
|---|---|---|
| **alu4** (1024 vectors, 71,560 blocks) | **GREEN 1024/1024** | `verify_par` cold exit 0, **35.7s** (was 108.7s at session start) |
| **alu1 hier** | **GREEN 32/32** | `hier_verify`, exit 0, ~39s |
| examples / latch / xor / micro1 / ctrl_decode | GREEN, bit-identical | 144 / 322 / 224 / 214 / 2925 / 5499 |
| alu1 **flat** | RED **by design** since `124d179` | 22-gate banded recipe, `22 < _TERR_MIN_GATES=40` |
| cpu4 | RED by inheritance | Y2 coupling, pre-dates all recent sessions |
| `hier_verify alu4` end-to-end | **GREEN, exit 0** | fixed by the co-tenant agent (`4d98d4c`); I verified it (173.7s) |

Paste-ready: `build_alu4full.schem` (+`.mcfunction`/`.html`, gitignored).
`build_alu4.*` / `build_alu4bank.*` are **stale** (pre-band-0). Nothing has
ever been pasted into Minecraft.

---

## What changed this session (all in `simvec.py` unless noted)

Engine ~2.8x per vector (interleaved same-process, spread indices), sweep 3.0x,
RAM per worker 112.5 → 38.1 MB, Python calls per 5 vectors 11.52M → 1.72M.

1. **Int-indexed tables + bytearray state** (biggest, 1.62x/vector). Tables were
   dicts keyed by `(x,y,z)`; 1.24M `dict.get`/vector. Now dense ids + six
   bytearrays. Also the reason 16 workers stopped thrashing the box's RAM.
2. **Z-order (Morton) cell ids** — pure relabelling, invisible to the physics
   (proven identical). 1–7% under concurrency; mostly NOT the parallelism answer.
3. **Coalescing marker: `set()` → reused bytearray per ring slot** (1.05x).
4. **Sign-encoded ring items** (1.05x). A wake append is a plain reference; a
   negative item is a scheduled fire (`~c`). This encoding is load-bearing, not
   cosmetic (see "the bug" below).
5. **Exact wake map** (1.11x). `wake` was geometric (279k edges on alu4); only
   45% are read by any relation. Subset + order-preservation makes it safe.
6. **Boolean edges wake only on a zero crossing** (~1.06x). 57.4% of edges only
   care *whether* a cell is lit; a wire decaying 15→14→13 wakes nothing boolean
   until the 1→0. Stored negated in the same list so order is identical either
   way. Halved `_cob_state_s` calls (149k→62k/vector).
7. **`verify_par`: a worker owns a GROUP of chunks** (~1–5%, not the 1.33x I
   first claimed from one noisy sample — retracted in LOG). Tables built once
   per worker; worker count alone sets parallelism.
8. **`REDSTONE_ASTAR_MARGIN` env gate** (default unchanged at 64). Answers the
   previous session's queued question: 64 is load-bearing (margin 16 loses band
   0 outright, `NO GREEN RUNG` exit 1; 32 and 48 reproduce exactly). Ladder wall
   time is 88–90s at every margin, so the ~10% router saving moves nothing.
9. **Dropped the `cid` dict from the hot tables** (40.6→38.1 MB). It existed for
   5 lamp lookups/vector; those are now precomputed `lamp_ids`.

## The bug that cost the most (read this before touching the ring)

First run of the rewrite: 2.00x, `vec0` bit-identical, but 5 of 6 vectors
settled exactly ONE TICK EARLY with identical final state. Root cause, found by
diffing both engines' ring-event logs down to event 15097 (== exactly `ncells`):
a repeater with delay 0 schedules its fire into the CURRENT bucket while its
own re-evaluation is already queued EARLIER in that bucket — both items are
legitimately pending at once. A per-cell flag cannot say which is which; the
item must carry it. Same inversion later bit the exact-wake filter AND two of
my own probes. `REDSTONE_WAKE_EXACT=0` / `REDSTONE_WAKE_BOOL=0` /
`REDSTONE_SERIES_VERIFY=1` are the escape hatches.

## Instruments (each says what it is for in its docstring; all in `scratch/`)

- `tbl_diff.py` — old-vs-new differ over ALL SIX returned values, on SPREAD
  vector indices (0..n are the easy ones — I measured 1.62x on those vs 2.1x on
  spread). Has three deliberate fault injections (`REDSTONE_TBLDIFF_FAULT`);
  a differ that has never gone red is untested. Takes `REDSTONE_TBLDIFF_REF`
  so a micro-opt is A/B'd against the engine it replaces; a byte-identical
  reference must read 1.00x before you trust it.
- `tbl_equiv.py` — exhaustive table equivalence (now checks wake as subset).
- `wake_need.py` / `wake_miss.py` / `wake_split.py` — the wake-map measurements.
  `wake_miss` scans GENERICALLY; a hand-written second copy of the enumeration
  is how the inversion hid.
- `tbl_probe.py` / `tbl_sizes.py` / `build_prof.py` / `gc_probe.py` — memory,
  per-table breakdown, build cost, GC (rejected: 82808 objects, 0 gen2, 1.00x).
- `tickdiff.py` — first divergent tick via `snap_at`. `evlog.py` — event-stream
  diff (needs its two-line instrumentation re-added; it says how).
- Reference copies for A/B: `simvec_old.py` (original tuple engine),
  `simvec_geo.py` (pre-exact-wake), `simvec_prev.py` (last committed).

## What was tried and REJECTED (do not re-derive)

GC hypothesis (1.00x) · `if v:` guards on dust classes (~2%, noise) · stall-check
amortisation (1.00x) · reading each changed cell once instead of twice (1.00x) ·
closures over `run_scalar`'s locals (~1.01x) · **argmax-gated level edges
(0.2% fewer calls — implemented fully, verified IDENTICAL, reverted; design and
correctness condition in LOG)** · worker 14 vs 16 (tie at best-of-5) · astar
default change (breaks band 0) · pre-astar flood / bound-prune (previous
session's dead ends).

## Open items (in priority order, with designs where I have them)

1. **Argmax tracking for level edges** — specified fully in LOG (last entries),
   with the exact skip rule and why both conditions are required. Proven
   correct but 0.2% here; re-measure before believing it anywhere else.
2. **Bit-parallel whole-field engine** — the only 10x-class idea left, with a
   documented blocker: it would agree on lamps and disagree on settle `ticks`,
   so it cannot pass the 3-way gate without redefining it (and 68dd094 is the
   precedent for it being slower). Additive + separately gated or not at all.
3. **alu4 vs cmc: 2286 cells in x 1082–1095.** Pre-existing (proven: untouched
   authority engine gives identical numbers to the digit), both engines still
   call the build green. The other agent narrowed it to dust-connectivity
   derivation. Repro in LOG. This is physics, not speed, and it is theirs.
4. **README** — rewritten this session (the old one documented a `--alu8` flag
   that does not exist). Check it still matches if commands change.
5. Operator items: paste `build_alu4full.schem`; delete-or-keep the stale
   `build_alu4*` / `build.*.bak` (I never delete); cpu4 untouched.

## MEASUREMENT DISCIPLINE (read twice — three of my numbers were retracted here)

- Single-run wall clock is NOT a measurement (~36s spread on an 80s run).
- Interleaved same-process ratios only — AND even those are biased LOW by up
  to 40% on this box (null on identical code reads 0.61x–0.96x; probably
  thermal throttling, reference always runs cooler first). Shipped wins are
  therefore conservative; "nulls" may mask small wins (revert anyway —
  unmeasurable wins do not ship). Micro-opt loop suspended until the null reads
  1.00x. Correctness gates are immune.
- NEVER time under `tracemalloc` (it inflated build time 20x and produced a
  fake "regression" I had to retract).
- Spread vector indices for engine A/B, never 0..n. Best-of-N>=3 for wall clock.
- `simvec.py` / `simvec_old.py` / `simvec_geo.py` / `simvec_prev.py` must all
  keep compiling; several tools import them.

## Gates (run in order after touching anything; each is the cheapest that fails)

    python scratch/mkref.py                    # ONLY after a sim.py/simvec.py commit
    python scratch/diff_engine.py              # must print ALL IDENTICAL
    python compose.py                          # self-test: buffers ok
    python scratch/compose_check.py            # 144 / 322 / 224 / 214 bit-identical
    python scratch/nonhier_suite.py            # 6/6 (alu1 flat RED by design)
    python scratch/hier_verify.py recipes/alu1.txt   # 32/32, exit 0
    python scratch/verify_par.py scratch/alu4merge_g.pkl recipes/alu4.txt 16 400 0 16  # 1024/1024

Re-freeze discipline: any commit touching `sim.py`/`simvec.py` must be followed
by `python scratch/mkref.py`, or `diff_engine` compares against a stale baseline
(it did, for hours, in a previous session). `refcheck.py` confirms
`worktree sim.py == HEAD:sim.py`.

## Files I touched

Tracked: `simvec.py`, `compose.py` (one env gate), `scratch/verify_par.py`,
`scratch/hier_verify.py` (per_call 2→0 so worker count sets parallelism; the
ins_target swap wiring is theirs, `4d98d4c`),
`README.md`, `LOG.md`, `MORNING-REPORT.md`, `notes/handoff-opt2 agent.md` (this).
New tracked tools (all force-added, `scratch/` is gitignored):
`tbl_diff.py`, `tbl_equiv.py`, `tbl_probe.py`, `tbl_sizes.py`, `tickdiff.py`,
`evlog.py`, `build_prof.py`, `gc_probe.py`, `wake_need.py`, `wake_miss.py`,
`wake_split.py`, `dump_cell.py`, `simvec_old.py`, `simvec_geo.py`,
`simvec_prev.py`.

Not touched (theirs): `scratch/evo_*`, `evolve.py`, `compact.py`, `enum_*`,
`memo.json`, `rig_verify.py`, `rcon.py`, `sweep*`, `mkref.py`, `ref*`,
`verify2.py`, `diffwhy.py`, `simwhy.py`, `compdiff.py`, `notes/to-opt-agent.md`,
`notes/handoff-ga- agent.md`. `notes/handoff.md` deleted (operator's
reorganization, left alone), `build.*.bak` (never delete).

## Shared tree discipline (non-negotiable, learned the hard way here)

- Never `checkout --` / `stash` a file you did not write; `git commit -- <paths>`
  only, and `git add -f` for anything new under `scratch/` (gitignored).
- LOG.md is append-only (`Add-Content` / `>>`), short entries, never rewrite —
  both agents were burned by wholesale rewrites before.
- A second agent IS working in this tree (physics forensics + gates). Re-earn
  `diff_engine` on a new HEAD before trusting your baseline, and never assume a
  quiet box: check `Get-Process` and expect 20–100% timing noise plus thermal
  bias when they are grinding.

## Build notes that cost time

- Every probe/script hard-bounded, `__main__` guard (spawn re-import = fork
  bomb). Band caches need `REDSTONE_ASTAR_CAP` unset. `lwire` will not route a
  span over ~350 cells. Repeater facing is stored `-travel`.
- `scratch/` is gitignored: new tools need `git add -f` or the commit silently
  drops them (the commit still "succeeds" — check `git show --stat HEAD`).
- `verify_par` cache keys fingerprint the recipe path + build path + all seven
  engine files, so a fresh pkl *path* (not just content) forces a cold run —
  useful for honest timing, and why A/B copies work.
