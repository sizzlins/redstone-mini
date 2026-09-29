# MORNING REPORT — redstone-mini dense builds (2026-09-30)

## Headline: NOT DONE. 1 of 5 dense builds verified. 0 new dense builds.

I did not reach the bar. Here is the honest state, what works, what does
not, and the three decisions only you can make.

## Verify command

```powershell
cd D:\redstone-mini
python scratch/dense_status.py            # all 5 dense, exit 0 iff all green
python scratch/dense_status.py micro1.txt # just micro1
python scratch/compose_check.py           # 4 small builds, sim-gate each
```

## What now generates AND verifies

| recipe | status | evidence |
|---|---|---|
| `micro1.txt` | **OK, verified** | 2301 blocks, 6.8s, via the maze backend |
| `example_and.txt` | OK, verified | 182 blocks |
| `example_2gates.txt` | OK, verified | 396 blocks |
| `latch_sr.txt` | OK, verified | 250 blocks |
| `example_xor.txt` | OK, verified | 282 blocks |

`micro1` is a genuine improvement: it is in the dense family and it now
comes out of `layout_retry(verify=True)` sim-verified. It gets there
through the maze fallback, not the new compose backend.

## What still fails

| recipe | wall (verbatim) | time |
|---|---|---|
| `alu1.txt` | compose: `no ground for CIN: (-11,30) -> (142,30)`; maze: `no route for A: (31,393) -> (57,96) (3D: self-lid)`, 25 tasks unroutable | 408s |
| `ctrl_decode.txt` | maze: `no route for OP1: (391,83) -> (373,23) (3D: self-lid)`, 17 tasks unroutable | 811s |
| `alu4.txt` | not re-measured this session (known RED; too slow to re-run) | — |
| `cpu4.txt` | not re-measured this session (known RED; too slow to re-run) | — |

### The one wall that matters (alu1, `CIN`)

Reproduce: `python scratch/astarprobe.py alu1.txt CIN` and
`python scratch/hopclause.py alu1.txt CIN`.

The input's long east-west leg runs at the *load's* row, straight through
the tile field — a 153-cell ground march. It fails 38 hop attempts, and
**every refusal is `feet-wire`**: the hop's far foot (victim + 2 cells)
lands on the next column's dust. Two north-south columns sit 2 cells apart
(`B@x6`, `n1@x8`), and the proven 5-cell hop needs 2 clear cells on each
side, so a 2-wide canyon is geometrically unhoppable.

This is not a search-budget problem. `astar_wrap` also finds no flat path,
because A* cannot see hop-over crossings at all. More field, more seeds,
or more candidates cannot fix it — the hop shape is the limit.

For the record, these alu1 nets used to die and now route: `m0`, `m4`,
`O`, `AB`, `n0`, `n1`.

### micro1's remaining defect (compose path only)

compose builds micro1 (3367 blocks) but the sim reports TORCH BURNOUT on
the latch's cross-coupled pair. I traced it: the latch's S/R arrive
through long diode runs, so the fuse on one torch trips before the other
torch's S arrives to break the ring. A porch guard I added around the
latch's S-row repeater removed the previous 329-cell dust ring — the
failure mode changed, it did not disappear. The maze path avoids it.

## What changed (commits 67044ba, a7dc462, aa29f26, 96d8faf)

All in `compose.py` unless noted. Every change is gated: green open
corridors take the identical path, so small builds stay sim-green
(182/396/250/282).

- `_walk` / `lwire`: ring-hop (span a reservation-only ring cell), ranked
  candidate fallback with per-candidate rollback, `_astar_wrap` — the
  maze A* reused as a last candidate for negative lane coordinates, and
  a **3D overflight** fallback (astar's y>=2 search with
  `layout._support`-validated pillars). The overflight is a real
  capability: it is the only thing that crosses a long N-S column, and it
  made alu1's `CIN` route (that leg had no flat and no ground-hop path).
