# Deterministic input lanes (2026-09-26)

Status: design (approved §§1–3 in session). Goal: one lever per input on
ALL builds including cpu4; all builds verify green. Inputs-only scope
(ponytail: gates already green flat; general 3D is unrequested).

Supersedes (history, do not implement): spine-fed spec (arbitration failed:
single-shot bridges under-deliver, chaining thrashes >300s, unrippable
blocks gates) and port-corridor spec (reservations self-seal: west rays
cross sibling lanes, bank-ward rays die in tile bodies, small builds went
dark). Third spike (west bank) reverted same turn: even 25-cell parallel
runs seal — the tile row itself is airtight.

## Constraints (user-pinned, unchanged)

- Single lever everywhere — no per-band / multi-lever fallback.
- Done = micro1, alu1, alu4, cpu4, ctrl_decode verify green + suite green.
- Area, wire, and layout time are unchained; compactness is a later
  project.

## Problem (evidence)

Every search-based delivery into dense rows failed with data: star (>290s),
organic taps (OPEN zero-length re-taps; sim-dark orphaned branches),
median-bank placements, inputs-first/last orderings, grow (78s, still
sealed), pitch 24→36 (no effect), last-resort bridges (feet land inside
walls), bridge-first, chained bridges (>300s thrash). Common root: asking
astar to thread the dense row. Full trail: handoff +
`scratch/panel-micro1-report.md` (gitignored).

## Architecture: lane compiler, not search

South bank and median anchors stay as merged. Per input, in recipe order
(groups shuffled per seed on the existing separate stream):

1. **N-S trunk**: straight `y = 1` dust stamp at bank-`x`, bank-`z` to
   the E-W bus lane (free middle field — unplaced, uncrossed). No astar.
   Blocked cell → loud.
2. **E-W transit**: straight dust stamp at the bus lane from the trunk to
   each load's `x`. The bus lane is computed post-placement: the
   southernmost fully-free E-W lane south of the tile rows (unbanded
   builds: ~`z = 26`). Banded tails (e.g. alu1 band-2 rows down to z~138)
   stretch north stubs past 15 cells — measured risk, owned by Task 5, not
   assumed away. Every trunk-crossing gets a deterministic pre-proven
   bridge (feet in the free lane, reachable by construction). Footprint
   check fails → loud. Bridges count against cap 24 (raise trigger below).
3. **Repeaters**: deterministic spacing every ≤14 on trunk + transit +
   long stubs (straight cells trivially satisfy `is_straight`). Levels
   guaranteed by construction; sim still verifies every build.
4. **North stubs**: the only search left — existing single-source `route()`
   from `(load-x, busZ)` to the port. Short on unbanded builds, row-length
   on banded tails (the measured risk above); fresh level-15 base,
   rip/bridge backup, loud on failure.

Search never enters the row except for 3–8-cell stubs, and every transit
step is O(1) stamp-or-loud: the >300s churn class cannot occur. Gate nets,
rip-up, bridges policy, sim, export: untouched.

## Verification (staged gates)

1. Trunk-stamp unit probe (~2s, dump asserts: unbroken runs, repeater
   spacing ≤14, bridge count == crossing count).
2. Panel self-check + fanout probe + suite (record wire counts).
3. micro1 full verify + one-lever assert. Red: classify transit-stamp
   loud (lane reality) vs stub unroutable (dump window, no patch without
   cause) vs sim-dark (spacing bug).
4. alu1, then suite re-green.
5. alu4 + cpu4 + ctrl_decode background + logs + poll. Record blocks,
   ticks, bridges vs cap, wall time, failure class.
6. Acceptance: all five green, suite green, one lever per input.

Red stops the line; keep-or-revert per task; no stacked patches.

## Out of scope

Compactness; lever facing/labels; OR-junction aiming; general 3D routing;
any `sim.py` / `export.py` / `serve.py` / `core.py` / `recipe.py` change;
any gate-net or router-policy change unless the cap trigger fires. Cap
trigger (sole router-adjacent knob): bridges exhausted at 24 with
everything else stamped → raise to 96 in its own commit.

## Alternatives cut (with reason)

- Spine-fed trees, port corridors, west bank: implemented, failed with
  data, reverted to green. Specs kept as history.
- Local placement spiral: packs tiles tighter against evidence that
  density itself is the wall.
- General vertical highways: biggest change; elevated trunks need
  per-cell supports (unbridgable walls) or drop-stations everywhere —
  strictly worse than ground lanes in free field.
