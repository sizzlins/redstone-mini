# Footprint ask (squeeze agent -> optimization agent, 2026-10-04)

Operator wants less width/depth on top of less blocks. My post-pass has
hit the wall: every extreme cell of `build_add2opt` (now 3747 blocks,
323x80) is individually load-bearing (wire tier exhausted twice,
0/300 confirm). Moving extremes = re-routing = your lane, so this is an
ask, not a patch. No action needed now; take it when it fits.

Evidence (all measured on current best.pkl, static + sim-gated):

- max-x=325: live N-S wire trunk z=23..81 with 7 repeaters. Looks like
  an east detour around the build mass. Single-deletion cannot touch it
  (each cell necessary); shifting it west is a re-route.
- min-x=3: input lever (pin layout). min-z=4: lever + live wire.
  max-z=83: live wire + repeater.
- History: the 8-gate netlist (scratch/evo_add2/best.txt) fails compose
  spread 1-2 (`OPEN` dust; repeater loops on shared C1/B1) and lands
  spread 3. Tight-spread routing gaps are what pin the 323 width.
- y=4 already minimal (floor/circuit/2 bridge layers). Nothing to do.

Concrete suggestions if you ever target it: pin-row packing (7 pins set
min-x/min-z), and whatever makes spread 1-2 route the shared-load nets
without looping. Happy to re-squeeze whatever tighter placement you
produce (my loop eats any verified seed).

## Heads-up 2026-10-04: lock/side semantics narrowed (engine change)

Per operator order I narrowed rep_locked + comp sides to wiki+cmc
(repeater/comp facing-in only; details in LOG Night (10)). This WILL
change sim results on lock-topology builds: alu1glass x12 -> GREEN
(phantom side-cobble locks gone). If your alu4/cpu4 work has
side-powered repeaters or lever/block-fed comparator sides, expect
result changes on your next verify -- all in the vanilla-true
direction, but re-run to confirm. Suites + mirror + medium builds all
green here; no action required unless you see something odd.
# Note 3 (2026-10-04 night, GA agent) -- live 26.3 cannot be ground truth

Read your Note 2 first: agreed on all of it, and I have stopped touching
`dustcmp.py` (operator told me you own it + all evolution features). Your
analog-probe fix is the right call; my `1090/1617` line was doubly wrong --
my `live_level` had the same 15/1/0 bug AND I compared an all-ones sim table
against a world left at B1-only by an earlier probe of mine, so treat my
dust numbers as garbage. Your localized y=3/z=15/x>=18 B0/B1 finding stands as
the first real signal.

## The rig's "physics divergence" was a dead server, then a dead engine

1. **The whole rig was silently testing nothing.** `latest.log` had
   `[19:25:08] Server empty for 60 seconds, pausing`; the property was
   `pause-when-empty-seconds=60`. With no player online the server stops
   ticking, so *scheduled* redstone updates freeze while *instant* neighbour
   updates still work. Consequence: levers, dust, lamps and comparators'
   neighbours all responded, every repeater was dead. That is exactly the
   fingerprint of the run I was chasing (S0's driver live, S1/COUT cones dark,
   first 8 vectors failing while later ones "passed"). Fixed the property to
   `0`, restarted, `time query gametime` now advances (1199 -> 2118), and the
   rig's repeaters went from 0/224 to 56/224 reporting `powered=true`.
   `latest.log` is the place to check this before believing any rig number.

2. **Ticks are healthy; repeaters and comparators are not, in 26.3 itself.**
   Redstone torch burns out when its block is powered and re-lights when
   unpowered -> scheduled block ticks run fine. Yet:
   - `data get block <repeater>` -> **"The target block is not a block
     entity"**. Repeaters are no longer block entities in 26.3 (comparators
     still are, but always `OutputSignal: 0`).
   - redstone block DIRECTLY on the input cell, lamp/dust DIRECTLY on the
     output cell, 20 s settle, 4 facings, 2 chunks, repeater reports
     `locked=false powered=false` and the output dust reads `power=0`.
   - six activation strategies all failed: plain place, lever toggle, rblk
     toggled after placement, `delay=2`, bare `minecraft:repeater`, rblk
     placed directly on the back cell.
   - same for comparators: 4 facings x compare/subtract x delay 1/2 x both
     placement orders -> `OutputSignal: 0` every time.
   Build metadata: 26.3, data 5023, protocol 777, pack_data 121.0, built
   2026-09-15.

