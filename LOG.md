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


## Session 4 (user present, 'continue') — 2/5 + 3/3, then stop

User clarified: builds may sprawl across chunks, wires may run long, levers stay banked. Implemented levers-at-lanes (d1 zero-length) + spread retry + vertical envelope.

Landed: lever-at-lane (micro1 compose-green, latch race gone), longer trunk jogs (add2 12539->8083 blocks), constant-1 routing, size-aware stall cap, full vertical envelope narrow-first, per-leg/flight liveness, load-foreign loud check.

New builds (all generate + verify, stop at 3): decode3 (19g, 9799 blocks), add2 (12g CORRECT adder, 8083 blocks), chainmix (24g, 11497 blocks).

Verified via authoritative dense_status: micro1 OK 2925, ctrl_decode OK 6111, decode3/add2/chainmix OK.

Still red: alu1 (OP1/OP0 y=3 collision + CIN lanes), alu4 (t33), cpu4 (AL_n1). All three share input-crossing/long-march walls needing 3D blame, highway router, or bus architecture — documented in MORNING-REPORT with ordered next steps.

Caught and fixed along the way: add2 shipped with a wrong carry (C1=A0 OR B0) and still went green — sim checks fidelity to recipe, not recipe correctness. Fixed to a correct adder, re-verified.

Reverted (evidence kept): port-roof guard, load-relative lanes, inputs-first, sibling avoid, RS_NOLANE, buried-wire, per-leg reachability, _displace both-nets (built on mis-framed reads).


## Overnight session (autonomous)

Goal: every recipe in redstone-mini/recipes builds + verifies, plus 3+ dense builds that never built before.

Starting point: 2/5 dense green (micro1, ctrl_decode). Red: alu1, alu4, cpu4.

### Harness (rule 7: nothing may hang)
- compose() had NO wall-clock bound and the ladder was about to grow to 20+ attempts, so a hard recipe could spin forever. Added REDSTONE_COMPOSE_SECS: a deadline over the whole ladder. REDSTONE_MAX_SECS still bounds a single attempt.
- scratch/run_detached.ps1 + scratch/run_fleet.ps1: every long build runs detached with a hard cap, so no shell call blocks. Polled instead of waited on.
- All ladder rungs tried: short jogs x spread 1,2,3,4,5,6,8,10 x {gates_first, inputs_first}, then long jogs over the same grid (32 rungs, deadline-bounded).

### Routing order became a retry axis
alu1 died on "wire OP1 touches OP0 beside (-7,3,13)" - its inputs routed last into a saturated field. Routing inputs FIRST gives them clean ground and gates route around the lanes. compose() now tries gates-first everywhere, then inputs-first. Greens still land on rung 1 bit-identical, so the gates never move.

Result: alu1 GREEN, 13300 blocks.

### Jog depth became a retry axis (and a bug it hid)
Removing the 16/20/24/32-row jogs fixed add2, which had gone SIM-RED with A0/A1/B0/COUT all dark - a long jog let the input march wander somewhere it could not be sealed, leaving the port cells undriven. But alu1 needs the long jogs. So both are rungs now: short first (proven baseline), long only as escalation.

### Clearance at run ends
_sealed's near_end window was 3 cells, so an input's outbound run was allowed to hug a foreign wire for its first three cells. Cut to 1: only the port cell itself may sit inside a foreign wire's neighbourhood. All greens bit-identical (micro1 2925, chainmix 11497, add2 12539, 4 small hashes unchanged).

### Slope-link lids (the fix that unblocked cmp2's short)
sim couples y=1 dust to a diagonal y=2 wire only when the upper has support under it AND the lower has no lid over it. Hops and 3D overflights both mint elevated dust on fresh cobble, and the search that placed them could not see the foreign wire landing diagonally below - so check_shorts raised SHORT3D only after the fact, and no spread in the ladder could escape it (cmp2 failed identically at spread 1 and spread 10).

_walk now drops one cobble directly above the lower wire, mirroring check_shorts' dy=-1 case cell for cell. Because it mirrors the raise condition exactly, a build that already passes gets zero extra blocks - confirmed: latch_sr 224, micro1 2925, chainmix 11497 all unchanged.

cmp2's SHORT3D is gone.

### New dense builds (all generate + verify)
- sub2 - 2-bit subtractor with borrow out, 3487 blocks. Arithmetic checked over all 16 input vectors by scratch/recipe_check.py.
- mux4 - 4-bit 2:1 mux, 9 inputs, 20239 blocks. Largest build in the repo.
- andor8 - 8-input AND tree plus 8-input OR tree, 17997 blocks. First written as three levels of dust OR; SIM-RED on 7/256 vectors while gate tracing was correct and 40000 settle ticks changed nothing, so the dust OR tree itself was racing. Rewrote O8 as NOT(AND of NOTs) - torch ANDs and inverters only, no dust OR. Green.

