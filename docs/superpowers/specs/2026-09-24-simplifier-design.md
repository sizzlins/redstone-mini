# Simplifier + keep-fastest (A+B) — design

Approved: 2026-09-24. Status: spec, not yet implemented.

## Goal

Given any unbanded recipe, ship the fastest verified Minecraft build for it,
with block count as tiebreak. Two independent pieces; neither touches
redstone physics, placement tiles, or the router.

## 1. Score: (ticks, blocks), lexicographic

- `ticks` = worst-case settling ticks over the sim's input vectors.
- `blocks` = `len(blocks)`.
- Lower tuple wins. Rationale (user): fastest circuit first, footprint second.

`sim_verify` must report worst-case ticks for every build size. Today it only
collects per-vector ticks when `collect and len(combos) <= 16`; bigger builds
return `states=None` with no tick data. Change: always track the max
settling tick across simulated vectors and return it alongside states.
Callers (`layout_retry`, `__main__` self-check) updated to the new return.

## 2. Minimizer: Quine-McCluskey on the truth table

- Input: unbanded recipe with AND/OR/XOR/NOT gates (constants "0"/"1"
  allowed in args; they are constants, not table variables).
- Method: enumerate all 2^n combos over `recipe["inputs"]` via `eval_net`;
  prime implicants; minimal cover (exact brute force — tractable under the
  input cap below).
- Output: equivalent gates using only AND/OR/NOT (two-level SOP + NOTs for
  negated literals), same inputs/outputs. The existing expander, placer,
  router, and sim consume it unchanged.
- Limits (deliberate, marked `ponytail:` in code):
  - More than 10 inputs: skip minimizing, pass the recipe through untouched
    (tables stay ≤1024 rows, instant).
  - Banded recipes (adder datapath): excluded entirely. Band tags are
    load-bearing placement info; the minimizer must not restructure them.
  - Multi-output: each output minimized independently; term sharing across
    outputs is a later optimization, not this spec.

## 3. Selector: keep the fastest verified

`layout_retry(verify=True)` already routes up to `tries` layouts per grow and
sim-checks each. Change: remember the lowest-scoring verified build per the
section-1 score and return it after all tries, instead of returning the first
verified build. Non-verify path unchanged (first success returns immediately).
Error behavior unchanged: last error raised when nothing verifies; grow loop
unchanged. Cost: all tries run their sim check instead of stopping at the
first pass — measured negligible on small builds (demo ≈0.3s total);
re-measure at implementation time and note the number here.

## 4. Testing

- Equivalence (exact, free): minimized recipe must equal the original on
  every truth-table row, for the demo collapser and a randomized sweep.
- Collapser demo: `(a AND b) OR (a AND NOT b)` → `a` (one assert-based
  self-check, no frameworks).
- Green gate unchanged: demo, and, xor, 2gates, `sim.py` self-checks,
  `serve.py --check` — same commands. Block counts re-recorded at
  implementation time; under the section-1 score a count may rise only if
  ticks fall, never otherwise.
- Out of scope: new block types (comparators, pistons, hoppers — project C),
  banded/adder8 changes, route-order or placement changes.
