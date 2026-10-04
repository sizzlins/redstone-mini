# Ponytail debt ledger — 2026-10-04

Scan: `Select-String -Pattern '# ?ponytail:'` over `*.py` + `scratch/*.py`
(`//` checked: none — Python-only stack). Line numbers are HEAD as of
`2ca3f69` and will drift; re-scan to refresh.
Convention: `ponytail: <ceiling>, <upgrade path>` — ceiling and trigger are
pulled straight from the comment. Rows with neither get `no-trigger`.
Most rows are green-neutral equivalence rationales (no ceiling at all);
the ones that matter are the ~25 with a NAMED ceiling and no trigger —
collected in the Watchlist at the end.

## compose.py (140)

- `compose.py:53`, hop cond2 counts committed sup/ctx.sup; tile cobble stays
  invisible (safe direction). ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:151`, HOP_PENALTY=2 prices a bridge at ~flat. ceiling: none
  named (tuned constant). upgrade: none named. `no-trigger`
- `compose.py:223`, L-path fast path, proven identical to full scoring.
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:255`, candidate fallback tries next-ranked corridor, keeps
  cands[0] error. ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:271`, blame uses cands[0]'s corridor only (the reported death).
  ceiling: other candidates' fences unseen. upgrade: none named. `no-trigger`
- `compose.py:287`, astar corridor fallback, deterministic, cost bounded by
  REDSTONE_ASTAR_CAP. ceiling: ASTAR_CAP bound. upgrade: none named
  (raise-cap trigger lives at layout.py:14). `no-trigger`
- `compose.py:309`, 3D overflight last resort (narrow y=1..4 band, then wide).
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:323`, REDSTONE_NO3D=1 skips overflights (env-gated).
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:341`, committed-pillar test on the flight (duplicate-block guard).
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:361`, one-cell-descent support refusal. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:371`, cobf = every support incl. tile bodies. ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:552`, endpoint columns costed, not walled, in astar congest.
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:624`, ring-hop spans reservation-only rings. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:653`, tall-hop (y=4) fallback, short stays primary. ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:743`, slope-link lids over foreign lower wires. ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:793`, booster-into-tile-torch ring refusal (torch host map cached).
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:833`, end_boost planter (hier stitches only, default off).
  ceiling: none named (default-off path). upgrade: none named. `no-trigger`
- `compose.py:842`, same-net repeaters assumed flow-compatible (topology
  argument, never per-cell checked; sim judges). ceiling: assumption unverified
  per cell. upgrade: none named. `no-trigger`
- `compose.py:854`, fresh-only planting (hier stitches; default None = anywhere).
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:863`, never plant on TILE dust (`own=` snapshot). ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:879`, boost elevated runs too (level triples, solid foot).
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:896`, facing = -travel convention. ceiling: none named. upgrade:
  none named. `no-trigger`
- `compose.py:919`, latch HEAD diode re-drives weak fan-out. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:951`, never inline a recipe OUTPUT. ceiling: none named. upgrade:
  none named. `no-trigger`
- `compose.py:1045`, territorial bands, off unless _TERR (fallback rung only).
  ceiling: none named (fallback-only path). upgrade: none named. `no-trigger`
- `compose.py:1118`, port-approach widening TRIED AND REVERTED (×2). ceiling:
  boosters don't guarantee 15 at ports. upgrade: `_plant_repeaters` change
  guaranteeing 15 at every port. (no tag — upgrade named)
- `compose.py:1131`, lever sits AT its lane (d1 zero-length). ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:1138`, hier edge nets defer to producer-facing edge. ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:1148`, lane pitch doubles past 9 inputs (8*spread). ceiling: 9-input
  gate (tuned). upgrade: none named. `no-trigger`
- `compose.py:1166`, hier edge levers face the producer. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:1175`, stub column clears lanes west of minx. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:1191`, lamp taps stamped BEFORE routing. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:1235`, driver halos (foreign driver + Chebyshev-1 reserved).
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:1251`, input trunk rows TRIED AND REVERTED (kept as note).
  ceiling: none named (dead approach). upgrade: none named. `no-trigger`
- `compose.py:1267`, greedy confinement ordering. ceiling: greedy, no lookahead
  (blame restarts compensate). upgrade: none named. `no-trigger`
- `compose.py:1300`, bottleneck-first takes max over driver + loads. ceiling:
  none named. upgrade: none named. `no-trigger`
- `compose.py:1320`, input-before-gate preds dropped (phase order already holds).
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:1349`, intra-band nets first (stable partition). ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:1362`, inputs honor precede via mini topo. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:1385`, pull gates-that-precede-inputs before lanes. ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:1432`, inputs blame too (failed AND owners). ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:1449`, blame BFS capped at 30k cells (RAM bound; partial Counter
  stays valid). ceiling: 30k-cell flood. upgrade: none named. `no-trigger`
- `compose.py:1513`, sealer cells must postdate the snapshot. ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:1575`, blame restarts (25; 100 tried = 50min/rung; ORDER_SEED
  diversifies). ceiling: 25 restarts, precede convergence assumed. upgrade:
  none named. `no-trigger`
- `compose.py:1588`, tile-owned dust snapshot guards booster sites. ceiling:
  none named. upgrade: none named. `no-trigger`
- `compose.py:1614`, ONE displacement shot at the blame pair, then loud.
  ceiling: single-victim rip-up, depth 1. upgrade: none named. `no-trigger`
- `compose.py:1665`, EDGE-levered inputs route stub→load directly. ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:1684`, offset-8/pitch-6 TRIED AND REVERTED. ceiling: none named
  (dead approach). upgrade: none named. `no-trigger`
- `compose.py:1694`, ONE lane leg (merged march + approach). ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:1716`, drop failed net's partial runs (stale diode guard).
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:1729`, stalled-blame fail-fast (same pair → raise). ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:1820`, load must never hold a FOREIGN net. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:1839`, post-hoc diode-drop (bisect, cap 9, sim judges decay).
  ceiling: single-culprit bisect, 9 drops max. upgrade: none named. `no-trigger`
- `compose.py:1890`, partition sim gate runs in the child (pickle cost).
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:2043`, sub ladders re-arm the global deadline (snapshot/restore).
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:2061`, partitions ride the full 44-rung ladder. ceiling: 44 rungs.
  upgrade: none named. `no-trigger`
- `compose.py:2079`, strip band tags inside partitions. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:2091`, edge-lever classification for _compose_once. ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:2099`, staged pipeline pins rung subsets (REDSTONE_HIER_RUNGS).
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:2114`, pinned-first default (order only). ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:2124`, lockstep parallel bands (router_hash verified identical).
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:2151`, port cell must be STAMPABLE, not just open-sided. ceiling:
  none named. upgrade: none named. `no-trigger`
- `compose.py:2167`, rule 7 at rung granularity (hard kill). ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:2271`, bank aims at each band's eastern edge. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:2327`, producer ports with no in-band loads carry no dust
  (allow-list driver). ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:2336`, bare torches forbid everything (empty allow = loud).
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:2348`, allow-list ONLY owner torches (broad allow went silent).
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:2369`, longest stitch first. ceiling: none named (heuristic).
  upgrade: none named. `no-trigger`
- `compose.py:2384`, LONG jogs for stitches. ceiling: none named (superseded —
  see 2389). upgrade: none named. `no-trigger`
- `compose.py:2389`, SHORT jogs for stitches (was LONG). ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:2396`, overflights STAY allowed for stitches. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:2403`, snapshot pre-stitch maxz ONCE (fixed base + stagger).
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:2413`, purge stale lids at merge start. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:2437`, pos points at drivers for cross nets. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:2445`, consumer lever-bank minima. ceiling: none named. upgrade:
  none named. `no-trigger`
