# Staircase lanes for micro1 (2026-09-26)

Status: SUPERSEDED (2026-09-26, construction review): the lane→port leg
is unfillable flat for 2-load inputs (order-isomorphism argument — see
handoff). Kept as history, do not implement. Active attempt:
bridges-as-primary on micro1 (bounded: 3 reds or 600s silence → park).

## Problem

`micro1` (10 gates, inputs `D,W,B,OP` × 2 loads) is red with the panel:
full-retry ends `no route for Q: (73,14)->(124,12)`; single-shot variants
die on `T1` marathons. Task-1 bus lanes (`z=(D-4)-idx*2`, full-width
`x=1..W-1`, tiles dodge) stand and keep the suite green, but connecting
the south bank to full-width lanes is unroutable flat: bank→lane jogs
bridge sibling lanes (`W bridges D at (55,1,34)`, SHORT-proven), and
full-width trunk wire itself walls N-S routes (`sim.py`: `S/a` no-route).
Relay buffers measured worse (>600s silent, 10→18 gates). All reverted
except Task 1.

## Decisions

- `layout.py` placement only. Router, `sim.py`, `recipe.py`, export/serve
  untouched (sim stays selector).
- Panel stays: one south-bank lever per used input, median-parked x.
- Loud fail stays; keep-or-revert per task; micro1 iterates
  foreground-fast on single-shot (`layout(r, seed=None, grow=0)`).

## Design

1. **Staircase lane starts.** Lane `i` (input order `idx`) claims E-W cells
   only from its own start eastward: `{(x, lz_i) for x in range(X_i, W-1)}`
   with `lz_i = (D-4) - idx*2` and nested starts `X_0 > X_1 > X_2 > X_3`
   (southmost lane starts farthest east). Starts need only W bounds and
   2+ spacing (tiles dodge all claimed cells); e.g. `{7,5,3,1}` for four
   inputs. The pre-claim covers lane cells PLUS each jog column
   (`{(X_i-1, z) for z in lz_i..bz}`), so tiles dodge jogs too and the
   later wire stamp cannot hit tile solid.
2. **Crossing-free jogs.** Input `i`'s bank feed jogs north at `x = X_i - 1`
   from `bz` to `lz_i`, then one step east onto its lane. It passes west
   of every lane it would otherwise cross: lanes south of the target
   (`j < i`) all start east of the jog (`X_j > X_i`), lanes north of the
   target are never reached. Crossing set empty by construction.
3. **Unchanged remainder.** Task-1 `spot_free` dodge covers staircase cells
   with zero code change (same `lanes{}` shape). Star tasks, spine-first
   order, rip-up, bridges, boosters, checkers all untouched — the attempt
   wins purely by giving each marathon an uncrossed corridor.

## Budget

~20 lines in `layout.py` (lane-start computation + jog stamp). No new
files (probes in gitignored `scratch/`), no new deps, one `__main__`
addition only if green (micro1 one-lever check).

## Alternatives cut

- Full-width lanes + trunks: measured wall, cut (dodge claim stays).
- Input relay: measured thrash, cut.
- 3D crossings / routine bridges / SA placement: real cost, parked until
  a consumer past micro1 exists.

## Verification gate

- `python scratch/probe_dense.py micro1` → `micro1 OK ... one-lever`
  (`layout_retry(verify=True)`).
- Suite green: `recipe.py`, `sim.py`, `serve.py --check`, `layout.py`.
- Red means: dump (`REDSTONE_DEBUG` + neighbour query) names the sealer,
  revert to `e5afcb5`, back to design. No stacking.
