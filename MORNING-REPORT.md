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

## What I changed (2 commits: 67044ba, a7dc462)

All in `compose.py` unless noted. Every change is gated: green open
corridors take the identical path, so small builds stay sim-green.

- `_walk` / `lwire`: ring-hop (span a reservation-only ring cell), ranked
  candidate fallback with per-candidate rollback, and `_astar_wrap` — the
  maze A* reused as a last candidate for negative lane coordinates.
- `_candidates`: 12 offset-trunk corridors.
- Halos: foreign *drivers* reserved, not just loads.
- `_expanded`: sibling streets widened (halo 2 -> 4).
- `_order` / `_blame` / `_displace`: most-bottlenecked-first ordering,
  blame-based order restarts (bounded 24), and single-victim displacement
  to break mutual seals that ordering cannot.
- `tiles.py`: latch repeater porch guard.
- `scratch/` probes: `dense_status`, `wallpanel`, `astarprobe`,
  `hopclause`, `netdump`, `rectdump`, `churnedge`, `plantlog`,
  `vecsweep`, `traceview` (gitignored, never merged).

Three experiments were measured and **reverted**, with the evidence kept
in-file as `ponytail:` notes: input trunk rows, lane offset 8/pitch 6, and
parity-staggered torch power-on in the sim.

## What I need from you

No credentials or payments. Three decisions:

1. **May the hop get a narrower shape?** A 3-cell hop (needs a support
   pillar) crosses a 2-wide canyon. This is the single change that
   unblocks alu1, and it is contained.
2. **Or authorise y>=2 overflight** for long input legs — 3D A* with
   support stamping. Bigger, but the maze backend already proves 3D
   routing works in this codebase.
3. **micro1: is a defined latch power-on acceptable** (drive R for a tick
   before the vector, i.e. reset-then-set), or must every build settle
   from a cold, unbiased start? The burnout is a power-on race, and this
   decision changes whether it is a bug or a spec question.

## Housekeeping

- Your PC restarted mid-run and separately ran out of RAM. Both were mine:
  a 10^6-wide A* window held ~100k heap entries. It is now bounded to
  manhattan+64. Diagnostic BFS is capped at 30k cells for the same reason.
- Branch `phase2-design`, HEAD `a7dc462`, working tree clean apart from
  the gitignored `scratch/` probes and `docs/plans/`.
