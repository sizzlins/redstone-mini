# Handoff — redstone-mini (2026-09-30, dense-build session)

> **Read this file first.** It supersedes everything in
> `docs/handoff-archive-2026-09-27.md`, which is kept verbatim for its
> measured evidence and is correct about the *sim contract* and the
> *vanilla bar*, but its verdicts on which wall binds are stale.

Branch `phase2-design`, HEAD `f79561e`, working tree clean.

## Goal

A generator whose output is **100% vanilla Minecraft compatible** — every
build is exported to `.schem` and pasted into a real world, so the
simulator is a *shipping* gate, not a design aid. A false green is a
broken build in someone's world.

**This session's bar (not met):** all 5 dense recipes generate *and*
sim-verify, plus 3 new dense builds. See Current state for the honest
score.

## Current state

| recipe | gates | status | how |
|---|---|---|---|
| `example_and` | 1 | **GREEN** 182 blocks | compose |
| `example_2gates` | 2 | **GREEN** 396 blocks | compose |
| `latch_sr` | 1 | **GREEN** 250 blocks | compose |
| `example_xor` | 1 | **GREEN** 282 blocks | compose |
| **`micro1`** | 10 | **GREEN** 2301 blocks, 6.8s | **maze** backend |
| `alu1` | 21 | RED — compose frontier below | — |
| `alu4` | 72 | RED — unmeasured this session | — |
| `cpu4` | 126 | RED — unmeasured this session | — |
| `ctrl_decode` | 15 | RED | — |

**Score: 1 of 5 dense verified, 0 new dense builds.** The bar is not met.

Gates, all green at HEAD:

```powershell
python compose.py                 # AND sim-verifies, bridge, buffer inline
python scratch/compose_check.py    # 4 small builds, each sim-verified
python recipe.py                  # parser / expansion / pre-place gate
python sim.py                     # 19 physics + checker canaries
python scratch/compose_status.py   # dense ladder, compose only (FAST)
python scratch/dense_status.py    # dense ladder, compose->maze (SLOW)
```

`micro1` greens through the **maze** backend. `compose` also builds it
(3367 blocks) but the sim reports TORCH BURNOUT on the latch pair — see
What failed.

## What changed (7 commits, all in `compose.py` unless noted)

Every change is inert on open corridors, so the 4 small builds stayed
sim-green throughout: 182/396/250/282, unchanged by all of it.

1. **Ring-hop** (`lwire`). A reservation-only ring cell now spans via the
   existing 5-cell bridge instead of dying loud. Found by BFS: alu1's `AB`
   had a provable violation-free len-53 run, and all 26 L/ray candidates
   died on *one* empty ring cell.
2. **Ranked candidate fallback** (`lwire`). Walks every ranked candidate
   with per-candidate rollback instead of dying on `cands[0]`. A failed
   attempt must roll back — phantom same-net wire would read
   live-but-unboosted downstream.
3. **`_astar_wrap`** (`lwire`). Reuses `layout.astar` as a last candidate.
   astar clips its search window at 0 while compose lanes run negative, so
   the box is shifted non-negative and the path unshifted. Bounded to
   manhattan+64 (an earlier 10^6-wide window held ~100k heap entries and
   **crashed this machine**).
4. **3D overflight** (`lwire`, `aa29f26`). astar's y>=2 search with
   `layout._support`-validated pillars, stamped after search. This is the
   only mechanism that crosses a long N-S column. Endpoints may not be
   overflown directly — a pillar there puts cobble on the load and lids
   the descent — so that is priced into astar's `congest`, not walled.
5. **Offset-trunk candidates** (`_candidates`). 12 parallel corridors
   `u` rows north/south of the load row.
6. **Driver halos.** Foreign *drivers* are reserved like loads. The
   measured seal was stamped on a driver, not a port.
7. **Wide streets** (`_expanded`, halo 2->4). Sibling tile yards were
   merging into one sealed super-block.
8. **Confinement ordering + blame restart + displacement** (`compose`).
   Most-bottlenecked net first; on a loud death, blame the sealing
   wire-owner, constrain order, re-run from the placement-end snapshot
   (24 restarts). When order cannot separate two mutually-sealed nets,
   `_displace` deletes the sealer's wire, routes the failed net through the
   freed ground, then re-routes the sealer around it.
9. **Latch porch guard** (`tiles.py`). The S-row repeater's front zone is
   ringed empty, so no routed run can close a front-back dust loop around
   the diode. `ring()` *updates*; this must **assign** — the family apron
   already ringed those cells and `setdefault+update` cannot narrow.
   micro1's failure changed from "not settling" to "torch burnout", i.e.
   the 329-cell dust ring is gone.

Nets that used to die on alu1 and now route: `m0`, `m4`, `O`, `AB`, `n0`,
`n1`, `CIN`.

## What failed (measured, reverted, evidence kept in-file as `ponytail:`)

- **Input trunk rows.** Route each input's long E-W travel on reserved
  rows south of every tile (open ground by construction). Fixed alu1's
  B/CIN legs; `example_and` went 182 GREEN -> 314 SIM MISMATCH because
  trunk runs bleed 15->5 before the hop dust and the OR junction reads
  weak. One shared row also shorted all inputs together (pitch 2 needed).
