# Overnight Log — redstone-mini dense builds (2026-09-30)

Operator asleep. No questions asked, no approval awaited. Verify every change,
commit often.

## Assumptions (best guesses, user left the repo path blank; the DONE bar
##  said "dense builds recipes in folder redstone-mini", so that is the repo)
- A1: work repo = D:\redstone-mini. DONE = (1) all 5 dense recipes
  (micro1, alu1, alu4, cpu4, ctrl_decode) generate without error AND
  sim-verify; (2) +3 NEW dense builds green, then stop.
- A2: verify command (user gave none; defined here):
  `python scratch/dense_status.py [recipe...] [tries]` — layout_retry
  (compose -> maze fallback, verify=True), one line per recipe, exit 0 iff
  all OK. Secondary gates: `python compose.py`, `python scratch/compose_check.py`
  (4 small builds sim-green), `python recipe.py`, `python sim.py`.
- A3: reference repos untouched; nothing cloned; no installs needed.
- A4: prior sessions' uncommitted tree taken as-is, validated by gates first.

## Result: NOT DONE. 1 of 5 dense builds verified (micro1). 0 new builds.

## Timeline / what landed (commit 67044ba, a7dc462)
Baseline green: 4 small builds 158/280/226/254.

1. **Ring-hop** (compose.py lwire): a reservation-only ring cell now
   spans via the existing 5-cell bridge instead of dying loud. Found by
   BFS: alu1 AB had a provable violation-free len-53 run; all 26 L/ray
   candidates died on ONE empty ring cell.
2. **Candidate fallback** (compose.py lwire): lwire walks every ranked
   candidate, rolling back each failure, instead of dying on cands[0].
3. **A* corridor** (compose.py `_astar_wrap`): reuses layout.astar (its
   coupling rules are sim-parity, not a re-derivation) as the last
   candidate, for ANY coords via a shifted margin box — astar clips at 0
   while compose lanes run negative. Bounded box (manhattan+64) to cap RAM
   after a PC restart was caused by a 10^6-wide astar window.
4. **Offset-trunk candidates** (_candidates): 12 parallel corridors
   u rows north/south of the load row.
5. **Driver halos** (compose): foreign drivers reserved like loads, so
   candidates and astar steer around *drivers* (the measured seal was
   stamped on a driver, not a port).
6. **Wide streets** (`_expanded` halo 2 -> 4): sibling tile yards stopped
   merging into one sealed super-block.
7. **Confinement ordering + blame restart** (compose): most-bottlenecked
   net first; on a loud death, blame the sealing wire-owner, constrain
   order, re-run from the placement-end snapshot. Bounded 24 restarts.
8. **Single-victim displacement** (compose `_displace`): when order can't
   separate two mutually-sealed nets, delete the sealer's wire, route the
   failed net through the freed ground, re-route the sealer around it.
9. **Latch porch guard** (tiles.place_latch): the S-row repeater's front
   zone is ringed empty so no routed run can close a front-back dust loop
   around the diode. micro1's failure changed from "not settling" to
   "torch burnout" (progress: the 329-cell ring is gone).
10. **Diagnostic probes** (scratch/, gitignored): wallpanel, astarprobe,
    hopclause, netdump, rectdump, churnedge, plantlog, dense_status,
    vecsweep, traceview.

Small builds stayed sim-green throughout the final state:
example_and 182, example_2gates 396, latch_sr 250, example_xor 282.

## Measured walls that survived (with the numbers, for the next session)

### alu1 (21 gates) — compose frontier: `CIN: (-11,30) -> (142,30)`
- The input's E-W leg runs at the LOAD's row, straight through the tile
  field: a 153-cell ground march. 38 hop refusals, **every one
  `feet-wire`** — the hop's far foot (victim+2) lands on the *next*
  column's dust.
- Root shape: two N-S columns 2 cells apart (B@x6, n1@x8). The 5-cell hop
  needs 2 clear cells each side, so a 2-wide canyon is unhoppable. This is
  a GEOMETRY limit of the proven hop shape, not a search failure: astar
  finds no flat path either (`astar_wrap: NO PATH`), because astar cannot
  see hop-over crossings at all.
- Cleared along the way: m0, m4, O, AB, n0, n1 (all route now).
- Maze backend: `no route for A: (31,393) -> (57,96) (3D: self-lid)`,
  25 tasks unroutable, 408s.

### Reverted experiments (kill-switch fired, tree clean, evidence kept)
- **Input trunk rows** (reserved rows south of all tiles for long E-W
  travel): fixed alu1's B/CIN legs but example_and went 182 GREEN ->
  314 SIM MISMATCH (trunk runs bleed 15->5 before the hop dust, OR
  junction reads weak). One shared row for all inputs shorted them
  (measured: pitch 2 required). Two failure classes at once = not a fix.
- **Lane offset 8 / pitch 6** (open a >=6-cell gap west of the leftmost
  tile port): did NOT move the wall (the 2-wide canyon is B@x6 vs n1@x8,
  a gate port, not the input lane) and cost small builds 30% more blocks
  (182 -> 238). Reverted.
- **Parity-staggered torch power-on in the sim** (break symmetric latch
  rings like vanilla's propagation skew): made micro1 WORSE (4 green
  W=1 vectors -> 0, all burnout). Reverted to same-tick.

### micro1 — generates + verifies via the MAZE backend, not compose
- `layout_retry(micro1, verify=True)` returns a **verified** 2301-block
  build in 6.8-22s. That satisfies DONE item 1 for this recipe.