- `compose.py:2453`, street waypoints between band pairs. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:2456`, _bankstreets is the REAL gap (same text as 2475 — duplicate
  site). ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:2464`, REDSTONE_STREETS=gap (default stays mid). ceiling: gate nets
  would all move geometry. upgrade: full re-verify (alu1+alu4+cpu4 green,
  counts compared). (no tag — upgrade named)
- `compose.py:2475`, _bankstreets is the REAL gap (duplicate of 2456). ceiling:
  none named. upgrade: none named. `no-trigger`
- `compose.py:2485`, ONE DROP COLUMN PER (band, net), 6 apart, 12 in. ceiling:
  fixed spacing constants. upgrade: none named. `no-trigger`
- `compose.py:2494`, stitch atomicity (snapshot/restore per strategy, repeaters
  included). ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:2554`, index once (sets, not linear scans). ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:2559`, glass/slab support-role split. ceiling: none named. upgrade:
  none named. `no-trigger`
- `compose.py:2639`, contiguity (every pair a sim link). ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:2662`, one bounded last mile (backtrack, fail loud). ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:2709`, stations only on straight runs. ceiling: none named. upgrade:
  none named. `no-trigger`
- `compose.py:2731`, dict only, no blocks.append (finish emits). ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:2789`, splice joints IN ORDER (travel direction for diodes).
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:2802`, stamp the joints (foreign neighbour fails loud). ceiling:
  none named. upgrade: none named. `no-trigger`
- `compose.py:2812`, contiguity gate (diagonal = hole). ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:2821`, _loop_check off for the banked trunk (_try diff covers).
  ceiling: blunt check skipped (compensated). upgrade: none named. `no-trigger`
- `compose.py:2863`, runs must be SIMPLE paths (reject overlap). ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:2913`, BANK strategy first, banked inputs only. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:2930`, east run split at street waypoints (lwire span limit).
  ceiling: ~350-cell lwire span. upgrade: none named. `no-trigger`
- `compose.py:2976`, banked nets don't fall through to generics. ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:2998`, bankdrop west-approach retry (retry-only). ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:3015`, route EVERYTHING fresh on retry. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:3037`, inner raise already carries the bank prefix. ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:3045`, relay_min lowered for fan-out callers. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:3064`, REDSTONE_HIER_FAST bounds SEARCH (default exhaustive).
  ceiling: none named (env-gated). upgrade: none named. `no-trigger`
- `compose.py:3090`, _err-None falls through (TypeError guard). ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:3096`, west approach last resort. ceiling: none named. upgrade:
  none named. `no-trigger`
- `compose.py:3108`, 3-segment corridor stitch. ceiling: none named. upgrade:
  none named. `no-trigger`
- `compose.py:3118`, south-around via empty south margin. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:3127`, stagger the margin per net (4 apart). ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:3141`, east-around (empty east margin). ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:3154`, north-around (negative z legal). ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:3189`, several hop rows, not one. ceiling: none named. upgrade:
  none named. `no-trigger`
- `compose.py:3201`, flow starts EMPTY (reverted undirected seeding). ceiling:
  none named. upgrade: none named. `no-trigger`
- `compose.py:3210`, stitch order env (default longest-first). ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:3251`, bank rows north of gate-net margin rows. ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:3258`, ROW ORDER by east reach, longest southernmost. ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:3269`, rows 6 apart (hop needs the room). ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:3364`, PRE-STAMP rows, route only drops. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:3402`, chain fan-out stitches west-to-east. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:3444`, banked inputs don't chain stub→stub. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:3462`, ring gate runs AFTER boosting. ceiling: none named. upgrade:
  none named. `no-trigger`
- `compose.py:3480`, per-stitch dump (HIERDUMP_EACH, env-gated). ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:3493`, dump on STITCH failure too (env-gated). ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:3510`, merge-wide slope-link lids. ceiling: none named. upgrade:
  none named. `no-trigger`