- **Lane offset 8 / pitch 6.** Did not move the wall — the 2-wide canyon
  is a gate port, not the input lane — and cost small builds 30% more
  blocks (182 -> 238).
- **Parity-staggered torch power-on** (`sim.py`). Break symmetric latch
  rings the way vanilla's propagation skew does. Made micro1 *worse*: 4
  green W=1 vectors -> 0, all burnout. Reverted to same-tick.
- **Input port-approach opening, twice.** See What next step 1.
- **Maze seed/grow sweep** — not a change, a *falsification*.
  `ctrl_decode` 0/8, `alu1` 0/4 across seeds x grow 0/1/2. **Both backends
  hit the same `no route` walls**, so no seed, grow level, or backend
  ordering can satisfy the bar. This retires "just search harder".

### The two live walls

**alu1, compose, frontier `OP1: (-15,12) -> (4,12)`.** This leg has **no
flat path and no 3D path**. Reason: a tile's own apron seals its west-edge
port cell, so the run must cross 4 cells of the NOT tile's reserved halo.
This is geometry, not search.

**alu1, the hop shape itself.** The 5-cell hop needs 2 clear cells on each
side of the victim. Two parallel wires 2 apart therefore form a canyon
that **no ground candidate can cross**, and since the columns are long,
*every* row is blocked. The 3D overflight is the only way past it.

## What we should do next (in order)

1. **Guarantee a strong 15 at OR-diode rears in `_plant_repeaters`.**
   This is the blocker for everything else. A comparator side and an OR
   diode rear are the only places that need 15; the current 8-cell spacing
   lets a long run arrive at 9. Diagnosis is confirmed, not guessed: the
   port-opening v2 failure was `example_2gates` (`t = a AND b`,
   `y = t OR c`) reading `y=False` where `y` must be 1 — the OR junction
   not firing. Gate: the 4 small builds stay green.
2. **Then re-open input port approaches** (v2: input nets, 3 cells west of
   the load, ringed empty). With step 1 done the approach can be longer
   without starving the junction. Expect alu1's `OP1` to route, which is
   the last compose wall measured on it.
3. **Re-measure with `scratch/compose_status.py`** — compose only, seconds
   per recipe. Only spend minutes on the maze backend for a recipe compose
   has already greened.
4. **micro1's compose SIM failure** is independent of all of the above.
   Traced: the latch's S/R arrive through long diode runs, so one fuse
   trips before the other's S breaks the ring. Needs either a defined
   power-on (reset-then-set) or a shorter S/R approach. **Open question for
   the owner: is a defined latch power-on acceptable, or must every build
   settle from cold?**
5. **`alu4` / `cpu4` are unmeasured this session** (minutes per attempt).
   Measure them only after 1-3 land, per step 3's discipline.

### Reference repos (assessed, not needed)

`nturley/netlistsvg`, `Nic30/d3-hwschematic`, `davidthings/hdelk`,
`kevinpt/symbolator`, `TerosTechnology/vscode-terosHDL` are all
diagram/document tools with **no** MC physics or routing — they would move
zero greens. `hneemann/Digital` is a fine logic scratchpad (ships a MIPS
CPU, 300k-component RAM sims) with no MC export. `YosysHQ/yosys` is the
only one worth taking, and only *after* the backend greens a dense build,
as a Verilog -> `recipe.py` frontend. **Clone none of them now.**

## Files touched

| file | what |
|---|---|
| `compose.py` | all 9 changes above (the whole session) |
| `tiles.py` | latch S-row repeater porch guard (`place_latch`) |
| `LOG.md` | session timeline, assumptions, every revert with numbers |
| `MORNING-REPORT.md` | morning summary + this TODO's source |
| `docs/handoff-archive-2026-09-27.md` | prior 1106-line handoff, moved verbatim |
| `scratch/*.py` | gitignored probes, **never merge** |

Untracked by design: `scratch/` (gitignored), `docs/plans/*.md`
(policy-excluded).

Useful probes, all in `scratch/`: `compose_status.py` (fast dense ladder),
`dense_status.py` (full ladder), `mazesweep.py` (maze seeds x grow),
`wallpanel.py` (pocket + boundary + hop log on first loud death),
`flywhy.py` (which stage kills a 3D attempt), `hopclause.py` (clause-level
hop refusals), `astarprobe.py`, `netdump.py`, `rectdump.py`, `churnedge.py`,
`plantlog.py`, `vecsweep.py` (per-vector fresh-state sweep).

## Environment notes (still true, still cost time)

- **Never pipe a long run through `Out-String`.** Redirect to a log file
  and poll the log; a buffered pipe looks hung.
- **`Start-Process` with two children throws `ChildProcess.kill`** and the
  children survive. Start one at a time, or use `&` with a log redirect.
- A python process running `chess_notifier.py` is **not ours** — leave it.
- The tool timeout kills long foreground commands silently: a chained
  `git commit && python ...` loses all output when the python part dies.
  Commit first, then run the long thing separately.
- A* over a 10^6-wide field will exhaust RAM. Bound every search window.