- `_candidates`: 12 offset-trunk corridors.
- Halos: foreign *drivers* reserved, not just loads.
- `_expanded`: sibling streets widened (halo 2 -> 4).
- `_order` / `_blame` / `_displace`: most-bottlenecked-first ordering,
  blame-based order restarts (bounded 24), and single-victim displacement
  to break mutual seals that ordering cannot.
- `tiles.py`: latch repeater porch guard.
- `scratch/` probes: `dense_status`, `compose_status`, `wallpanel`,
  `astarprobe`, `flywhy`, `hopclause`, `netdump`, `rectdump`,
  `churnedge`, `plantlog`, `vecsweep`, `traceview` (gitignored).

### Reverted, with the evidence kept in-file as `ponytail:` notes
- **Input trunk rows** — fixed alu1's B/CIN legs, but example_and went
  182 GREEN -> 314 SIM MISMATCH (trunk runs bleed 15->5 before the hop
  dust; the OR junction reads weak).
- **Lane offset 8 / pitch 6** — did not move the wall (the 2-wide canyon
  is a gate port, not the input lane) and cost small builds 30% more.
- **Parity-staggered torch power-on in the sim** — made micro1 worse
  (4 green vectors -> 0, all burnout).
- **Input port-approach opening, twice.** This is the important one and it
  is the next session's opening move. alu1's `OP1` leg
  `(-15,12) -> (4,12)` has **no flat and no 3D path** because a tile's
  own apron seals its west-edge port cell — the route must cross 4 cells
  of the NOT tile's reserved halo to reach it. Empty-ringing the port
  fixes reach and costs correctness instead: v1 (port + 4 neighbours,
  all nets) broke example_xor's input lane outright; v2 (input nets, 3
  cells west) made example_and SIM MISMATCH because the opened approach
  lengthens the run and it reaches the OR junction at **level 9 where a
  diode input needs a strong 15**. Opening a port buys reach with signal
  strength.

## TODO, in order (this is the concrete next session's plan)

1. **Guarantee a strong 15 at OR-diode rears in `_plant_repeaters`.**
   This is the blocker for everything above: a comparator side and an OR
   diode rear are the only places that need 15, and the current 8-cell
   spacing lets a long run arrive at 9. A per-net "last N cells before
   each OR load get boosted" rule is small and makes the port opening
   safe. Verify: 4 small builds stay green.
2. **Then re-open input port approaches** (v2 above). Expect alu1's `OP1`
   to route, which is the last compose wall measured on it.
3. **Then re-measure the dense family** with `scratch/compose_status.py`
   (fast, compose only) before spending minutes on the maze fallback.
4. **micro1's compose SIM failure** (TORCH BURNOUT on the latch pair) is
   independent of all the above: S/R arrive through long diode runs, so
   one fuse trips before the other's S breaks the ring. Needs a defined
   power-on (reset-then-set) or a shorter S/R approach.

## What I need from you

No credentials or payments. Two decisions:

1. **Is a defined latch power-on acceptable** (drive R for a tick before
   each vector, i.e. reset-then-set), or must every build settle from a
   cold, unbiased start? micro1's last compose defect is a power-on race
   and this decides whether it is a bug or a spec question.
2. **alu4 / cpu4 were not re-measured** this session (each is minutes per
   attempt; the machine also restarted once under memory pressure). If you
   want them measured, say whether to spend the wall-clock — otherwise I
   will treat the compose-only ladder as the gate and report maze timings
   only for a recipe that compose greens first.

## Housekeeping

- Your PC restarted mid-run and separately ran out of RAM. Both were mine:
  a 10^6-wide A* window held ~100k heap entries. It is now bounded to
  manhattan+64. Diagnostic BFS is capped at 30k cells for the same reason.
- Branch `phase2-design`, HEAD `a7dc462`, working tree clean apart from
  the gitignored `scratch/` probes and `docs/plans/`.
