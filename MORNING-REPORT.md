# MORNING REPORT — redstone-mini dense builds (2026-09-30, session 3)

## Headline: NOT DONE. 1 of 5 dense builds verified. 0 new dense builds.

The bar was not met. 7 commits landed, each gated on the 4 small builds
staying sim-green (182/396/250/272). The stuck process you saw was the
final maze verify on alu4+cpu4 grinding for ~6h; I killed it — the numbers
it would have produced were already known.

## Verify commands

```powershell
cd D:\redstone-mini
python scratch/compose_check.py     # 4 small builds, sim-gated (fast)
python scratch/compose_status.py    # dense ladder, compose only (fast)
python scratch/dense_status.py      # dense ladder, compose->maze (SLOW)
```

## What now generates AND verifies

| recipe | status | evidence |
|---|---|---|
| `micro1.txt` | **OK, verified** | 2301 blocks, 6.7s, via the maze backend |
| `example_and.txt` | OK, verified | 182 blocks |
| `example_2gates.txt` | OK, verified | 396 blocks |
| `latch_sr.txt` | OK, verified | 250 blocks |
| `example_xor.txt` | OK, verified | 272 blocks (was 282; routes got shorter) |

## What changed (session 3, commits 34f2607 … 66cc52a)

All in `compose.py` / `tiles.py` unless noted. Small-build hashes confirm
nothing moved except where a shorter route now wins.

1. **Single-leg input routes.** The N-S lane + E-W approach pinned the turn
   cell, and a blocked ENDPOINT is unhoppable. Whole leg now routes as one
   lwire; offset-trunk candidates jog the turn. Cleared the walls both
   backends were dying on: alu1 `OP1 (-15,12)->(4,12)`, ctrl_decode
   `OP2 (-3,1)->(-3,12)`.
2. **Outputs never inlined.** `_strip_buffers` ate hand-written buffers that
   were recipe outputs (`ALU1 = OP1 AND OP1`), leaving a bare `KeyError`
   after routing had already succeeded. Cost: one AND tile.
3. **Lamp taps before routing.** The post-routing field has no clear lamp
   spot in a dense band (`lamp spot taken for Y`).
4. **Torch-adjacency seal** (`tiles.seal_tiles`). A run beside a foreign
   torch is driven by lever AND inverter = ring oscillator. Measured on a
   6-gate OR/AND chain: TORCH BURNOUT -> GREEN (1186 blocks).
5. **Self-lid counts tile-body cobble.** `_support` legitimately reuses tile
   bodies; the flight check didn't count them and rejected every descent
   past a tile. alu4's carry `C1 (107,41)->(195,55)` now routes.
6. **Load-held-by-foreign-net is loud.** This is the diagnostic, not a fix:
   a netspec load holding another net's dust/repeater is a hard error with
   the exact cell. It fires on 4 of 5 dense recipes — the mis-wiring is
   everywhere and used to surface as `SIM MISMATCH x9` with no cell named.

Reverted with evidence kept in-file: buried-wire guard (walled a valid
240-cell flat-astar path), cobble-side seal (walled every dense route),
two speculative orphan guards (never fired).

## What still fails (verbatim)

| recipe | wall | time |
|---|---|---|
| `micro1` (compose) | `load (34,15) of W holds D` | 0.2s |
| `alu1` (compose) | `load (82,29) of n1 holds B` | 3.9s |
| `ctrl_decode` (compose) | `load (94,12) of OP2 holds a` | 2.1s |
| `alu4` (compose) | `no ground for t33: (492,42) -> (446,154)` | 129s |
| `cpu4` (compose) | `no ground for AL_n1: (398,12) -> (744,118)` | 152s |
| `alu1` (maze) | `no route for B (34,398)->(28,399) (3D: self-lid)`, 30 unroutable | 798s |
| `ctrl_decode` (maze) | `no route for OP0 (344,76)->(484,12) (3D: self-lid)`, 15 unroutable | 409s |

New dense builds: 0. Authored 5 candidates (minterms/pairfuncs/muxlattice/
popcount/group4), all died on long input routes; files removed, nothing
committed. Sequential (counter/D-FF) shapes are not orderable by `_topo` —
a LATCH back-edge is a cycle — so new dense work must be combinational.

## The one thing the next session should do

**Fix why a netspec load cell ends up holding a foreign net** (or nothing at
all: OP0's five loads held OP1, n1, a lterm repeater, and two empty cells).
Routes exist for every one of those ports — the legs are in the path list —
but the final field disagrees. Prime suspects, in order:

1. `place_and` can relocate a tile to `(dv+3, dv[1])` but compose records
   the *requested* origin in `used_fp`/`placed` (`compose.py` ~line 590) —
   later placements and halos can be built on a lie. Check `recs` coords
   vs the stamped tile first.
2. A route of net X stamped onto a cell where a tile port of net Y was
   supposed to go — audit `stamp_wire`'s `setdefault` + `ends` interplay.
3. `_displace`/rollback asymmetry (one defensive commit landed; may not
   be the path taken).

Supporting evidence already in the repo: `scratch/repadj.py` (rules out
the booster pass: 0 repeaters beside foreign wire on all builds),
`scratch/gatewhy.py` (first-wrong-gate per vector),
`scratch/whopowers.py` + `scratch/q.py` (consistent-frame cell queries),
`scratch/shrink.py` (delta-debugs a failing recipe), `scratch/ortopo.py`
(small OR/AND/NOT topology ladder, all green except regw_shape).

## What I need from you

Nothing credential-related. One standing decision, answered or not — the
builds gate on your answer eventually: a 2-NOR SR latch with both inputs
low at power-on genuinely hunts (micro1's pair peaks at 10 OFF-transitions
in 30 ticks vs vanilla's 8; genuine rings peak at 15 *and* trip the
independent not-settling check at churn=210). Is a defined latch power-on
(reset-then-set) acceptable, or must every build settle from cold? Until
then the latch stays green-via-maze only.

## Housekeeping

- Killed PID 14948 (the ~6h `dense_status alu4 cpu4`); do not rerun the
  full maze ladder on alu4/cpu4 in one shot.
- Branch `phase2-design`. Working tree clean. Head is the LOG.md commit
  below this report.
- `scratch/` probes are gitignored by policy — never merge.
