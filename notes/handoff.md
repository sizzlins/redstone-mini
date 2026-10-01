# handoff — cpu4 hierarchical merge (updated)

Repo: `D:\redstone-mini` (branch `phase2-design`)
Last commit: `7fdbd72`. Working tree clean except `notes/`.

## Goal

Make every recipe in `recipes/` generate and verify. `cpu4` is still the only
red one. It is built as a 10-band hierarchical layout from
`scratch/cand_cpu4hier.txt` (equivalence-checked over all 128 vectors).

## Where cpu4 stands

The merge **reaches the simulator and 3 of 5 outputs are now correct** (was:
torch burnout, then all-dark). `Y2` is the last mismatch.

```
$ python scratch/hier_stitch.py scratch/cpu4bands.pkl scratch/cand_cpu4hier.txt 240
MERGE 76444 blocks (3480, 241)
SMOKE 0000000 OK
SMOKE 1111111 MISMATCH ['Y2']
```

## Fixed this session (all measured, all committed)

1. **Undriven latch must hold, not hunt** (`sim.py`). From a fully dark start
   a NOR latch is symmetric in this model: both torches fire and hunt until
   burnout (a lone `LATCH` burned out on `S=R=0`). Vanilla breaks the symmetry
   with update-order skew; `eval_net` already assumes hold-0.
   `_latch_hold_seed` presets `~qb` dust **and** its driver torch (each alone
   was measured to fail), and a new power-on pre-roll (`_solve`) iterates
   dust/blocks/torches to their tick-0 fixpoint so no gate output pulses on
   tick 1 — that pulse reached an idle latch's S/R at T~9 and broke the
   seeded hold into a permanent hunt (churn=14736). Latch-free builds take a
   byte-identical path.
2. **A lever powers its attachment block only** (`sim.py`). The old all-sides
   term let a floor input lever strongly power foreign cobble beside it; D3's
   lever drove R0Q0's stitch run to 15 and forced R0Q2 high whenever `D3=1`
   (bit-0 AND/XOR wrong). `_parse_build` now records `leveratt` from
   `face`/`facing`. `_parse_build` returns a 12-tuple — the three scratch
   probes that unpacked 11 were updated.
3. **Relay stations only on straight runs** (`compose.py`). A station is a
   diode; on a corner it rectifies the turn away (E1's station orphaned
   1100+ cells, whole R1 bank unwritable).
4. **A stitch must DELIVER onto its stub by sim-conducting links**
   (`_landed`, `compose.py`). `lwire` stops at the target xz whatever y it
   arrived with, so an elevated end over a lidded/unsupported stub was dark
   in sim while every checker stayed silent. Support + no-lid + diode-forward
   terms mirror `sim.dust_lvl`/`rep_on` — **keep the two in sync**. Every
   strategy is now atomic through the gate (a landing-failed relay used to
   leave its whole run in the field and poison every later strategy), with one
   bounded last-mile `lwire` before giving up.
5. **Head-boost diode** (`_plant_repeaters`). A latch Q tail is ~10 dust
   cells, so a register fan-out stitch starts at level ~5 and the every-8
   planter's first diode never fires: R0Q0's stitch lit 5 cells then dark for
   850.
6. **`_ends_ok`** — a booster may not fire into foreign dust. Also applied to
   relay stations.

## Verified no regression

`python sim.py`, `python recipe.py` pass. `scratch/compose_check.py`
bit-identical (144/322/224/214). `scratch/dense_status.py` OK for
example_and, latch_sr, mux2 (4226), micro1, decode3, sub2 (3487) at banked
block counts. **alu4 re-verified 1024/1024** on its cached merge with the new
physics (`scratch/verify_par.py`, all 16 chunks green).

## The remaining Y2 fault (measured, not yet fixed)

`R0Q2: 3/1865 cells lit`, and the three are at the far end (x=2366), driven
by a *neighbouring* run — not by its own stitch. The stitch head
`(768,2,76)` is dark from tick 1.

Head geometry: the latch Q port is at y=1 and the very first stitch cell steps
**up** to y=2 (`(768,2,76)` → `(768,3,77)` → repeater `(768,3,78)`), so the
head arrives at level ~4 and bleeds out in a handful of elevated cells. The
head-boost diode never fires there: its straight-triple test requires
`py == cy == ny` and the first level triple only starts at the third cell.
R0Q0 escapes this because its head is flat.

Two candidate fixes, cheapest first (neither verified yet — do not ship
unverified):

1. Let the head boost plant on the first LEVEL straight triple even when the
   path is climbing into it (drop `py == cy == ny` for the head case only,
   keep the support check). ~2 lines.
   **TRIED AND REVERTED**: it changes every route's booster cost, so the
   whole merge re-routes (76444 -> 78193 blocks) and lands a *worse* result —
   the R0/R1 bank went fully dark (`R0Q2 0/1897`, `R1Q2 12/1746`) and `Y1`
   joined `Y2` as red. A booster planted on a climbing head evidently becomes
   a one-way trap (its back is a slope link the sim may not even read). So
   the head is not the right place to fix this; the climb itself is.
2. Make `_landed` symmetric: today it only gates the **stub** end, so a broken
   **driver** link stays silent. A per-step sim-link check over `full` would
   have caught this at compose time. Risk: it can reject a currently-green
   stitch (alu4's cached merge would have to be recomposed to prove it).
3. Untried, and arguably the real one: stop the stitch from climbing at the
   driver. `lwire` is free to overflight out of the latch port; forcing the
   first leg flat (or seeding the port with a booster on the latch's own flat
   Q tail, which is the tile's dust, not fresh street) keeps the head on
   ground where the existing head-boost already works (R0Q0 proves it).

Note `R0Q2`'s latch and the E1 run both sit inside band 2's field; the
`(774,1,48..50)` cells are E1's own crossing, not an overwrite (they were
empty when stamped — `stamp_wire` never overwrites foreign dust, it raises).

## Commands

```powershell
$env:REDSTONE_ASTAR_CAP="6000"
python scratch/hier_stitch.py scratch/cpu4bands.pkl scratch/cand_cpu4hier.txt 240
python scratch/verify_par.py scratch/alu4merge.pkl recipes/alu4.txt 16 400 2
python scratch/dense_status.py recipes/<name>.txt 1
python recipe.py
python sim.py
```

## Files

- `sim.py` — `_latch_hold_seed`, power-on pre-roll (`_solve`), `leveratt`.
- `compose.py` — `_ends_ok`, `_landed`, `_try`, relay corner guard, head boost.
- `scratch/cand_cpu4hier.txt` — 10-band candidate, 128-vector equivalent.
- `scratch/cpu4bands.pkl` — cached bands, all 10 re-verified green on the new
  physics (`C:\...\opencode\bandcheck.py` equivalent: all 10 GREEN).
- `recipes/cpu4.txt` — still the original unbanded recipe. Do not promote
  until `Y2` is fixed and 128/128 verifies.