- `compose.py:3519`, merge lids default ON again (opt-out env). ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:3546`, never lid airspace a same-net slope needs. ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:3559`, slope-clearing AFTER the lid pass, on purpose. ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:3571`, hoisted lid-set maintenance (rebuild hung the merge).
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:3589`, directly-above only for lid clearing. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:3600`, connect producer stubs (single-digit legs; farther is a
  real wall). ceiling: short legs only. upgrade: none named. `no-trigger`
- `compose.py:3620`, check_opens-exact flood (no radius cap, parity load-bearing).
  ceiling: none named. upgrade: none named. `no-trigger`
- `compose.py:3636`, seed AND traverse EXACTLY like check_opens. ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:3700`, _seen holds (cell, net) states. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:3712`, cap legs per net (first few; dozens = disconnected region).
  ceiling: handful of legs per net. upgrade: none named. `no-trigger`
- `compose.py:3743`, mark new leg reached (states, not cells). ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:3756`, banked nets seed EVERY consuming band. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:3774`, exact-state dump on opens failure (env-gated). ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:3791`, same dump for finish_assembly failures. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:3804`, post-merge dump REDSTONE_HIERDUMP2. ceiling: none named.
  upgrade: none named. `no-trigger`
- `compose.py:3810`, ship the shrink-wrap shift WITH the dump. ceiling: none
  named. upgrade: none named. `no-trigger`
- `compose.py:3905`, territorial fallback (44-rung exhaust → territories).
  ceiling: none named (fallback-only path). upgrade: none named. `no-trigger`
- `compose.py:3912`, split-and-stitch macros for big banded recipes (<40 gates
  never). ceiling: 40-gate branch. upgrade: none named. `no-trigger`
- `compose.py:3953`, sim-gated ladder (default OFF). ceiling: none named
  (env-gated). upgrade: none named. `no-trigger`
- `compose.py:4016`, last-None guard names the real wall. ceiling: none named.
  upgrade: none named. `no-trigger`

## core.py (1)

- `core.py:13`, cache the palette split (was ~half of check_shorts). ceiling:
  none named. upgrade: none named. `no-trigger`

## export.py (7)

- `export.py:26`, textures stream from upstream at runtime (no PNGs). ceiling:
  none named. upgrade: none named. `no-trigger`
- `export.py:37`, slabs ride the stone.png fallback. ceiling: none named.
  upgrade: none named. `no-trigger`
- `export.py:57`, missing props := vanilla defaults (WorldEdit strictness).
  ceiling: none named. upgrade: none named. `no-trigger`
- `export.py:78`, bid-completion cache (pure function). ceiling: none named.
  upgrade: none named. `no-trigger`
- `export.py:177`, floor renders as one plane. ceiling: none named. upgrade:
  none named. `no-trigger`
- `export.py:190`, torch mounts include glass/slab/target. ceiling: none named.
  upgrade: none named. `no-trigger`
- `export.py:390`, template text FIRST, JSON payloads LAST (spell-check
  mangling). ceiling: none named. upgrade: none named. `no-trigger`

## layout.py (63)

- `layout.py:14`, pop cap bounds worst-case search per astar call (sealed field
  = W*D pops of thrash). ceiling: per-call pop cap. upgrade: raise via
  REDSTONE_ASTAR_CAP if a verified build ever trips it. (no tag — ceiling +
  trigger named)
- `layout.py:19`, 3D wires Attempt 1 (tiles flat; y=1..4 + trenches, priced).
  ceiling: none named. upgrade: none named. `no-trigger`
- `layout.py:43`, ground-first passes env-switched (2 vs 1 trade off). ceiling:
  none named (explicitly points at PONYTAIL-DEBT). upgrade: none named. `no-trigger`
- `layout.py:51`, transparent block sets _src3/_sup3/_flood3 (read twice).
  ceiling: none named. upgrade: none named. `no-trigger`
- `layout.py:521`, hoist coupling predicate per-search (63M gets → ~1.3k ops).
  ceiling: none named. upgrade: none named. `no-trigger`
- `layout.py:542`, repeater cell is not dust (one guard covers flat/3D/bridge).
  ceiling: y==1 only (no y>=2 repeater before cover). upgrade: none named. `no-trigger`
- `layout.py:640`, negotiated congestion lite (zero when nothing failed).
  ceiling: none named. upgrade: none named. `no-trigger`
- `layout.py:645`, no hugging solids mid-run (ports exempt within 2).
  ceiling: none named. upgrade: none named. `no-trigger`
- `layout.py:697`, single bridge shape; footprint collision → detour.
  ceiling: single shape, router detours. upgrade: full 3D search if hops ever
  dominate. (no tag — ceiling + upgrade named)
- `layout.py:771`, shrink-wrap grid to content (+3 margin). ceiling: none named.
  upgrade: none named. `no-trigger`
- `layout.py:787`, one component per cell (repeater wins over dust). ceiling:
  none named. upgrade: none named. `no-trigger`
- `layout.py:797`, loop-flood power sets (cobble + slabs; never pads/glass).
  ceiling: none named. upgrade: none named. `no-trigger`
- `layout.py:804`, booster→torch-host ring fails loud (ladder retries). ceiling:
  none named. upgrade: none named. `no-trigger`
- `layout.py:818`, stone only where a ground component sits (no trench pad).
  ceiling: none named. upgrade: none named. `no-trigger`
- `layout.py:827`, trench floor stamps missing single cubes. ceiling: none named.
  upgrade: none named. `no-trigger`
- `layout.py:844`, ONE CELL ONE BLOCK checked LAST, O(N). ceiling: none named.
  upgrade: none named. `no-trigger`
- `layout.py:924`, support-role split for glass/slab. ceiling: none named.
  upgrade: none named. `no-trigger`
- `layout.py:946`, y != 1 (trench slopes couple like high ones). ceiling: none
  named. upgrade: none named. `no-trigger`
- `layout.py:963`, every lever island seeds check_opens. ceiling: none named.
  upgrade: none named. `no-trigger`
- `layout.py:979`, slope-walk support split. ceiling: none named. upgrade: none
  named. `no-trigger`
- `layout.py:1000`, slope links use sim's rule. ceiling: none named. upgrade:
  none named. `no-trigger`
- `layout.py:1057`, D clears bus lanes (max() leaves placed builds untouched).
  ceiling: tuned inequality. upgrade: none named. `no-trigger`
- `layout.py:1068`, infinite room grows on demand (W cap ~830 bands). ceiling:
  W cap fits ~830 bands. upgrade: none named. `no-trigger`
- `layout.py:1197`, levers park below loads' median band. ceiling: colliding
  medians run east and may go out of bounds (loud). upgrade: input fanout
  chaining (recipe.py still excludes inputs). (no tag — ceiling + upgrade named)
- `layout.py:1233`, bus lanes pre-claim (maze detours on saturation). ceiling:
  none named. upgrade: none named. `no-trigger`
- `layout.py:1316`, repeaters ride along on replace (dict.copy both ways).
  ceiling: none named. upgrade: none named. `no-trigger`
- `layout.py:1373`, inputs ride the router like gate nets. ceiling: none named.
  upgrade: none named. `no-trigger`
- `layout.py:1385`, spine-first per input (separate shuffle stream). ceiling:
  none named. upgrade: none named. `no-trigger`
- `layout.py:1416`, duplicate task queue with O(1) recount. ceiling: none named.
  upgrade: none named. `no-trigger`
- `layout.py:1426`, output-tap reservation (retry layer only). ceiling: none
  named. upgrade: none named. `no-trigger`
- `layout.py:1475`, last-resort hop, cap 24 per build (short then tall).
  ceiling: 24 hops. upgrade: none named. `no-trigger`
- `layout.py:1510`, tall supports may share a solid key (snapshot unwind).
  ceiling: none named. upgrade: none named. `no-trigger`
- `layout.py:1514`, for/else (UnboundLocalError guard). ceiling: none named.
  upgrade: none named. `no-trigger`
- `layout.py:1530`, splice the hop into ONE path (adjacency-ordered). ceiling:
  none named. upgrade: none named. `no-trigger`
- `layout.py:1542`, cover assumes a CHAIN (assert adjacency). ceiling: none
  named. upgrade: none named. `no-trigger`
- `layout.py:1555`, all-or-nothing hop (unwind pa on pb fail). ceiling: none
  named. upgrade: none named. `no-trigger`
- `layout.py:1566`, undo the hop (un-stamp, don't rely on raise). ceiling: none
  named. upgrade: none named. `no-trigger`
- `layout.py:1601`, two passes (flat-only first, 3D only for leftovers).
  ceiling: none named. upgrade: none named. `no-trigger`
- `layout.py:1609`, total search budget (default 0 = unlimited). ceiling: none
  named (unbounded by default). upgrade: set it to bound a runaway dense
  attempt. (no tag — action + condition named)
- `layout.py:1664`, per-NET retry cap 6 (per-set 2). ceiling: still no space
  created, hopeless nets just defer sooner. upgrade: corridor mechanism (more
  ground) if the census shows no-search rising 1:1 with the NO-ATTEMPT drop.
  (no tag — ceiling + upgrade + condition named)
- `layout.py:1694`, defer, do not abandon (collect and keep going). ceiling:
  none named. upgrade: none named. `no-trigger`
- `layout.py:1725`, permanent debug tap (one env check). ceiling: none named.
  upgrade: none named. `no-trigger`
- `layout.py:1746`, facing negate convention (±dx symmetric guards). ceiling:
  none named. upgrade: none named. `no-trigger`
- `layout.py:1755`, repeater-feeding-side refusal (static check can't see it).
  ceiling: hairpin routes legal-but-refused (longer run, never correctness).
  upgrade: none named. `no-trigger`
- `layout.py:1800`, walk ONE chain not a tree (bounded trunk drag-in). ceiling:
  none named. upgrade: none named. `no-trigger`
- `layout.py:1807`, feed fragments from the tail side (dangling-head rule).
  ceiling: none named. upgrade: none named. `no-trigger`
- `layout.py:1840`, goal gets nearest booster (interior gaps ≤14). ceiling: none
  named. upgrade: none named. `no-trigger`
- `layout.py:1851`, torch host map built once per booster round. ceiling: none
  named. upgrade: none named. `no-trigger`
- `layout.py:1881`, same unwind for booster→inverter rings (retry, not refusal).
  ceiling: none named. upgrade: none named. `no-trigger`
- `layout.py:1921`, ONE runnable check — port grid spec. ceiling: none named
  (test scope). upgrade: none named. `no-trigger`
- `layout.py:1949`, port holds dust or west repeater. ceiling: none named.
  upgrade: none named. `no-trigger`
- `layout.py:1959`, OR-feeding inputs keep batch levers. ceiling: none named.
  upgrade: none named. `no-trigger`
- `layout.py:1965`, ONE panel check — one lever per input. ceiling: none named
  (test scope). upgrade: none named. `no-trigger`
- `layout.py:1973`, AND/OR blind to XOR — XOR gets its own check. ceiling: none
  named (test scope). upgrade: none named. `no-trigger`
- `layout.py:1981`, bars count LABELS — check the real graph (dust+slopes).
  ceiling: none named (test scope). upgrade: none named. `no-trigger`
- `layout.py:2034`, negative controls (canary must be seen red). ceiling: none
  named (test scope). upgrade: none named. `no-trigger`
- `layout.py:2054`, POINTING table asserted from the wiki (only external oracle).
  ceiling: none named. upgrade: none named. `no-trigger`
- `layout.py:2077`, Target joins wire shape (asserted directly). ceiling: none
  named. upgrade: none named. `no-trigger`
- `layout.py:2095`, export round-trip gate (file is the shipping gate). ceiling:
  none named. upgrade: none named. `no-trigger`
- `layout.py:2118`, ONE bridge check (live-fire two nets). ceiling: none named
  (test scope). upgrade: none named. `no-trigger`
- `layout.py:2156`, tall bridge template + live-fire. ceiling: none named (test
  scope). upgrade: none named. `no-trigger`
- `layout.py:2178`, Attempt-1 rules (support assert fires on bad case). ceiling:
  none named (test scope). upgrade: none named. `no-trigger`
- `layout.py:2196`, no booster on sideways-run cells (negative control).
  ceiling: none named (test scope). upgrade: none named. `no-trigger`

## recipe.py (10)

- `recipe.py:22`, hier edge levers file syntax ("EDGE <net> <W|E>"). ceiling:
  none named. upgrade: none named. `no-trigger`
- `recipe.py:33`, optional datapath columns (adder8). ceiling: none named.
  upgrade: none named. `no-trigger`
- `recipe.py:120`, three vectors not the exhaustive set (speed bound).
  ceiling: defect off {0^n, 1^n, alternating} not caught pre-layout. upgrade:
  mirror sim_verify's 2^n <= 4096 rule (trigger explicitly none — widening is
  free whenever wanted). (no tag — upgrade named, though trigger is none)
- `recipe.py:139`, fanout chains (inputs/constants never chain). ceiling: none
  named. upgrade: none named. `no-trigger`
- `recipe.py:155`, banded fanout replicates input-driven shared gates. ceiling:
  none named. upgrade: none named. `no-trigger`
- `recipe.py:189`, sort by index only (tuple sort TypeError guard). ceiling:
  none named. upgrade: none named. `no-trigger`
- `recipe.py:202`, relay runs on fresh indices. ceiling: none named. upgrade:
  none named. `no-trigger`
- `recipe.py:213`, banded relay (replicated nets need nothing). ceiling: none
  named. upgrade: none named. `no-trigger`
- `recipe.py:253`, 2-load nets pass untouched. ceiling: none named. upgrade:
  none named. `no-trigger`
- `recipe.py:285`, pre-layout gate rejects what sim would reject. ceiling: none
  named. upgrade: none named. `no-trigger`

## redstone_mini.py (1)

- `redstone_mini.py:33`, demo is the no-arg self-test (was 2.2s on every
  invocation). ceiling: none named. upgrade: none named. `no-trigger`

## sim.py (68)

- `sim.py:13`, settling budget scaled to build size (hier alu4 needs 20000
  ticks). ceiling: ceilings only, greens settle long before. upgrade: none
  named. `no-trigger`
- `sim.py:24`, stall window (progress vs convergence vs oscillation). ceiling:
  none named. upgrade: none named. `no-trigger`
- `sim.py:30`, whole-attempt wall clock (BudgetGuard; 0 = off; fails LOUD).
  ceiling: seed-boundary only (one seed always completes; tries=1 unbounded).
  upgrade: thread the deadline through layout()'s search cap → per-A*-call.
  trigger: one seed overrunning the budget by more than the budget. (no tag —
  all three named)
- `sim.py:46`, lever-power mode read once (module constant). ceiling: none
  named. upgrade: none named. `no-trigger`
- `sim.py:51`, Target-block projectile clocks (engine supplies clock on choice).
  ceiling: none named. upgrade: none named. `no-trigger`
- `sim.py:97`, sim-gate the ladder when verifying (saved/restored). ceiling:
  none named. upgrade: none named. `no-trigger`
- `sim.py:210`, transparent power sets (empty pre-glass → bit-identical).
  ceiling: none named. upgrade: none named. `no-trigger`
- `sim.py:221`, trace flag + stall window read once (run-level locals). ceiling:
  none named. upgrade: none named. `no-trigger`
- `sim.py:246`, live Target-block emissions (exact 1..15 level). ceiling: none
  named. upgrade: none named. `no-trigger`
- `sim.py:264`, same-tick re-queue coalescing (key incl. tick; event sequence
  unchanged). ceiling: none named. upgrade: none named. `no-trigger`
- `sim.py:292`, wake on behind OR beside (late lock re-evaluates). ceiling: none
  named. upgrade: none named. `no-trigger`
- `sim.py:325`, dust above lit torch reads 15 (zero behavior change for tiles).
  ceiling: none named. upgrade: none named. `no-trigger`
- `sim.py:333`, dust on strongly-powered block reads 15. ceiling: none named.
  upgrade: none named. `no-trigger`
- `sim.py:365`, chip layers ±1 link rule + glass/slab refinement. ceiling: none
  named. upgrade: none named. `no-trigger`
- `sim.py:395`, dust powers side block only when POINTING. ceiling: none named.
  upgrade: none named. `no-trigger`
- `sim.py:404`, LEVER powers ATTACHMENT block only (bare bids keep legacy).
  ceiling: none named. upgrade: none named. `no-trigger`
- `sim.py:416`, lit torch powers adjacent except its host. ceiling: none named.
  upgrade: none named. `no-trigger`
- `sim.py:431`, feeds from directly below (weak dust / strong torch / rblk).
  ceiling: none named. upgrade: none named. `no-trigger`
- `sim.py:457`, repeater reads powered slab like stone. ceiling: none named.
  upgrade: none named. `no-trigger`
- `sim.py:465`, repeaters chain back-to-back (upstream ron). ceiling: none
  named. upgrade: none named. `no-trigger`
- `sim.py:527`, comparator strong-block rear read (conservative under-read).
  ceiling: none named. upgrade: none named. `no-trigger`
- `sim.py:534`, sides feed from dust/rblk/facing-in repeaters (phantoms cut).
  ceiling: none named. upgrade: none named. `no-trigger`
- `sim.py:568`, glitch-free power-on pre-roll to tick-0 fixpoint. ceiling: none
  named. upgrade: none named. `no-trigger`
- `sim.py:579`, repeaters belong IN the fixpoint (settled value = f(input)).
  ceiling: none named. upgrade: none named. `no-trigger`
- `sim.py:593`, WORKLIST not whole-field sweep (170 s → seconds, same fixpoint).
  ceiling: none named. upgrade: none named. `no-trigger`
- `sim.py:628`, pop budget not round count (ring spins → same "no fixpoint").
  ceiling: cap value. upgrade: none named. `no-trigger`
- `sim.py:675`, booster-free fallback names the CHURN SET. ceiling: none named.
  upgrade: none named. `no-trigger`
- `sim.py:697`, stall cap scales with build size (3× cells). ceiling: tuned
  multiplier. upgrade: none named. `no-trigger`
- `sim.py:708`, name the OSCILLATOR via churn, not leftovers. ceiling: none
  named. upgrade: none named. `no-trigger`
- `sim.py:760`, blocks count as churn too. ceiling: none named. upgrade: none
  named. `no-trigger`
- `sim.py:777`, vanilla burnout (torch OFF >8× per 60 game ticks dies dark).
  ceiling: tuned constants. upgrade: none named. `no-trigger`
- `sim.py:787`, power-on grace (default 60, verdict-preserving). ceiling: tuned
  constant. upgrade: none named. `no-trigger`
- `sim.py:841`, lamps need pointing-at dust (isolated = cross assumed). ceiling:
  none named. upgrade: none named. `no-trigger`
- `sim.py:893`, STANDING torch support (RDL's 70 torch alu1). ceiling: above-torch
  cell unpowered in model (pre-existing, both types). upgrade: none named. `no-trigger`
- `sim.py:911`, lamps are electrical identity (dead `lampat` set removed).
  ceiling: none named. upgrade: none named. `no-trigger`
- `sim.py:918`, facing negate once (comparators keep vanilla). ceiling: none
  named. upgrade: none named. `no-trigger`
- `sim.py:934`, stone pads join cob (NOT loop/flood cobble). ceiling: none named.
  upgrade: none named. `no-trigger`
- `sim.py:943`, transparent insulator (router stays cobble-only). ceiling: none
  named. upgrade: none named. `no-trigger`
- `sim.py:952`, transparent-but-powerable slabs (bare = bottom). ceiling: none
  named. upgrade: none named. `no-trigger`
- `sim.py:965`, opaque conductive Target source (emissions via target_hits).
  ceiling: none named. upgrade: none named. `no-trigger`
- `sim.py:978`, levers are identity; ATTACHMENT recorded. ceiling: none named.
  upgrade: none named. `no-trigger`
- `sim.py:1002`, fail loud on unknown bids. ceiling: none named. upgrade: none
  named. `no-trigger`
- `sim.py:1067`, target counts (game-proven). ceiling: none named. upgrade: none
  named. `no-trigger`
- `sim.py:1078`, a WIRE is not a support (sim's last chance to be loud).
  ceiling: none named. upgrade: none named. `no-trigger`
- `sim.py:1092`, flat builds + chip verticals + vanilla tick delays. ceiling:
  none named. upgrade: none named. `no-trigger`
- `sim.py:1115`, 3D io keys (2-tuple = y1, 3-tuple carries level). ceiling: none
  named. upgrade: none named. `no-trigger`
- `sim.py:1125`, bit-parallel fast path (narrow eligibility: no LATCH, states
  None). ceiling: eligibility deliberately narrow. upgrade: none named. `no-trigger`
- `sim.py:1135`, never fan out from inside a worker (fork-bomb guard in
  sim_verify). ceiling: none named. upgrade: none named. `no-trigger`
- `sim.py:1237`, ONE runnable check — delay-4 settles at tick 4. ceiling: none
  named (test scope). upgrade: none named. `no-trigger`
- `sim.py:1251`, timed-press proof (stone-20 through delay-4). ceiling: none
  named (test scope). upgrade: none named. `no-trigger`
- `sim.py:1297`, UNDRIVEN latch must hold (hold-0 seeded). ceiling: none named
  (test scope). upgrade: none named. `no-trigger`
- `sim.py:1310`, gate-fed latch EVERY seed (7 ship, one layout hides class).
  ceiling: none named (test scope). upgrade: none named. `no-trigger`
- `sim.py:1353`, glass/slab verticals (wiki-verified). ceiling: none named.
  upgrade: none named. `no-trigger`
- `sim.py:1399`, repeater side-lock, vanilla-true form (dust side can't freeze).
  ceiling: none named. upgrade: none named. `no-trigger`
- `sim.py:1414`, freeze needs SEQUENCE (power-on freeze impossible). ceiling:
  none named. upgrade: none named. `no-trigger`
- `sim.py:1439`, self-loop latch through facing-in repeater. ceiling: none named.
  upgrade: none named. `no-trigger`
- `sim.py:1455`, Target-block oracle (emitted level reaches dust/comparator).
  ceiling: none named. upgrade: none named. `no-trigger`
- `sim.py:1614`, corner pointing is directional. ceiling: none named. upgrade:
  none named. `no-trigger`
- `sim.py:1626`, standing torch cases ×2 (bracket the below-cell). ceiling: none
  named. upgrade: none named. `no-trigger`
- `sim.py:1644`, lamp/comparator/burnout oracles. ceiling: none named (test
  scope). upgrade: none named. `no-trigger`
- `sim.py:1660`, lever→host→dust-on-top source (both directions asserted).
  ceiling: none named. upgrade: none named. `no-trigger`
- `sim.py:1675`, FLOOR lever powers only its block (negative assert). ceiling:
  none named. upgrade: none named. `no-trigger`
- `sim.py:1685`, dust directly above a torch (canary for the parser gap).
  ceiling: none named. upgrade: none named. `no-trigger`
- `sim.py:1698`, torch powers neighbors except host. ceiling: none named.
  upgrade: none named. `no-trigger`
- `sim.py:1703`, host exception (dust over host stays dark). ceiling: none named.
  upgrade: none named. `no-trigger`
- `sim.py:1714`, dust on pillar over lit torch reads lit. ceiling: none named.
  upgrade: none named. `no-trigger`
- `sim.py:1748`, Phase-C infra (budget LOUD, snapshot round-trip, fail-only).
  ceiling: none named. upgrade: none named. `no-trigger`
- `sim.py:1764`, patch THIS module's binding (silent no-op measured). ceiling:
  none named. upgrade: none named. `no-trigger`

## simvec.py (22)

- `simvec.py:58`, transparent power sets mirror sim (bit-identity gate can't
  tell). ceiling: none named. upgrade: none named. `no-trigger`
- `simvec.py:74`, per direction not per cell (comparator early-RETURN order
  kept). ceiling: none named. upgrade: none named. `no-trigger`
- `simvec.py:120`, loop over pwr; glass needs no row. ceiling: none named.
  upgrade: none named. `no-trigger`
- `simvec.py:122`, below-feeds mirror sim cob_state. ceiling: none named.
  upgrade: none named. `no-trigger`
- `simvec.py:179`, ONLY facing-in repeater/comparator locks sides. ceiling: none
  named. upgrade: none named. `no-trigger`
- `simvec.py:197`, sides mirror sim.comp_in. ceiling: none named. upgrade: none
  named. `no-trigger`
- `simvec.py:228`, strong-block rear read (mirror exact). ceiling: none named.
  upgrade: none named. `no-trigger`
- `simvec.py:245`, slab vertices included, glass excluded. ceiling: none named.
  upgrade: none named. `no-trigger`
- `simvec.py:258`, REAR test not back() (repeaters re-evaluated on input change).
  ceiling: none named. upgrade: none named. `no-trigger`
- `simvec.py:286`, lock sides wake their repeater (static edges free). ceiling:
  none named. upgrade: none named. `no-trigger`
- `simvec.py:345`, run_scalar = same physics over precomputed tables (Dial
  buckets; diff_engine proves bit-identity). ceiling: none named. upgrade: none
  named. `no-trigger`
- `simvec.py:443`, side-lock mirrors sim.rep_val (ron starts False). ceiling:
  none named. upgrade: none named. `no-trigger`
- `simvec.py:617`, coalesce same-tick re-queues (removes work, not information).
  ceiling: none named. upgrade: none named. `no-trigger`
- `simvec.py:760`, SWAR engine CUT (5.6% regression; burnout never reimplemented).
  ceiling: 2^n unaffordable at 12+ inputs. upgrade: restore engine from git
  history at 68dd094 (diff_engine.py is the gate). (no tag — ceiling + upgrade
  + trigger named)
- `simvec.py:783`, drop parsed-tables cache with the inputs (wrong-build green
  guard). ceiling: none named. upgrade: none named. `no-trigger`
- `simvec.py:807`, parse once per worker (cache exact). ceiling: none named.
  upgrade: none named. `no-trigger`
- `simvec.py:903`, floating-support gate mirrored for direct callers. ceiling:
  none named. upgrade: none named. `no-trigger`
- `simvec.py:909`, serial fast path (≤8 vectors AND ≤100k cell-vectors; 26x).
  ceiling: deliberately tight thresholds. upgrade: none named (REDSTONE_SERIAL_CELLVEC=0
  is an A/B escape, not a revisit trigger). `no-trigger`
- `simvec.py:929`, refuse to fan out from pool workers (fork-bomb guard).
  ceiling: none named. upgrade: none named. `no-trigger`
- `simvec.py:951`, parent blocks in imap_unordered at 0% CPU (count in consumer).
  ceiling: none named. upgrade: none named. `no-trigger`
- `simvec.py:974`, FAIL FAST on structural faults (22 min → first fault; churn
  raised verbatim; mismatches still collected). ceiling: none named (behavior).
  upgrade: none named. `no-trigger`
- `simvec.py:989`, ONE runnable check — table engine bit-agrees with authority.
  ceiling: none named (test scope). upgrade: none named. `no-trigger`

## snapshot.py (1)

- `snapshot.py:64`, whole build as one JSON (content-hash bounds it; N builds =
  N files). ceiling: no eviction. upgrade: prune by count/mtime in target(),
  or gzip. trigger: `.snapshots/` past ~100MB or a few hundred files. (no tag —
  all three named)

## stack3d.py (26)

- `stack3d.py:57`, support-valid bids mirror sim._check_supports. ceiling: none
  named. upgrade: none named. `no-trigger`
- `stack3d.py:146`, air-only paths (diode-on-net severs loads behind it).
  ceiling: none named. upgrade: none named. `no-trigger`
- `stack3d.py:287`, shafts hunt near the TAP (level to spend). ceiling: none
  named. upgrade: none named. `no-trigger`
- `stack3d.py:309`, path ends IN an ex-lever cell (forced end diode re-15s).
  ceiling: none named. upgrade: none named. `no-trigger`
- `stack3d.py:319`, avoid = other feeds' 3x3 columns (all y). ceiling: none
  named. upgrade: none named. `no-trigger`
- `stack3d.py:358`, booster dodges the shaft itself (glass reusable, dust never
  built on). ceiling: none named. upgrade: none named. `no-trigger`
- `stack3d.py:366`, top booster (fresh 15 for leg2). ceiling: none named.
  upgrade: none named. `no-trigger`
- `stack3d.py:377`, leg2 leaves through the diode's front (validated). ceiling:
  none named. upgrade: none named. `no-trigger`
- `stack3d.py:417`, legs must not use shaft/booster cells (joints bypass via
  allow). ceiling: none named. upgrade: none named. `no-trigger`
- `stack3d.py:452`, periodic diodes every ≤7 flats (same footprint). ceiling:
  none named. upgrade: none named. `no-trigger`
- `stack3d.py:463`, never diode the booster front (measured dark leg). ceiling:
  none named. upgrade: none named. `no-trigger`
- `stack3d.py:467`, straight runs only (corner diode reads dark branch).
  ceiling: none named. upgrade: none named. `no-trigger`
- `stack3d.py:485`, forced end diode (fresh 15 IN the feed cell). ceiling: none
  named. upgrade: none named. `no-trigger`
- `stack3d.py:547`, repeater bids face the DRIVER (tiles.py convention). ceiling:
  none named. upgrade: none named. `no-trigger`
- `stack3d.py:597`, port alignment not center alignment (decay budgets). ceiling:
  none named. upgrade: none named. `no-trigger`
- `stack3d.py:608`, feed points are B's removed lever cells, NOT diode backs.
  ceiling: none named. upgrade: none named. `no-trigger`
- `stack3d.py:635`, diode backs locate the tile side. ceiling: none named.
  upgrade: none named. `no-trigger`
- `stack3d.py:654`, strip lever-ONLY tails (snake cells kept). ceiling: none
  named. upgrade: none named. `no-trigger`
- `stack3d.py:704`, t/c2 live in both decks (that IS the via). ceiling: none
  named. upgrade: none named. `no-trigger`
- `stack3d.py:744`, via step-ban (kept tile-side runs + anchors). ceiling: none
  named. upgrade: none named. `no-trigger`
- `stack3d.py:749`, B-deck legs gone → no ban set (plain gates suffice). ceiling:
  none named. upgrade: none named. `no-trigger`
- `stack3d.py:756`, order retries (longest-first, shortest fallback, rebuilt
  state). ceiling: none named. upgrade: none named. `no-trigger`
- `stack3d.py:787`, keep via out of the other feed's 3x3 column. ceiling: none
  named. upgrade: none named. `no-trigger`
- `stack3d.py:819`, diode replaces dust (pop own-dust under it). ceiling: none
  named. upgrade: none named. `no-trigger`
- `stack3d.py:876`, one cell one block checked last (mirrors finish_assembly).
  ceiling: none named. upgrade: none named. `no-trigger`
- `stack3d.py:927`, collect=True for the preview IO table. ceiling: none named.
  upgrade: none named. `no-trigger`

## tiles.py (18)

- `tiles.py:10`, 2D maps are why tiles cannot stack (~140 y==1 sites; elevated
  physics proven; stacking needs 3D maps). ceiling: maps keyed (x,z), half
  migration pastes unroutable tiles. upgrade: key maps 3D (or deck-segregated
  2D per level) — a compiler migration, not a tile edit. (no tag — ceiling +
  upgrade named; trigger none)
- `tiles.py:71`, re-stamping OWN wire is a no-op (return first). ceiling: none
  named. upgrade: none named. `no-trigger`
- `tiles.py:87`, no routing beside a foreign tile's TORCH (live shipping
  failure). ceiling: none named. upgrade: none named. `no-trigger`
- `tiles.py:124`, same-level adjacency guard (output taps, bank stubs, port
  rows). ceiling: none named. upgrade: none named. `no-trigger`
- `tiles.py:170`, funnel input stubs with cobble (no repeaters — back-feed
  latch). ceiling: none named. upgrade: none named. `no-trigger`
- `tiles.py:182`, ~A approaches NOR host along its pointing axis (dust_points).
  ceiling: none named. upgrade: none named. `no-trigger`
- `tiles.py:192`, ~B hugs west (never touch the NOR torch — ring oscillator).
  ceiling: none named. upgrade: none named. `no-trigger`
- `tiles.py:200`, op/ox/gz footprint sets cached (callers read-only; grep
  fp.add/discard/update before mutating). ceiling: none named. upgrade: none
  named. `no-trigger`
- `tiles.py:208`, reserve what spot_free checks (9x7, not 11x9). ceiling: none
  named. upgrade: none named. `no-trigger`
- `tiles.py:250`, facing identity (toward driver at junction). ceiling: none
  named. upgrade: none named. `no-trigger`
- `tiles.py:339`, S-row repeater (only cell seeing guaranteed minimum level).
  ceiling: none named. upgrade: none named. `no-trigger`
- `tiles.py:351`, funnel the R stub like AND/NOT inputs. ceiling: none named.
  upgrade: none named. `no-trigger`
- `tiles.py:362`, repeater-front porch guard (EMPTY-set ring, ASSIGN not update).
  ceiling: none named. upgrade: none named. `no-trigger`
- `tiles.py:416`, merge-tail diodes (two fixed diodes). ceiling: two fixed
  diodes. upgrade: revisit if the merge grows. (no tag — ceiling + trigger named)
- `tiles.py:431`, side feeds are repeaters not levers (strong-power rule).
  ceiling: none named. upgrade: none named. `no-trigger`
- `tiles.py:450`, comparator sides read dust (four side cells walled in solid).
  ceiling: none named. upgrade: none named. `no-trigger`
- `tiles.py:497`, input stub approaches host along pointing axis. ceiling: none
  named. upgrade: none named. `no-trigger`
- `tiles.py:504`, funnel like AND inputs (repeater reverted). ceiling: none
  named. upgrade: none named. `no-trigger`

## scratch/diff_engine.py (1)

- `scratch/diff_engine.py:122`, sampled build parks lever-direct side dust +
  delay-4 repeater (tri-engine EXACT agreement). ceiling: none named (test
  scope). upgrade: none named. `no-trigger`

## scratch/enum_and.py (2)

- `scratch/enum_and.py:85`, resample per trial (lamp-pointing hinges on ending
  geometry). ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/enum_and.py:104`, ANALOG LEVEL DISCIPLINE (rear level, not refreshed).
  ceiling: none named. upgrade: none named. `no-trigger`

