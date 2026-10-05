# Handoff — redstone-mini, phase2-design (2026-10-05)

Supersedes notes/handoff-ga- agent.md + notes/handoff-opt2 agent.md (both kept
for history; this file is the current one). Two agents share this tree; the
opt agent's lane is speed (simvec table engine), this lane is gates + builds.

## Goal

Every recipe generates, verifies, and exports with evidence that survives an
independent implementation (sim AND cmc, per-cell). Standing project goal;
tonight's work was the verification layer, the 49k diff, add8, alu8 start,
and a survey of downloaded redstone computers.

## Current state

| what | state | evidence |
|---|---|---|
| **add8 + 16 indicators, pitch 2** | **GREEN LIVE, 44,650 blocks** | **19/19 in real Minecraft, overflow included** |
| full coldstart | **16/16 green** | new `pin_lamp` gate |
| LAMP pin | **now a routed load** | band S0 pinned to lever row: 1,054 blocks (vs 135,260 naive) |
| sweep (99 builds) | 21 green / 28 red characterized / 2 DIFFs | sweep.json at 1200 ticks |
| add8 exhaustive | 65536/65536 green (opt lane, XOR version) | commit 83fbd60 |
| alu8 | all 8 bands ROUTE (first time) | merge oscillates: churn 52,985, max_gap 205,950 |
| known diverges | stairglass 0v13, notmin (Finding 3) | contained, gated, re-confirmed |
| cpu4 | red by inheritance, untouched | not this lane |

### Live rig: ONE BUILD PER REGION

| region | what | state |
|---|---|---|
| **z 803..973** | **add8 pitch-2 + indicators** | **19/19 green** — `/tp 2 68 820` |
| z 404..483 | add2opt | re-pasted, intact |
| z 303..403 | orphaned first add8 paste | ignore |
| z 3..293 | four-deep stale add8 debris | **ignore** |

Use `scratch/live_check.py` (reads levers back, 20s settle). Do **not** use
`rig_read` for anything big: it never reads the levers back and settles too
briefly, so a slow carry chain reads as a wrong bit.

### The one trap that cost the whole night

Every in-game add8 failure until now was **my own pastes overlapping**, not the
circuit. `build1..4` were one add8 pasted four times at z offsets 0/0/1/2, and
add2opt (z 404..483) sat inside tonight's add8 (z 303..473). **Read the paste
log — the rig's datapack still holds every function ever pasted, with
coordinates — before believing any live measurement.**

Related: never compare a wire's full NBT with `execute if block`; the game
recalculates `east/west/south/north/power` on placement, so it always says
false. Compare the type.

## What changed (this lane's commits, newest last)

1. `d6b74e7` — 49k root cause (settle ticks), verify2 default 400->1200,
   stairlid.py + repchain.py probes, coldstart 14/14.
2. `4ba4214` — repface.py covers all 4 facings, all agree.
3. `a72e5d5` — 64-vector 0/1957248 proof, MORNING-REPORT update.
4. `dc399cd` — slabfall.py documents cmc slab-support refusal (0 slabs in
   2.5M banked blocks, provably out of scope).
5. `01ea4db` — sweep refreshed at 1200 ticks, 21/28/2.
6. `d714dbe` — full coldstart 15/15, slab census, report.
7. `17460d0` — handoff addendum + add8 OR-version green files.
8. `1ecc57b` — add8 NAND carry, 46,502 blocks, dual PASS.
9. `6924c6d` — build_add8.html/.schem/.mcfunction.
10. `7b1fca1` — alu8 recipe (add/sub/and/or/xor + ZNC flags).

New probes (all 2s runs): stairlid, repface (x4), repchain (gates, green),
slabfall (refusal probe, exit 2, not a gate). New recipes: add8.txt (NAND
carry), alu8.txt, add8b0-7.txt (band seeds). New tools: census_world.py
(Anvil + Bedrock census), repchain/stairlid/slabfall above.

## What failed / is open (with owner)

1. **alu8 bands 0-6 red** — double-NOT pairs seal each other; rewritten
   without OP1x/OP0x, recipe re-verified, ladder retest PENDING. (this lane)
