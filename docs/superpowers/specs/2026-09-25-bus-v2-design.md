# Bus routing v2 design (2026-09-25)

Status: design (approved §1–3 in brainstorm). Supersedes the routing
geometry of `2026-09-25-bus-routing-design.md` (v1 rigid lanes walled on
the 4-gate: 5000+ order samples, mutual walling under pitch-2 — see
phase2-design branch history). Keeps the v1 invariants: stations every
14, taps only at full-strength outputs, loud fail into tries/grow, sim
is selector. Refines `docs/phase2-bus-routing.md` (still the goal).

## Locked decisions

- **Vertical trunks** in inter-band gaps (~14 cells, empty by
  construction) instead of horizontal lanes through tile columns.
- **Relay splitting**: every band crossing goes through `buf = x AND x`
  (tagged like the existing `rep` precedent), so no net ever spans more
  than one gap. Extends the existing `expand_gates` relay/replica
  machinery; per-band input replication retires in favor of chains.

## Architecture

`expand_gates` gains crossing-relays (buffer per gap crossed, parked by
the normal band machinery; inputs chain from a single head lever).
`layout()` routes only local hops and reuses the v1 planner core
(legality, decay budgets, tap rule, order search): same-band hops go
direct (Manhattan L); cross-band hops go through one N-S trunk per
relay-net in the gap. Maze stays deleted; retry/grow/verify untouched.

## Hop mechanics

- Same-band hop: direct stub, legality-checked, decay-capped (≤14).
- Cross-band hop: driver stubs east to its gap trunk, trunk runs N-S,
  stubs west to load ports. Stations every 14 measured both directions
  from the feed point (south- + north-facing; repeaters are one-way).
- Inputs: single lever at the chain head; `minimize_recipe` passes
  tagged relay gates through (banded/LATCH precedent).

## Errors

Loud `RuntimeError` on illegal cell/stub into tries/grow. No new
recovery machinery, never silent wrong.

## Verification

Existing harness: suite green, 4-gate `0/6` + sequence (first proof of
the new geometry), demo, micro1 + alu4 with ~10× fewer repeater blocks
than maze (counted). New check: every hop is intra-gap-local (span
assertion from `io["bus"]`).

## Risks

- Relay ANDs add torch-delay stages; latch sequences must still settle
  (sim arbitrates — sequence proofs are gates, not assumptions).
- minimize must not eat tagged buffers (guard + dedicated assert).
- Block count rises with buffers (unconstrained; only repeaters gated).

## Non-goals

No layers/bridges (flat), no clock, no new tile types, no sim changes,
no per-recipe tuning.