## scratch/enum_xor.py (7)

- `scratch/enum_xor.py:99`, no degenerate placements (Manhattan>=2, tap cells
  avoided). ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/enum_xor.py:137`, NET floods (A,B,O order; share self, avoid earlier).
  ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/enum_xor.py:150`, TRUNK TAPPING from any own-net cell. ceiling: none
  named. upgrade: none named. `no-trigger`
- `scratch/enum_xor.py:182`, q2 stays SINGLE-start (strand guard). ceiling: none
  named. upgrade: none named. `no-trigger`
- `scratch/enum_xor.py:194`, TRUE electrical lengths on the assembled graph.
  ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/enum_xor.py:260`, isolation NOT enforced as filter (unsatisfiable at
  density; sim scores truthfully). ceiling: prefilter dropped. upgrade: none
  named. `no-trigger`
- `scratch/enum_xor.py:306`, save FIRST miss-(3) (diagnostic artifact, not a
  product). ceiling: none named. upgrade: none named. `no-trigger`

## scratch/evo_blocks.py (4, GA-owned)

- `scratch/evo_blocks.py:307`, rear terminal is dust OR stuck-ON lever (constant
  is structural). ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/evo_blocks.py:604`, live-key convention (phantom incumbent lesson).
  ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/evo_blocks.py:673`, future timeout, rule 7 (falls back to failed
  eval). ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/evo_blocks.py:719`, regrow don't grind (best.pkl keeps best).
  ceiling: none named. upgrade: none named. `no-trigger`

