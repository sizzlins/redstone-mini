# handoff — GA/squeeze agent, 2026-10-05 overnight session (supersedes the 10/4 file)

Repo `D:\redstone-mini`, branch `phase2-design` (shared with the optimisation
agent — we interleave commits; coordination in `notes/to-opt-agent.md` Note 5
and `notes/to-ga-agent.md` Note 5).

**Read in this order:** this file → repo-root `MORNING-REPORT.md` (operator
summary, current) → repo-root `LOG.md` last ~400 lines (tonight's trace) →
`notes/to-opt-agent.md` (my Note 5 to them) → `notes/handoff-opt2 agent.md`
(their current state). Do NOT trust `notes/MORNING-REPORT.md` (dated 10/1) or
`notes/LOG.md` (stray copy).

## Goal

Standing goal unchanged: every recipe generates, verifies and exports, with
evidence that survives an independent implementation. Tonight's goal was the
verification layer itself, because four gates were quietly wrong on arrival —
each passing unnoticed because the *other* gates were green.

## My commits tonight (in order; theirs interleave — `1aad3ec 7241dee 5e2a25a
d2af128 3c2748a a3c042c cd528c3 2a6a53b 397deda d74fd3d 3625461 39b7bc0 e3733e1
0a29b89 3d03ca5 05520c1 a5b4876 999efcf 3008c1c b01464c` are NOT mine)

| commit | what |
|---|---|
| `fa58552` | mkref.py was LOSSY not stale (cp1252 decode); freeze now byte-faithful + refdrift/refcheck/refbytes gates |
| `f81977c` | sweep.json flushed per row; cached rows rehydrate; `--cached-only` |
| `6f1030b` | verdicts carry engine stamp; stale-engine cache auto-re-gates; full sweep 98 builds |
| `8b5f54c` | FINDING: sim cannot power a non-pin lever (blast radius 1 build) |
| `7861ff7` | export_bank.py gated: no export without both engines + per-cell diff |
| `093c503` | cmc structural REFUSAL distinguished from physics disagreement |
| `c022703` | simvec "sim not settling" diagnostic crashed; one-word fix |
| `4d98d4c` | hier_verify was missing load-bearing ins_target; alu4 gate now passes |
| `9927475` | MORNING-REPORT rewritten (supersedes stale 10/4 file) |
| `c52ab72` | coldstart.py: one command, 8 gates, 4.6 min |
| `ef4709f` | compdiff: alu4bank_ins is 633 scattered fragments, not one root cause |
| `cfbe5bb` | notmin.py failing seam + coverage.py (48/48 builds gate) |
| `9085eda` | wireconn.py refutes params-vs-geometry |
| `d35079a` | CORRECTION: alu4 "0 diff" was 4-of-1024 sampling; coverage fields on rows |
| `083a50f` | 49k diff localized to vertical staircases, both directions |
| `5a7c872` / `89c7e79` | stair.py rise + stairdown.py fall agree (not the split) |
| `98460e1` / `4037040` | coldstart locks in wireconn/stair_fall/lid; --probes for known diverges |
| `453e7f9` | stackfail recipe + verify2 handles 3D io keys (**claim corrected below**) |
| `0bb0b1b` | containment: gate names levers sim cannot power (doubt-cycle driven) |
| `e84afd9` / `90d3598` | stairglass 0-vs-13 on glass; staircase has cobble lid over joint |
| `260be61` / others | lid agrees; stair lamp was keying error; export --force; doc cache keys |

## Current state (all verified tonight; `coldstart.py` reproduces in ~5 min)

| what | state |
|---|---|
| `coldstart.py` (12 gates + refdrift_after_mkref) | **13/13 green, exit 0** |
| alu4 hier | **VERIFY OK 1024 vectors, 16 chunks, exit 0** |
| alu1 hier | VERIFY OK 32/32, exit 0 |
| diff_engine | ALL IDENTICAL 16/16 (ref == live == table engine) |
| sweep (98 builds) | 21 green both engines, 28 red (all 28 characterized), 2 per-cell DIFFs |
| bank path | gated; refuses red, exports green, --force marks UNGATED |

## The verification layer (the actual capability — these files ARE the handoff)

```
scratch/verify2.py   dual-engine gate: sim AND cmc per vector + per-cell diff.
                     Usage: verify2.py <recipe> <build.pkl> --diff-all [--max-vectors N]
                     Verdict JSON carries engine stamp, n_vectors, cmc stage,
                     unrepresentable_levers. Refuses on wrong recipe (exit 2).
scratch/sweep.py     gate sweep over every banked pkl, recipe auto-match by pin
                     names. Rows carry sim/cmc/diff/n_vectors/sampled/engine/
                     stage. --cached-only rebuilds from cache; flushes per row.
scratch/coldstart.py ONE command, every gate: 12/12 green ~5 min. --quick skips
                     hier_alu4; --probes reports known divergences; --only a,b.
scratch/export_bank.py refuses export unless both engines pass + diff empty.
                     --force writes .UNGATED.txt marker.
scratch/refdrift.py  freeze health: 0 changed lines + equal AST = healthy.
scratch/diffclass.py classify a per-cell diff (direction matters more than count).
scratch/compdiff.py  connected components + comparator outputs for a diff.
scratch/coverage.py  what the sweep does/does not cover (48/48 real builds).
scratch/notmin.py    FAILING seam for Finding 3 (exit 1, correct signature).
scratch/wireconn.py / stair.py / stairdown.py / stairglass.py / lid.py
                     2-second rule probes (see matrix below).
```

Probe matrix (each a 2s run, each committed):
| probe | verdict | meaning |
|---|---|---|
| wireconn | AGREE 15/14 | params do not overrule geometry |
| stair rise | AGREE 15/14/13 + lamp | rise fine (3D io key required above y=1) |
| stair fall (cobble) | AGREE 14/13 + lamp | fall fine on opaque support |
| lid (straight) | AGREE 15/14/13 | horizontal flow under lid fine |
| stairglass (fall on glass) | **DIVERGE 0 vs 13** | sim refuses down-flow onto glass; cmc powers |
| notmin (non-pin lever) | **DIVERGE 0 vs 15** | sim blind (Finding 3) |

## Findings (each proved by a run, each with a retraction where I was wrong)

**F1. mkref.py corrupted the freeze on every run** (`text=True` → cp1252 decode
of UTF-8). HEAD clean (`0x2014`) vs freeze mojibake (`0xe2 0x20ac 0x201d`).
All 30 lines comments/log-strings → no physics differed; earlier ALL IDENTICAL
claims stand. Fixed with `encoding="utf-8"` + `newline=""` (now idempotent).
I first claimed the baseline was wrong on a hash compare — retracted; the
header + autocrlf made hashing meaningless. Gates: refdrift/refcheck/refbytes.

**F2. sim cannot power a non-pin lever; cmc and vanilla can.** `sim.py:542`
does `vec.get(lever[rear], False)`; a non-pin lever's key is its floor
coordinate, never in the vector. Proved on not_full.pkl (sim Y=false, cmc
Y=true on a correct subtract inverter). Blast radius: exactly 1 build.
NOT fixed in physics (shared hot loop, no oracle, other agent mid-flight);
contained instead — the gate now warns loudly. Failing seam: notmin.py.

**F3. alu4merge_g 49k-cell diff is vertical staircases, both directions.**
Reproduced to the digit (49814/1957248, sim=True cmc=True). Vector-dependent
(vec 0-3 zero — what the first sweep sampled; others to 2260). 633 scattered
dust-only fragments; 14/18 comparators agree; 318/329 repeater splits are
downstream of dust. Eliminated: sources, locks, decay, params, settling (2x
ticks: 21619→21563), simple rise, simple fall, glass support generally. Open:
staircase+lid joint (cobble lid found over one) and glass down-flow (stairglass
proves the material rule differs).

**Corrections I owe:** (a) alu4 "0 diff" was 4-of-1024 sampling — corrected
with coverage fields; (b) stackfail "green" was sim-green/cmc-red (cmc
miscomputes its AND) — upgraded to a surfaced divergence, not a closed hole;
(c) "49 junk files" are 235 MB of legitimate band caches; (d) my "propagation"
read of alu4bank_ins was over-read from one probe.

## Open items (exact next steps, narrowest first)

1. **Staircase+lid joint.** Build the combined probe (staircase with opaque lid
   over the joint, wireconn.py pattern). Decides the 49k diff's last mile.
2. **Glass down-flow.** stairglass.py proves sim=0 vs cmc=13 onto glass. Needs
   wiki/game to adjudicate; the fix is relaxing sim.py:405 `in cob` toward
   `sup3`, mirrored in simvec, then full re-verify. NOT done unilaterally.
3. **Non-pin lever physics.** notmin.py stands ready. Needs the single-cell
   directional source category in both engines + banked re-run.
4. **11 independent repeaters.** Need a one-repeater facing-convention test
   before citing (sim/cmc read facing oppositely on paper yet agree on 4000+).
5. **cpu4.** Untouched, red by inheritance. Not this lane.

## Traps that cost time (so you don't re-pay)

- Printed output is not evidence; decoded bytes/codepoints are. (Three agents
  asserted things about freeze bytes without decoding one.)
- `ast.parse` passing proves nothing; only execution does. (Caught my own
  NameError and IndentationError that way.)
- sim io pins exist ONLY at y=1 for 2-tuple keys (`_y` maps to `(x,1,z)`); use
  3-tuple keys above y=1. (Four probe bugs from this.)
- Sparse vs dense power maps: absent in sim = 0; compare accordingly. (Third
  time this project has been bitten.)
- `git status` is not evidence a file is yours; never `checkout --` another
  agent's path; never delete (only dirty: their deleted `notes/handoff.md`
  is now restored, plus two untouchable `.bak` files).
- A sampled green is not an exhaustive green. Rows carry coverage now.
- A gate only ever seen passing is untested. Test both directions.

## Files

Mine (scratch/, force-added): verify2.py sweep.py coldstart.py export_bank.py
refdrift.py refcheck.py refbytes.py diffclass.py compdiff.py coverage.py
notmin.py wireconn.py stair.py stairdown.py stairglass.py lid.py ref_sim.py
mkref.py hier_verify.py hier_stitch.py. Recipes: alu4.ins_target,
stackfail.txt. Docs: LOG.md (append-only), MORNING-REPORT.md, this file,
notes/to-opt-agent.md Note 5.
Shared-core touched deliberately: simvec.py once (error path, `for c in
cset:` — cannot change any verdict); sim.py NEVER.
NOT touched: evo_*, compact.py, enum_*, verify_par.py, compose.py, layout.py,
memo.json, rig_verify.py, rcon.py, dustcmp.py, cmc/, reference repos (read-only).

## Addendum 2026-10-05 (GA night loop, same session continues)

F3 RETRACTED AND CLOSED: the 49k diff is cmc settle ticks, not staircases.
vec47 single-vector ladder: 2260 cells @400 ticks -> 146 @600 -> 0 @800 ->
0 @1200/@1600 (vec62/vec29 0 @1600). Full 64-vector re-gate at 1200 ticks:
SIM ok n=64 13s, CMC ok n=64 865s, dust 0/1957248, repeaters 0/279552,
DUAL-ENGINE PASS (receipt: scratch/alu4merge_g.v2doc.json.verdict.json).
Durable fix: verify2.py default --ticks 400->1200 (one line in the shared
gate; tiny probes cost the same seconds). My "2x ticks: 21619->21563"
elimination above tested the wrong build scale (alu4bank_ins, both-red);
on the lamp-green alu4merge_g the discriminator answers the other way.

Open items update: #1 CLOSED (stairlid.py: dust-cobble-dust joint from
1097,1-3,182 agrees -- direct stacks never link, upper stays 0/0 both
engines). #4 CLOSED (repface.py: all 4 facings agree, dust 15/15, rep 1/1
-- facing convention exonerated, no engine change). #2 UNCHANGED
(stairglass 0v13 re-confirmed, tiny build -- rule gap, still needs
wiki/game). #3 UNCHANGED (notmin signature re-confirmed, containment
holds). #5 UNCHANGED (cpu4 other lane). NEW: slab support is a cmc
structural boundary (slabfall.py: cmc pops dust-on-slab; 0 slabs in
2,522,792 banked blocks -- provably out of scope). NEW: carry-OR blind
spot in hier stitch (add8/add4 C2+ dead while C1 lives; OR-less carry
greens -- full note in LOG.md, engine owner's lane, not fixed here).

Commits since (mine): d6b74e7 (ticks + stairlid/repchain, coldstart 14/14),
4ba4214 (repface x4), a72e5d5 (64-vector proof + report), dc399cd
(slabfall), 01ea4db (sweep refreshed at 1200: 21 green / 28 red all
characterized / 2 DIFFs), d714dbe (full coldstart 15/15 incl hier_alu4
1024/1024 in 207s + slab census + report). Co-tenant live (82fa638 numba,
verify_par.py + simvec_numba.py uncommitted -- untouched).

Current state: coldstart.py 15/15 green (was 13/13: +stairlid, +repchain).
sweep 99 builds at 1200 ticks: 21 green both, 28 red (same 28), DIFFs only
alu4bank_ins (both-red opposite-sign) and not_full (Finding 3). New probes:
stairlid.py repface.py repchain.py (gates, green) slabfall.py (refusal
probe, exit 2, not a gate). Recipes: add8.txt (OR-less ripple-carry, 8
bands). Kill the stale claims above on next rewrite: F3, open #1, open #4,
"12 gates" counts, and the settling elimination line.
