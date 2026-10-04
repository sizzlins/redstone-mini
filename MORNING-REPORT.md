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