## scratch/hier_bands.py (3)

- `scratch/hier_bands.py:22`, engine fingerprint voids band caches (stale cache
  cost sessions; hier_stitch refuses LOUD). ceiling: none named. upgrade: none
  named. `no-trigger`
- `scratch/hier_bands.py:212`, per-band rung skip (HIER_SKIP, env-gated).
  ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/hier_bands.py:239`, smallest green rung not first (compact stitches
  shorter). ceiling: none named. upgrade: none named. `no-trigger`

## scratch/hier_stitch.py (4)

- `scratch/hier_stitch.py:24`, refuse stale band cache LOUD (re-climb).
  ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/hier_stitch.py:50`, child takes PATHS not objects (spawn pipe cost;
  flush every print). ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/hier_stitch.py:81`, optional 4th arg saves the merge (forensics on
  red smoke). ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/hier_stitch.py:90`, smoke here not full verify (silence reads as
  hang). ceiling: none named. upgrade: none named. `no-trigger`

## scratch/hier_verify.py (1)

- `scratch/hier_verify.py:36`, HIER_NCHUNKS fans verify finer (fresh namespace
  re-verifies once). ceiling: none named. upgrade: none named. `no-trigger`

## scratch/ins_allvec.py (2)

- `scratch/ins_allvec.py:78`, per-VECTOR parasitic evidence (full re-verify is
  the precision). ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/ins_allvec.py:89`, "x,y,z" string keys translated once per vector.
  ceiling: none named. upgrade: none named. `no-trigger`

## scratch/prof_router.py (1)

- `scratch/prof_router.py:27`, bound armed at call not import (spawn inherits
  module-level kill). ceiling: none named. upgrade: none named. `no-trigger`

## scratch/rcon.py (1)

- `scratch/rcon.py:27`, Valve framing ends in TWO nulls (mock caught it).
  ceiling: none named. upgrade: none named. `no-trigger`

## scratch/ref_sim.py (31, frozen reference — mirrors sim.py; diff_engine.py gates drift)

- `scratch/ref_sim.py:87`, STANDING torch (above-torch cell unpowered — ceiling
  pre-existing, both types). ceiling: pre-existing model gap. upgrade: none
  named. `no-trigger`
- `scratch/ref_sim.py:105`, lamps are electrical identity (dead set removed).
  ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:112`, facing negate once. ceiling: none named. upgrade:
  none named. `no-trigger`