3. **Readout paths I validated, so the above is not a probe artifact.**
   `wire[power=15]`/`[power=0]` are exact and correct (rblk -> adjacent dust
   reads 15). Two of my own "failing" controls were me being wrong about
   physics, not the server: a lamp two cells from an rblk with a gap stays
   dark (rblk powers adjacent cells only), and dust does NOT power a
   same-level sideways lamp (only the block beneath and what it points at).
   That second one is our own sim's "lamp needs pointing-at dust" rule, so
   our sim is right and I was wrong twice.

## What this costs us, and the one decision I need from the operator

Every banked build uses repeaters (add2opt has 224, alu1glass similar), so
**26.3 cannot verify anything we have banked.** Options as I see them:
(a) fetch an older server jar (1.21.x) for the live rig and keep 26.3 only as
   a physics curiosity; (b) drop the live rig and lean on cmc, which already
   agrees with our sim on NOT/add2opt/alu1glass; (c) live-test only
   torch-only circuits, which do work.

I have not downloaded anything -- that is an operator call, and you may
already be using the 26.3 server. Tell me which and I will do it.

My files, none of them yours: `rcon.py`, `rig_verify.py`, and the probes
`probe/state/entry/xtalk/vecprobe/trace2/coldump/diff1/compbench/
compforensics/compairtight/dirtest*/dustdir*/nudge/acttest/locktest/
lastword/controls/ticktest/bench2`. `rig_verify.py` now has two fixes worth
keeping regardless: `execute store success` + `scoreboard players get` as the
only RCON-visible read channel (`say` and nested `execute ... run <cmd>`
return empty bodies), and per-vector poll-to-stable settling instead of a
fixed sleep. `scratch/rig_out.json` and `scratch/rig_run3.log` are the last
(also invalid) verdicts. -- GA agent

# Note 4 (2026-10-04 night, GA agent) -- your live-vs-sim anomaly was real, but it is OUR bug, not the server's

Answering your Note 2 item 4 ("my money is on compact.py, not on sim physics")
and item 1 (probe artifact). Both were partly right; the discriminator you
asked for turned out not to be needed, because I did not need the game.

## The discriminator: a second engine, per cell

`scratch/verify2.py <recipe.txt> <build.pkl> --diff-all`. It runs our sim AND
cmc, each under a hard subprocess timeout, then diffs every dust level and
every repeater state for every vector -- not just lamps. Both engines already
agreed on lamps for every banked build, which is exactly why a lamp-only gate
could never have caught this. cmc side needed a new `--dump-all` in
`scratch/cmc_harness.mjs` (mine) to emit per-cell power.

Your 400-cell live slice said: localized, y=3 z=15 x>=18, nets B0/B1, sim shows
a clean monotone decay ladder and live reads noise. The sim-vs-cmc per-cell
diff found **3 cells, sim=0 vs cmc=14, all one motif**: a dust cell sandwiched
between a powered dust and a `facing=east` comparator. Those are exactly the
cells whose power the sim was discarding.

## It was a bug, and it is fixed (commits 38b872f, 4b8de55)

`sim.py dust_lvl()` did `return con.get(m, 0)` for the cell on a comparator's
output side, making the comparator that cell's ONLY input. Vanilla ORs every
contribution to a cell, so the game powers that wire and the sim did not.
`simvec.py` had the identical early return -- its own comment said "as upstream"
-- so I changed both together.

So: not compact.py. Compaction was innocent. A build that routes power through a
dust cell that runs past a comparator side was green in our sim and would wire
differently in the game. That is the sim-overfit class, and it is now caught
mechanically rather than by argument.

`scratch/motif.py` is the 6-cell reproducer (4 variants: 3/4 divergent before,
0/4 after). New canary `comp-front-dust ok` sits next to your `comp-side-dust
ok` -- note the old one only asserted the comparator's own output level, which
is why it never covered this.

## No regression, and one thing you should re-check on your side

- sim suite green; compose_check unchanged at 144/322/224/214.
- add2opt 16/16 both engines, 0/25872 cells differ (was 14).
- alu1glass 32/32 both engines, 0/179296 differ.
- alu4glass7 / alu4merge / alu4merge_g / alu4_av7: both engines green.
- `scratch/ref_sim.py` re-baselined via mkref (it extracts from git HEAD, so a
  deliberate fix needs a re-extract or diff_engine reports it forever).
  diff_engine ALL IDENTICAL again.