Also added scratch/recipe_check.py: checks a recipe's arithmetic against a reference expression over every input vector, no placement. It immediately caught that my first sub2 was wrong (bit-0 sum is A0 XOR B0 - the +1 carry-in cancels the inversion - and the bit-0 carry is OR not AND). Same lesson as add2 shipping green with a bad carry: sim checks fidelity to the recipe, never the recipe's arithmetic.

### Still red, with the wall identified
- cmp2 - past SHORT3D, now dies on ONE orphan dust cell: OPEN (unconnected dust, nothing drives it) at (165,1,46) at spread 1, (175,1,62) at spread 2, (245,1,78) at spread 3. One cell, same relative spot at every spread, so it is systematic, not congestion. Suspect: a lid landing on a cell a later net still wanted.
- alu4 / cpu4 - both have 10+ inputs. Every input's lane-to-load leg crosses the others and stamp_wire refuses the touch ("wire B3 touches A1 beside (1268,1,7)"). Lever rows are already staggered 2 per index and lane columns are 4*spread apart, so this is the approach cone, not the port row. mux4 at 9 inputs is the proven ceiling.
- shift4 - TORCH BURNOUT at (64,1,47) during compose. LATCH chain placement, untouched so far.

Reverted/narrowed: the slope-link lid pass was first written too broadly and moved proven builds (latch_sr 224->226, micro1 2925->2942). Narrowed to mirror check_shorts exactly, which restores every hash.

## Night session 2 (assumption + start)

User named MAIN REPO D:\redstone-compiler, but DONE item 1 says "folder
redstone-mini". Checked: D:\redstone-compiler is a separate Rust project
(crates/src/Cargo.toml) with zero .txt recipes and no redstone-mini folder.
All recipes, LOG, tools, and verified builds live in D:\redstone-mini.
ASSUMPTION: D:\redstone-mini is the work target. Proceeding there.

Start state (authoritative dense_status, final code f19fa33):
OK 13: add2, alu1, andor8, chainmix, ctrl_decode, decode3, example_2gates,
example_and, example_xor, latch_sr, micro1, mux4, sub2.
RED 4: cmp2 (compose passes; maze "no route for nB1, grid full"),
alu4/cpu4 (>=10-input approach cone), shift4 (LATCH chain, grid full).
New dense builds already at 6 (decode3, add2, chainmix, mux4, sub2, andor8).

### alu4/cpu4: 3D-only routing also fails (architectural wall confirmed)
Added REDSTONE_NOFLAT (skip flat candidates, astar corridor + 3D overflight
only) as a diagnostic. alu4 with NOFLAT runs 500s and dies on "no ground for
C2: (816,194) -> (1292,240)". So even the full 3D envelope cannot place it.
Combined with: spread 1-10 exhausted, clearance window at 1 cell, nearest-first
load order. The current flat+overflight architecture cannot route a 10-input
72-gate field. Needs a bus/hierarchical router or much sparser placement, which
is a new subsystem, not a rung. Documented in MORNING-REPORT. Greens unaffected
(NOFLAT is env-gated; 4 small + micro1/chainmix re-verified bit-identical).

Final: 14/17 green. cmp2 joined via constant elimination. alu4/cpu4/shift4 red
with identified architectural walls.

### cmp4 GREEN (25408 blocks, authoritative)
4-bit comparator (GT/EQ/LT), 8 inputs, De Morgan LT so no dust OR trees.
Arithmetic proven over all 256 vectors by scratch/recipe_check.py before
routing. Largest build in the repo. (Recipe file shipped in the sub4 commit;
green confirmed after.)
New dense builds this session: mux4, sub2, andor8, sub4, cmp4 = 5. With the
prior three (decode3, add2, chainmix) that is 8 total.

Running total: 16/19 green (14 original + sub4 + cmp4, of 19 recipes).
Red: alu4, cpu4 (architectural >=10-input wall), shift4 (LATCH chain).

### Lane pitch doubled past 9 inputs (5th alu4/cpu4 attempt)
10 input lanes at 4*spread collide in the approach cone. Pitch is now 8*spread
when a recipe has >9 inputs (ports and routing lanes together, so they align).
Gated so all green builds (max 9 inputs) keep exact geometry - verified
bit-identical on the 4 small + micro1. alu4/cpu4 still fail with the same
"no ground" on inputs. The wall is not spacing; it is the greedy routing
itself. Final answer: needs a bus/hierarchical router (new subsystem).

Session totals: 16/18 recipes green in recipes/ (alu4, cpu4 red). 8 new dense
builds total (5 this session: mux4, sub2, andor8, sub4, cmp4). shift2/shift4
moved to known-hard/ (gate-driven LATCH burnout, distinct architectural gap).

