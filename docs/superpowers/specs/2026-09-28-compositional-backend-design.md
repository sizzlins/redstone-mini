# Compositional second backend (2026-09-28)

Status: design (proposed). Goal: every dense recipe generates deterministically
by construction, verified through the unchanged sim gate — mechanism, not seed
luck. Supersedes nothing. It reuses the proof standard of the chaining spec
(holdout cpu4 + synthetic paired floor) and absorbs approach 1 (tile-reserve
tightening) into the tile-hoist step. Approaches 2–3 stay open; this spec neither
needs nor blocks them.

## Acceptance bar (pinned)

- Every dense recipe (micro1, alu1, alu4, ctrl_decode, cpu4) verifies within
  the default `layout_retry` ladder, and the composer — not seed luck — is
  what makes it do so. No seeds involved: the composer is deterministic.
- Proof of generality is twofold, both required (same standard as
  `2026-09-27-input-fanout-chaining-design.md`):
  1. **Holdout:** cpu4 stays frozen until final validation, then goes green
     untouched.
  2. **Synthetics:** paired pre/post green-rate improvement per recipe family.
- The sim's vanilla contract and all suite gates are frozen. No `.txt` recipe
  changes, no export changes. Block count is reported, never optimized.

## Evidence (why this, why now)

- Our wall is ground-existence, not length/order/placement (handoff §§What
  failed/What next): three mechanisms died by relocation, growing the field is
  falsified for alu1, a 4-cell hop fails at 0.15s. Nothing in the tree creates
  ground.
- Upstream RHDL (`D:\redstone_description_language`, Zig 0.15.1, built and run
  locally) never shares ground: recursive tiles sized by subtree
  (`dl.zig:97-133`), children stacked in Z (`construction.zig:804-853`),
  outputs spread in X+10 (`:781`), collisions bridged *over* in wool
  (`:1038-1091`), repeaters every 5 by construction (`:13`). Measured on
  flattened translations of our own recipes (equivalence proven vs
  `recipe.eval_net` on all vectors: 32/32 alu1, 8/8 ctrl_decode, 1024/1024
  alu4): alu1 3485 blocks in 0.2s, ctrl_decode 1440 in 0.0s, alu4 24396 in
  0.2s, byte-identical across runs, 7–9% of blocks elevated.
- Mirror image: their tiles are the weak part (unverified, `panic` on nor/nand
  at `construction.zig:1022`, no sequential logic at all — micro1/cpu4 cannot
  enter their pipeline). Our tiles are the strong part (`latch_sr` green, 4/4
  small-build hashes). So: our tiles + our sim, their placement discipline.
  The composer covers sequential builds, which upstream structurally cannot.

## §1 — Tile hoist (mechanical, zero behavior change)

The tiles live as closures inside `layout()` (`stamp_wire:718`,
`stamp_cobble:918`, `stamp_torch:922`, `stamp_and:926`, LATCH block
`1140-1203`). Hoist each to an importable builder taking explicit geometry +
nets, returning blocks, with `layout()` calling the same builders. During the
hoist only, tighten each `footprint` reserve toward what `spot_free` actually
checks (11×9 → 9×7 on AND is the known instance; measure per tile) — approved
approach 1 riding along free, each tightening gated on its own canary.

Gate: 4/4 small-build hashes byte-identical and full suite green after every
hoisted tile. Any hash move or red canary stops the line — the hoist is
reverted, the composer is not started.

## §2 — Composer (new module, one job)

`compose.py`: recipe DAG → blocks. No search, no seeds, no retry.

- **Placement:** topological bands in Z (loads above drivers, mirroring
  `connect`'s shift-by-length), outputs spread in X with fixed streets sized
  off the widest tile plus wire pitch (mirroring `combine`'s width+10). Per-tile padding from subtree size (their
  `paddingNecessary` idea, our numbers — sized off measured tile extents, not
  copied constants). LATCH places as a placed tile like any gate; its
  cross-coupled pair is internal, so composition cannot break it.
- **Wiring:** one L-wire (Z then X) per connection, repeater every 14 cells by
  construction (the booster cover's existing per-segment rule).
  On collision, bridge over first using the existing bridge height/block rules;
  there is no search-around fallback inside the composer — a placement that
  cannot bridge is a loud failure, never a silent detour.
- **Inputs:** one bus per input on the field edge at fixed pitch (their
  `translateToEntity:1148-1173`), each load tapped short. This deletes the
  130–390-cell bank marathons by construction.
- **Scope limit:** the composer emits blocks + io in the exact shapes
  `sim_verify` and `export` already consume. It knows nothing about physics.

## §3 — Ladder integration (no regression by construction)

`layout_retry` tries compose first (seconds, deterministic), gates the result
through the unchanged `sim_verify`, and falls back to the maze router on any
failure. The maze path is untouched, so every currently-green seed stays
green; a composer that produces nothing sim-green costs only its own runtime
and changes no verdict. First green ships; block count is logged, not scored.

## §4 — Validation and kill-switch

- Gates every step: full suite, 4/4 hashes (hoist phase), micro1 still
  generates ≤60s via either path, `serve --check` green.
- Kill-switch (fires in order, each reverts only its own phase): (a) any hash
  move during §1 → revert hoist; (b) composer sim-green on 0 dense recipes
  after §2 lands → revert composer calls, keep the hoist (it still paid for
  approach 1); (c) composer greens some but holdout cpu4 fails at final
  validation → ship combinational wins, sequential tiles become their own spec.
- Out of scope: router deletion (a later deletion PR once sequential
  compositional tiles are proven — not this spec), tile electrical redesign
  beyond reserve tightening, sim/export/recipe changes, pinned-seed manifests.

## Provenance

Translator + NBT inspector used for the measurements are scratch
(`C:\Users\LOQ\AppData\Local\Temp\opencode\translate.py`,
`inspect_nbt.py`), intentionally uncommitted. Upstream checkout with the two
Windows-compat fixes is `D:\redstone_description_language` (uncommitted,
`git diff --stat`: 2 files, +11/−5).
