# MORNING REPORT -- 2026-10-05 (new GA/squeeze session)

Supersedes the 10/4 file, which was written before the comparator fix and before
the dual-engine gate existed. Repo `D:\redstone-mini`, branch `phase2-design`.
My commits: `fa58552` `f81977c` `6f1030b` `8b5f54c` `7861ff7` `093c503`
`c022703` `4d98d4c`. The optimisation agent was working in the same tree
concurrently (`1aad3ec` `7241dee` `5e2a25a` `d2af128`) -- see COORDINATION.

## The one-line summary

The verification layer was lying in four different ways at once. All four are
fixed, and **the project's headline claim (alu4 1024/1024) is reproduced from
cold tonight** -- but only after fixing a gate that was missing a load-bearing
step and therefore could never pass.

## What builds and is proven now

| build | sim | cmc | per-cell diff |
|---|---|---|---|
| **alu4** (71560 blk, 2198x353, 10 levers) | 1024/1024 | - | **VERIFY OK: 1024 vectors, 16 chunks green, exit 0** |
| **alu1 hier** (15104 blk merge) | 32/32 | - | VERIFY OK 32 vectors, 16 chunks, exit 0 |
| alu1/alu4 flat green set | green | green | 0 cells (12 alu4 builds, e.g. alu4ab2) |
| add2opt `compact_add2/best.pkl` | 16/16 | 16/16 | 0/25872 dust, 0/3584 repeaters |
| examples / micro1 / ctrl_decode | green | - | 144 / 322 / 224 / 214 / 2925 / 5499 |

Cold-start chain, all run tonight, all green:
`refdrift` FREEZE SEMANTICALLY IDENTICAL TO HEAD · `diff_engine` ALL IDENTICAL
16/16 exit 0 · `compose.py` self-test ok · `compose_check` 144/322/224/214 ·
`nonhier_suite` 6/6 (alu1 flat RED by design, now with a real message) ·
`hier_verify alu1` 32/32 exit 0 · `hier_verify alu4` 1024/1024 exit 0.

## What was broken, and is now fixed

**1. The frozen engine baseline was LOSSY, not stale.** `mkref.py` used
`subprocess(text=True)`, which decodes with the Windows locale (cp1252), so
every re-freeze mangled the em-dashes and `+/-` in sim.py and re-encoded the
mojibake as UTF-8. Codepoints: HEAD `0x2014`, freeze `0xe2 0x20ac 0x201d`. All
30 damaged lines were comments or one log-message string, so **no redstone
behaviour differed and every earlier ALL IDENTICAL claim stands** -- but the
artifact could never be diffed again, and the trap re-armed on each re-freeze.
Two decoys had to be eliminated first: `mkref` prepends a docstring header
(hash-equality impossible by construction) and `core.autocrlf=true` (worktree
bytes never equal blob bytes). New gates `refdrift.py` (the regression test),
`refcheck.py`, `refbytes.py` (the diagnostic that ended it).
**I retracted a claim here**: I first told you the baseline was wrong on the
strength of a hash comparison. It was not.

**2. `sweep.json` could not exist, and a resumed sweep reported no
differences.** The summary was written only after the loop, so the 10/4 sweep
being killed by a tool timeout lost it entirely while the per-build verdicts sat
cached and unreadable. Worse, a resumed run wrote `{'status': 'cached'}` with
no sim/cmc/diff fields, producing a summary that looked complete and reported
**zero differences for every build because it carried no numbers at all** --
the worst failure a gate can have. Now flushed after every row, cached rows
rehydrate from the cached verdict, plus `--cached-only`.

**3. A verdict recorded no engine identity.** Same class as the stale freeze: a
verdict from an older `sim.py` was indistinguishable in the cache from a current
one, which is why nobody could tell which of the 50 cached verdicts predated the
comparator fix. Verdicts now carry a sha256 stamp over `sim.py`, `simvec.py`,
`cmc_harness.mjs`; a mismatched stamp is re-gated loudly. Deliberately does NOT
hash HEAD -- my first attempt did, which would have made every commit a
two-hour re-run.

**4. The authoritative gate was missing a load-bearing step.**
`python scratch/hier_verify.py recipes/alu4.txt` **exited 1**, at
`SMOKE 1010101010 MISMATCH ['Y2']`, with every band and the merge reproducing
the recorded numbers exactly. The handoff calls `ins_target` "load-bearing" and
lists it in the cold-start reproduce -- but `hier_verify` never called it, *and*
passed the raw `merge.pkl` to `verify_par` instead of `<merge>_g.pkl`. Fixed via
a `recipes/alu4.ins_target` sibling (the existing `<recipe>.skip` convention);
`hier_stitch`'s smoke becomes advisory only when that sibling exists.
**After: VERIFY OK 1024/1024, exit 0.**

**5. A diagnostic crashed instead of reporting.** `simvec.run_scalar`'s
not-settling branch iterated `churn` (integer ids) and subscripted them as
cells, so a non-settling build raised `TypeError` instead of the "sim not
settling" report it exists to write -- and `nonhier_suite` still exited 0.
One word (`for c in cset:`); cannot change any verdict.

**6. The bank path was ungated.** `export_bank.py` now runs the dual-engine
gate first and refuses to export unless both engines pass every vector and the
per-cell diff is empty. `--force` exists but writes a `.UNGATED.txt` marker.