- compose also builds it (3367 blocks) but the sim is RED: TORCH BURNOUT
  on the latch's cross-coupled pair. Root cause (traced, not guessed):
  the latch's S/R arrive through long diode runs, so the fuse on one torch
  trips before the other's S breaks the ring. The porch guard removed the
  329-cell dust ring; the remaining failure is a power-on/latency race in
  the latch, not a router fault.
- TODO: seed the latch to a defined state (drive R for a tick) or shorten
  S/R to the latch before sim, so the fuse race cannot be lost.

## What I need from you
- Nothing credential-related. Decisions only:
  1. Accept a narrower hop shape (3-cell, needs a support pillar) so
     2-wide canyons cross? That is the single change that unblocks alu1.
  2. Or authorise composing in y>=2 overflight (3D astar with support
     stamping) for long input legs — bigger, but the maze backend already
     proves 3D routing works.
  3. For micro1: is a defined latch power-on (reset-then-set) acceptable,
     or must every build settle from cold?

## Session 2 (continued after first report) — maze sweep falsified a config fix

Ran `scratch/mazesweep.py` (maze backend only, seeds x grow, self-bounded),
because micro1 greens through the maze and a config-only change would have
been zero-risk against the DONE bar. It is not a config problem:

| recipe | attempts | result |
|---|---|---|
| ctrl_decode | 8 (seeds None/0/1, grow 0/1/2) | 0 green, all `no route for <net>` |
| alu1 | 4 (seeds None/0, grow 0/1/2) | 0 green, all `no route for B` / `no route for OP1` |

Verdict: **both backends hit the same ground-existence wall**, so no seed,
grow level or backend ordering can satisfy "all dense builds generate".
The wall is placement/routing geometry, not search. This retires the
"just sweep harder" option that the first report left open.

Also confirmed this session: a tile's own apron seals its west-edge port
(alu1 OP1 `(-15,12)->(4,12)` has no flat and no 3D path), and opening
that port trades signal strength for reach (arrives at 9 where an OR
diode rear needs 15). Root-caused, not guessed; the fix ordering is in
MORNING-REPORT.md TODO.


## Session 3 (continued after second report) — 7 commits, 1/5 verified, 0 new builds

Assumptions: work repo = D:\redstone-mini; verify = scratch/dense_status.py (layout_retry verify=True) and scratch/compose_status.py (compose only).

### Landed (compose.py / tiles.py / sim.py, all gated on the 4 small builds staying sim-green 182/396/250/272)

1. **Single-leg input routes** (34f2607): the N-S lane + E-W approach was a pinned turn cell; a blocked ENDPOINT is unhoppable, so the whole leg now routes as one lwire and the existing offset trunks jog the turn. Cleared alu1 OP1 (-15,12)->(4,12) and ctrl_decode OP2 (-3,1)->(-3,12). xor 282->272, micro1 3367->3361.
2. **Outputs never inlined** (34f2607): _strip_buffers ate a hand-written buffer that was a recipe OUTPUT, leaving pos[] unset (bare KeyError).
3. **Lamp taps before routing** (ba5305e): tap_lamps ran on the post-routing field where a dense band has no clear spot (alu1 Y); the tile-only field has all four streets open.
4. **Torch-adjacency seal** (e32deeb): tiles.seal_tiles snapshots per-torch allowed nets; a routed run beside a foreign torch is driven by lever AND inverter (ring oscillator). A 6-gate OR/AND chain went TORCH BURNOUT -> green (1186 blocks). Cobble-host variant tried and reverted same commit — it walled every dense route.
5. **Self-lid counts tile-body cobble** (11b40f5): the 3D flight check missed supports _support legitimately reuses (alu4 C1 (107,41)->(195,55) now routes). sim.py gains REDSTONE_BURNOUT (default 8, unchanged) for audit.
6. **Buried-wire guard REVERTED** (66cb1a0): cobble above a wire does not break it; the guard walled a valid 240-cell astar path.
7. **Blame-restart voids staged routing** (c7dadb4): defensive, did not reproduce.
8. **Load-held-by-foreign-net is loud** (66cc52a): turns silent SIM MISMATCH into an attributable error. Fires on 4 of 5 dense recipes (micro1 W holds D, alu1 n1 holds B, ctrl_decode OP2 holds a, plus or_ands_chain). TRADE-OFF: or_ands_chain went sim-GREEN -> COMPOSE-RED (was accidentally correct).

### Final measured state
- micro1: compose load (34,15) of W holds D; **maze OK 2301 blocks 6.7s = the only verified dense build**
- alu1: compose 
1 load holds B; maze 798s RED (B (34,398)->(28,399), 3D self-lid, 30 unroutable)
- ctrl_decode: compose OP2 load holds a; maze 409s RED (OP0 (344,76)->(484,12), 3D self-lid, 15 unroutable)
- alu4: compose 
o ground for t33 (492,42)->(446,154) 129s
- cpu4: compose 
o ground for AL_n1 (398,12)->(744,118) 152s
- New dense builds: 0. Candidates (minterms/pairfuncs/muxlattice/popcount/group4) all died on long input routes; files removed.

### The hung process (for the record)
The final dense_status.py alu4.txt cpu4.txt ran ~6h without output and was killed 09:24. It was the maze backend grinding on alu4 (minutes per attempt, 6 tries x grows). Do not run the full maze ladder on alu4/cpu4 in one shot again.
