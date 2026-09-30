# MORNING REPORT — redstone-mini dense builds (2026-09-30, final)

## Headline: PARTIAL. 2 of 5 original dense verified. 3 of 3 new builds verified.

DONE item 2 is COMPLETE. DONE item 1 is 2/5. Everything below is measured,
committed on branch `phase2-design`, working tree clean.

## Verify commands

```powershell
cd D:\redstone-mini
python scratch/compose_check.py     # 4 small builds, sim-gated (fast)
python scratch/compose_status.py    # compose-only ladder (fast)
python scratch/dense_status.py      # compose->maze, verified (authoritative)
python compose.py recipe.py sim.py  # module gates
```

## What generates AND verifies (authoritative `dense_status`, verify=True)

| recipe | status | evidence |
|---|---|---|
| `micro1.txt` | **OK** | 2925 blocks, 0.7s, compose (latch race GONE) |
| `ctrl_decode.txt` | **OK** | 6111 blocks, 3.3s, compose |
| `decode3.txt` (NEW) | **OK** | 9799 blocks, 31.7s, compose |
| `add2.txt` (NEW) | **OK** | 8083 blocks, 1.2s, compose |
| `chainmix.txt` (NEW) | **OK** | 11497 blocks, 1.9s, compose |
| `example_and/2gates/latch_sr/xor` | OK | 144/322/224/214 blocks |

New builds stop at 3 per instructions. All three never built before; all
three generate without error and sim-verify. `add2` is a CORRECT 2-bit
adder (verified on all 16 input pairs against integer addition).

## What still fails

| recipe | wall (verbatim, latest) |
|---|---|
| `alu1` (21 gates) | `wire OP1 touches OP0 beside (-7, 3, 13)` — two y=3 input overflights collide; also CIN 700-cell lane and a 2-cell CIN orphan at other spreads |
| `alu4` (72 gates) | `no ground for t33: (492,42) -> (446,154)` (129s) |
| `cpu4` (126 gates) | `no ground for AL_n1: (398,12) -> (744,118)` (152s, 825s at wider spread) |

## What changed (this session, all gated)

Root-cause fixes in `compose.py`/`tiles.py`/`layout.py`/`sim.py`:

1. **Single-leg input routes** — pinned turn cells are unhoppable endpoints.
2. **Outputs never inlined** — bare KeyError after routing succeeded.
3. **Lamp taps before routing** — post-routing field has no clear spot.
4. **Torch-adjacency seal** — runs beside foreign torches oscillate (6-gate chain TORCH BURNOUT → green).
5. **Self-lid counts tile-body cobble** — alu4 C1 routes.
6. **Boost elevated runs** — y=3 spans bled to dark (ctrl_decode GREEN).
7. **Flight liveness BFS** — reject flights that can't couple a→b.
8. **Net '1' is routable** — constant stubs stood alone (cmp2 class).
9. **Spread retry 1..5** — green builds bit-identical at spread 1; dense retry wider.
10. **Size-aware sim stall cap** — flat 5000 tripped on healthy 7000-block startup.
11. **Levers at lanes (d1 zero-length)** — kills 100+ cell centroid marches; this is what greened micro1 via compose (latch S/R skew gone).
12. **Longer trunk jogs (u to 32)** — add2 12539→8083 blocks, 24s→1s.
13. **Full vertical envelope** (layout astar y=-4..6, _support below ground, trench-aware stone, compose narrow-first) — per request; maze keeps y=1..3.

Reverted with evidence (all in-file as `ponytail:` notes or commit messages):
buried-wire guard, cobble-side seal, per-leg reachability, _displace
both-nets, port-roof guard, load-relative lanes, inputs-first order,
sibling-lane avoid, RS_NOLANE bypass.

## Why alu1/alu4/cpu4 stand (honest assessment)

All three share one wall class: **5+ inputs whose loads interleave across
a saturated field must cross each other, and crossings need 3D room that
isn't there.** Specifically: OP1/OP0 y=3 overflights collide (no
3D-aware blame/displacement exists — `_blame` is y=1-only); CIN needs a
700-cell march astar cannot span (100k step cap vs ~800-cell box); alu4/
cpu4 carry chains need the same. What would unlock them, in order:
(1) 3D-aware blame/displacement for overflight collisions;
(2) a fixed-shape 3D highway candidate (up, straight at y=3/4, down) for
long marches instead of astar search;
(3) an input bus architecture so inputs never cross.
None of these is a small diff; all three were red for two prior sessions
for the same underlying reasons.

## Decisions needed (no credentials, just calls)

1. **Latch power-on** (standing): a 2-NOR SR latch with both inputs low
hunts ~10 OFF-transitions/30 ticks vs vanilla's 8 (genuine rings hit 15
*and* trip not-settling at churn=210). Accept reset-then-set, or require
cold settle? micro1 is green either way (compose now, maze before).
2. **Fidelity vs correctness**: sim_verify checks the build against the
recipe, not the recipe against arithmetic — my first add2 had a wrong
carry and still went green. Want a golden-reference gate for recipes?
3. **Compactness**: builds are 8-16k blocks (router overhead, not logic).
If block count matters, say so — currently the router optimizes for
routability (sprawl, repeaters), never density.

## Housekeeping

- Killed PID 14948 (~6h maze grind on alu4/cpu4); don't rerun the full
  maze ladder on those in one shot.
- `scratch/` probes gitignored, never merge. Useful: `ghost.py`
  (frame-correct ghost check), `gatewhy.py` (first-wrong-gate),
  `orphanmap.py`, `hsweep.py`, `batch.py`, `leglog.py`.
- Branch `phase2-design`, HEAD `09969ff`, working tree clean.
