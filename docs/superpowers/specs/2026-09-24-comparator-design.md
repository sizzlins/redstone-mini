# Comparator pilot — design

Approved: 2026-09-24. Status: spec, not yet implemented.

## Goal

Analog computation for real: comparator physics in the sim, a rendered
model, and one hand-found XOR tile. Acceptance: `example_xor.txt` builds
at ~60 blocks or fewer (from 482), all vectors green, full gate green.

## 1. Sim: analog comparator (researched, Java Edition)

- Parse `minecraft:repeater`-style block ids with facing + delay-equivalent:
  `minecraft:comparator[facing=<dir>,mode=compare|subtract]`.
- Inputs: rear + both sides, read as signal LEVELS (dust levels already
  tracked 0-15 with decay). Side inputs count only from STRONGLY powering
  sources (repeater/comparator output, lever, redstone block, torch,
  strongly powered block) — dust side-feeds do not register (wiki).
- Compare: output = rear iff neither side exceeds rear, else 0.
  Subtract: output = max(rear − max(left, right), 0).
  No powered sides: output = rear (diode/repeater behavior).
- Delay 2 game ticks (= 1 redstone tick, same as repeater delay-1).
- Known limits (documented, out of scope): repeater locking by comparator
  sides, 2-game-tick pulse quirks, containers (no inventories exist).

## 2. Export: repeater-style model

Base slab + dots from existing primitives, facing + mode from block state,
textures from the asset pack. No new art.

## 3. XOR tile: found in sim, not drawn

Seed 2-3 candidates from the reference structure, sim-verify the XOR truth
table over levels (not just on/off — subtraction lives in strengths), keep
the smallest. Bounded: three strikes, then stop and report. Recipe side
needs nothing (XOR is already a primitive). Tile uses existing placement
primitives (solids, dust stubs, rings, footprint, ports).

## 4. Acceptance

- `example_xor.txt` ≤ ~60 blocks, sim-verified all vectors.
- Green gate unchanged: demo/and/2gates/latch/sim/serve/recipe.
- Out of scope: containers/barrels/hoppers, locking, general comparator
  routing (any-net → comparator), pistons.