### Optimization: Big-O, measured clean (user request)
Profiled compose+sim. Sim is already event-driven O(events) with
change-checks before propagation - tight, left alone. Two safe wins:

1. lwire fast path: score 2 L-paths O(2L); a perfect L (bad=0) is
   GUARANTEED cands[0] (nothing beats 0, L wins ties), so skip the other
   36 corridors. Amortized O(L) vs O(38L) in open field.
2. _expanded memoized (lru_cache, frozenset): O(1) vs O(fp x 81) rebuild.

Clean before/after on a quiet machine (stashed to HEAD~1 for BEFORE):
  micro1: BEFORE compose 0.18s / AFTER 0.11s (39% faster). sim 0.48s both.
  decode3: BEFORE compose 21.4s / AFTER 19.6s (8% faster). sim 0.8s both.
All hashes identical (4 small + micro1 2925 verified).

Honest limit: hard builds are dominated by astar on doomed rungs
(decode3 rung 1: 28 searches, 8s; 3.3M ok() calls) and sim is O(2^n).
Those are structural (need fail-fast / parallel sim), not scoring.
Documented, not attempted in this pass.

## Night session 3 (DONE = all recipes green; item 2 dropped)
User simplified DONE to item 1 only: every recipe in redstone-mini/recipes
must generate + verify. New-build quota is gone (already at 8 anyway).
ASSUMPTION (as before): D:\redstone-mini is the target; D:\redstone-compiler
is a separate Rust project with no recipes.

Start: 16/18 green. Red: alu4 (10in/72g), cpu4 (7in/126g). Note cpu4 has
only 7 inputs, so the wall is NOT input count alone - it is total
gate-count congestion. known-hard/shift2+shift4 stay out (latch gap).

Plan: test ultra-high spreads (12/16/20/24) directly. Ladder stops at 10;
if 16+ gives room, add it. All runs detached + bounded (rule 7) with
Big-O-clean scripts (one process per recipe, no sleeps in shell).

### Spread 16/20 probed and rejected (4 fast fails)
alu4 @16/@20: "no ground for A2B2" (30s). cpu4 @16/@20: "no ground for
AL_AB1 / AL_O3" (8s/46s). Ultra-high spread does NOT move the wall, so it
is algorithmic (greedy, no lookahead), not spacing. Per rule 3, switching
to the maze backend at high grows (different algorithm, untried above
grow=2). 4 probes launched (alu4/cpu4 x grow 4/6), detached + bounded.

### Maze at grow 4/6: intractable (killed after 610s CPU each, zero output)
4 probes (alu4/cpu4 x grow 4/6) burned 2440s total with not one byte of
output. A single layout() call that grinds 10min+ on 72-126 nets in a
W x11 field is an exponential blowup, not slow progress. Killed.
Maze high-grow is rejected. run_maze.ps1 now hard-kills via Wait-Process
(layout() checks no deadline; rule 7 demanded the wrapper).

### Dead-gate elimination in alu4/cpu4 (correct, insufficient)
Both carried U=X AND 0 (always 0), C=AB OR U (=AB), S=X XOR 0 (=X).
Removed by substitution. scratch/recipe_equiv.py proves old==new on all
vectors (alu4: 1024, cpu4: 128). 3 fewer gates and 4 fewer routes each.
Did NOT green them: rung 1 still fails the same way (seals, not space).
Confirms the wall is greedy-ordering, not gate count. Restarts already
explore all orders (25 per rung), so single rip-up would not help either.
The wall stands: needs a bus/hierarchical router (new subsystem).

### Backup plans queued (full-ladder runs in flight, 3h budgets)
1. 100 restarts (committed, gated >9): if 25-restart ladder fails, relaunch.
   Rationale: 25 orders under-samples a 72-gate space; 100 gives 4x samples.
2. Nearest-edge levers (not yet implemented): all input levers sit on the
   west edge, forcing every route to cross from west. For >9 inputs, place
   each lever on the edge nearest its loads centroid. ~20 lines, gated, so
   greens keep the banked-lever contract. Only for red builds.
3. Territorial placement (last resort): partition field by input cone.
   Invasive; only if 1+2 fail.

### Seed-diverse ordering (7th approach, in flight)
compose() is deterministic; the maze backend already uses seeds. Added
REDSTONE_ORDER_SEED: ties in confinement ordering break by hash(seed:name)
instead of name. Topology + precede preserved; only tie order shuffles.
Off by default (micro1 SEED=7 greens bit-identical). 6 seeds x 2 recipes
in parallel, 900s budgets. If ANY trajectory routes, DONE. 2 full-ladder
(25-restart, pre-seed) runs also in flight with 3h budgets as backup.