## Open, unresolved, needs judgement

**A. `sim` cannot power a lever that is not a declared input pin.** cmc and
vanilla can; sim cannot, so it reads `Y=false` on a working circuit. Found via
`not_full.pkl`, a 146-block comparator-subtract **inverter** (9/20 cells differ,
`sim=False cmc=True`). Root cause proved by reading `_parse_build`: `lever` maps
a lever cell to its io pin key, and for a non-pin lever that key is its own floor
**coordinate**, while the vector is keyed by pin *name* -- so
`vec.get((1,0,2), False)` is False forever (sim.py:542). Blast radius measured
across 104 pkls: **exactly one build**, `not_full.pkl`; every banked build's
levers are declared pins. **This matters because the NOT/full-adder search is
open and `not_full` is a NOT candidate** -- candidates may have been rejected
for a construct sim cannot represent. NOT FIXED: cmc (`engine.js:132-136`) is a
*directional single-cell* source and vanilla agrees, so the fix is a new source
category in two engines, not the `rblk` shortcut (which would over-power
neighbours). No oracle here to adjudicate.

**B. `alu4bank_ins.pkl`: 21619/103260 cells and 3017/14764 repeaters disagree.**
Reproduced fresh, so it is not a stale cache. Classified: 87.7% of cells agree;
3069 are `sim=0/cmc=powered` with a clean cmc decay ladder; only 45 are
both-powered-at-different-levels. So it is a propagation/structure
disagreement, not a decay or lock rule gap. Open.

**C. Our sim has no support stage.** cmc refuses builds structurally (its
`support` stage popped 24 wire-on-wire blocks in `alu4mergeNEW` and never
simulated). That is why those two read `sim=True cmc=False` -- **not** a
sim-overfit class, contrary to the handoff's open item, which is now closed.
`verify2` now distinguishes the two verdicts.

## Answers to things the handoff called open

- *"diff=0 on every single build that ran"* -- **false**. Two builds disagree:
  `alu4bank_ins` (huge) and `not_full` (9/20).
- *Which pkl does alu4 1024/1024 rest on?* -- the **71560-block** builds:
  `alu4ab` `alu4ab2` `alu4merge` `alu4merge_g`, all green in **both** engines at
  0/122328 cells. The red `alu4_build`/`alu4bank` family is a different, smaller
  artifact. **Both agents were describing different files; nobody was wrong.**
- *Is `alu4mergeNEW` the interesting sim-overfit class?* -- no, closed above (C).
- Full sweep for the first time: **98 builds, 21 green both engines, 27 red,
  2 with per-cell differences, 50 unmatchable by recipe** (21+27 = 48 = every
  pkl whose io pins match a recipe, so nothing gateable was left ungated).

## Needs you (human)

1. **Paste test.** Still the only thing that can settle vanilla-vs-sim. The live
   RCON rig is a documented dead end (`setblock` does not propagate power on
   vanilla 26.3 or 1.21.11 -- see LOG); a real client paste of
   `build_alu4full.schem` is the only path. Everything else tonight is two
   engines agreeing, which is stronger than one but is not the game.
2. **Open A needs a decision**, ideally with the wiki to hand: a powered non-pin
   lever is unambiguously a source in vanilla, and cmc already models it
   correctly and directionally. I did not change shared core on one engine's
   authority.
3. **Stale artifacts, still not deleted** (no-delete rule stands):
   `build_alu4.*`, `build_alu4bank.*`, `build.*.bak`, and the red
   `alu4_build`/`alu4bank`/`alu4ctrl*`/`alu4fresh` family (15 builds, red in both
   engines). Worth marking rather than removing.
4. `notes/handoff.md` is still deleted-in-worktree from the opt agent; I left it
   alone. This file replaces it.

## COORDINATION (please read)

The optimisation agent worked in this same tree **concurrently** and I did not
know until `git log` showed commits that were not mine. Its `5e2a25a` rewrote
`simvec.py` (int-indexed tables) after my `c022703`. Consequences, all checked:
my churn fix survived; the latent `fire` NameError I was about to log was
**deleted outright** by that rewrite; and I re-ran `diff_engine` afterwards --
**ALL IDENTICAL 16/16, exit 0** against the current engine. Its `7241dee`
(verify_par worker grouping) was not touched by my `hier_verify` change, which
calls `verify_par` exactly as before. Full note in `notes/to-opt-agent.md`
(Note 5). I touched `sim.py` not at all, `simvec.py` once in the error path,
and no `evo_*`, `compact*`, or `verify_par.py`.

## For the next agent, in order

1. `python scratch/mkref.py` then `python scratch/refdrift.py` -- **always**,
   after any `sim.py`/`simvec.py` commit. `mkref` alone cannot report its own
   failure.
2. Cold-start chain (all seven commands, all green tonight, listed above).
3. `python scratch/sweep.py --diff` for the dual-engine picture; read
   `scratch/sweep.json`. Investigate any `DIFF` row first.
4. Pick up **A** (non-pin lever) or **B** (`alu4bank_ins` propagation gap).
   `scratch/diffclass.py` classifies a per-cell diff in one pass and is the
   fastest way to tell a rule difference from one stuck region.
5. Nightly proof: 21 green builds, 0 unexplained diffs, all seven cold-start
   gates green.

**Do not trust any gate that has not been run this session.** Four of them were
quietly wrong on arrival.
