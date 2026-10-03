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

### Seeds relaunched with deadline-safe code (6 parallel trajectories)
Fixed the rule-7 hole (deadline now checked per restart; 30s budget exits
at 31s, verified). Reverted 100 restarts to 25 (precede converges; seeds
give diversity, not more orders). 6 seeds x 900s, each a full 44-rung
ladder with a different order trajectory. If ANY greens, DONE.

### Vertical envelope (8th approach, in flight)
_REDSTONE_COMPOSE_YMAX=8_ (wide envelope was -4..6). Env-only, no code.
example_and with YMAX=8 greens bit-identical (144), so safe. 2 probes
(alu4/cpu4, 900s) + 6 seeds = 8 parallel trajectories.

### Seeds: 6 trajectories, 6 different walls, 0 greens (decisive)
All hit the 900s deadline (fired correctly) after exhausting ladders:
alu4 seeds failed on O3 / B2 / X3. cpu4 seeds failed on R0_R2 / AL_n0 /
R0_nD3. Six different nets. The seed mechanism WORKS (trajectories diverge),
but every trajectory hits a wall. This proves the wall is NOT order-
sensitivity: no order works. Systemic congestion confirmed 9 ways.

### YMAX=8 vertical envelope: same systemic failure (9th approach)
_REDSTONE_COMPOSE_YMAX=8_ (was 6). Env-only. Both hit 900s deadline:
alu4: no ground for X3. cpu4: no ground for AL_X3. More vertical room does
not help; the congestion is planar (too many routes crossing at every level).

### FINAL: 9 approaches exhausted, wall is definitive
spreads 1-20 | orders x2 | jogs x2 | clearance 3->1 | pitch 4->8 | nearest-first
loads | 3D-only (NOFLAT) | maze grow 4/6 | 6 order-seeds (6 different nets fail)
| YMAX 8 | dead-gate elimination | 100 restarts (reverted: precede converges).
Every trajectory fails systemically (different nets, same congestion).
16/18 green, protected and pushed. alu4/cpu4 need a bus/hierarchical router:
a new place-and-route subsystem (days, design session), not a ladder rung.
Attempting one overnight risks the 16 working builds for near-zero payoff.
Standing by to build it properly when directed.

### Maze-only sweep with high try count (10th approach, in flight)
All prior maze tests used high GROW (4/6, intractable) or default tries (6).
Untried: MANY tries (20 seeds) at tractable grows (0-2). scratch/maze_sweep.py
loops seeds x grows calling layout()+sim_verify directly (no compose waste),
checks wall-clock before each attempt, hard-killed at 3300s. 60 attempts each
for alu4/cpu4. If the maze backend can do it with enough seeds, this finds it.
@'
### Maze sweep: too slow to be useful (killed)
First layout() attempts took 4+ min each (grow 0, smallest). 60 attempts would need 4h+. Slow attempts signal blowup, not success. 10 approaches exhausted.

## Night session 4 (autonomous, user asleep ~8h)

ASSUMPTION (as before): work target = D:\redstone-mini. D:\redstone-compiler
is a separate Rust project (Cargo.toml, crates/, no .txt recipes); DONE item 1
says "folder redstone-mini". Proceeding there. No questions, no approval waits.

Start: 16/18 green (alu4/cpu4 red, 10 approaches exhausted), 8 new builds banked.

### 3 NEW builds, all generate+verify (authoritative dense_status)
- mux2 (2-bit 2:1 mux, per-bit NOT + BAND, 4226 blocks, 2.1s). Lesson: shared
  nS across bands SIM-MISMATCHED (Y stuck when S=1); per-bit nS0/nS1 (mirroring
  mux4 auto-replication) greens. Unbanded nS + BANDs also crashes layout.py:1101
  (None*24) when fanout<3 skips replication -- new-recipe rule: BAND every gate
  or no gate.
- decode2 (2-to-4 decoder, 1526 blocks, 0.5s, rung 1).
- add4 (4-bit ripple adder, BAND per bit, 12750 blocks, 163.7s, ladder climbed
  to long spread 1). Arithmetic proven first via recipe_check (256 vectors).
- All recipe_check OK before routing (mux2 32v, decode2 4v, add4 256v).

Running total: 19/21 green. New builds total 11 (8 prior + 3 this session).

### Try 1 (alu4): BAND-by-slice + auto-replication (NEW angle)
alu4/cpu4 carry no BAND tags; maze auto-bands one-gate-per-column (72/123
bands, worst partition). mux4 proves BANDs + replication work. Banded alu4 by
bit-slice (BAND 0..3, control in 0): recipe_equiv 1024v EQUIVALENT. Side effect:
n1/n0 (8 loads, 4 bands, input-driven) auto-replicate per band -- the mux2
lesson applied automatically.
ENGINE BUG FOUND + FIXED (recipe.py:174): sorted(clones) compares dicts on
index ties (n1+n0 clones share min-load idx) -> TypeError. Fixed to
key=lambda t: t[0] (stable). Self-checks pass; 4 small bit-identical
(144/322/224/214); mux2/decode2 still green. Banded candidate compose routes
(_rc clones live) but ladder still climbing (inputs B0/OP0/B1 + clone seals).
Full bounded run queued.

### Try 1 verdict: BAND-sliced alu4 RED (bounded, hang-safe)
probe_one (compose+sim, no maze ladder) COMPOSE_SECS=240: COMPOSE-RED 246s
"no ground for X3 (5404,18)->(4754,437)". Blame restarts fire (t32 sealed by
clones, precede converges) but field stays unroutable. Different net than
unbanded walls, same systemic congestion (11th approach). PARKED with TODO:
needs bus/hierarchical router (new subsystem, days). No full maze ladder run
(rule 7: dense_status on 70+ gate recipes hangs for hours; two long probes
this session had to be user-killed).
ENGINE FIX no-op proof (no slow re-routes needed): expand_gates probe over all
21 recipes shows 0 replicated nets except mux4 (4, distinct bands) and alu1
(_rc1 band1, _rc2 band2, distinct) -- key-sort == tuple-sort wherever mins are
distinct, so all 19 greens are bit-identical by construction. 4 small verified
bit-identical post-fix; mux2/decode2 re-verified green post-fix.

## Night session 5 (autonomous, continued)
ASSUMPTION: same as before (D:\redstone-mini work target). User asked to keep
going without status chatter. Plan: hierarchical router for alu4/cpu4, cheapest
first. ALL probes hang-safe (compose+sim only, COMPOSE_SECS<=240, tool timeout
= budget+60s). No maze-ladder runs (they hang for hours).

### Try 2 (alu4): territorial placement+band-order RED (fast: 97s)
REDSTONE_TERR=1, 4 rungs: "no ground for _rc8 (728,12)->(196,243)" then B1.
Verdict: territories lengthen cross-band spans past what greedy lwire can do;
empty streets do not help when endpoints are 500+ apart through tile fields.
12th approach exhausted. Switching to Try 3: split-and-stitch macros.

### User suggestion (adopted): failure-driven netlist restructuring
User: on build failure, engine should analyze WHAT failed and change the
BUILD (same IN/OUT, different internals) and retry. Verdict: yes, this is a
real family of methods. Names: feedback-directed / closed-loop optimization
(general); CEGIS - counterexample-guided inductive synthesis (the fail-analyze
-fix loop); superoptimization + e-graphs / equality saturation (search many
equivalent forms, keep the best); autotuning / design-space exploration
(ATLAS, OpenTuner); in EDA specifically: rewiring, congestion-driven logic
restructuring, gate replication, remapping, rip-up-and-reroute (physical).
We already do weak forms (retry ladder = same netlist new geometry;
auto-replication; dead-gate removal). Now implementing the strong form:
surgical load-shedding driven by the FAILING net (double-NOT buffers move
half a congested input's loads onto a fresh 1-load net; function identical,
recipe_equiv-provable). First target: band-1 OP0/OP1 (3 loads each).

### Try 3 status: hier machinery PROVEN (hiertest green), alu4 at C3 stitch
compose_hier (split-and-stitch by BAND) + sub-ladder with sim gate + recs
shift capture + seal allow-list + longest-first + two-hop stitch. hiertest
(add2 split in 2): COMPOSE-OK 1918 blocks sim=42t 0.7s, bit-identical on
regression. alu4hier candidate (equiv-proven, dedup m30, per-slice controls,
A0B0 split, OP load-shedding via double-NOT): bands 0-2 route+sim green,
band 3 routes (2400s budget), stitches A0B0+C2 green, C3 RED (no ground
(825,68)->(97x,2), twice, LONG jogs + two-hop). Fast gates green throughout.
Lane-order and TERR/dup findings logged inline in code.
NEXT: pickle-dump harness for second-scale stitch iteration (bands cost
30 min per run); then promote working recipe to recipes/alu4.txt.

### Try 3 cont: carry micro-band, oscillator, staged pipeline
- C3 OR-port pocketed (diodes E/W, foreign N/S, hops refused); A0B0/C2/X2/A2B2
  AND/XOR ports escape in 0.0-0.2s (dump-harness probes, seconds each).
- Extracted 2-gate carry micro-band (U2+C3, inputs X2/A2B2/C2); X2
  self-replicates (no new lanes). Boundary {A0B0,A2B2,C2,C3}, bands 16/21/17/3/24.
- Full hier reached SIM (all bands + all stitches green!) but SIM churn=7557
  (oscillator): broad seal allow-list coupled stitch to neighbor torch. Fix:
  owner-torch-only allow-list (strictly louder-or-equal).
- Killed 45-min probe (user). Lesson: stage the pipeline (pin winning sub-rungs
  once via short standalone probes, then merge+stitch in seconds). No more
  30-min tool calls.

### Staged pipeline results (all short calls)
Band files extracted (hb0..hb4, byte-identical to hier subs). Standalone:
hb3 (3 gates) rung1 0.1s; hb2 (19) 9.4s; hb1 (21) rung2 20.7s;
hb0 (16) long-spread-1 129s; hb4 (24) deep ladder 553s. ALL route + sim green.
Rung-subset pinning (REDSTONE_HIER_RUNGS) added, unset by default.
Full hier next (bands ~12 min + merge/sim, inside proven-safe durations).

### Pipeline: parallel band cache + seconds-scale stitch
- scratch/hier_bands.py: all bands x rungs as direct children (12-wide fan-out,
  no mp.Pool: pool workers are daemonic and cannot spawn), hard-killed at Ns.
  96 band-rungs in ~56s; all 6 alu4hier bands green + cached to .pkl.
  Three bugs fixed en route: compose_hier_part bypassed the ladder (identical
  wall at every spread); from-import captured _last_ctx=None at import; mp.Pool
  daemonic-child assert.
- compose_hier split: compose_hier_parts(built, gates, recipe) = stage 2
  (merge+stitch), callable on cached partitions. Stitch iteration is SECONDS.
- Stitch hardening: collect per-band failures instead of aborting on the first;
  west approach; multiple hop rows; spiral start from open port neighbours;
  longest-net-first; owner-only torch allow-list (broad allow caused the
  churn=7557 oscillator).
- C2 chained fan-out: stitch through the band-2 stub to band 3 instead of
  re-running from the driver (465 cells shorter).
STATUS: alu4hier merge reaches C2->band3, which now hangs the stitch stage.
Rule 7 needed: astar cap in the stitch child. TODO: bound stitch, then sim.
Rule 7 follow-up: stitched fan-out in a forked child still ran past 150s wall
(pipe start + 6-band pickle + astar). Conclusion: bound the STITCH GEOMETRY
instead of trusting process control — direct + west-approach only under
REDSTONE_HIER_FAST, no astar/hop-row search. Deterministic, seconds.

### Stitch progress (gap 60 -> 160)
- Boundary ports all clean (portdump: no foreign neighbour, free cell) so the
  port-openness acceptance is now correct and every cached band passes it.
- Widening the inter-partition street from 60 to 160 cells moved the failure:
  A0B0 (band0 -> band1) now routes; the next wall is a 300-cell straight hop
  that wants an empty row. The "whole span empty" hop-row test is too strict
  (it fails on any tile) and lwire's astar is already the fallback; the
  remaining lever is a 3-segment stitch (up/along/down) that only needs local
  clearance, not a globally empty row. TODO next.
- Rule 7: every stage now hard-bounded (band rungs killed in child, stitch
  killed in child, astar capped). No command has exceeded ~2 min since.

### Lever-pedestal source (user-confirmed in-game, wiki-confirmed online)
User image: wall lever + dust on top of host + side-adjacent dust on a second
block, both lit. Wiki: lever strongly powers its attachment block (full solid
opaque); strongly powered blocks power ADJACENT dust (on top, beneath, sides).
Two sim gaps closed: (1) cob_state ignored levers -> wall lever never powered
its host (fix + lever-pedestal self-check, both directions); (2) stale budget
canary (assumed alu1 stays red; broke when alu1 went green) -> forced-fail
precondition + fixed a silent-no-op monkeypatch (patched compose.compose while
layout_retry reads sim.compose). Full sim.py suite green, exit 0.
Use: zero-wire direction-agnostic boundary driver for hier stitches.