- `scratch/ref_sim.py:128`, stone pads join cob (not loop/flood cobble).
  ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:137`, transparent insulator (search stays cobble-only).
  ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:146`, powerable slabs (bare = bottom). ceiling: none named.
  upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:159`, Target source (emissions via target_hits). ceiling:
  none named. upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:172`, lever identity + ATTACHMENT recorded. ceiling: none
  named. upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:196`, fail loud on unknown bids. ceiling: none named.
  upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:221`, transparent power sets (bit-identical pre-glass).
  ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:248`, Target emissions (exact 1..15 level). ceiling: none
  named. upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:306`, dust-above-torch canary. ceiling: none named.
  upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:314`, dust on strongly-powered block. ceiling: none named.
  upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:346`, chip layers + glass/slab refinement. ceiling: none
  named. upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:376`, dust powers side block only when POINTING. ceiling:
  none named. upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:385`, LEVER powers ATTACHMENT only (bare = legacy).
  ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:397`, torch-host exception. ceiling: none named. upgrade:
  none named. `no-trigger`
- `scratch/ref_sim.py:412`, below-feeds (weak/strong/host rules). ceiling: none
  named. upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:438`, repeater reads powered slab. ceiling: none named.
  upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:446`, back-to-back repeater chain. ceiling: none named.
  upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:515`, glitch-free power-on pre-roll. ceiling: none named.
  upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:526`, repeaters IN the fixpoint. ceiling: none named.
  upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:540`, WORKLIST sweep (same fixpoint). ceiling: none named.
  upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:575`, pop budget (same "no fixpoint"). ceiling: cap value.
  upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:622`, booster-free fallback names churn. ceiling: none
  named. upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:643`, stall cap scales with build size. ceiling: tuned
  multiplier. upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:656`, name the OSCILLATOR via churn. ceiling: none named.
  upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:708`, blocks count as churn. ceiling: none named. upgrade:
  none named. `no-trigger`
- `scratch/ref_sim.py:725`, vanilla burnout. ceiling: tuned constants. upgrade:
  none named. `no-trigger`
- `scratch/ref_sim.py:735`, power-on grace (verdict-preserving). ceiling: tuned
  constant. upgrade: none named. `no-trigger`
- `scratch/ref_sim.py:789`, lamp pointing (cross assumed). ceiling: none named.
  upgrade: none named. `no-trigger`

## scratch/rig_verify.py (6, GA-owned)

- `scratch/rig_verify.py:122`, 26.x gamerule renames (live discovery). ceiling:
  none named. upgrade: none named. `no-trigger`
- `scratch/rig_verify.py:126`, feedback MUST stay true (blind reads measured).
  ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/rig_verify.py:180`, lamp state via execute-store + scoreboard-get
  (RCON swallows broadcast/nested). ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/rig_verify.py:209`, generous timeout (chunk-gen wedges RCON past 10s).
  ceiling: tuned timeout. upgrade: none named. `no-trigger`
- `scratch/rig_verify.py:219`, reconnect-resilient exec (retry on fresh conn).
  ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/rig_verify.py:256`, post-reload RCON mute (gate on `seed`). ceiling:
  none named. upgrade: none named. `no-trigger`

