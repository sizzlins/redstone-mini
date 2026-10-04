# MORNING REPORT — 2026-10-05 (optimization shift 2: speed, and one red flag)

Repo `D:\redstone-mini`, branch `phase2-design`. Full trace in `LOG.md`;
my instruments are in `scratch/` and each says what it is for in its docstring.

**Read this first: the paste-ready alu4 build disagrees with `cmc` on 2286
cells, and it is not from tonight.** Details in "THE RED FLAG" below. It does
not make the build wrong, but it is the one thing here I would not ship without
your paste test.

---

## 1. What builds now

| build | verdict | evidence |
|---|---|---|
| **alu4** (10 inputs, 71,560 blocks) | **GREEN 1024/1024** | `verify_par` cold, exit 0, 35.9s. Bands 6/6: 13304 · 7518 · 6957 · 571 · 2414 · 4878 |
| **alu1 hier** | **GREEN 32/32** | `hier_verify`, exit 0, 37.2s |
| examples / latch / xor / micro1 / ctrl_decode | GREEN, bit-identical | 144 / 322 / 224 / 214 / 2925 / 5499 |
| alu1 **flat** (nonhier suite) | RED **by design** since `124d179` | 22-gate banded recipe, `22 < _TERR_MIN_GATES=40` |
| cpu4 | RED by inheritance (pre-dates this repo's sessions) | Y2 cross-band coupling |

Paste-ready: **`build_alu4full.schem`** (hash-verified copy already in
`…/worldedit/schematics/`). `build_alu4.*` and `build_alu4bank.*` are **stale**
— do not paste those.

Every gate re-run green after every change: `sim.py` 8 canaries, `simvec.py`
self-check, `compose.py`, `compose_check`, `nonhier_suite` 6/6,
`diff_engine` **ALL IDENTICAL** (3-way: frozen `HEAD:sim.py` == live
`sim._run_vec` == the new table engine), `hier_verify` alu1, alu4 1024/1024.
`mkref.py` + `refcheck.py` re-run after the `simvec.py` commits.

## 2. What I changed, with numbers

Everything below is in `simvec.py`'s table engine and `scratch/verify_par.py`.
The engine is **~2.65x** the original per vector, measured interleaved in one
process so machine load cannot flatter it.

| # | change | measured |
|---|---|---|
| 1 | Int-indexed tables + bytearray state. Tables were 112 MB and 0.4s per worker; `wake` alone was 59 MB of `(kind,cell)` tuples and `d_dirs` 28 MB of nested tuples | **1.62x/vector, 2.8x less RAM** |
| 2 | Z-order (Morton) cell ids — pure relabelling, invisible to the physics | 1–7% under concurrency |
| 3 | Coalescing marker: fresh `set()` per bucket → one reused bytearray per ring slot | **1.05x** (268k set-adds/vector gone) |
| 4 | Sign-encoded ring items — a wake append is now a plain reference, no `<< 1` | **1.05x** (268k allocations/vector gone) |
| 5 | **Exact wake map.** `wake` was geometric; only 45% of its edges are read by any relation | **1.11x**, 54.6% of the walk provably dead |
| 6 | `verify_par`: a worker owns a *group* of chunks, so tables are built once per worker, not once per chunk | ~1–5% (see retracted #2) |
| 7 | `REDSTONE_ASTAR_MARGIN` env gate (default **unchanged** at 64) | answers your queued question; 64 is load-bearing |

Full 1024-vector alu4 sweep, 16 workers, cold: **108.7s → 35.9s**.

**Tried, measured, reverted** (so nobody re-derives them): cyclic-GC
hypothesis (82808 tracked objects, 0 gen2 collections, `gc.disable()` = 1.00x);
`if v:` guards on the dust classes (~2%, noise); amortising the stall check
(1.00x); neighbour-locality via Morton was mostly *not* the parallelism answer;
the pre-astar flood and bound-prune ideas from the previous session.

## 3. THE RED FLAG — alu4 vs cmc

`verify2 --diff-all` on the banked build **fails**:

```
DIFF: dust 49814/1957248 cells differ, repeaters 7280/279552 differ
DUAL-ENGINE VERDICT: FAIL
```

**It predates tonight, proven:** `REDSTONE_SERIES_VERIFY=1` runs the authority
engine `sim._run_vec`, and `sim.py` is byte-identical to what I inherited
(`refcheck`: `worktree sim.py == HEAD:sim.py`). It produces the *same numbers
to the digit*.

**Shape:** 2286 distinct cells in one contiguous region — x 1082–1095, y 1–3,
z 167–183 — a decay ladder our sim reads 12–15 and cmc reads 0. So the risk
direction is *our sim being too generous*, the opposite sign to the
comparator-front bug fixed in `38b872f`.

**Why it was never caught:** `verify2` had only ever been run on alu4's *lamp*
verdict, where both engines say green. Both still do — ours on all 1024 vectors
against the logical oracle. The disagreement is internal wire state that does
not move the lamps, which is precisely the sim-overfit class: green in sim,
different in the game.

**Specific to alu4:** I re-ran alu1 tonight → `0 / 204224`, DUAL-ENGINE PASS
(the GA agent measured 0/179296 on alu1glass, 0/25872 on add2opt).

Reproduce (bounded; doc is cached so a re-run is sim-only):

```
python scratch/verify2.py recipes/alu4.txt scratch/alu4merge_g.pkl --diff-all
python scratch/diffwhy.py scratch/alu4merge_g.v2doc.json --examples 8
python scratch/simwhy.py scratch/alu4merge_g.v2doc.json 35 1082 1 169
```

**I did not fix it.** It is physics forensics, it belongs to whoever owns
`sim.py` semantics, and I was not opening a semantics change at the end of a
speed shift. It is reported with commands instead.

## 4. Three numbers of mine that were wrong

I retracted these in `LOG.md` rather than leaving them to be cited:

1. **"Table build 7.78s → 8.60s, a regression."** Both numbers were measured
   under `tracemalloc`, which inflates by more than 10x. Measured clean:
   0.395s old vs 0.353s new — the new tables build *faster*.
2. **"Grouped chunks = 1.33x."** One sample each. Re-ran twice: old 82.6/119.2s,
   new 77.7/98.5s. The within-variant spread exceeds the difference. Real
   effect ~1–5%.
3. **"Engine 1.62x."** That used vector indices 0–4, the easy end. Interleaved
   over *spread* indices three times: 2.19x / 2.10x / 2.10x.

**Rule this box taught me:** single-run wall clock is not a measurement here
(~36s spread on an 80s run — 14 physical cores, hyperthreaded, plus a
co-tenant agent and a Minecraft server). Only interleaved same-process ratios
mean anything. `scratch/tbl_diff.py` now takes a `REDSTONE_TBLDIFF_REF` so a
micro-opt is A/B'd against the engine it replaces, and a byte-identical
reference must read 1.00x before I trust it.

## 5. What I need from you

1. **Paste `build_alu4full.schem`** — never tested, and §3 makes it matter more.
2. **Decide on alu4 vs cmc** (§3). It is a physics question, not a speed one.
3. Stale files: `build_alu4.*`, `build_alu4bank.*`, `build.*.bak`,
   `build_alu1.html` (stale). I never delete.
4. **README is materially wrong** — still not fixed (I never got to it; it says
   "doesn't model timing yet", documents only `--alu8`, never mentions hier,
   the 1024-vector alu4, or alu4bank). It is ~20 lines of work.

## 6. Also true, for whoever reads this next

- **Another agent was committing to this tree during the shift** (`fa58552`,
  `f81977c`, and a stub `f81977c`-class commit after my cold start). My
  `diff_engine` was re-earned on their HEAD and stayed green. They own
  `scratch/sweep*`, `scratch/mkref.py`, `scratch/ref*`.
- **`hier_verify.py recipes/alu4.txt` cannot earn the alu4 green** — it exits 1
  at `SMOKE 1010101010` because the load-bearing `ins_target` 3-pillar swap is
  an out-of-band manual step. The green artifact is `alu4merge_g.pkl`. Same
  family as the two gate bugs already fixed: a green you cannot re-earn. Not
  fixed; it needs the swap wired in.
- The `parallax`/GA agent owns the **cpu4** Y2 coupling, which I never touched.