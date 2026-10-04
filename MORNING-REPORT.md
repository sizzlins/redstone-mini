# MORNING REPORT — autonomous session 2026-10-04 (alu4 Y2 fault fixed)

## DONE: alu4 verifies 1024/1024

**What now builds:** `build_alu4bank.*` re-exported from a 5-pillar
glass-swap repair of the banked merge: **VERIFY OK: 1024 vectors, 16
chunks green** (staged verify_par, ~30 min). Block count identical
(60724), 10 levers still one column. The October pillar-feed saga is
closed: the sim was right, the build was wrong, the build is now right.

## The fault and the fix (short version; full trace in LOG)

- **Fault:** torch-topped cobble pillars inject parasitic power into dust
  above them (below-neighbour feed the old sim never modeled). On all-off:
  Y2 stuck lit (1570 lit-should-be-dark dust cells, whole runs hot).
- **Blanket insulate() FAILED** (tried first): swapping all 579 fed
  pillars went 2/4 -> 4/4 red -- most fed pillars carry LEGITIMATE
  vertical conduction; glass kills it. Discarded; original pkl untouched.
- **Targeted fix:** settled-state forensics (lit dust + dark logic ->
  torch-fed pillar under it, restricted to the failing output's fanin):
  4 pillars for Y2 (`612,2,221 612,2,224 851,2,189 963,2,208`), 1 more
  for residual COUT (`1855,2,231`). 5 swaps -> smoke 4/4 -> 1024/1024.
- **Reproduce:** `python scratch/ins_target.py scratch/alu4bank.pkl
  <out.pkl> 612,2,221 612,2,224 851,2,189 963,2,208 1855,2,231`
  then `hier_stitch.py` smoke + `verify_par.py`. Tools:
  `scratch/y2trace.py` (fanin forensics), `scratch/ins_target.py`.
- **Exported:** `build_alu4bank.{mcfunction,schem,html}` (static HTML;
  1024-vector interactive states not collected -- ~20 min, optional).
  Game `build.schem` NOT touched (needs your paste).

## Not done / open

1. Generalizing the fix (verify-driven insulation: swap torch-fed
   pillars whose dust is dark on ALL vectors -- provably safe, unlike
   blanket) is designed but unbuilt. Current fix is 5 merge-space
   coordinates; a re-merge invalidates positions. TODO with the design
   in LOG.
2. Subset-minimization of the 5 swaps skipped deliberately: each subset
   would need its own 1024-verify (9 x 30 min); the set is proven safe
   as a whole, minimality is aesthetic.
3. LOG.md sharing: unchanged situation, still needs your merge decision
   (history in git + `notes/LOG-history-2026-10-04.md`).

## GA agent status (observed, not touched)

Squeeze loop still running. No file overlap (my work: scratch probes +
  gitignored pkls + LOG/MORNING-REPORT appends). No collisions this
  session. Tree clean except the two protected `.bak` files.

---

# MORNING REPORT 2026-10-04 (squeeze agent, ~12:30)

## DONE: 2-bit adder 13359 -> 3730 blocks (-72%), verified

| stage | blocks | how |
|---|---|---|
| fattened seed (GA start) | 13359 | predeterministic padding for the GA |
| GA best, eval 40 (stalled) | 6707 | random mutation, 17 gates |
| after op_simplify | 4648 | exact algebra: X AND X->X, NOT NOT->X, dead sweep (17->8 gates) |
| after level-3 block compaction | **3730** | 1000+ sim-gated single deletions, all tiers |

Final artifact: `build_add2opt.{mcfunction,schem,html}` (8-gate ripple-carry,
16/16 vectors green, support-audited 0 violations, extent 323x80x4).
Acceptance re-run this morning: recipe-identical, sim green, audit clean.

## What I need from you (human)

1. **Game paste of build_add2opt.schem** (16 vectors: 00+0..11+1 x cin... full
   4-bit input space is 16 combos; lamp check S0 S1 COUT). The compactor
   optimizes against the sim; one paste closes the loop. Non-negotiable
   before this replaces any banked adder.
2. **LOG merge decision**: notes/LOG-history-2026-10-04.md (other agent
   recovered full history after mutual overwrites). I stayed append-only;
   nothing of mine needs rescuing, but read their file before assuming
   LOG.md is complete.
3. **Footprint call**: count-squeeze is DONE (criterion met 4x over), but
   width/depth (323x80) is placement-pinned: min-x=lever pins, max-x=east
   wire trunk, z-extremes=live wire. Shrinking the box = tighter compose
   spread / pin packing = router lane. I left evidence + ask at
   notes/to-opt-agent.md. Say whether to pursue with them or bank 3730.

## What still fails / known gaps

- evo_add2 GA never resumed (memo fingerprinted, best.txt=8-gate seed ready;
  resume command: `python scratch/evolve.py recipes/add2fat.txt
  scratch/evo_add2 100 2` -- but the netlist is already minimal, so the GA
  has nothing left to find there; only useful for NEW recipes).
- Pair-deletion moves not implemented (singles exhausted; adjacent-pair
  probe is the obvious next 1-3% if you want it -- ~20 lines in compact.py).
- alu1glass sim-red x12 (lock ambiguity) predates me tonight; untouched,
  other agent + your game check own it.
- My piggyback lesson, twice learned: scripts that call sim_verify MUST
  have the `__main__` guard (spawn re-imports), and the sim is BLIND to
  structural support (242/300 poisoned stone deletions, caught by static
  audit before promotion -- full story in LOG.md Night (6)). Both are now
  enforced in compact.py (guard + _load_bearing pre-filter, FN=0 validated).

## Coordination state

- Other agent (router/optimization): truce held all night. Paused heavy
  slices during their prof_router timing run; ran serial 1-core meanwhile.
  Their engine changes are semantics-preserving per their note; my loop is
  drift-resilient by construction. Their files (hier_*, simvec.py) and
  processes never touched. Open thread: my notes/to-opt-agent.md footprint
  ask; their notes/to-ga-agent.md (all three points acked in LOG.md).
- No strays: no python processes of mine remain (verified pattern each kill
  by command-line match before touching anything).
