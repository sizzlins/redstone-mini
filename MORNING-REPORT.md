# MORNING REPORT — alu1 GREEN (autonomous session 2026-10-04)

## DONE: alu1 verifies 32/32

**What now builds:** `recipes/alu1.txt` (2 bands, 22 gates) through the
standard hier gate — `hier_bands.py` (2 bands green) + `hier_stitch.py`
(MERGE + 4/4 smoke) + `verify_par.py` (**VERIFY OK: 32 vectors, 16 chunks
green**). Verified twice: BANK=1 default merge (15104 blocks) and BANK=0
merge (13996 blocks), both 32/32. `hier_verify.py recipes/alu1.txt`
exit 0 end-to-end, no env vars.

**Recipe promoted** (alu4 precedent): 27-gate 4-band original replaced by
22-gate 2-band restructured recipe, equiv-proven 32/32 vs original.
Original survives in git HEAD. BAND 0 = recompute slice + split NOTs +
mux (19 gates, 5 recipe inputs, 0 boundary); BAND 1 = OR chain (3 gates,
4 boundary).

## The three fixes (commit messages carry the full trail)

1. **Edge-levered inputs skip the lane march** (`2722ad1`, band 3 green).
2. **Bankdrop west-approach retry** (retry-only, zero green-geometry risk):
   bank drops that detour east past the stub short an existing booster
   (front-joins-back ring, measured twice at exactly +8 east of stub).
3. **Split-NOT qn1a/qn1b** (recipe): shared-inverter fanout built two
   adjacent lane rows; boosters beside same-net parallel dust latch ON via
   repeater side-lock (wiki, user-measured). One NOT per load = nets can't
   share a corridor (checkers enforce separation).

## Regression state

nonhier suite bit-identical: 144/322/224/214/2925/5499. `compose.py`
self-checks green. alu1 flat compose still RED by design (22 gates <
_TERR_MIN_GATES; lowering it would reroute 10 flat-green banded recipes --
rejected). alu4/cpu4 untouched: both fixes are retry-only / no-op paths
for green builds (edge nets absent; bank legs succeed first try).

## What still fails / needs hands

1. **LOG.md conflict -- needs your merge decision.** The GA agent's tooling
   rewrote LOG.md wholesale twice tonight (2202-line project history
   deleted in c788eb8; my entry wiped the same way). I recovered the full
   history to `notes/LOG-history-2026-10-04.md` (1874 lines) and put my
   trace in `notes/alu1-green-2026-10-04.md` + commit messages. I did not
   touch their squeeze notes. Recommend: keep both files, stop sharing one
   mutable log (or you merge by hand). The `write` tool overwrites -- both
   agents must append-only (`Add-Content`) on shared logs.
2. OP0 y=3 orphan dust (66 cells lit with OP0=0): seen during forensics,
   not implicated in any failure. TODO if it ever gates a vector.
3. `dense_status recipes/alu1.txt` still reports RED (flat+maze only).
   If you want one command for everything, hier_verify is it (it is for
   alu4/cpu4 too).

## GA agent status (observed, not touched)

Squeeze loop running (add2opt 4648 -> 4339 last banked). Their commits are
LOG.md-only; their code lives in gitignored scratch. My commits are
`compose.py` + `recipes/alu1.txt` + notes only -- no file overlap. They
noted my hier_stitch pid in their log; no kills exchanged. Coordination
worked; the only collision is LOG.md (above).