## scratch/verify_par.py (5)

- `scratch/verify_par.py:29`, fingerprint covers the ENGINE not just inputs
  (stale green that looks fresh is the failure mode). ceiling: none named.
  upgrade: none named. `no-trigger`
- `scratch/verify_par.py:81`, ENGINE in the cache key (cpu4/alu4 stale-green
  measured; over-hashing only re-runs). ceiling: none named. upgrade: none
  named. `no-trigger`
- `scratch/verify_par.py:109`, generous worker caps (slowest vectors need
  20000/2000000). ceiling: tuned caps (greens settle long before). upgrade:
  none named. `no-trigger`
- `scratch/verify_par.py:127`, empty chunks vacuously green (no child per hole).
  ceiling: none named. upgrade: none named. `no-trigger`
- `scratch/verify_par.py:173`, poll() raises once the far end is gone (terminal).
  ceiling: none named. upgrade: none named. `no-trigger`

## Excluded from the ledger (291 markers, untracked files)

Byte-copy backups of live modules (same markers, stale line numbers — ledging
them would triple-count): scratch/compose_cur.py (25), compose_cur2.py (25),
compose_cur3.py (25), layout_with_guard.py (25), cc_after.py (24), cc_lane.py
(24), c834.py (23), c834full.py (23), compose834.py (23), layout_head.py (21),
sim_backup.py (19), tiles_bak.py (15), recipe_prev.py (2). GA-owned live work:
scratch/evolve.py (3), unweave.py (3), muxlevel.py (5). Untracked micro-probes:
check4gate, churnmap, compose_check, dense_status, lockprobe, mkcanary (1 each).

