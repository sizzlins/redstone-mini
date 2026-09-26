# Input port corridors (2026-09-26)

Status: design (approved §§1–3 in session). Goal: one lever per input on
ALL builds including cpu4; all builds verify green.

Supersedes: `2026-09-26-spine-fed-input-distribution-design.md` (spine
arbitration failed with data — see post-mortem below; that spec stays as
history, do not implement it).

## Constraints (user-pinned, unchanged)

- Single lever everywhere — no per-band / multi-lever fallback.
- Done = micro1, alu1, alu4, cpu4, ctrl_decode verify green + suite green.
- Area, wire, and layout time are unchained; compactness is a later
  project.

## Problem (evidence)

Dump-proven killer across micro1/alu1/alu4/cpu4: input ports sit embedded
in the gate-wire row with every neighboring cell foreign wire, guard ring,
or solid (e.g. micro1 W→(52,15) sealed N by bridge supports; cpu4 D1
2-cell jog unlandable 64s). Star fanout fails (marathons seal, >290s);
organic taps fail twice (OPEN zero-length re-taps; sim-dark orphaned
branches); spine variant fails at gate-vs-spine arbitration (single-shot
bridges under-deliver, chained bridges thrash >300s, unrippable blocks
gates). Grow/pitch/ordering ruled out with timings. Full trail:
`scratch/panel-micro1-report.md` (gitignored) + handoff.

## Architecture: reserved port corridors

At tile placement, for every input-fed port, stamp a westward approach ray
for that input's net: 8 cells long, 3 wide (port row ±1: lane + halo
clearance, since 1-wide still halo-seals), truncated at the first solid.
Same `ring()`/`own()` calls tiles already make — placement-only, ~10 lines
where ports are known (`stamp_and` returns `pa`/`pb`; NOT/NOR/LATCH/XOR
record theirs in `recs`). The router is untouched: it already treats
mismatched-net rings as walls. Foreign wire can never enter a full ray, so
delivery's last cells are routable by construction. Truncated rays degrade
to today's behavior (loud if truly sealed — never worse than now).

Crossing cost: E-W marathons detour around ray west tips; N-S branches
sidestep 3-wide rays. Bounded, in free gaps, no bridges required.

## Transit policy: unchanged, measured

Corridors own the last 8 cells; everything before them rides today's
machinery with zero policy changes: inputs-first order, single-source star
branches, rippable delivery, rip-up first, last-resort bridges at cap 24.
Gate-gate arbitration already greens; input branches rejoin as ordinary
nets. Each dense probe records failure location (transit vs truncated
corridor) + bridge count. Triggers only: failure inside a full corridor =
placement bug (fix the ray, never the router); transit failure with bridges
exhausted at 24 = bridge-first for inputs returns as its own commit.

## Verification (staged gates)

1. Corridor unit probe (dump asserts full 8×3 rays, ~2s).
2. Panel self-check + fanout probe (decay/SHORT catchers).
3. micro1 single-seed + verify, one lever per input; classify reds first.
4. Full suite byte-green on small builds.
5. alu1 → alu4 + cpu4 + ctrl_decode background + logs + poll. Record
   blocks, ticks, bridges, wall time, failure class.
6. Acceptance: all five green, suite green, one lever per input.

Red stops the line; §2 triggers decide router changes; keep-or-revert.

## Out of scope

Compactness; lever facing/labels; OR-junction aiming; any `sim.py` /
`export.py` / `serve.py` / `core.py` / `recipe.py` change; any gate-net or
router-policy change unless a §2 trigger fires. Placement stamp only.

## Alternatives cut (with reason)

- Spine-fed trees: implemented (order + taps + unrippable + bridges);
  arbitration failed with data (T0 fixed, Q needs 2 hops, chaining
  thrashes). Reverted to green; spec kept as history.
- West bank: moves transit, doesn't unseal ports (drops face sealed
  neighbors either way).
- Local placement spiral: reshapes every green build for a *maybe*;
  full re-verify with no delivery guarantee.
- Vertical highways: biggest change; revisit with data only if corridors
  fail on cpu4.
- Per-band levers: violates the single-lever constraint.