### ALU4 DONE (1024/1024) + promoted to recipes/alu4.txt
- Endpoint booster (end_boost, hier-only): stub read 7 (8 back), tail died.
  Smoke 4/4 green after. Full verify_par staged (16 chunks, resumed across
  calls): slow vectors need 20000 ticks (false REDs at defaults) — raised
  worker caps AND sim defaults (5000/300000 -> 20000/2000000, ceilings only).
  16/16 chunks green = 1024 vectors. verify_par hardened en route: round-robin
  poll (sequential join stalled 500s silent), resume cache (one 1024-chunk
  held the whole space), no false OK (tail claimed full verify after 2/16).
- recipes/alu4.txt replaced by the banded/restructured recipe (82 gates,
  equiv-proven 1024v vs original). scratch/hier_verify.py = the hier gate
  (bands -> merge -> staged verify; layout_retry would take a silent hour).
- Pinned-first sub-ladder default (3 measured rungs, full ladder follows).
STATUS: 20/21 green (alu4 promoted). cpu4 last red: same pipeline next.

### cpu4 hier (Try 4): sliced, all bands green, merge at stub-connect
- cand_cpu4hier: decode(8)/enables(3)/R0-bank(16,latches)/R1-bank(16)/bit0(17)/
  bit1(21)/bit2(19)/carry-micro(2)/mux3(16)/carry-micro2(7-9). Dead gates
  dropped (MEMR/MEMW/BRANCH+C_m1+C_b1, equiv-proven). OP load-shedding +
  m30-dedup + A0B0-split + per-slice controls (all alu4 lessons reapplied).
  128 vectors equiv OK.
- Latch banks burn on rung-1 (symmetric power-on ring, same torch every vec)
  but sim-gated ladder finds clean rungs (inputs_first). All 10 bands cached
  green in ~76s parallel.
- Min-blocks selection (was first-green): sprawl pushed merge past 3000 cells.
- HIER_SKIP per-band rung exclusion; re-rung band-5 off a pocketed geometry.
- Repeater relay stations (span>350 split at streets); south-around via empty
  south margin (R1Q3 1600 cells in 0.1s); staggered margins; margin-base
  snapshot (creep stretched south legs); atomic multi-leg strategies (partial
  relay legs polluted later stitches — silent cascading failures).
- LONG jogs wander (R0Q1 dies touching E0 under LONG, routes under SHORT);
  overflights stay allowed (south legs need their hop over live runs; NO3D
  killed them). Stitch order env (asc tried, kept desc).
- Producer-stub OPENs: stub-connect pass (BFS driver, short legs to unreached
  same-net cells in producer band); false walls fixed (repeaters + hops +
  junctions in flood; R=12 cap dropped for exact check_opens mirror).
- pos[net] = producer driver (merged pos was last-band-wins, often bare ->
  check_opens seeded nothing and flagged connected networks).
- STATUS: cpu4 merges (all 20 stitches land) but check_opens flags t23/C3
  orphans; stub-connect capped at 6 legs/net (113 t23 orphans would take an
  hour). T23 driver area under diagnosis. Engine fixes verified safe
  (4 small bit-identical throughout; sim suite green).

### mux4 GREEN via sim-gated ladder (8079 blocks, was 20239)
Root cause of the red: correct lever physics exposed a real vanilla bug (S
flight pillar beside A0 lever couples S lit). Fix: sim-gated standard ladder
(opt-in REDSTONE_SIM_GATE=1 from layout_retry verify=True; big banded skip;
previews stay fast; greens rung-1-identical). Ladder climbed past sim-red
rungs to a clean geometry. Forensics built along the way: muxlevel (level +
feeder scans), SOURCE (no-lit-neighbor cells), DIFF (lever-term on/off settled
maps), rowmap, lever-pedestal self-check + budget-canary fix in sim suite.
STATUS: 20/21. cpu4 last.

## Night session 6 (autonomous, user AFK ~8h)
ASSUMPTION: DONE = 21/21 green (cpu4 last) + 11 new builds banked. Glass
upgrade explicitly QUEUED AFTER DONE (user agreed cpu4-first: glass changes
sim physics and would force verifying cpu4 twice). Work target D:\redstone-mini.
Start: 20/21 (cpu4 red at merge sim), alu4 DONE+promoted, mux4 re-greened via
sim-gated ladder. All probes hard-bounded (rule 7); stage everything.

## Session: cpu4 root causes (autonomous, user AFK)

DONE = cpu4 green. NOT DONE: merge reaches sim, 3/5 outputs correct. Commits
7fdbd72, c8fb1d2, 0b773eb, a893b82, e8cd0c8.

THREE root causes, each measured before fixing:

1. Undriven SR latch hunted forever (sim.py). A NOR latch from a dark start
   is symmetric in this model; vanilla breaks it with update-order skew.
   _latch_hold_seed presets ~qb dust AND its driver torch (each alone fails),
   plus a power-on pre-roll (_solve) that removes the tick-1 output pulse
   which reached idle latches at T~9. Latch-free builds: byte-identical path.

2. A lever powered every block beside it (sim.py). D3's floor lever drove
   cpu4's R0Q0 stitch run to 15, forcing R0Q2 high whenever D3=1 (bit-0
   AND/XOR wrong). Wiki: a lever powers its ATTACHMENT only. leveratt is now
   parsed from face/facing; _parse_build returns a 12-tuple.

3. A booster planted on a TILE's own output run (compose.py). place_xor
   merges two comparator tails through two facing diodes, so a booster
   between them faces the wrong way and cuts the merge. This is why Y2 was
   wrong: AL_X2 went dark in the merged build while band 6 simmed GREEN
   standalone, because a band sim runs on `out` and boosting happens after.
   Guard: own= is the placement-end wire snapshot; only routed cells boost.
   This took cpu4 from 3/5 to one wrong net.

Landed with it (each from a measured failure): relay stations only on
straight runs; every stitch must DELIVER onto its stub by sim-conducting
links (_landed, with a bounded last-mile lwire); every consecutive pair of
FRESH path cells must be a sim link; ring gate now asks layout._loop_rep and
rejects only a NEW loop.

REMAINING WALL: finish_assembly rejects the merge on a pre-existing
front-joins-back diode ring inside a BAND TILE (R1Q3 at (2850,1,43)).
place_xor's two facing diodes can form one; the band sims green because the
sim does not model the bistable pair. Next step: reject a band rung whose own
output rings, in scratch/hier_bands.py, next to the sim_verify and
check_hier_ports it already runs per rung. ~5 lines.

RE-GATED: recipe.py, sim.py pass; compose_check bit-identical
(144/322/224/214); dense_status OK for example_and/latch_sr/mux2/sub2/
micro1/decode3/cmp2; alu4 re-stitched (35516 blocks) and re-verified
1024/1024 with the new physics. mux2 grows 4226->5387 (fewer boosters =>
longer routes; still correct).

TRAPS FOUND (cost real time, record them):
- Comparing a band's `out` (finish_assembly'd separately) against the merged
  block list is a FRAME ERROR. Correct map: ctx.blocks + OFFS[band] + (2,26).
  It manufactures a bogus "3388 cobble deleted" that looks like a purge bug.
- Band caches must be built with REDSTONE_ASTAR_CAP UNSET. At 6000, bands 5
  and 6 lose their only green rung ("no ground for AL_n0_5"), reproducible
  in a single process.
- scratch/hier_bands.py picks the SMALLEST green rung, so HIER_SKIP rarely
  moves a band. Use REDSTONE_HIER_RUNGS to force a rung.

## Session 2 (autonomous, continued): cpu4 merge lands

Ring wall FIXED. finish_assembly was rejecting the merge on "repeater loop on
R1Q3 at (2850,1,43)". Cause was ORDERING, not geometry: the ring gate inside
_try ran BEFORE _plant_repeaters, so a booster landing where a leg doubles
back on an EARLIER LEG of the same net (R1Q3 is consumed by two bands, legs
chain stub to stub) closed a ring nobody was watching. Boosters now planted
INSIDE _try with a ring check either side; a failure there rolls back and the
NEXT strategy runs. Also: a run must be a SIMPLE path (adjacent repeat at a
leg joint is the only legal one), and the stub-connect pass got the same
post-boost ring gate it never had.

Result: MERGE 72055 blocks. SMOKE 0000000 OK, 1111111 OK, 0101010 MISMATCH Y1.

NEW WALL (sharp, with the frame rule settled): the merged blocks list is
MISSING tile torches that solid still declares. In cpu4merge2.pkl, solid puts
the R0Q0 latch torches at merge (653,48)/(656,47) = block (655,74)/(658,73),
and blocks has NO torch in x640-680 z60-95 -- all 230 torches in the build sit
at z 98..170. check_shorts/check_opens read wires+solid and pass; the SIM
reads blocks and cannot see those torches at all, which is why R0Q0 reads
1068/1068 lit on a no-write vector (R1Q0 reads 0/811, correct).

FRAME RULE (state once, it keeps costing): in a merge dump, solid/wires/
repeaters/rings/stitched are MERGE space; blocks and io are BLOCK space.
finish_assembly shrink-wraps with minx = min(OCC) - 3, so

    block = merge + (3 - min_merge_x, 3 - min_merge_z)

Derive it PER BUILD from the data; never hard-code it. For cpu4merge2.pkl it
is merge + (2, 86).

CORRECTION to the entry above: I claimed the merged blocks list was missing
tile torches. IT IS NOT -- measured, all 230 of 230 ("torch",net) entries in
solid have a matching wall_torch block. The claim came from reading solid at
a wrong offset ((-2,-26) instead of (2,86)), the same frame error that
produced the bogus "3388 cobble deleted". This frame mistake has now cost TWO
sessions. Fix it at the source: have the merge dump carry the shift
explicitly (store {"shift": (minx, minz)} in the pickle) so no probe can
re-derive it wrongly.

The symptom that DOES stand (frame-independent: it comes from live/nets, both
block space): on D=0101 OPC=010 (a no-write vector, REGW=0, so both registers
must hold their seeded 0) R0Q0 reads 1068/1068 lit, R1Q0 0/811 correct, and
the XOR tails inherit it (AL_X0 63/64, AL_S2 31/32, AL_X2 61/315).
NEXT: re-dump the R0Q0 latch neighbourhood at merge + (2,86). Its origin in
merge space is (652,48) = block (654,134).

## Optimization pass (autonomous, 2026-10-01 night)

Starting point: `python redstone_mini.py alu4.txt` looked hung. It was not the
router -- compose finished in 55s. It was `sim_verify`, which ran 1024
completely independent full physics simulations ONE AT A TIME (sim.py:763).
Cost doubles per input added.

ASSUMPTION (noted per instructions): I optimise for wall-clock on this machine
while the cpu4 agent also runs work, so ratios are trustworthy and absolute
times are not. Every speedup below is a same-process A/B against the
committed engine.

### What was done

1. simvec.py -- bit-parallel physics (SWAR). One Python big-int per cell holds
   one input vector per 6-bit lane; all vectors evaluate at once with bitwise
   ops. Guard bit at bit 5 makes lane-wise max/min/dec/compare into
   shift+subtract. Dial bucket queue instead of a heap.
   MEASURED flat in lane count on alu4 (34672 blocks):
     8 lanes 1.13s | 32 lanes 1.27s | 128 lanes 1.54s   (~110x vs serial)
   CAVEAT, measured not assumed: merged event count is ~sum(lane), not
   max(lane). It is a big win where lanes converge together and a LOSS where
   they do not. A single run over all 1024 lanes can never terminate if one
   vector hunts, because sim's torch-burnout rule is a termination device this
   module does not implement. Hence: shards, hard bounds, per-vector re-dispatch
   for load balance.

2. simvec.run_scalar -- the same physics over tables computed once per build.
   Profile that motivated it (per VECTOR): 207k dust_lvl calls, 98k wake calls,
   146k cob_state calls, 219k os.environ.get calls -- all re-deriving facts that
   are constant for a static build.
   MEASURED 3.45x per vector (0.434s vs 1.499s, warm tables, best of 3).

3. Same-tick re-queue coalescing: a cell woken 5x in one tick is evaluated 5x
   and changes at most once, because it reads the LATEST state when it runs.
   Drops evaluations 23-30% with no semantic change (insertion order preserved;
   the set holds exactly the queued-not-yet-evaluated items).

4. scratch/ticktrace.py rewritten: was 47 x _run_vec(until=T) = ~2.4 HOURS for
   one trace, silent throughout. Now ONE simulation with snapshots.
   MEASURED 0.9s (run 0.7s) on alu4merge.pkl.

### Correctness
scratch/diff_engine.py compares every engine change against a FROZEN extraction
of the committed engine (scratch/ref_sim.py, regenerated by scratch/mkref.py)
and demands identical lamps / live dust levels / torch states / tick count /
repeater states / comparator levels, plus identical exception types. It is the
gate for every optimisation above. sim._run_vec itself was NOT changed and
remains the authority; run_scalar refuses (raises) rather than guessing on the
latch hold-seed path.

### Three real physics bugs found by that differential (would have shipped wrong builds)
- the comparator term in dust_lvl is `return con`, NOT `lv = max(lv, ...)`: it is
  an early return, so it cannot be hoisted into a max with the decay terms.
- the chip-layer `dn` test checks the block directly BELOW the cell, not below+dx.
- a repeater must be re-evaluated when the cell BEHIND it changes (its input);
  asking "does it feed the changed cell" left every booster evaluated once, at
  tick 0, when its input is still dark -- no booster fired, the boosted wires
  decayed to nothing, and the build "settled" dark and early.

