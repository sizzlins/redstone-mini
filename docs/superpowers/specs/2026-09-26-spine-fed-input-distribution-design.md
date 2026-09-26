# Spine-fed input distribution (2026-09-26)

Status: design (approved §§1–3 in session). Goal: one lever per input on
ALL builds including cpu4; all builds verify green.

## Constraints (user-pinned)

- Single lever everywhere — no per-band / multi-lever fallback.
- Done = micro1, alu1, alu4, cpu4, ctrl_decode verify green + suite green.
- Area, wire, and layout time are unchained; compactness is a later
  project, not this one.

## Problem (evidence, not theory)

- Star fanout (one full marathon per load): seals dense rows. micro1
  >290s; alu4 723-cell OP0 marathon fails 30s; cpu4 2-cell D1 jog
  unlandable 64s. Goals end surrounded (dump-proven).
- Organic taps (nearest own-wire multi-source): killed twice. (a) Ripped
  trunks re-tap zero-length at goals doubling as starts → OPEN stubs.
  (b) Gate rip-up orphans tap branches → sim-dark decay (panel self-check
  vector a=1,b=1,c=0). Both reproduced, then reverted.
- Grow (78s, still sealed), pitch 24→36 (no effect, reverted), ordering
  games, and last-resort bridges all ruled out with timings. Full trail:
  `scratch/panel-micro1-report.md` (gitignored) + handoff.

## Architecture

Each input gets exactly one **spine**: bank → farthest load, routed as a
first-class task and recorded in `paths`, so the booster pass covers it
(the uncovered-spine decay that killed organic taps cannot recur). Every
other load **taps** the spine via short hops (astar multi-source restricted
to bank-connected wire — the zero-length OPEN failure cannot recur).

Two rules keep the tree stable:

1. **Spines are unrippable.** Path cells join `placed` on success (same
   status as tile stubs). Gate rip-up can no longer delete trunk under
   live branches; gates detour around or bridge over spines instead.
2. **Spines are bridgeable.** The bridge-victim filter drops its
   `not in placed` exclusion (sort still prefers non-placed victims).
   Each N-S spine × E-W marathon pair crosses exactly once via the
   pre-proven hop with reachable feet in the spine's free corridor —
   instead of today's rip ping-pong. Footprint/guard checks unchanged.

Star = N wall-crossings per input (each seals); spine = 1 crossing + local
taps, in an empty field (inputs route first) with bridge-first policy.

## Routing policy

- **Order** (deterministic on seed-None): inputs first. Per input — groups
  shuffled per seed on a *separate* RNG stream so gate shuffle is
  byte-identical to today: spine task first, then tap tasks
  nearest-from-bank. Gate tasks keep today's distance/shuffle order.
- **`route()`**: input starts = bank feed + bank-connected same-net wire
  (BFS at call time; spine calls degenerate to single-source). Gate nets
  stay single-source.
- **Bridges**: input tasks bridge-first on route failure, rip-up second.
  Gates rip-up-first, unchanged. Cap stays **24**; explicit trigger: a
  build that routes everything except cap exhaustion
  (`len(bridged) == cap` at failure) earns a raise to 96. No speculative
  bump. cpu4 is expected to test the trigger (est. dozens of crossings).
- **Failures** stay loud (no fallback paths): unroutable spine/tap raises
  like any gate net; retry/grow handles it. `sim_verify` remains the
  levels guard — it caught tap decay and gates this design too.

## Verification (staged, each a gate)

1. micro1 single-seed probes (~10s): route + `verify=True`, incl. the
   decay-catching vector.
2. Panel self-check + fanout probe: exactly 1 lever per used input,
   lever-less unused. Assert `io["levers"]` counts on every build below.
3. alu1, then full suite (`recipe.py`, `sim.py`, `serve.py --check`,
   `layout.py`).
4. alu4 + cpu4 + ctrl_decode as background jobs with logs + polling
   (never foreground).
5. Acceptance: all five verify green, suite green, one lever per input.
   Record per build: blocks, ticks, bridges used, wall time.

Red stops the line: diagnose with dumps, one change at a time,
keep-or-revert. No stacked patches.

## Out of scope

Compactness/optimization; lever facing or labeling; OR-junction aiming;
any `sim.py`/`export.py`/`serve.py`/`core.py`/`recipe.py` change; any
gate-net behavior change. `layout.py` only, stdlib only, no new files.

## Alternatives cut (with reason)

- Per-band levers: violates the single-lever constraint.
- Vertical highways (y=2+ trunks): biggest change; revisit with data only
  if the spine fails on cpu4.
- Reserved port-approach corridors: more placement↔router machinery;
  same revisit rule.
- Input relay/buffer chains: buffers park at the bank, marathon
  preserved; measured useless for fanout-2.
