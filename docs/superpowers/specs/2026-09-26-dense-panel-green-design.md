# Dense panel-green (2026-09-26)

Status: design (pending review). All 8 `.txt` verify green with one lever
per used input. Reuses bus spec + installed relay; placement yields room
instead of router searching harder.

## Problem (measured, not theory)

Panel shipped with ceiling (`handoff.md`): small builds green (demo 246),
dense red. Re-verified 2026-09-26: `micro1 seed=None grow=0` fails fast
`no route for T1: (126,12)->(196,12)` (`layout.py:798`). Dump `256x38
wires=517`: corridor `x150-178` holds `OP@(154,11/12/13)`, `T0@(172,11/12)`,
torch `@(178,13)` — flat crossing forbidden by `touches_foreign:45` +
`guard:92`, bridge feet land in same wall (`try_bridge:708` cap 24).
Root pin: `gridpos=(6+b*24,gz):350` + `reserved/others_reserved:362` +
`spot_free:fp.isdisjoint:391` pins tiles to columns; local chain caged
`±16/±7`. Row fits gates xor delivery. Router-only rungs exhausted
(star/grow/pitch/order/spine/corridor/lanes/west-bank, `>290s`/`78s`/`>300s`).

## Decisions

- `sim.py` stays selector, untouched. No new deps, no new tiles, no 3D.
- `layout.py` first; `recipe.py` only if measured (cpu4 fanout).
- One change per task, keep-or-revert. Dense probes background + poll only.
- Loud fail stays; no silent multi-lever fallback.

## Design (3 changes, phased)

1. **Bus lanes pre-claim (layout.py).** Before tiles, claim one straight E-W
   lane per used input at `z = (D-4) - idx*2` (just north of the south bank,
   south of tile rows which start at `gz=12`), spanning `x=1..W-2`, 2 apart
   per `docs/phase2-bus-routing.md:11-13`. `spot_free:371`
   gains one disjoint check against lanes (reuse `footprint` machinery).
   Tiles dodge lanes instead of lanes threading tiles. `ponytail: lanes
   are straight claims, maze detours if a lane saturates`.
2. **Trunk + repeater-output taps (layout.py).** Each input drives its bus
   head (single south-bank lever, `_ax:277` unchanged). Stamp trunk dust +
   repeaters every <=14 reusing `place_rep:830` spacing (bus stations, never
   on tile dust). Loads stub N/S to ports (short maze); taps ONLY at
   repeater outputs (full 15, sim-sound per `sim.py:112-113,163-167`;
   spec `phase2:18-21`). Deletes N full-length marathons per input.
3. **Input relay iff measured (recipe.py).** Lift `:102` exclusion only for
   inputs with >=3 loads, chaining `AND(x,x)` via existing
   `buf_of:179-191`, parked adjacent to bus. micro1 (2-load) untouched.
   `ponytail: threshold 3 reused, raise only if cpu4 proves exhaustion`.

OR-wall footnote: `alu1 t1->(78,14)` diode-backs buried in own OR cluster
is a separate tile-local park bug; same task family (OR diode parking dodges
own junction cluster), still `layout.py`.

## Budget

~40 lines in `layout.py` (lanes + trunk + taps) + ~10 iff relay. No sim/
export/serve changes. One `__main__` check: micro1 one-lever verify green.

## Alternatives cut

- More maze (ordering/rip-up/bridge tuning): measured dead, cut.
- Per-band multi-lever: breaks single-lever ask, cut.
- Full 3D layers: pays vertical physics + sim scope, no consumer, cut.

## Verification gate

- Suite green: `recipe.py`, `sim.py`, `serve.py --check`, `layout.py`.
- All 8 `.txt` via `layout_retry(verify=True)`: `Counter(levers)==1`/used input.
- Dumps: bus lanes 2-apart, taps at repeater outs, no SHORT/OPEN.
- Economics: foreground micro1/alu1 only; alu4/cpu4/ctrl_decode background
  `cmd /c start /b ... > log 2>&1` + poll, kill at 600s silence.