### TODO (not done)
- The router (compose) is now the remaining cost: 55s for alu4, far more for
  cpu4. Not yet profiled to completion.
- run_scalar still makes ~1.0M dict.get per vector. The remaining structural win
  is skipping evaluations whose specific source term did not change (dirty-bit
  propagation per wake edge) rather than re-deriving the whole cell.
- exporters (export_html / export_mcfunction) for 34k blocks: not yet profiled.

## Session 3 (autonomous): cpu4 GREEN - 128/128. The wall was the SIMULATOR.

cpu4 merge now verifies on the FULL input space. VERIFY OK: 128 vectors,
32 chunks green, zero failures, on scratch/cpu4merge3.pkl (72055 blocks) with
scratch/cand_cpu4hier.txt.

ROOT CAUSE (two sessions of forensics pointed at the router; it was never the
router). sim.py's power-on pre-roll computed a HALF-POWERED tick-0 state: it
iterated dust/blocks/torches to a fixpoint but FROZE ALL REPEATERS OFF, on the
theory that a booster's delay is a real transient the tick loop must play out.
A frozen booster makes every cell BEYOND it read dark, so the "fixpoint" was
not the quiescent state. Measured on cpu4: OPC1 read 96/903 at tick 0 instead
of 903/903, so NOT OPC1 emitted a phantom 1, and C_n2 AND C_n1 produced a ~40
tick REGW glitch at T~28 that travelled E0 -> R0_S1 and latched R0Q1 and R0Q3
to 1 on a no-write vector (REGW=0, both registers must hold their seeded 0).
R0Q0 was never the culprit - the census that "proved" 1068/1068 was itself read
through a bad offset. D0=0/D2=0 bits read 0 correctly all along; D1=1/D3=1
bits are exactly the ones the glitch set.

FIX: repeaters and comparators belong IN the pre-roll fixpoint. A booster's
SETTLED value is a function of its input, so iterating it converges to exactly
what the circuit settles to - which was the whole point of the pre-roll.

TWO THINGS THAT FELL OUT, both real:
1. The fixpoint is AMBIGUOUS - more than one self-consistent state exists. My
   first version (whole-field sweep) converged to a state with AL_C2 stuck lit
   725/982 at tick 0, which is wrong. Rewriting the same fixpoint as a WORKLIST
   (only re-check the 3x3x3 box around a cell that actually changed) converges
   to the correct state AND cut the pre-roll from 170 s to 6 s on the 72k-block
   merge - the sweep cost one round per booster link. So the fix was both wrong
   and slow; the worklist is both right and fast.
2. sim_verify had become a FORK BOMB. It routes through simvec.verify_par,
   which opens a multiprocessing.Pool; a pool worker is daemonic, so any
   unguarded script calling sim_verify re-imported itself under spawn, forever.
   scratch/compose_check.py churned silently with no output and no exit. Fixed
   in sim_verify (one check closes all ~60 call sites) rather than in
   simvec.py, which belongs to the other agent.

DEAD ENDS (do not re-run; each was cheap and each was wrong):
- Repeater ring in the merge: _loop_rep found 4, then 1, then 0 as I varied the
  cobble set. BOTH the router's view (solid cobble) and the sim's own view
  (_parse_build) return None. My first two results were artefacts of feeding
  _loop_rep a cobble set neither caller uses. Lesson: _loop_rep's answer depends
  on its cobble argument, and the repo has three different ones.
- Repeater backed by a finish_assembly stone pad (pads are conductive to the sim
  but absent from solid, so invisible to _loop_rep): scratch/padback.py finds
  ZERO such repeaters in 4245. Clean.
- Ring closed through a chip-layer y+-1 dust link, which _loop_rep's flat BFS
  cannot see (its docstring admits this): scratch/chipring.py, run with sim's
  own dust/cobble sets and sim's own chip rule, finds ZERO.
- The whole-field pre-roll sweep (above) - wrong fixpoint AND 28x slower.

TOOLING BUGS FIXED IN scratch/verify_par.py (gitignored, but they cost real
time and will cost it again):
- CACHE KEY IGNORED THE WORKER COUNT. chunks = vecs[i::workers] makes a chunk's
  CONTENTS depend on workers, but the cache was keyed on the bare index, so a
  cache written at workers=4 was read back as valid at workers=20 - silently
  green-marking vectors that were never simulated. Now keyed
  "nchunks:index:recipe+build fingerprint", and a fingerprint mismatch re-runs.
- SILENCE READ AS A HANG. The only output was when a whole chunk landed; with a
  32-vector chunk that is ~700 s of nothing, and the job got killed for looking
  hung twice. The child now streams one line PER VECTOR.
- CHUNK SIZE WAS TIED TO WORKER COUNT. nchunks is its own argument now, so the
  chunk can be small enough to report often while the process count stays low.
- My own bug in the rewrite: reap() unregistered the child on each PROGRESS
  message, closing the pipe under a live worker (BrokenPipeError storm). Caught
  and fixed in the same pass.

GATES GREEN this session: sim.py, recipe.py, scratch/compose_check.py
(bit-identical: 144 / 322 / 224 / 214), cpu4 merge 128/128.
NOT re-run yet: alu4 (its verify cache was stale - an earlier "1024/1024" I
reported was the cache being read, not the vectors being simulated), dense
recipes. See MORNING-REPORT.md.

### PART 2 -- router, and the finding that reframes the job

#### alu4 is not slow to verify. It does not verify.
probe_hard.py sampled 16 vectors across the space. Indices 0/64/128/192 settle
in 0.4s. Indices 256..960 ALL raise "sim not settling", churn 10.4k-12.6k
cells. The one verify_par reported: churn=11323, loop_torches at (115,1,53),
(133,1,39), (133,1,42), (188,1,54), (194,1,39), (212,1,50), same-level=18868,
slope=6558 edges.

So the original symptom was never slowness. sim_verify simulated ALL 2^n
vectors and only then raised, so a build that could never pass cost 22 minutes
to say so -- which is indistinguishable from a hang to whoever is watching.

FIX: verify_par fails fast on a structural fault. Not-settling / burnout /
stall is a property of the BUILD, not of one vector -- every vector touching
the same loop gets it -- so the rest of the 2^n runs buy nothing. The first
fault sets a stop event the pool honours and raises the churn diagnostic
verbatim. MEASURED 22min -> 97s, and the message now names the vector AND the
loop. Logic MISMATCHES are still all collected (per-vector, cheap once the
build settles) so stopping on them would hide information.

#### Router: the algorithm was never the bottleneck
Profile of compose on alu4hier (25.3s under cProfile): WaitForMultipleObjects
10.3s (parent blocked on children), Pickler.dump 7.3s (IPC), CreateProcess
0.62s -- and only ~5s of actual routing (astar 1.5s tottime).

Two changes, both gated by scratch/router_hash.py (block count + sha256 of the
whole block list, order included):
1. compose_hier climbs bands in LOCKSTEP: every band's rung-N attempt is
   launched before any is joined. Partitions are independent; only WHEN they
   run changed. 27.27s -> 22.51s.