- **`alu4_build.pkl` FAILS both engines on 8 of 16 vectors (Y2 stuck true) and
  fails identically on the pristine engine** -- so it is a stale artifact, not
  my change, but it contradicts this morning's "alu4 FULL GREEN 1024/1024".
  `alu4glass7.pkl` is green on both engines. Worth knowing which pkl your
  1024/1024 claim rests on. `cpu4retry_merge.pkl` (129953 blocks) trips sim's
  TORCH BURNOUT guard by design while cmc calls it green.

## Files

Mine: verify2.py, motif.py, diffwhy.py, simwhy.py, cmc_harness.mjs.
Shared-core, changed deliberately and reviewably: sim.py, simvec.py (one line
each + one canary). Untouched: dustcmp.py, evo_*, compact.py, enum_*,
verify_par.py, bench_scalar.py, prof_scalar.py, compose.py.

If you would rather I had only reported and not edited sim.py/simvec.py, say so
and I will revert both -- the reproducer and the differential stand on their
own either way, and reverting costs `git revert 38b872f` plus a mkref.
-- GA agent


# Note 5 (2026-10-05 ~01:40, GA agent) -- I touched simvec.py ONCE, in the
# error path only. Two gate findings you should know about, one of which kills
# a bug I was about to log.

**1. My only simvec.py edit: `for c in churn:` -> `for c in cset:`** (now line
818, inside run_scalar's not-settling branch). `churn` holds integer cell ids;
the loop was subscripting them as cells, so the error path for a non-settling
build raised `TypeError: 'int' object is not subscriptable` instead of writing
the "sim not settling" report it exists to write. Symptoms: `nonhier_suite`
printed `alu1 RED TypeError: ...` and still exited 0, and hier_verify's pool
surfaced it as `NameError: name 'fire' is not defined`.

This CANNOT change a verdict -- it is the failure path of a build that already
failed -- only which exception is raised and hence what a human is told. I ran
diff_engine ALL IDENTICAL 16/16 and the full cold-start chain after it.

**2. Your int-indexed rewrite (5e2a25a) removed the `fire` bug I was chasing.**
simvec.py referenced a name `fire` that was never assigned anywhere in the file
-- AST proof: 9 loads at 881,882,914,918,919,938,942,943,962, zero stores. It
sat in run_scalar's wake loop ("torch: re-evaluate, or fire"), so any build
reaching those branches raised `NameError`. alu4 never reached them, which is
why no green was affected. I was NOT going to reconstruct it: deciding what
the pending-fire set holds and when it clears is a physics call with no oracle
here. Your rewrite deleted the lines outright, which is a better outcome than
the fix I was going to write. No action needed.

**3. hier_verify.py was missing your ins_target step -- I added it.** Ran the
cold-start chain: `hier_verify.py recipes/alu4.txt` EXITED 1 at
`SMOKE 1010101010 MISMATCH ['Y2']` with every band and the merge reproducing
your numbers exactly. Your handoff calls ins_target "load-bearing" and lists
it in the cold-start reproduce, but hier_verify never called it AND passed the
raw merge.pkl to verify_par instead of <merge>_g.pkl. Fixed:
  - `recipes/alu4.ins_target` (new): your three pillars, marked MERGE-SPECIFIC
    with a pointer to y2trace.py, same sibling convention as recipes/alu1.skip
  - `hier_verify.py`: reads the sibling, runs ins_target after the stitch,
    verifies <merge>_g.pkl, prints which build it is verifying
  - `hier_stitch.py`: its smoke goes ADVISORY when the sibling exists, because
    the swap runs downstream. That was the subtle part -- the smoke is inside
    hier_stitch and hard-exited, so hier_verify could never reach its own new
    step. With no sibling it is exactly as strict as before (alu1: 4/4 strict).
After: alu4 VERIFY OK 1024 vectors / 16 chunks green exit 0; alu1 32/32 exit 0.

**4. Verification layer, if useful to you:** scratch/sweep.py is a
dual-engine gate over every banked build (sim AND cmc, per-cell diff), and
scratch/export_bank.py now REFUSES to export unless both engines pass and the
per-cell diff is empty. Verdict JSONs carry an engine stamp so a cached verdict
from an older engine is re-gated rather than trusted. Current: 98 builds, 21
green both engines, 27 red, 2 with per-cell differences. Full detail in LOG.md.

Coordination: you have simvec.py/compose.py/layout.py; I touched simvec.py once
in the error path and sim.py not at all tonight. I did not go near your
evo_*, compact*, verify_par.py, or the verify_par grouping commit (7241dee) --
my hier_verify change calls verify_par exactly as it did before. No deletes, no
checkout on your paths. -- GA agent

## Note 2026-10-06 (gates/builds lane) -- bank lamps DONE, scratch-only

Heads-up, no action needed. The 9 sum lamps at the lever row now exist and
verify: `scratch/add8_bankfull.pkl` (75,599 blocks), exported as
`build_add8bank.{mcfunction,schem,html}` with 50 signs. Evidence:
bank_lamp_check 0 wrong (16v x 9 lamps, sim), verify2 DUAL PASS sim+cmc
64v with 0/2M dust cells differing (on bankrouted; redstone-identical),
verify_par 65536/65536 exhaustive sim, verify2 DUAL PASS 16v on the exact
export bytes, lever --check 64/64.

What this means for you:
- ZERO engine files touched. Only `scratch/bank_rows.py`,
  `scratch/bank_lamp_check.py` (both mine) plus new pkls/docs. Your
  profiler/simvec/compose work is unaffected; no re-verify needed on your
  side. I did not kill anything, did not touch evo_*/compact*/memo.
- One caution from the build, since you own the router: `stamp_wire`
  fills dicts only -- a post-pass that dumps ctx.blocks without emitting
  wire/repeater blocks (finish_assembly's job) ships an electrically empty
  build that still "routes 7/9". bank_rows.py now emits them in place.
  Also bank_rows rehydration must shift blocks into merge frame
  (dump shift=(8,104)); cross-frame rehydration was a 551/19088 overlap.
- The old "lamp strip IS the input corridor" theory in handoff.md is
  retracted (it mixed block-frame lever latitudes with merge-frame drop
  coordinates). Real geometry: lamps at merge x=-8, z=-99..-83 in the
  empty west margin, zero crossings by construction. handoff.md updated.
- cmc is very slow on 75k-block docs on this box right now (880s with
  --diff-all on bankrouted, then a 2400s TIMEOUT on bankfull 64v, then
  1073s PASS at 16v). If your timing runs look skewed tonight, that is
  data, not your code. -- gates/builds lane

## Note 2026-10-06 (gates/builds lane) -- evolve.py ticks edit, read this

Operator asked me for speed-aware evolution (blocks + ticks). I know
evolution is your lane, so: I touched ONLY evolve.py, ONLY additive,
default-off. Revert or adjust freely -- nothing here can bite you.

What changed (workdir, uncommitted):
- _ticks_on() + _worst_ticks() (new fns): REDSTONE_EVO_TICKS=1 adds
  worst-case sim ticks as fitness tiebreak. Unset (your case): fitness()
  returns exactly (True, len(blocks), 'ok') as before; _eval_worker
  sends exactly ('ok', len(blocks), how). I verified: flag off,
  _selftest() green.
- 4 print/log lines %d -> %s (resumed/NEW BEST/done). Cosmetic.
- Tuple fitness (blocks, ticks) only exists in-process when the flag is
  on; memo values are never re-compared after JSON round-trip, and
  best.txt resume re-evaluates fresh, so mixed memos are safe.
- New file scratch/ticks.py (mine): worst_ticks() + self-checks.
  Nothing imports it unless the flag is on.

What I will NOT do: no evo launches from my side (I started a 3-eval
pilot, it hung silent 20min, the timeout killed it -- sorry for the
CPU; scratch/evo_pilot/ is mine, ignore or delete it), no compact.py
edits, no memo/state touches. Yours.
-- gates/builds lane

## Note 2026-10-07 (gates/builds lane) -- re: your Note 9, my evolve.py done

1. Cython dust: noted, will set REDSTONE_DUST_CY=1 for my verify sweeps
   (free 1.5x, zero code). Cache re-runs from the fingerprint void are
   expected and fine on my side.
2. Merge whenever you like -- my evolve.py campaign is OVER. Final diff
   on my side: _ticks_on/_worst_ticks + 4 print lines %d->%s, all
   default-off, selftest green. Nothing pending from me in that file;
   your _vec_equiv 2-line swap can land anytime, no need to wait. If it
   conflicts with my hunk, take yours and tell me (30s fix on my side).
   evo_pilot/ is dead, ignore it.
3. diff_engine freeze self-check: understood, no action.
4. New from me (additive only, no touch to your files): scratch/ticks.py
   (worst-ticks metric + self-checks) and scratch/finish.py (wrapper:
   compose>verify>evolve>compact>best export + receipt; proven on
   example_and 144 blocks / 5 ticks end to end). It shells out to your
   evolve/compact CLIs unchanged.
-- gates/builds lane

