## Night 2026-10-04: alu1 band 2 wall (3 approaches exhausted)

**DONE: edge-lever fix committed (2722ad1)** — alu1 band 3 green, non-hier suite bit-identical.

**STUCK: alu1 band 2** (11 gates, 10 inputs). Three approaches exhausted:

1. **Recipe restructuring (alu1_self.txt)** — band 2 self-contained (5 recipe inputs, 0 boundary). All 4 bands place green. Stitch fails: OP0 ring collision at (550,1,2) — bank OP0 (-4,-89) to band 2 stub (542,2) creates ring 8 cells east of stub. HIER_SKIP (rung 2→3) same collision.

2. **Wider spreads on band 2 sub-recipe** (spreads 1-10, short/long, gates/inputs_first) — all 32 rungs fail:
   - gates_first: OPEN orphan OP1 dust at z=23
   - inputs_first: no ground for m0 (local run crosses n1/B horizontal runs, 1-cell canyon unhoppable)

3. **Flat compose ladder** (30 rungs, spreads 1-10, short/long, gates/inputs_first) — all fail:
   - spread 1: OP1 touches OP0 at y=3 (vertical run collision)
   - spreads 2-10: no ground for OP1 (lane march from west edge to port at (4,12) crosses tile apron)

**Root cause (measured):** Band 2 has 10 inputs (6 boundary + 4 recipe) feeding 5 west-fed AND gates in ONE grid row (z=12). Each gate's A port is a 1-cell funnel at (ox-2,12) with only one legal approach (west along z=12). 6 edge levers sit ON z=12 (median load row), wall-to-wall. 4 recipe input lanes also march east along z=12. **5 gates share one approach lane** — structural limit of current tile geometry (AND tile A port admits exactly one approach lane). Same wall as LOG.md:128.

**What's needed (not a rung):** AND tile A port needs a second approach (north/south) by freeing the outer funnel cell (ox-2, gz-1). Requires tile geometry change (blast radius: all AND tiles) or bus/hierarchical router subsystem (days, design session). Per LOG.md:372-380: ">9-input field needs a bus/hierarchical router — new place-and-route subsystem, not a ladder rung."

**Recommendation:** Do not burn more cycles on ladder rungs. Wall is architectural. Next session: design decision — tile geometry change vs. bus router vs. move alu1 to known-hard/.
## Night 2026-10-04 (3): squeeze continues, compactor goes loud

User stopped a run that looked stuck. It wasn't: the Select-Object pipe
was buffering all output to exit, and the heartbeat didn't exist yet.
Two fixes, both in compact.py: a `... evals=N blocks=N` heartbeat every
pass (plus every accept line, unbuffered via python -u, no pipe), and
best.pkl saved after EVERY accept, so a killed run keeps its progress
(the killed slice had reached 4371 in-log but best.pkl still said 4382;
11 blocks of progress evaporated -- now impossible).

    slice 300e seed4: 4442 -> 4411  (31 acc, 10%)
    slice 300e seed5: 4411 -> 4382  (29 acc, 10%)
    slice 300e seed6: 4382 -> 4366  (16 acc, 5%)
    total: 4648 -> 4366 (-282, -6.1%, ~1560 evals)

Hit-rate curve: 47 -> 29 -> 19 -> 11 -> 10 -> 10 -> 5. Still positive,
clearly asymptotic. Wire tier still yielding; repeater/cobble/stone
tiers still untouched. Promoted 4366 to build_add2opt.*.

## Night 2026-10-04 (4): squeeze slice seed7

    slice 300e seed7: 4366 -> 4350 (16 acc, 5%)
    total: 4648 -> 4350 (-298, -6.4%, ~1860 evals)

Hit rate holding at ~5%, all wire tier. Promoted 4350 to build_add2opt.*.

## Night 2026-10-04 (5): autonomous squeeze loop (operator AFK)

Assumption A5: DONE = wire-tier single-deletion exhaustion, defined
operationally: two consecutive 300-eval slices with <=5 accepts each,
then one confirm slice; promote best, write MORNING-REPORT, stop.
Repeater/cobble/stone tiers get tried naturally once wire stops
yielding (loop restarts from wire tier only after an accept).
Rule 3 armed: if 3 consecutive slices all land <=5 with no new tier
reached, switch approach (2-block moves) instead of grinding slice 4.
Other agent active on alu1 (hier_stitch.py pid 10916): my slices stay
foreground-bounded with heartbeats; no kills except my own orphans by
command-line match.
    slice 300e seed8: 4350 -> 4339 (11 acc). Promoted.

## Night 2026-10-04 (alu1 GREEN)

alu1 VERIFY OK 32/32 (hier gate, BANK=1 default). recipes/alu1.txt promoted to 22-gate 2-band restructured recipe (equiv-proven vs original). Fixes: edge-lever lane-march skip (2722ad1, band 3 green); bankdrop west-approach retry (stitch ring); split-NOT qn1a/qn1b (side-lock latch). Full trace: notes/alu1-green-2026-10-04.md. Project history recovered at notes/LOG-history-2026-10-04.md (was wiped from this file twice tonight -- see notes file; needs operator merge decision).
    slice 300e seed9: 4339 -> 4333 (6 acc). Promoted. (One more low slice starts the <=5 streak.)

    slice 300e seed10: 4333 -> 4326 (7 acc). Promoted.
    Rule-3 switch (slices 8/9/10: 11/6/7, long 5-7 tail, repeater tier
    never reached because wire always yields first): adding tier-focus
    so a slice can sweep the full repeater tier (286 blocks) instead of
    grinding wire at ~7/slice.

    repeater-focus slice 400e: 4326 -> 4278 (48 acc, 12%). The tier-focus
    switch paid off immediately: repeaters had 48 removable (redundant
    refresh on short runs, sim confirms timing still closes). Promoted.
    NOTE: operator reports another agent on optimization (prof_router.py
    on decode3, pid 27652, since 11:03). Pausing slices while their
    timing run is live -- my sim pool would skew their measurements.
    Doing read-only analysis meanwhile; zero engine edits (their profiler
    imports the router; I touch nothing it reads except by import).
    Polite mode while prof_router lives: REDSTONE_SERIES_VERIFY=1 in my env only (no engine edits) -> my slices run 1 core, their wall-clock timings unskewed. Slower (~4s/eval), so 100-eval slices.
    repeater-completion slice (serial, polite): 4278 -> 4269 (9 acc/100e). Repeater tier nearly exhausted. Promoted.
    Other agent's profiler exited (no python left). Resuming full-parallel slices.

## Night 2026-10-04 (opt pass: serial sim -43%)

sim.py _run_vec: stall window + lever/trace env reads hoisted out of hot loop (4.6M len, ~170k environ.get gone); same-tick re-queue coalescing in sched() (simvec's proven pattern). Measured: 5.34s -> 3.04s / 16.75M -> 9.08M calls. redstone_mini.py skips the 2.2s demo preamble on custom runs. Exporters (0.58s), simvec, router measured clean, untouched. Gates: sim suite + diff_engine ALL IDENTICAL + nonhier bit-identical. Heap->buckets (~11%) and dirty-bit wake (~big) parked as TODOs -- reference-ordering risk.