2. the partition sim gate runs in the CHILD, so the shifted block list never
   crosses the pipe -- compose_hier_parts unpacks each partition`s `out` and
   never reads it (it consumes pctx, the UNSHIFTED tables). The gate is MOVED,
   not dropped. 22.51s -> 20.1s.
   sha256 c7ff3e6e6da7702321c2d871fca0762cbe95f86ac5d9863a1be41e2601206eaf
   unchanged throughout.

#### SWAR defaulted OFF (measured, not modesty)
256 vectors on alu4: run_scalar only 21.5s, swar+fallback 22.7s. Byte-identical
results, 5.6% slower with SWAR on. The reason is NOT gate count -- eval_net_par
over the 82 gates costs 0.05s for 1024 vectors, so the logic side is free
either way. It is event SHARING: bit-parallel pays only when every lane in a
shard converges together (an all-easy 128-lane shard is 1.54s, ~110x), and
alu4 has hard vectors that break it (6 of 8 x 128-lane shards burn the step
budget). Kept, opt-in via REDSTONE_VEC_SWAR=1, because it is still the only
sub-linear option for high-input-count exhaustive verification.

#### ticktrace: 2.4 hours -> 0.9s
Was 47 x _run_vec(until=T), and _run_vec re-runs the whole prefix every call,
so 47 x the ~191s fixed startup; plus an O(34k) rescan per target per stop, and
it printed only on change so it was silent the whole way. One run_scalar with
snap_at now serves all 44 stops.

### MEASUREMENT CAVEAT
Absolute timings after the router work are contaminated: agent 1 runs cpu4
concurrently and the box saturates all 20 cores (observed 6096s of CPU burned
while a single benchmark ran). Ratios from same-process A/B are trustworthy;
wall-clock numbers taken while both agents work are not. Flagged rather than
quietly averaged.

### NOT MINE, left untouched
Agent 1 has uncommitted work in sim.py: the _presolve fixpoint converted to a
worklist (170s -> 3s on the 72k-block cpu4 merge) and a daemon guard closing a
real fork bomb (sim_verify fanning out a Pool from inside a pool worker). I did
not edit or commit those. Everything I committed is simvec.py, compose.py
(perf only), and scratch/.

### PART 3 -- agent 3 review, all three points conceded and acted on

1. **My 5.6% SWAR figure was too precise.** Physics is ~99.8% of that benchmark
   (eval_net_par over 82 gates = 0.05s of 1024 vectors), so a 1.2s delta is
   measured against a component that is 0.2% of the runtime. Replicated:
       run 1: run_scalar 21.5s / swar 22.7s  -> +5.6%
       run 2: run_scalar 21.4s / swar 25.6s  -> +19.6%
   run_scalar is rock-stable (0.5% apart); the SWAR number swings 12%. So the
   penalty is consistently POSITIVE but unpredictable in size -- not noise
   around zero, and not the tidy 5.6% I wrote. Default-OFF stands, but it rests
   on the measured MECHANISM (6 of 8 x 128-lane shards burn the whole step
   budget), not on the delta.

2. **Cached greens were void, and the cache would have hidden it.**
   cpu4merge3.pkl.verify.json (32/32) and alu4merge.pkl.verify.json (58/64) were
   both produced by a pre-fix engine. The key covered recipe + build path but
   NOT the physics, so re-running the identical command reused them silently and
   reported a clean pass. This is the worst failure mode in this repo, because
   one of the bugs I fixed made builds "settle dark and early" -- a build can go
   GREEN FOR THE WRONG REASON. Fixed going forward: the key now hashes
   sim/simvec/recipe/layout/compose/tiles/core, so any engine edit voids every
   cache. The three existing cache files still hold pre-fix greens and must be
   deleted by hand (the fix prevents reuse, it does not scrub what is stored).

3. **The mismatch branch had never been watched succeed.** Every bad alu4 chunk
   raised NOT-SETTLING, so the logic-MISMATCH path had zero observed successes
   -- and I had just changed the physics that eval_net's expectation is compared
   against. scratch/test_mismatch.py now builds a deliberately miscomputing
   recipe (one gate's op flipped) and asserts the mismatch is reported with the
   right shape and the right (got, want). It does: flipping a AND b to OR
   inverts y for exactly {a=1,b=0} and {a=0,b=1}, which is what came back, and
   nothing is mislabelled as RED. The same test drives verify_par from a
   DAEMONIC process and completes in 0.1s in-process.

4. **The daemon guard was in the wrong file.** It lived in sim.sim_verify, so
   only callers going through sim_verify were protected; verify_par called
   DIRECTLY (rsmp.py and anything like it) could still nest a Pool inside a pool
   worker, which under spawn is a fork bomb rather than an exception. The check
   now lives inside verify_par and a daemon caller runs in-process.

## Session 3, continued: promoted + end-to-end green, fleet re-gate pending

Promoted scratch/cand_cpu4hier.txt to recipes/cpu4.txt (11 BAND lines; the old
unbanded recipe never produced a verifying build). End-to-end from the recipe:

  compose(recipes/cpu4.txt) -> 98827 blocks, layout_retry(verify=True) ALL OK
  (~1200 s single run). That is DONE by the repo'"'"'s own criterion.

Regression on the engine change: scratch/alu4merge.pkl re-verified from a
cleared cache -> VERIFY OK, 1024 vectors, 64 chunks green. The sim fix does
not regress alu4. (An earlier "1024/1024" I reported was a stale cache read;
this one is real vectors.) micro1 passed, alu1 OK (13300 blocks) via
dense_status. alu4/ctrl_decode fresh-compose gate still running at handoff.

verify_par.py fingerprint now hashes the full engine
(sim/simvec/recipe/layout/compose/tiles/core), so any physics edit voids every
cache automatically. No more hand-deleting, no more silent stale greens.

## Overnight 2026-10-02: vertical envelope (trench + y=4 bridge + sim support gate)

Assumption: DONE = the vertical items from the height-ceiling thread (trench
support export, sim repeater-support rule, taller bridge, usable wide bands).
True 3D tile stacking stays out of scope (different compiler, stated before).
Did not touch simvec.py except a 3-line support-gate call (agent 2's file;
their morning report asked for no edits — this one is required for the trench
to verify honestly, and it only ADDS a fail-loud check).

Commit 5d93e1d (trench): the router skipped support for every y<2 cell while
_support's own docstring promised "above and below alike". astar move legality
(`my >= 2` -> `my != 1`, two sites), layout route() and compose lwire 3D
stamping (`cell[1] < 2` -> `== 1`), _has_support (`<= 1` -> `== 1`, trench
needs a stamped pillar, never 2D solid), compose _plant_repeaters (three
`cy > 1` -> `cy != 1`), finish_assembly stamps one cobble cube at y-1 under
every y<=0 wire/repeater (loud on stacked columns), sim._check_supports fails
loud on any floating dust/repeater/comparator at y!=1 (y==1 rides the world).
simvec.verify_par runs the same gate first so direct callers can't bypass it.

Commit 7e98176 (tall bridge): bridge_plan_tall, 7-cell staircase peaking y=4
(short 5-cell y=3 untouched and still tried first). maze try_bridge tries
short then tall (shared 24-cap, solid snapshot/restore on unwind so a tall
support sharing a key with tile cobble can't delete it), compose _walk falls
back to tall only when the short footprint seals (short error preserved).
layout.__main__ has tall template asserts + tall live-fire sim green.

Proofs (all bounded, all green): recipe.py, sim.py, layout.py full __main__
suites; compose_check bit-identical 144/322/224/214; astar routes y=0 under a
sealed y=1 wall with ymin=-1 and every trench cell resolves a pillar; hand
trench circuit (slopes down/up, repeater-free) sim-greens; trench repeaters
unit-checked floating-loud / pillared-ok.

alu1 COMPOSED (was loud no-ground on CIN): 12294 blocks in 86 s, y-histogram
{0:5455, 1:5463, 2:744, 3:624, 4:8} — the y=4 tall hop fired in a real build.
Verify running at handoff (background job, see MORNING-REPORT).

Probe hygiene (learned the hard way): simvec.verify_par opens a spawn Pool,
so any probe script WITHOUT `if __name__ == '__main__':` re-runs top-level in
every child = fork bomb that eats the timeout. All probes here are main-
guarded; REDSTONE_SERIES_VERIFY=1 forces the serial engine for quick probes.
Same class the daemon guard already covers — repo rule: no unguarded probe.

## Finish session 2026-10-02: cpu4 root-caused, 128/128, bands widened

### cpu4 R0Q0: stale pre-flip diodes, not a router bug (no code fix needed)

Handoff's live wall (R0Q0 lit-when-dark on a no-write vector; 1068/1068 lit).
Forensics, each step bounded and offline against cpu4merge3.pkl:

1. Latch neighbourhood (merge (652,48)): intact tile, S/R rows present.
2. Same-y foreign adjacency to R0Q0/S/R: 0. Slope-coupled foreign: 0.
   Torch/lever beside: 0. Foreign repeater front/back onto R0Q0: 0.
   Junction mixing: none. Flat AND slope-closed front~back rings: none.
3. Per-vector sweep (128 serial _run_vec): 16 mismatches, ALL dark-when-lit
   (R0Q0 on odd-low vectors, Y1 on high vectors), ticks=0 throughout.
4. Bisection: live REGW=0 everywhere incl. driver cell while eval says True;
   C_rterm/C_lterm dark; C_l1 AND starved with C_n2/C_n1/C_n0 lit only 9
   cells each at the source end.
5. Band-0 ctx (cpu4bands2.pkl) is HEALTHY: 122 C_n2 dust + 16 diodes, trunk
   fully wired. (A mid-hunt scare about "diodes on air" was my own frame
   error — io/nets are block space, repeaters merge space; the handoff
   warned twice and I still mixed them. Row re-check in one frame: trunk
   intact.)
6. The 9-lit-cells pattern reproduces in BAND 0 STANDALONE (sub has no
   outputs, so the partition sim gate never checked it — "bands green" was
   vacuous for band 0).
7. Root cause: band-0 C_n2 diodes face EAST on an eastward run. Post-flip
   convention (29fc565, vanilla output->input) says WEST. cpu4bands2.pkl was
   built 10/1 6:16PM, the flip committed 10/2 10:56AM. Every pre-flip diode
   reads backwards under the current sim (rep_on takes the downstream cell
   as its back) and never fires. Trunk dies at cell 9; C_l1 starves; REGW
   never lights; registers never write.

Fix (artifacts, not code): `hier_bands.py scratch/cand_cpu4hier.txt
scratch/cpu4bandsNEW.pkl` → 10/10 green in 69s, diodes face WEST.
`hier_stitch.py` → MERGE 74473 blocks, SMOKE 0000000/1111111/0101010/
1010101 ALL OK (0101010 was the Y1 red). `verify_par.py` ×8 calls →
**VERIFY OK: 128 vectors, 16 chunks green.** Canonical caches replaced
(cpu4bands2.pkl, cpu4merge3.pkl + its verify.json now hold current-engine
greens). recipes/cpu4.txt already identical to cand (no copy needed).
Lesson: the engine fingerprint voids VERIFY caches, but band/merge PKLs are
build INPUTS — a physics-meaning change must rebuild them; nothing enforces
that today (future work: fingerprint the band cache too).

### try_bridge for/else (pre-existing crash, mine to trip)

Dense alu4's maze fallback hit `UnboundLocalError: _sup` in try_bridge:
when every candidate refuses, execution falls out of the axis loop into
`cond.update(_sup)` unbound. `git show` proves the shape predates the tall
bridge (same structure, 3-tuple keys) — it just never fired before. Fix:
`break` after a stamp + `for...else: continue` (first-stamp-wins was already
de facto: success returns True, unwound failure returns False). Suites
green, compose_check bit-identical.

### Default bands widened upward, with a measured NO downward

- Maze `_H` 3→4, compose narrow (1,3)→(1,4). Full suites green,
  compose_check bit-identical, alu1 recomposed under final defaults:
  12294 blocks (identical count/trajectory), VERIFY GREEN.
- Negative result, kept: `_YMIN` 1→0 breaks gate-fed D-latch seed (nD
  3D-self-lid). Mechanism: ground cobble roofs trench slopes, so the wider
  band returns only self-lidding candidates and the proven path is never
  returned (the exact failure astar's comment predicted). Trenches stay in
  the wide fallback band + REDSTONE_YMIN=0 (both proven by the trench e2e).
  sim.py is the tripwire that caught it — that check earned its keep.

### Vertical stacking verdict (TODO with teeth, not a half-migration)

- Proven: hand-placed NOT at y=2 on a pillar platform sim-greens (ticks 1).
  Elevated physics works; sim/export/finish are y-generic.
- Blocked: ~140 sites across layout/compose/tiles/sim hardcode y==1 or 2D
  (x,z) keys (solid/rings/junctions/pos/netspec/route endpoints/seal).
  Measured by pattern count, not estimate.
- Decision: no y0-threading through placers alone — stamping works on an
  empty field but routing/checks still assume y==1, so it pastes unroutable
  tiles. End-to-end stacking needs the 2D→3D map migration (or
  deck-segregated 2D maps per level). Anchor comment at tiles.new_ctx.
  Compiler project, correctly sized, not an overnight task.

## Glass + slab transparent physics (wiki-measured, 2026-10-02)

Request was vague ("vertical wires using glass, a new block called slab"),
so the reference repos went first: HDL repos have no glass; redstone-compiler
uses "slab" geometrically; redstone-university's ALU lesson names the actual
idiom (glass towers + slabs as inter-floor insulation: dust sits/climbs on
them, they refuse to pass power through). Vanilla rules verified against
minecraft.wiki (Redstone Dust + Slab pages) before modeling:

- dust sits on glass (1.16+) and upside-down slabs; top-slab dust reads from
  below but never transmits down; slabs carry signals yet never block a
  vertical connection; non-conductive never passes power downward; only an
  opaque block between dusts cuts the diagonal.
- Full-cell model: slab at (x,y,z) rests dust in the cell above (half-height
  nuance unmodeled — logic position is what the sim reads; documented).

Three sets, three roles (layout._src3/_sup3/_flood3; lids stay
cobblestone-only): src=opaque down-sources, sup=any solid rest,
flood=powerable crossing (no pads, no glass). sim: pwr=cob|slab in
wake/dust-side/rep/comp/lamp/presolve/sched paths, dn-term support accepts
sup3, up-term stays opaque-only, _check_supports accepts glass/slab rests.
Router search sets untouched (never stamps glass/slab; hand glass invisible
to search = conservative rejections only). Checkers/floods mirror sim
cell-for-cell (check_shorts also fixed its y>=2 gate to y!=1 — trench slopes
couple exactly like high ones). simvec declines glass/slab to serial
(NotImplementedError → _serial_shard fallback, latch precedent). Export:
colors, glass.png, slab state completion (type+waterlogged), torch mounts.
_parse_build is a 14-tuple now (3 scratch unpacks updated; scratch/ ignored).

Validation: 4 new sim oracles (tower climbs, glass dark, down-off-glass
blocked with cobble control twin, slab power/up/lid, support gate ±), full
suites green, compose_check bit-identical, diff_engine ALL IDENTICAL after
re-freezing the reference (mkref — the gate was stale from six feature
commits, not from these terms: empty-set deltas are identical by
construction), ctrl_decode dense green, export + fallback probes green.
Deliberately NOT done: router auto-stamping glass (supports must stay
conservative — a glass pillar under a run that must feed down goes dark),
panes/stained/wood slabs (still loud).

## The three conservative holds, worked (2026-10-02)

1. **simvec tables: DONE.** _tables_from precomputes pwr/sup sets; new side
   code 8 = slab (powerable like 4, transparent unlike it: cup keeps
   `code == 4`, cdn lid keeps `code != 4`, power terms take both); wake
   vertices/edges, r_src, side(), l_cob, ncells, both sched loops extended.
   Tri-engine probe: serial == scalar == SWAR on a glass tower. diff_engine
   ALL IDENTICAL (empty deltas on glass-free builds). No refusal left.
2. **Search awareness: DONE.** _support gains reuse (ownerless hand glass/
   slab → None, stamp nothing); astar gains reuse/ig (slopes onto hand
   glass legal, wire INTO glass refused at every level); _ig3 helper.
   Probe: astar climbs a glass gate stamping nothing (vs a colliding pillar
   without reuse). route()/lwire threading deliberately SKIPPED: both
   builders start from empty fields and never stamp glass, so a threaded
   set is provably always empty — direct astar callers pass ig explicitly.
   finish_assembly now rejects duplicate coordinates (the whole double-block
   class, O(N), proven safe by the full suite).
3. **Router auto-stamp: MEASURED ZERO, not built.** Provably-safe rule would
   be glass iff all 4 diagonal-below cells are immutably occupied (else a
   future dust could need down-feed). Audit on cpu4merge3: 0 of 4709
   off-ground pillars qualify (corridors are open by construction). YAGNI:
   no code for zero fires. Honest boundary: auto-glass has no routing
   payoff in clean fields (coupling avoidance, not stamping, is what
   shortens routes); its value is hand-designed insulation, which verifies.

## Repo-wide over-engineering audit (2026-10-02 night, applied in 3 batches)

Committed before starting: `629f262`. Each batch verified with sim.py +
layout.py + compose_check.py + diff_engine, then alu1 spot-check, then the full
alu4 1024-vector sweep. Three commits, no behaviour change (alu1 geometry
identical at 13,300 blocks, ctrl_decode 5,499).

**b1 `68dd094` (-85 lines).** Dead flexibility, found by asking who actually
passes the thing:
- `_support(..., reuse=)` and `astar(..., reuse=, ig=)` — the ONLY two
  occurrences in the whole tree were the definitions themselves. No caller,
  no test, no probe. Cut with `_ig3`.
- `_unused_ok_reference` and `_unused_touches_foreign_reference` in astar:
  70 lines of second implementation of the hot-path rules, reachable only
  under `REDSTONE_XCHECK`, which nothing in the repo ever sets. They were the
  pre-optimization predicates kept beside the optimized ones.
- Three inline copies of the torch-attach map while `core.TORCH_BACK` already
  existed and was imported by two modules. sim.py did not even import it.
  This is the drift class that produced the facing bug earlier tonight.

**b2 `a197c86` (-601 lines, simvec 1456 -> 855).** The bit-parallel SWAR
engine: `run()`, `_swar_shard`, `_Ops`, `Indecisive`, `eval_net_par`,
`lanes_of` and the five lane-wise rules. Its own comment recorded the verdict
(22.7s vs 21.5s on alu4 = 5.6% SLOWER, byte-identical), it was default-off,
nothing enabled it, and it could not terminate on a hunting vector at all
(sim's torch-burnout rule was never reimplemented) which is why it needed
shards, a 4M-step budget and a fallback path. `verify_par` lost the whole
retry/re-dispatch branch that existed only to feed it. The module docstring
advertised SWAR as the reason the file exists; it now describes the table
engine, and the name is documented as historical. Restore point recorded in
the driver note (68dd094) with the trigger: a 12+ input recipe making 2^n
unaffordable.

**b3 `17adc59` (-7 lines, 14-field parse tuple).** `lampat` was collected by
the parser and read by nothing — six unpack sites just named it. One less
field to thread through every future edit of `_parse_build`.

**Not applied, on purpose:**
- `scratch/` holds 299 files / 28,036 lines of one-off probes. It is
  gitignored (0 lines in the repo), and it is the live tooling for the alu4
  and cpu4 pipelines plus every forensic probe in this log. Pruning it is a
  judgement call about evidence, not dead code — the six tools that matter
  (hier_bands, hier_stitch, verify_par, mkref, diff_engine, dense_status)
  are the ones to keep, and the other ~290 are dead. Worth a decision when
  nobody is relying on them for a bisect.
- The ~40 `REDSTONE_*` env knobs that nothing sets: several are documented
  escape hatches (band depth for a sealer that has not appeared yet), so
  cutting them removes capability, not complexity.
- Delegating-wrapper parameters (`tiles.stamp_cobble(o, ...)`, `tiles.ring`,
  `export.build_stamp(label, nblocks)`): each names the one value it forwards.
  Removing them means touching every call site for no behaviour change —
  pure churn, so they stay.

Tracked python: 9,795 -> **9,731** lines net after all three batches
(layout 2,288 -> 2,212, simvec 1,456 -> 927; sim.py and compose.py grew by
the bug fixes they needed, which is not what this audit was for).

### export.py: a concurrent agent's fix, and how I nearly buried it

Mid-audit `export.py` began changing under me — 139-169 uncommitted lines
appearing between two commands. It was another agent's work (confirmed by the
user), and it is a real fix: the HTML preview shipped every vector's state as
raw JSON plus per-page coordinate→instance maps, which is ~1.6GB of page for
alu4's 1024 vectors. The replacement packs one nibble of dust level per cell
and one bit per repeater/torch/comparator into base64 rows, ordered to match
the page's InstancedMesh build order so the page indexes by instance number
and never builds a coordinate map.

**What I did wrong:** I ran `git stash push -- export.py` and later
`git checkout -- export.py` to isolate it while I ran my own test batches.
Both were meant as temporary set-asides and I did not put it back. Nothing was
lost (git keeps the stash and I had a copy), but for several minutes another
agent's uncommitted fix was sitting in a stash while its working tree showed
HEAD. Lesson, written where the next agent will hit it: **another process may
be editing this tree.** `git status` is not evidence that a file is yours.
Isolate with a worktree or a copy, never with `checkout --`/`stash` on a path
you did not write.

**Resolution:** restored their furthest-along version (a Temp copy; the earlier
514-line variant is at `Temp/opencode/export_earlier_514.py` for the record),
and instead of touching their code I fixed the one thing that was actually
broken — sim.py's hand-rolled preview fixture omitted the comparator field the
packer reads, which is what made `sim.py` red twice (`ValueError: too many
values to unpack`, then `KeyError: 'o'`). Their `_pack_states` was never wrong;
the fixture was. One line, committed with their work in `9be02f8`.

Standing rule from the user, recorded here and in notes/handoff.md: **do not
delete files.** Cut code inside a file freely; the file stays. Comment out
rather than remove. Verified for this session: 87 tracked files before and
after, zero deletions/renames in `ed4c2a7..HEAD`, all 300 `scratch/` probes
present, and the audit's file-level candidates (`debug.py`, `serve.py`, ~290
scratch probes) deliberately left in place.

Verified after adoption: `sim.py` green, and the real alu4 preview regenerated
— packed rows present, zero raw vector JSON in the page, 4.0MB for 4 vectors
(against ~1.6GB extrapolated for the full 1024).

alu4 was never green under current physics, and the `64/64` in
`scratch/alu4merge.pkl.verify.json` was a pre-flip ghost: re-verified today
that merge is RED on all 16 chunks, every failure `Y2`/`Y3` with `B2`/`B3`
set. So the old geometry was dead regardless, and a rebuild was required.

Rebuild: `hier_bands` 6/6 green -> `hier_stitch` MERGE 41031 blocks. All-zero
settled, **15 of 24 sampled vectors hunted** (0 logic mismatches — purely a
ring). `REDSTONE_CHURN` named 18059 churn cells; the repo's own cycle finder
(scratch/trace_cycle.py's rule graph, extended with repeater/lever/rblk/
comparator edges) gave the shortest ring, 6 nodes, on net OP1x_3:

    torch (2044,1,34) -> dust (2045,1,34) -> dust (2045,1,35)
      -> repeater (2044,1,35) -> dust (2043,1,35) -> cobble (2043,1,34)
      -> torch (2044,1,34)

One inverter plus one wire is a ring, so the band-3 handoff latched itself.
The twin at (2060,1,33) on OP0x_3 is the same shape.

Why every existing guard missed it: `_closes_loop`/`_loop_rep` flood same-net
DUST over blocks; `_ends_ok` only checks that a booster's front/back cells
carry its own net. This ring leaves the dust through a TORCH -- a directed,
inverting edge neither models. Fix, both places that plant or judge a booster:

- `compose._ends_ok`: refuse a booster whose output cell drives a tile torch
  that has this same net beside it. Torch host map cached on ctx, keyed by
  block count (torches never move once placed; alu4 plants ~2400 boosters).
- `layout`'s booster loop: same predicate, with the same unwind-and-try-the-
  next-triple behaviour the loop check already uses.
- `finish_assembly` keeps the loud all-scan version (`_booster_inverter_ring`)
  so nothing hunted can ever ship. 0 hits on cpu4's green 74473-block merge
  and on the old alu4 merge; 2 on the bad merge.

Result: bands rebuilt under the new router, stitch MERGE 41031 blocks, and
**SMOKE 0000000000 / 1111111111 / 0101010101 / 1010101010 ALL OK** — the
all-ones vector that hunted now settles.

**VERIFY OK: 1024 vectors, 16 chunks green.** alu4 is done. Reproduce:

    python scratch/hier_bands.py scratch/cand_alu4hier.txt scratch/alu4bandsNEW3 150
    python scratch/hier_stitch.py scratch/alu4bandsNEW3.pkl scratch/cand_alu4hier.txt 480 scratch/alu4mergeNEW4.pkl
    python scratch/verify_par.py scratch/alu4mergeNEW4.pkl scratch/cand_alu4hier.txt 16 2400 16 16

(~1150 s wall for the full 1024 on 16 workers; the cache is keyed by an
engine fingerprint, so any future engine edit re-verifies from zero.)
Canonical caches replaced: `alu4bands.pkl`, `alu4merge.pkl` + its
`verify.json` (16/16 green, fp 327ee4a52f1b), and `alu4_build.pkl` (the
diff_engine fixture). The pre-flip dead geometry is kept beside them as
`alu4bands.preflip.pkl` / `alu4merge.preflip.pkl` for forensics.

Full regression after the fix: cpu4 re-verified from scratch under the new
engine (**128 vectors, 16 chunks green**), `diff_engine` ALL IDENTICAL on the
NEW alu4 build, sim.py / layout.py / compose_check.py suites green, alu1
12294 blocks and ctrl_decode 4923 green.

### The export round-trip caught what the sim could not: dust on dust

`export_schem` + read-back (500-block sample, 0 mismatches) is the only check
that sees the PASTE, and it failed on the first alu4 export attempt: 24 cells
came back as wire where the build list said cobblestone. All 24 were
cobblestone+wire in one cell, and every one had a **dust cell above resting on
what became a wire** — a staircase of dust on dust in the input-bank approach
(OP1/B2/B3/OP0x_3 at x≈8, 456, 1063…). The sim read both blocks in the cell and
called it supported; vanilla refuses dust on dust, so all 24 would have popped
on paste while every verdict stayed green.

Two causes, both fixed:

1. **The duplicate guard ran too early.** It sat right after
   `out = list(blocks)`, but wires/repeaters/stone are appended *after* it, so
   the entire wire class was invisible to it. Moved to the end, on the
   finished list, and extended with the real invariant: a component at y!=1
   may not rest on a WIRE. `sim._check_supports` got the same rule, so the sim
   is loud too rather than only the assembler.
2. **compose's bridge/hop sites stamped their own supports** and never asked
   whether the cell was occupied — `layout._support` has refused that since
   the beginning, but compose bypasses it. Added `_supports_free` at the
   tall-bridge and hop sites so those strategies refuse and the router takes
   another path.

With the guard first (bands 0 and 1 went NO GREEN RUNG — the class is
systematic, so measuring first was what made the second fix findable), then
the compose fix: bands 6/6 green again with *smaller* geometry (35,082 blocks
vs 41,031), stitch MERGE green, **0 conflicting cells**, and
**VERIFY OK: 1024 vectors, 16 chunks green** in 245 s instead of 1,150 s —
the no-ring build also settles faster.

Canonical caches replaced again (`alu4bands.pkl`, `alu4merge.pkl` +
`verify.json` fp `6bd0cbfd80fe`, `alu4_build.pkl`). cpu4 re-verified from
scratch under the new engine (128 vectors green), `diff_engine` ALL
IDENTICAL, sim/layout/compose_check suites green, alu1 12,294 and ctrl_decode
4,923 green.

### alu4 exported

- `build.schem` (12,356 bytes) installed at
  `C:\Users\LOQ\AppData\Roaming\FreesmLauncher\instances\26.3\minecraft\config\worldedit\schematics\build.schem`,
  round-trip checked: every one of 35,082 blocks reads back with the state it
  was written with, plus a 500-block random re-read of the installed file (0
  mismatches). The previous `build.schem` was copied to
  `build.schem.bak-20261002-210028` rather than overwritten blind.
- `build_alu4.mcfunction` (2.28 MB) and `build_alu4.html` (4.5 MB, with
  per-vector state for the four smoke vectors so the preview is interactive —
  `sim_verify` only collects states when a recipe has <=16 vectors, and alu4
  has 1024).
- Installed contents: 14,634 wire, 13,821 stone, 4,386 cobblestone, 2,059
  repeaters, 138 torches, 21 levers, 18 comparators, 5 lamps.
needed. The root cause was a placement rule, not bad luck, so fixing the rule
produces a green stitch on the first attempt instead of burning retries on a
seed ladder. `hier_stitch.py` did gain an optional 4th argument that saves
the merge pkl — the pipeline could not otherwise hand a stitched build to
`verify_par` at all.

### Facing trap, now asserted in a comment

`layout`'s booster helpers treat `front = cell + _VEC[facing]`, but sim
treats `facing` as pointing output->input, so the real output cell is
`cell - _VEC[facing]`. Measured on the alu4 merge: **2426 of 2426 repeaters
disagree** between the two readings. Harmless so far only because those
helpers are direction-agnostic (they need the two cells, not which is which).
Any new direction-aware check must use sim's rule; `_booster_out_cell` is the
one place that encodes it.

## Target block: full wiki physics (2026-10-02, fd0aaeb)

Wiki Target page read before modelling (minecraft.wiki/w/Target). Features
and where each one landed:

- **Opaque, full cube, conductive** (1.19+ `22w13a`): `minecraft:target`
  joins `cob` (so slope-support, lid-cutting, loop-flood and strong-power
  conduction all come from the one set that already encodes them) and joins
  `_src3` / `_sup3` / `_flood3` in the checkers.
- **Emits 1..15 for a clock**: ordinary projectiles 8 game ticks, arrows and
  tridents 20, i.e. 4 and 10 redstone ticks (`_TARGET_TICKS`). The projectile
  list is a frozenset from the wiki page and an unknown one raises. `tg`
  carries the EXACT level, so dust on top, dust beside and a comparator
  behind all read the hit accuracy instead of a generic 15; `tx` holds the
  deactivation tick so a second hit renews the clock and a stale event
  clears nothing (`F`/`G` events, `wake` on both edges).
- **Stimulus is an argument, never the block**: `_run_vec(..., target_hits=)`
  and a third `sim_pulse` schedule element. A bid carrying `power=5` is
  rejected, because a file cannot say when the hit happened.
- **Cross-phase pulses**: `sim_pulse` tracks absolute expiry and passes
  `("hold", level, remaining)` per phase, so a 4-tick snowball hit can span
  a short phase and expire in the next one (asserted).
- **Redirection**: `dust_points(cell, dust, targets=)` treats a target as a
  connection endpoint even while idle, which is the wiki's "redirects
  adjacent dust toward itself". Wired into the sim's block-power term and
  `wire_bid`, so the baked .schem/.mcfunction wire state matches. Empty by
  default: bit-identical on every target-free build (diff_engine ALL
  IDENTICAL, alu1/ctrl_decode green).
- Not modelled: the observer (bedrock does not see target updates, and the
  repo has no observer at all).

Cost note: simvec's fixed tables model only the idle role; a build with
timed hits raises NotImplementedError from `run_scalar` after validating
the stimulus, and `verify_par` falls back to the serial authority. Zero
behavior change for generated builds, which never stamp a target.

---

## 2026-10-03 night session: ONE INPUT BANK (single-cluster levers)

**Goal (user):** the input levers must be in one cluster, so an input can be
flipped from one place. Measured starting state: `alu4` shipped **21 levers**
for 10 inputs over 1757 blocks of x (A0 x=15, A1 x=439, A2 x=834+1244,
A3 x=1484+1760, B0 x=11, B1 x=435, B2 x=830+1236, B3 x=1476+1756,
OP0 x=3/427/822/1748, OP1 x=7/431/826/1468/1752); `cpu4` **21 levers over
3352 blocks**. Cause: every BAND composes alone and each stamps its own input
bank (`compose.py:1055`), and the merge only deletes levers for boundary
(`recipe["edge"]`) nets, so recipe inputs keep one lever per partition
(`compose.py:1812`, `recipe.py:156`).

**Assumption recorded (rule: do not ask, decide and log):** "one cluster" means
one place in the world to flip any recipe input, not one lever per input
necessarily co-located with each other at the same x. The implementation
below is the stronger form (all inputs on one lever column) because the
weaker form was measured and rejected: keeping each input's own westernmost
lever makes **four** clusters (A0's at x=13, A1's at x=437, A2's at x=832,
A3's at x=1482) because the westernmost copy of each input lives in a
different band.

### Two real engine bugs found on the way (both fixed, both narrow)

1. **A 3D flight could put dust and cobblestone in one cell.**
   `lwire`'s flight path collected `needs` from `_support()` and then stamped
   the flight's own cells. For a ONE-CELL DESCENT the lower step IS the
   support for the cell above it, so the same cell got both. The existing
   self-lid test cannot see it: it asks `hi.y-1 in cobf`, and that cell is in
   `needs` only because it is about to become dust too. Now refused loudly
   (`support under own dust`); the next y band / strategy / rung retries.

2. **`_support()` reports an already-recorded pillar as reusable.**
   It returns `None` for a cell in `sup`, so a LATER leg of the same net lays
   dust on a cell that already owes a cobblestone. `_support` is about
   support, not occupancy, and nothing else checked. Measured: R1Q1's pillar
   at (1852,2,25) with its own dust over it ->
   `duplicate block at (1854,2,139): cobblestone vs redstone_wire`, which
   kills the whole merge in `finish_assembly`. Now the flight refuses any
   cell that is already a committed pillar (`dust over own pillar`); fatal for
   every net including the pillar's own, because the block is committed.

Both guards are in `lwire`'s flight branch only, and both are no-ops for any
field that was already valid (a green build never had those cells). Verified:
`REDSTONE_INPUT_BANK=0` on `alu4bands.pkl` merges to **35,082 blocks, byte
identical** to the shipped `alu4merge.pkl` (sha `e5d1915191ba6191` over the
block list, `io["levers"]` equal), 4/4 smoke vectors OK.

### cpu4 is RED on the current engine, independent of this work

`cpu4bands2.pkl` bands 5 and 6 each carry 3 cells that are in `sup` (y>=2)
AND in `wires` -- the defect class of bug 1 above, baked into the cached
partitions. `scratch/cpu4merge3.pkl` (the "green" cpu4 merge, fp
`47fb2a6e0efb`) itself contains **8 conflicting duplicate cells**, e.g.
(1854,1,108) cobblestone+wire: it predates the one-cell-one-block gate added
2026-10-02, so its 16/16 was scored by a sim that read both blocks.
`hier_stitch cpu4bands2.pkl` now dies with or without the bank:
`duplicate block at (1854,2,87)`. **cpu4 needs its bands rebuilt, not
re-stitched** -- see the morning report.

### State of the bank itself

`REDSTONE_INPUT_BANK=1` (default OFF until it verifies green) builds one lever
column in the empty margin west of the merge, deletes every partition's input
lever, and fans each input out to the stubs it used to drive directly. The
bank strategy is tried FIRST and only for banked nets, because the generic
ladder cannot express it: `_relay` puts its waypoints at the DRIVER's z (the
lever latitude, which drags a run east through every band) and the
stub->stub chain needs one leg to cross every intervening field.

Measured progress on `alu4`: the column builds, all 21 levers collapse to 10,
and legs reach bands 0-3. Still red on the far bands:
`hier stitch A2: band 4/5 stub ... no ground`. That is the router's long-span
weakness, not the bank geometry.
### Bank ON: the cluster is achieved; the distribution trunk is not

`REDSTONE_INPUT_BANK=1`, `scratch/alu4bands.pkl`, measured on the
stitch-failure field dump:

    LEVERS IN MERGED FIELD: 10
    x -5..-5 (span 0)   z -51..-15 (span 36)
       OP1(-5,-51) OP0(-5,-47) B3(-5,-43) B2(-5,-39) B1(-5,-35)
       B0(-5,-31) A3(-5,-27) A2(-5,-23) A1(-5,-19) A0(-5,-15)

**One column, one cell of x, 36 cells of z. Every input flips from one spot.**
That is the requested geometry and it is measured, not argued. The old build
had 21 levers over 1757 cells of x.

All ten input nets now stitch their fan-out to every consuming band's stub.

**Still red, and it is not the levers.** The value has to be carried east
along a trunk row per input, and the trunk obstructs the field's own gate-net
routing:

- `hier stitch A3B3: band 4 stub (1566,63): no ground for A3B3:
  (1834,50) -> (1341,1)`. A3B3's only open margin is north of the build --
  where the ten trunk rows now are -- and its north-around drops at the stub's
  column, crossing them.
- Ordering the trunk rows by how far east each input reaches (longest row
  southernmost) cut the crossings from ten to three and moved the failure:
  `hier stitch OP0: band 2 stub (821,2): bridge support lands on wire at
  (8,1,-23)`. The drop can cross a trunk row or two; three is past what
  `lwire`'s single hop absorbs.

**Why no straight-line fix exists.** A planar one-level fan-out cannot work
here, and this is worth writing down so the next session does not re-derive it:
every band's stub sits at the same latitude (z 2..8) while every band's field
reaches further north (min z -19). A row per input must therefore be north of
the field, and every drop from a row goes south, so every drop crosses every
row south of it. Crossings are structural, not a bug in the placement.

Three ways out, cheapest first, none built:

1. **A street-crossing trunk.** `_HIER_GAP=160` leaves a 160-wide empty column
   between every band pair. Run each trunk row east along the north margin,
   then hand the band off by dropping down the street immediately west of it
   and running east at the stub's latitude. The street descent is empty top to
   bottom, so the only crossings left are at the stub's latitude, in that one
   band's own north margin. Cost: one extra horizontal per band, and it needs
   the stub latitude to be reachable -- which for A3B3's stub (z=63) it is not.
2. **Trunk in the gap between y.** Stack the ten rows at y=1,3,5,... over
   z rows 4 apart, so a drop crosses a row at a different y and only the
   pillar under it conflicts. Needs a `dust over own pillar` exemption for the
   cell directly above a row, which bug 2 above just made fatal.
3. **A real constant-source tile.** A lever per input at the bank, feeding a
   **repeateral-free** chain of the existing `_relay` stations, which already
   re-drives 15 across a street. Needs `_relay` to run its waypoints on the
   bank row rather than at the driver's z (`compose.py:2490` hardcodes
   `(x, drv[1])`). That is a two-line change to `_relay` plus a row argument,
   and it is the most promising of the three.

### `REDSTONE_INPUT_BANK` default

Default **OFF**. With it off, `alu4` merges byte identical to the shipped
`alu4merge.pkl` (35082 blocks, `io["levers"]` equal, 4/4 smoke OK), so the ten
green builds are untouched. Flipping it on does not yet produce a green build,
so it must not be the default until the trunk lands. Do not delete the flag:
it is the A/B for the trunk work.

### New: dump on a stitch failure

`REDSTONE_HIERDUMP_FAIL` now also fires when a stitch never lands. The
opens/finish dumps only cover everything downstream of a landed stitch, and the
banked fan-out is the first thing that can fail before that -- which is why
this session spent several iterations with no field to inspect.
### Last iterations: what moved and what did not

Ordered the trunk rows by reach (longest row southernmost) and spaced them 6
apart with an explicit waypoint in each gap, so a drop crosses exactly one row
per leg instead of three at once. Measured progression, same command each time:

| change | failure |
|---|---|
| cluster at band-0 latitude, chain stub->stub | `hier stitch OP1: band 4 stub (1467,2): path re-enters (1341,1,2)`; band 5 `no ground (825,4)->(1653,1)` |
| fan out from the cluster, no chain | `hier stitch A2: band 3 stub (1243,4): no ground for A2: (-4,2) -> (1123,1)` |
| bank strategy first (north-margin route) | same, because the riser ran into the other nine stubs in the shared stub column |
| one lever per trunk row, no risers | all ten input nets stitch; `hier stitch A3B3: band 4 stub (1566,63): no ground for A3B3: (1834,50) -> (1341,1)` |
| rows ordered by reach | `hier stitch OP0: band 2 stub (821,2): bridge support lands on wire at (8,1,-23)` |
| rows 6 apart, gapped drop waypoints | `hier stitch OP1: band 5 stub (1751,4): no ground for OP1: (-4,-33) -> (1653,1)` |
| + street waypoints on the east run | unchanged -- `lwire` still will not route it |

The trace for that last one is the useful artefact: OP1's bank route for band 4
was `(-4,-33) -> (206,-33) -> (609,-33) -> (1005,-33) -> (1312,-33) ->
(1467,-33) -> (1467,2)`. Every waypoint is on its own row or in a street, so
the SHAPE is right and the failure is a routing-capacity problem, not a
geometry one. OP1's row is the southernmost of the ten (it reaches furthest
east), so its own drop crosses no rows at all, and that leg still does not
land.

**Two constraints worth not rediscovering:**
- `lwire` will not route a span over ~350 cells even on empty ground (measured:
  `no ground for OP1: (-4,-33) -> (1653,1)`, 1657 cells of clear north margin).
  That is why `_relay` and `_streets` exist. The bank route splits at the
  streets but gets NO repeater stations, because it goes through `_legs`, not
  `_relay` -- and `_legs` leaves a 1657-cell east run to `_plant_repeaters`
  alone. **Relaying the bank route instead of `_legs`-ing it is the next
  change.**
- `_bank_pts` must keep its waypoints ordered and gap-aligned; the drop leg
  length is what decides whether a hop fits.

Control after every one of these changes: `REDSTONE_INPUT_BANK=0` on
`alu4bands.pkl` merges to 35082 blocks, byte identical to the shipped
`alu4merge.pkl`, `io["levers"]` equal, 4/4 smoke OK. Re-verified after the last
edit.
### `_relay` for the bank route: TRIED, FAILED

`_relay` puts its waypoints at `(x, drv[1])` and for a banked net `drv[1]` IS
the trunk row, so the obvious next move was to route the bank through `_relay`
(it splits the east run at the streets AND plants a repeater station at each
one) instead of `_legs` (which did neither). Committed as an experiment and
measured: **identical failure**, `hier stitch OP1: band 5 stub (1751,4): no
ground for OP1: (-4,-33) -> (1653,1)`.

So the east run was never the problem. The part that does not route is the
descent into the band at the stub's own latitude: every band's stub is at
`minx - 1`, the westernmost cell of its margin, and the lever rows march east
from there at 2 cells of z pitch, so any run at that latitude meets them. The
relay's own last leg is the clearest evidence -- `(1577,4) -> (1751,4)`, 174
cells at z=4, which is exactly the lever-bank latitude.

Next session: do not re-try `_relay`. Drop down the `_HIER_GAP` street
immediately west of the band instead (empty top to bottom, 160 cells of
approach), and check `A3B3` first -- its stub is at z=63, far inside band 4, so
its latitude may not be reachable from a street either. Full list in
MORNING-REPORT.md.
### DONE: one lever column, verified 1024 vectors / 16 chunks green

`REDSTONE_INPUT_BANK` now defaults **ON** and alu4 is green with every input
lever on ONE column:

    LEVERS: 10   x 3..3 (span 0)   z 3..93
    VERIFY OK: 1024 vectors, 16 chunks green
    60724 blocks (was 35082), size (1980,285)

Five things had to be true at once. Each was found by measurement, and the
order matters -- each one only became visible once the previous was fixed.

1. **The lever column sits north of the merge**, one row per input, rows **10
   apart**. 10 is not arbitrary: `_hop_free`'s shape is a 5-cell staircase
   whose back and front sit two cells either side of the wire it crosses, so
   a row needs 9 clear cells to be hoppable. At 6 apart there was no room and
   the walk answered "compose: stitch rings for OP1".
2. **Rows ordered by how far east each input reaches, longest row
   SOUTHERNMOST.** A drop crosses exactly the rows south of it, so this makes
   a drop cross only the rows of inputs reaching *further* east than the band
   it feeds. Cut the crossings from ten to three.
3. **Every row run is stamped UP FRONT**, straight, in open ground; only the
   drops are routed. This puts every row/drop crossing in a drop, where the
   hop fits. The other order put them in a 1000-cell row run, and the router's
   detour to hop a single drop came back through a waypoint and the leg was
   rejected ("path re-enters (332,1,-116)"). The rows are genuinely free: they
   sit north of every gate-net margin row and no drop exists yet, so
   `stamp_wire`'s adjacency/solid/ring/torch guards all pass.
4. **The bank is stitched LAST and its cluster is built after `_minz0`.** A
   full-width trunk in the north margin takes away the only open margin the
   gate nets have -- `A3B3` died with "no ground for A3B3: (1834,50) ->
   (1341,1)". Building the column before the loop but routing the bank after
   every gate net gives each gate net the field it verified green with.
   `_gate + _bank` in the stitch loop is the whole of it.
5. **Drop columns prefer the stub's OWN column**, checked clear of solids and
   repeaters. `_streets` is the midpoint of two band START offsets, which is
   *inside the earlier band*, not in the reserved gap (so the first relay
   attempt descended band 3's middle); and a gate net's 3D flyover roofs a
   whole gap with y=1 pillars, so no fixed gap column is reliable. The stub's
   column is `minx_band - 1`, one cell west of the tiles in the band's north
   margin, which is empty by construction, and the input lane that leaves the
   stub already runs down it -- so arriving from the north is the same net.
   `_bankstreets` was left in place as the gap fallback list; `_streets` is
   untouched so no gate net's geometry moves.

### Third engine bug: `_landed`'s contiguity checker had repeaters backwards

`_landed` flood-checks that every consecutive pair of a stitch path is a sim
link, and it re-implements the repeater rule locally. Both halves were
inverted against `sim.py:835` (which stores `rep[c] = -parsed_facing`, i.e.
TRAVEL):

- `if c in repeaters` yielded `c + stored` -- the cell BEHIND the repeater.
  A flood has to continue out the FRONT.
- `elif m in repeaters` tested `c == m - stored` -- the cell AHEAD.

So every correctly-oriented booster counted as a break, and the error walked
along the banked row one cell at a time as each half was corrected
("broken link (-4,1,-115) -> (-3,1,-115)", then "(-3) -> (-2)", then
"(813,1,-95) -> (814,1,-95)"). The third hop needed one more fix: the two
every-8 passes (forward from the driver, backward from the load) can leave two
boosters one cell apart where they meet, and sim reads that fine ("repeaters
chain back-to-back (standard)"), so the front test now accepts a booster too.

Harmless to the old path: `REDSTONE_INPUT_BANK=0` still merges byte identical
to the shipped `alu4merge.pkl` (35082 blocks, `io["levers"]` equal, 4/4 smoke
OK), re-verified after every change including this one.

### Also fixed while making the failure legible

- A banked leg no longer falls through to the six generic strategies. All six
  are anchored on the driver's own cell or at the stub's latitude, which for a
  bank means running east at the TRUNK row through six fields; every one has
  been measured to fail on every banked leg, and running them cost ~40s per leg
  while replacing the error that mattered.
- `_loop_near` is skipped for the bank. It floods a +-25 box around EVERY path
  cell, so a 1000-cell trunk run sees the whole consumer band and reports a
  ring that was already there and already fine. `_try` wraps every strategy in
  a before/after `_lr` diff, which is the check that can tell a NEW ring from
  an old one.
- `REDSTONE_HIERDUMP_FAIL` fires on a stitch failure, not just opens/finish.
- Leg failure messages are no longer truncated to 60 chars (that alone hid
  every bank error behind the last generic strategy's message).

### Exported and installed

    build_alu4bank.schem       17390 bytes   60724 placed cells, 22 palette
    build_alu4bank.mcfunction  3999496 bytes
    build_alu4bank.html      25100239 bytes  1024 vectors, full states

The schematic is installed at
`…\FreesmLauncher\instances\26.3\minecraft\config\worldedit\schematics\build.schem`
and last night's 35082-block build is preserved beside it as
`build.schem.bak-20261003-063141`. Read back and confirmed after the copy:
60724 placed cells, 22 palette entries, `minecraft:lever` present.

The old `build_alu4.html` (4.0 MB) turns out to have been exported from a
partial states set -- its wire blob is ~29 bytes per vector, i.e. ~58 wire
instances, not a whole build. The new page's is ~13 KB per vector, which is
the full 25815-wire field at 4 bits each.
### Reproducibility, and cpu4

The alu4 result does not depend on a stale cache. Rebuilt end to end with the
fixed engine:

    python scratch/hier_bands.py  scratch/cand_alu4hier.txt scratch/alu4bandsBANK 150
    -> 6 bands, 161 s; ALL SIX byte identical to scratch/alu4bands.pkl
       (shift, block count and a sha over blocks+wires all match)

    python scratch/hier_stitch.py scratch/alu4bandsBANK.pkl scratch/cand_alu4hier.txt 900 scratch/alu4fresh.pkl
    -> MERGE 60724 blocks, byte identical to scratch/alu4bank.pkl, 4/4 smoke OK

So the three engine fixes are geometry-neutral for band composition, and the
16/16 verify was not an artifact of a cache that no longer matches the engine.
(That was worth checking: alu4 had been stitched from CACHED bands throughout,
so a guard that changed partition geometry would have been invisible.)

**cpu4 rebuilt from scratch: bands green, merge RED, and it is not the bank.**

    python scratch/hier_bands.py scratch/cand_cpu4hier.txt scratch/cpu4bandsBANK 150
    -> all 10 bands green per-band, 203 s

    REDSTONE_INPUT_BANK=1  -> MERGE 101031 blocks; SMOKE 1111111 MISMATCH ['Y2']
    REDSTONE_INPUT_BANK=0  -> MERGE  73589 blocks; SMOKE 1111111 MISMATCH ['Y2']

Identical failure with the bank off, so this predates the input bank and is
independent of it.

**Diagnosis: the band ladder optimises per band, correctness is a property of
the combination.** `hier_bands` keeps the FIRST rung that makes a band green
STANDALONE; each band does sim green alone, but the cross-band handoff is what
`Y2` depends on, and a fresh climb is free to pick a different combination than
the old cache did. The old cache's combination only worked because the sim
reading it let 8 cells hold two blocks.

Next step for cpu4 is therefore NOT redstone: make the ladder
combination-aware. The bands are cached and the stitch is ~9 min, so the cheap
version is a loop -- merge, smoke, and on disagreement re-climb only the bands
feeding the wrong output, then re-stitch. Pinning the `Y2` producers and
re-climbing only those is the smallest version.

**A gate that would have caught this**: `hier_stitch` already runs a 4-vector
smoke and exits 1 on a mismatch, but nothing above it treats that as a signal
to re-pick rungs. The ladder has no merge-level retry at all.
### handoff rewritten

`notes/handoff.md` now describes THIS session rather than 2026-10-02: the goal
(one lever cluster), the current state table with the lever coordinates and the
byte-identical control/reproducibility evidence, the seven commits and what each
one changed, the three engine bugs, the full failed-attempt table with the
exact error strings, the files touched (and the explicit list of tracked files
NOT touched), and the next steps.

Evidence added for this rewrite, since two of the three engine fixes live in
`lwire` and every partition composition uses it, not just the hier ones:

    python scratch/nonhier_suite.py
    example_and GREEN 144 | example_2gates GREEN 322 | latch_sr GREEN 224
    example_xor  GREEN 214 | micro1 GREEN 2925
    alu1         GREEN 13300  == 13300     <- unchanged
    ctrl_decode  GREEN 5499   == 5499      <- unchanged
    python compose.py   ->  lwire ok / compose ok / buffers ok

So the `lwire` guards and the `_landed` repeater-direction fix moved nobody
else's geometry. New bounded tool: `scratch/nonhier_suite.py` (one killable
child per recipe, per-recipe cap).
## 2026-10-03 day session: in-game paste test finds a real sim gap (fixed)

Pasted `build_alu4bank.schem` (verified hash `837113a0`, 60,724 cells) into
a fresh world via WorldEdit, force-loaded the footprint with a datapack
function (`/function alu4:load`, 2375 chunks; one command covers max 256,
so 10 strips — block coords, not chunk coords), lever column left-to-right
B0 A0 B1 A1 B2 A2 OP1 OP0 B3 A3, lamps teleported. Full automation built
along the way: datapack auto-suite (lever set/read/probe/schedule chains,
results to chat log which is machine-readable), `scratch/gen_pack.py`
regenerates the whole pack for any paste origin, `scratch/regiondiff.py`
+ `scratch/mapdump.py` + `scratch/levercheck.py` diff on-disk block
states vs sim (nbtlib region parsing).

### Finding: Y2 stuck lit with all inputs off, stable for hours

T1 (all off) reads Y=0001 in game, sim said 0000. T3 (1+1 ADD) reads
Y1+Y2+COUT, T4 (5+3 ADD) reads Y3+COUT; T2a/b/c all correct. Bisected
in game (wire-power probes) and on disk (region diff, 1824 divergences):
whole runs hot with dark inputs (C2 842/903 cells, OP1, S2, m22, t22,
o22, Y2, A3B3 380/614, C4); everything downstream conducts correctly.

### Root cause: cob_state/pbs had no below-neighbour terms

`cob_state` (sim.py) derived solid power from same-y neighbours and dust
above only — never from directly below. Vanilla powers solids from below
(torch strongly powers the block above it; dust powers the block beneath
it). Every torch-topped pillar (the 3D flights stamp them everywhere)
reads dark in sim, lit in vanilla; dust on top follows. Elevated-only
fault, which is why no flat build ever tripped it.

### Fix (sim.py +31, canary `pillar-feed ok`)

Below-terms in `cob_state`: dust below (weak), torch below (strong,
same host exception), redstone block below (strong), lever below (via
attachment). Standing-torch-below and repeater/comparator-below excluded
(attach / cannot face up).

Gates: sim.py suite green (canary fails pre-fix, passes post-fix, both
measured); diff_engine diverges ONLY on the alu4 bank vectors (Y2 now
lit, matching the game); small builds bit-identical; simvec agrees
(no scalar mismatches, no simvec change needed); compose/recipe/layout
suites green; nonhier geometry untouched (compose-side, unaffected).

Post-fix sim reproduces all 8 in-game vectors lamp-for-lamp, including
T1/T3/T4 mismatches and T2a/b/c correct.

### Deliberately NOT done (needs direction)

- No commit (not requested). Tree: `M sim.py` only. ref_sim NOT
  re-frozen (run `scratch/mkref.py` after committing a physics change).
- The BUILD is still wrong in game (Y2 fault stands in the pasted
  schematic). Fixing it means re-routing bank/gate runs off
  torch-topped pillars (or insulating), re-compose, re-verify green
  in sim, re-export, re-paste, in-game auto-verify. Separate phase.
- `scratch/` gained probe tooling (gen_pack, gen_snap, regiondiff,
  mapdump, levercheck, loophunt, diodeloop, liveloop, simexact,
  latchtest, maxima, explain, finaldiv, vcontact, traceback, mapfirst,
  clean_pack, mkcanary, gen_flick). All gitignored; keep the six that
  matter (gen_pack, regiondiff/mapdump/levercheck, verify_par,
  diff_engine, nonhier_suite) when pruning.
- Dead ends recorded: repeater-locking (no side cells anywhere on the
  fault paths), comparator modes (all subtract, modeled + oracled),
  torch burnout (relight + full torch replacement both leave Y2 lit;
  not the mechanism), bistable loops (zero torch cycles full-build,
  even with slope edges; sim drains from full-hot seed in 353 ticks),
  paste gaps (presence/facing verified for all 3862 devices; the 629
  property-less repeaters are all intended-north = defaults match),
  stale power in schem (palette is all power_0/powered=false/lit=true),
  chunk loading (2375 forceloaded, schedules advance at full 20tps).

### simvec mirror + ref freeze (same session)

`simvec.py` tables mirror the below-feeds (`c_dust/c_torch/c_lev/c_rblk`
gain below-neighbour rows; repeater/comparator cannot face up, so no
new rows there). `diff_engine` is ALL IDENTICAL across ref/live/scalar
afterwards. `scratch/ref_sim.py` re-frozen via `mkref.py` (the +19 is
exactly the cob_state hunk).

### color organization: per-net floor quilt + markers (same session)

Course-style readability (redstone-university: colored wool per signal).
`export_marked.py` recolors y=0 floor pads per net (20,566 pads, curated
colors for inputs/outputs, hash for the rest) + 15 labeled wool marker
columns. Sim/router untouched (recolor is post-compose; router never sees
wool). Preview COLORS +16 wool. In-game auto-suite is the physics gate
for the recolored build.

## Overnight: cpu4 GREEN 128/128 via combination-aware retry (same session)

cpu4's Y2 ghost reproduced under the fixed sim with fresh bands (all 10
green per-band in 92s, merge 105,080 blocks, SMOKE 0101010 MISMATCH Y2).
New tool `scratch/hier_retry.py`: on merge smoke mismatch, map failing
outputs to fanin bands (gate-arg closure), skip their cached rungs via
HIER_SKIP, re-climb, re-stitch, re-smoke (bounded iters, hang-safe).
First retry round (7 Y2-fanin bands re-climbed) merged 129,953 blocks
with 4/4 smokes green; full `verify_par` then 128/128 green (~9 min).
Exported `build_cpu4retry.{schem,mcfunction,html}` (7 levers, one column
x=3 z=3..63). Lesson: the ladder optimizes bands standalone but
correctness lives in the combination — retry must too. Lesson 2: the
fixed sim's below-feeds didn't move cpu4's geometry (bands re-climbed
identically green); the fault was purely combinational rung choice.

### GA superoptimizer parallel + adder run (same session)

`scratch/evolve.py`: netlist mutations (buffer/dedup/dead/rebind/unshare/
factor) with exhaustive equiv gate + compose/verify fitness. Hardened for
speed: memo dict (sha256, survives restarts), batched parallel evals (4
direct non-daemon children like hier_bands, hard deadlines, low priority
so the game stays playable), hillclimb-from-best with elitism. PoC:
pessimize mux2 (14 gates) recovered 13311->5387 = exactly the known
optimum (dedup fired). Notable: rebind/dedup mutants often pass equiv
but fail sim (shared-nS, band moves change physics, not logic) — the
two-stage gate earns its keep; equiv is necessary, never sufficient.
SOP-form adder (91-gate minterm mesh) does NOT route in 10 min: starting
points must be near-routable. Queued: add2fat (19 gates, equiv-proven)
100-eval run detached.

### insulate() post-pass + alu1 repaired (same session)

Generalized the 7-pillar fix into `scratch/pillars.py:insulate()` (any
pkl in/out: sim-dark dust-on-cobble y>=2 with torch/dust feed, no
attached torch; tile bodies excluded after the 579-swap broke tile
attaches on alu4). alu1: 3 torch-pillars -> `scratch/alu1glass.pkl`,
sim-verify 32/32 x3 runs, block count identical (13300), exported
`build_alu1glass.*`. Full nonhier suite: 6/7 green with counts
bit-identical to the handoff record (example 144/322/224/214, micro1
2925, ctrl_decode 5499); alu1 RED is the fixed sim catching the same
pillar class (repaired via glass, not a regression). Lesson: recolor
(safe, post-compose) vs repillar (changes conduction, verify-gated)
are different operations with different gates; never blanket-swap.

## Overnight 2026-10-03/04: TRUE 3D TILE STACKING v1 (stack3d.py) — DONE

DONE = true 3D tile stacking. Delivered: `stack3d.py` (new file, ~900
lines, zero engine edits) + `build_stack3d.*` demo (gitignored outputs,
regenerate: `PYTHONHASHSEED=0 python stack3d.py`, ~3 min).

ASSUMPTIONS (per sleeping rules, logged not asked):
- A1: DONE means a genuinely stacked build (two tiles sharing one
  (x,z) footprint on different decks, signals crossing decks),
  composed end-to-end by the pipeline and sim-verified green -- not a
  full 2D->3D map migration (the ~140-site migration stays documented
  in tiles.new_ctx; this is the deck post-pass rung below it).
- A2: reference HDL repos skipped after a listing peek (all flat
  compilers, no stacking pass); the in-repo hier pipeline + post-pass
  is the mechanism.
- A3: course priority = compact/stacked slices (user's redstone-
  university note); wool color-coding stays OUT tonight (the marked
  quilt already proved untestable: sim raises on wool).
- A4: verify = sim_verify 8/8 on the merged build + engine suites
  (compose/recipe/sim/export self-checks) + deterministic rerun
  (PYTHONHASHSEED=0). No paste test possible overnight (needs hands).

### Design (maps untouched; decks merge vertically as a post-pass)
- Each deck composes FLAT via layout_retry(verify=True) (proven
  regime); deck1 translates +5y over deck0's footprint; glass floor
  plate at y=5 (transparent: conducts nothing, cuts nothing, floats
  legally); boundary nets cross decks on staircase vias; sim gates all.
- Deck pitch 5: lower decks top at y<=4, sim couples dy<=1 only, so
  dy>=2 is parasitic-free by construction. Translation (never mirror:
  preserves facings + dust shapes). Glass pillars for all via support
  (inert; a cobble pillar beside foreign dust is a parasitic feed --
  the engine verifies glass wire but never stamps it, compose.py:2337).
- Vias: driver-region taps (sim-measured level-15 cells, not arbitrary
  leg cells) -> y=1 leg -> fixed diagonal shaft (x+i,1+i, provably
  stack-free) -> top booster (flat+repeater, fresh 15) -> y=6 leg ->
  forced end diode INTO the ex-lever cell (B's leg then behaves exactly
  as standalone with lever on) -> port-aligned translation (drivers
  over feeds, not centers: 35-49 dust dead-on-arrival otherwise).
  Periodic diodes every <=7 flats, straight-runs only (a corner diode
  faces one branch and reads the other dark).
- Feed points = ex-lever cells (unambiguous, one per boundary input);
  B's tile-side runs kept whole (an earlier component-strip orphaned
  the diode→junction continuation: diode firing into air).

### Failures measured along the way (each a real rule now in code)
1. Decay: 40-cell unboosted vias arrive dark (shaft top needs entry
   >=7). Fix: taps at drivers + boosters (top mandatory, periodic,
   forced end diode). Caught a real typo this way (rep z missing 2*:
   every z-directed booster was a dud).
2. Order landlock: first via's wall starves the second (6 starts, 0 of
   166 shafts, both orders). Fix: longest+shortest order retries with
   rebuilt state + 3x3 avoid columns around the other feed.
3. Dust-on-dust stacking (leg above shaft, booster flat above shaft):
   reserved sets + explicit pillar-on-path/self-stack rejections.
4. Slope coupling: sim reads diagonal dust (cup/cdn) regardless of
   lids on transparent supports -- clearance covers 8 vertical
   diagonals + above, not just orthogonal.
5. Dust-on-torch supports reused (occ-only rule): support-valid set
   (mirrors sim._check_supports) gate.
6. Diode severs: diodes planted on pre-existing nets face walk-dir and
   cut loads behind (deck0 t lamp dark with driver lit). Air-only
   paths (joins by adjacency at endpoints) + no diodes on B runs.
7. Lamp arms: via dust hugging a lamp corner-blocks its arm (t lamp
   dark at 13 on the arm). Vias keep 1 cell from every lamp block.
8. Hairpins (leg doubling back over booster) + degenerate loops:
   explicit rejects, next shaft.

### Result
`stack3d ok: 8/8 vectors` (FULL recipe t/c2/y), 2464 blocks, 122
shared footprint columns, 2069 glass, 11 repeaters on vias. Decks
overlap (asserted structurally, not side-by-side). Engine suites all
green (compose lwire/compose/buffers, recipe xor/fanout/latch/gate,
sim canary+tall-bridge+latch+lamp+burnout+ladder+budget, export pack).
Deterministic under PYTHONHASHSEED=0 (compose geometry otherwise
varies run to run: 268 vs 324 blocks measured on deck0).

### Course mapping (redstone-university 09 ALU, verified read)
- Dust staircase (vertical wire) = via shafts. Glass insulation
  between floors = the plate. Bit-slices = BANDs (already).
  Comparator-XOR = dual-subtract tiles (already).
- Through-floor reads do NOT span pitch 5 passively (weak power
  doesn't hop block-to-block; needs repeater zigzag): documented v2
  direction (2-tall slices need redesigned tiles, not translated
  flat ones), not attempted.
- Compact/stacked tiles: v1 stacks flat-composed decks (course would
  hand-design tighter slices; GA superoptimizer is the code lever).

### TODO (ordered)
1. Paste test (needs hands): `build_stack3d.schem` (952 B) -> tell me
   B0 and I regen a `stack3d` datapack suite in 30 s (vec/readsay fns);
   or hand-test 8 vectors (3 levers a/b/c, lamps t/c2 deck0 + y deck1).
2. stack3d generality: demo-hardcoded SUB_A/SUB_B/FULL + boundary
   ["t","c2"]; generalize to BAND partitions (alu1 4-deck stack is the
   obvious next demo) once one paste test confirms vanilla parity.
3. True map migration (tiles.new_ctx 2D->3D) remains the full fix;
   stack3d is the v1 capability on top, not a replacement.
4. wool==stone one-liner (sim.py:865) still open before any marked
   (quilt) build pastes again.
5. evo_add2 (add2fat 100-eval) was still running at session start;
   check `done best=` before trusting old evo numbers.

## Evening 2026-10-03: repeater side-lock modeled (user lesson) + glass ladder canary

User (in game): glass staircases conduct UP but never DOWN in Java;
and a repeater feeding its own side sticks ON permanently. Both
verified against the sim before touching it:

- Glass ladder: sim already models exactly this (dust_lvl DN term
  accepts any solid rest incl. glass = climb; UP term still needs
  opaque cobble = no down-feed on glass). Measured probe: glass
  UP 10 / DOWN 0, cobble UP 10 / DOWN 10. No physics change; the
  recipe is now a canary (`glass ok` line covers tower + down-block).
  stack3d shafts already ride this (glass pillars).
- Lock: sim did NOT model it (fresh A=1,B=1 read 1, vanilla locks 0;
  no "lock" anywhere in sim/simvec). Real vanilla-parity gap.
  Implemented: sim.rep_locked (side terms mirror comp_in sides +
  lit torch) + rep_val hold-last (power-on locked stays off) + wake
  on behind-or-beside (sides were deaf: late lock/unlock read stale).
  simvec mirror: r_side specs (+torch variant), _rep_on_s hold,
  side wake edges. Canaries: fresh-1,1 freezes off; output→own-side
  latches on across sim_sequence phases.

Gates, all green: sim suite (incl. 2 new lock canaries), diff_engine
ALL IDENTICAL (ref/live/scalar), compose_check 144/322/224/214,
nonhier 6/7 bit-identical (144/322/224/214/2925/5499; alu1 RED is the
known pillar fault, proven byte-identical pre/post lock by stash A/B
on alu1_current.pkl: same 4 Y vectors), chainmix 11497 + mux4 20239
fresh recompose+verify green, stack3d re-verified 8/8 (2464 blocks,
identical geometry) under the locking sim.
NOT re-run (needs quiet machine; GA still grinding add2fat):
alu4glass7 1024v (timed out at 900s under GA+game load; prior green
289s pre-lock) and cpu4retry 128v. Queued, not skipped.

## Night 2026-10-03 (2): lock diverges serial-vs-scalar on alu1glass

alu1glass.pkl (shipped green 32/32, exported): serial GREENS it,
scalar (run_scalar, what sim_verify actually runs) REDS x12 (Y on
OP01 vectors, COUT on ADD). Bisected to a side-locked repeater pair:
both side cobbles hot (dust above), back glitches in one event order
and holds in the other -- 598 dust + 86 rep cells diverge downstream.
Scalar's state is NOT a sim fixpoint (serial walks it to y=1), but
that probe is inconclusive (init seeds dust/torch/rep, not cobble
power: a 1-tick transient can unlock what settled locked).

Standing question, recorded not guessed: pre-roll (serial) starts
from a fixpoint with sides hot (glitch arrives locked-off, ignored);
blank-start (scalar, and arguably vanilla power-on) races the glitch
against the sides. If vanilla latches the glitch (1-tick pulse
suffices for a delay-1 repeater with hot sides), the x12 are REAL
vanilla faults and alu1glass needs side-feed repair (same saga shape
as pillars: sim-green/game-broken until the model caught up). If
vanilla doesn't latch, my side terms are over-broad somewhere.
QUEUED FOR GAME: paste build_alu1glass.schem, 4 vectors from the
mismatch list (ask me, I'll print them), report lamps. Until then
the x12 stands LOUD (not waived, not reverted).
diff_engine suite gap noted: its sampled builds have no side-powered
repeaters, so it gates lock vacuously; the sim canaries are the real
lock gate for now.

Lesson for the router: side-lit diodes are now load-bearing truth,
not decoration. stack3d vias already keep foreign dust off diode
sides (clear()); same-net side dust self-follows (settles +1 tick,
verified). No new exposure class.

## Night 2026-10-03: bridges beat detours (router cost, user ask)

User: make a bridge cheaper than long wires. Was true: lwire ranked
flat corridors by seals then length, so a 200-cell clean detour beat
a 20-cell corridor needing 2 hops (bridges only fired on failure).
Fix (compose.py only): _score_cells returns (fatals, hops, eff) with
eff = len + 2*hops (a hop costs ~flat+marginal); candidates sort by
(fatal, eff, L-first); fast-path perfect check is fatal==hops==0
(same winner guaranteed: Ls are Manhattan-minimal). Open-field
scoring is byte-identical (no seals: eff==len).

Gates: compose self-checks green; 4 small bit-identical
(144/322/224/214); micro1 2925 + ctrl_decode 5499 green identical.
alu1 suite RED as before (pillar fault) but changed SHAPE
(sim-mismatch x-vectors -> compose no-ground on one seed): blame-
restart is order-sensitive, new order explores a new trajectory.
NOT a regression (never green flat; glass repair path intact --
alu1glass re-verify queued below). Compose geometry is hash-seeded
nondeterministic across processes anyway (268 vs 324 measured).

GA add2fat found DEAD at eval 40/100 (out tail 18:33, empty .err,
no python alive 23:48): silent death ~5h ago, cause unknown (OOM?
host sleep? NOT restarted: midnight CPU burn while user is on the
machine + memo staleness under locking sim needs a look first --
memo keys netlist hash; pre-lock fitness entries may be stale).
Resume cmd: `python scratch/evolve.py scratch/add2fat.txt
scratch/evo_add2 100 2` (memo.json resumes). Queued for direction.

## Evening 2026-10-03 (2): stacked preview IO + schem restage

User: preview IN/OUT broken; did the .schem update? Both real:
- Preview shipped with states=None (no lever/lamp maps). Fixed by
  collecting sim states in stack3d + a real engine gap found on the
  way: sim_verify's collect dicts hardcoded "x,1,z" keys and CRASHED
  (ValueError) on the deck1 y=6 lamp. Fixed with _iokey (2-tuple =
  y=1 as before, 3-tuple carries level; flat builds byte-identical).
  Preview now embeds levers a/b/c + lamps t/c2/y@deck1 + 8 vectors.
- Staged schematics copy WAS stale (repo schem re-exports on every
  green run and geometry varies run to run despite PYTHONHASHSEED --
  compose has unseeded randomness somewhere; determinism claim in the
  morning report softened to per-run verification, which is what
  actually gates). Restaged + hash-matched (D747DA35).
  Correction method for the future: compare hashes, never assume.
