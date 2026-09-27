# Input fanout chaining (2026-09-27)

Status: design (approved §§1–4 in session). Goal: new recipes go green by
default. Proof: a frozen holdout plus a synthetic green-rate floor — not
cherry-picked seeds.

Supersedes nothing; it reuses the existing relay machinery. The two placement
mechanisms (port corridors, per-input bank) were implemented, measured, and
reverted — same failure species (middle-field walls) — and are explicitly out
(see §4).

## Acceptance bar (pinned)

- Every dense recipe verifies within the default `layout_retry` ladder, and
  the mechanism — not seed luck — is what makes it do so.
- Proof of generality is twofold, both required:
  1. **Holdout:** cpu4 is frozen now. No tuning to it, no reading its dumps to
     steer, until the final validation run. It must go green untouched.
  2. **Synthetics:** novel recipes by small mutation of each dense recipe
     (swap an op, add a gate, change fanout width). Same set measured before
     and after; post-change green rate must strictly exceed pre-change, per
     recipe family. No absolute floor — base rates (0–17%) are too low for one
     to mean anything.
- Pinned greens are recorded in a manifest (`recipe → seed, grow, blocks,
  hash`) with a one-command rebuild. Manifest only — no suite canary rebuilds
  a pinned dense green, because such a canary would go red spuriously every
  time the router improves (the pin moved, not a product bug).

## Evidence (why this, why now)

- Input nets run 130–390-cell marathons from a far bank to spread-out ports
  (alu1 OP1: 214, A/B: 166, CIN: 127; ctrl_decode OP0: ~291; loads span
  z=12..141, levers all at the south edge). Gate nets are short and local.
- `recipe.py` relays gate-net fanout with buffer `AND(x,x)` chains but
  excludes inputs (`:102`, `:156`), because — quote — "layout taps every
  input load with its own lever (zero-wire), so input relay would only add
  tiles." That premise died with the single-lever panel: zero-wire taps were
  deleted and inputs now ride the router at real cost (`layout.py:1384`).
  Inputs pay exactly the marathons fanout chains exist to end
  ("star-fed buffers would just move the marathon; chains end it").
  The exclusion is a leftover, not a decision.
- Inputs already ride first (`layout.py:1411` sorts them to the front); the
  shuffle only orders within groups. So the wall is not order — it is
  marathon geometry plus mutual blocking among 5–10 parallel long routes.

## §1 — Chaining policy

Delete `and a not in inputs` from the two chain gates (`recipe.py:102` and
`:156`). Everything else rides untouched: the 3+-load threshold, buffer
`AND(x,x)` tiles, ALAP adjacent parking, banded vs unbanded paths, constants
never chain, 2-load nets pass through.

Effect: every input feeding 3+ loads gains a buffer chain (alu1: all five —
A×4, B×6, OP1×4, OP0×3, CIN×3). Price: +1 AND tile per chained load (gates,
space, ticks); the marathon wire it replaces was also space.

## §2 — Panel-proof preservation

Reachability holds by construction (lever → B1 → B2 → … → each load is
linear). No new proof: the existing `panel-wire` canary walks the real net
graph across repeaters, and a chain is just more graph. Pass = promise holds;
fail = red build. Same gate, no new machinery.

Precision: chaining converts N marathons into **one long hop plus short
hops**, not zero long routes. B1 parks adjacent to the first load, so
lever→B1 is still bank-to-band; the chain hops are tile-pitch. For 6 loads
that is 1 marathon + 5 short hops, a 6× reduction in long-route pressure.

The load-bearing assumption: ALAP-adjacent parking absorbs ~20 new AND tiles
on alu1 locally. If the grid cannot fit them, that is a loud placement
failure, never silent damage.

## §3 — Validation

- **Holdout:** cpu4 (126 gates, 376 unrouted, 402s/seed — hardest and most
  structurally different). Frozen; run rarely and deliberately, never as an
  iteration loop.
- **Synthetics:** paired improvement per recipe family, as above.
- **Gates, every step:** four small builds byte-identical, all suite canaries
  green, micro1 still generates at 26s, `panel-wire` passes on every chained
  build. XCHECK stays on for any `forb` touch.
- **Kill-switches:** (1) a canary breaks outside an intended placement shift —
  stop, revert; (2) holdout fails *and* synthetics don't improve — hypothesis
  wrong, revert, wall stands as measured; (3) buffers overflow the grid past
  what a field-grow clears — price exceeds budget, stop.

## §4 — Scope boundaries

In scope: the two-gate deletion plus validation. Nothing else in `recipe.py`;
nothing in `layout.py`, `sim.py`, or the tiles unless a kill-switch forces a
design amendment, never a drive-by.

Explicitly out: task order (already correct); bank placement and corridors
(both falsified — middle-field walls); field shaping and edge trunks
(Approaches 2–3, revived only on new "no ground, not bad routes" evidence);
the Q-latch / one-circuit track (separate spec, micro1 reliability only);
cpu4-specific tuning of any kind (voids the holdout); absolute rate floors;
seed hunting (a green found by sweeping 24 seeds proves nothing — a green on
the first seeds after chaining proves the mechanism).

Done means: chained inputs land on all four development recipes with gates
green, panel-wire passing, small builds byte-identical, synthetics
paired-improved, and cpu4 green untouched. Anything less per the
kill-switches is a revert, which is a result, not a failure.
