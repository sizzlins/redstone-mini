# MORNING REPORT — 2026-10-04 (alu4 FULL GREEN)

## DONE: full 4-bit ALU verifies 1024/1024 in sim

- **6/6 bands green** under engine `f462f6f` (`hier_bands.py recipes/alu4.txt`):
  b0 13304 (Y0 — was RED for the whole campaign) via `3,inputs_first,short`
  (+long, same blocks); b1 7518; b2 6957; b3 571; b4 2414; b5 4878.
- **MERGE 71560 blocks** (2198×353), 10 levers, smoke 3/4 → Y2 pillar
  re-derivation (`y2trace` → 3 glass swaps at 868,2,221 + 868,2,224 +
  1170,2,218, same fault family as the old 5-pillar fix, new coords) →
  smoke 4/4 → **`verify_par` VERIFY OK: 1024 vectors, 16 chunks green**.
- **Paste-ready:** `build_alu4full.schem` (hash-verified copy already in
  `.../worldedit/schematics/`), + `.mcfunction` (4.7 MB) + `.html` (7.9 MB)
  in repo root (gitignored by design).
- Engine gates all hold: `compose_check` bit-identical 144/322/224/214,
  nonhier suite 6/6 identical (2925/5499; alu1-flat RED by design since
  124d179), `hier_verify alu1` VERIFY OK 32/32.
- Commits: `ee61873` (corridor blame + pull-early), `f462f6f` (hop-cond2 +
  diode-drop). Probes in `scratch/` (`reachmap`, `corridor_map`,
  `shortdiag`, `stampwho`, `loopdiag`) — gitignored, kept for forensics.

## What changed in the engine (all green-neutral by construction + gated)

1. `lwire` tags `first_err` with cands[0] corridor; `_blame` counts foreign
   wires within 2 of it — a fence (≥10, beats pocket) outranks endpoint blame.
2. `_order` pulls gates-that-precede-inputs before lanes (stable partition)
   and drops auto-satisfied input preds (inputs_first).
3. `_hop_free` cond2 counts committed `sup`/`ctx.sup` (was own-supports only).
4. Compose tail: on `repeater loop`, bisect router diodes via `_loop_rep`
   mirror, drop the single closer (cap 9); sim judges decay.
5. Stall guard: duplicate blame pair fails fast (was 24-restart grind).
6. Tried and REMOVED: flight veto, span-refusal, lower-role lids, lever-at-load
   (unfired / orphaned hop-chains / wrong layer — see LOG).

## Still red / known limits (no action unless you say so)

- `gates_first` rungs on band 0 die input-phase repeater loops theDrop can't
  always clear (multi-diode/tile) — inputs_first covers, no campaign need.
- One `4,inputs_first,long` attempt: loop dropped, then SIM MISMATCH x1
  (decay from the drop — sim gate correctly rejected; other rungs green).
- Old `build_alu4.*` / `build_alu4bank.*` are STALE (pre-b0, unverified) —
  paste `build_alu4full.schem`, not those.
- GA agent's files untouched: `scratch/evo_blocks.py`, `scratch/rig_verify.py`
  (their commits `c439751` etc.), `build.*.bak`. `scratch/` stays gitignored.

## Needs you (human)

1. **Game paste test** of `build_alu4full.schem` (in your schematics folder).
2. Nothing else. No passwords, no payments, no secrets blocked anything.