2. **OR-tile recs go stale in bands** — add8/add4 carry-OR drivers vanish in
   merge while C1 (AND) survives; worked around (OR-less carries), NOT root
   caused. Needs engine owner (compose/tiles lane). Evidence in LOG.md.
3. **Glass down-flow** (sim 0 vs cmc 13) — needs wiki/game adjudication;
   fix mapped (sim.py:405 toward sup3 + simvec mirror), NOT applied
   unilaterally. Needs operator.
4. **Non-pin lever** (Finding 3) — needs directional-source physics in both
   engines; contained (gate warns), notmin seam ready. Needs operator call.
5. **cpu4** — red by inheritance, untouched. Other lane.
6. **Evo squeeze too slow on loaded box** — 0 evals/30min; parked
   (scratch/evo_add8b1). Retry on quiet box or faster eval.
7. **PMC profile download blocked** — Cloudflare challenge, no headless
   bypass. Mirror had 2 maps; GitHub BatPU/BatPU-2/Graphing-Calculator cloned
   to D:\put gitrepos here\. Survey at survey/REPORT.md + census.txt.
8. **Sum lamps at the lever row — root cause FOUND, fix is forward
   reservation.** The pin mechanism is DONE and gated (`pin_lamp`, 1,054 blocks
   per run in-band). What blocks the 9-lamp version is NOT a pin bug and NOT
   distance: on the real merged field (via `REDSTONE_HIERDUMP2`) `compose.lwire`
   from S0's driver `(39,32)` dies **12 blocks out** with `no ground for S0`.
   That message means the router failed to *escape a seal* — its recovery is to
   hop a foreign dust column (compose.py:630-640), and at a driver the net's own
   3x3 ring (1,550 ring cells) is the wall. The own-ring that stops shorts also
   **walls the net in**, and no green build noticed because every load is placed
   *before* it is ringed.
   **Fix:** reserve a street from the bank to each sum driver at compose time,
   the same trick that makes the lever bank work (`_bankstreets` reserves
   corridors; the stitch aims into the real gap). Reserving after the fact
   cannot work — the ring is already a wall. This is `hier_bands`/`hier_stitch`
   work, not pin work.
   Ruled out: `sup` keying (it is `(x,y,z)` as `_walk` reads it, and holds only
   the 1,592 paid hop supports), distance/attenuation (dies at 12), and the pin
   itself (gated).

## Files touched (this lane)

Tracked: recipes/add8.txt, recipes/alu8.txt, recipes/add8b0-7.txt,
scratch/verify2.py (ticks default), scratch/coldstart.py (+2 gates),
scratch/stairlid.py, scratch/repface.py, scratch/repchain.py,
scratch/slabfall.py, scratch/census_world.py, scratch/sweep.json +
verdicts, LOG.md, MORNING-REPORT.md, notes/handoff-ga- agent.md (addendum),
handoff.md (this file), build_add8.*.
Force-added under gitignored scratch/: *_bands.pkl, add8merge.pkl + docs.
NOT touched: sim.py, simvec*.py, compose.py, layout.py, tiles.py, evo_*,
evolve.py, compact*, memo.json, verify_par.py, rig_verify.py, rcon.py,
cmc/, reference repos.

## Shared-tree discipline (still binding)

- `git commit -m "msg" -- <paths>` only; `git add -f` for scratch/.
- LOG.md append-only; never rewrite. Never checkout/stash others' files.
- Co-tenant live: simvec_numba.py + verify_par.py were uncommitted at last
  check; verify_par fingerprint now covers simvec_numba.py (caches void once).

## Next (narrowest first)

1. Re-run alu8 ladder (rewritten recipe) → stitch → smoke → sampled verify.
2. Stitch + verify alu8; render + schem on green.
3. 8-bit register file (locked-repeater pattern per survey) + output latch.
4. BCD + 7-seg display (~1k lamps budget) → calculator shell complete.
5. Control sequencer + RAM (full CPU) — largest slice, last.
6. Operator-only: paste build_add8.schem on 1.21 rig; rule glass + lever calls.