## Watchlist — named ceilings with no trigger (highest rot risk)

- `compose.py:1449` — blame BFS 30k cap; a bigger denser field truncates blame silently.
- `compose.py:1575` — 25-restart cap assumes precede convergence (100 tried: 50min).
- `compose.py:1614` — ONE displacement shot, depth 1; mutual seals beyond it go loud.
- `compose.py:1839` — diode-drop: single-culprit bisect, 9 drops max; multi-diode
  or tile-geometry loops go loud.
- `compose.py:271` — only cands[0]'s corridor is blamed; other candidates' fences unseen.
- `compose.py:1267` — greedy order, no lookahead (blame restarts compensate).
- `compose.py:842` — same-net repeaters assumed flow-compatible, never per-cell checked.
- `compose.py:3712` / `3600` — few legs per net / single-digit stub legs; bigger
  disconnects go loud.
- `compose.py:151` / `1148` / `287` — tuned constants (HOP_PENALTY=2, 9-input pitch
  gate, ASTAR_CAP bound) with no retune trigger.
- `compose.py:2485` / `2061` / `3912` — fixed geometry constants (6-apart drops,
  44 rungs, 40-gate macro branch).
- `layout.py:542` — repeater-is-dust guard is y==1 only.
- `layout.py:1068` — field W cap fits ~830 bands.
- `layout.py:1475` — last-resort hop capped at 24 per build.
- `layout.py:1755` — hairpin routes legal-but-refused (longer run, silent cost).
- `sim.py:13` / `628` / `697` / `777` / `787` — settling budget, pop budget, 3×
  stall cap, burnout 8/60, grace 60: all tuned, none with a retune trigger.
- `simvec.py:909` — serial fast-path thresholds (≤8 vectors, ≤100k cell-vectors).
- `sim.py:893` / `scratch/ref_sim.py:87` — above-torch cell unpowered in the model
  (pre-existing, both torch types); needs a stacked-tile build to matter.
- `tiles.py:10` — 2D maps block tile stacking (has upgrade path: 3D maps, no trigger).
- `layout.py:43` — ground-first ordering tradeoff explicitly punted here.
- `scratch/verify_par.py:109` — generous worker caps, tuned, no trigger.
- `scratch/rig_verify.py:209` — RCON timeout tuned, no trigger (GA-owned).

425 markers, 412 with no trigger.
