# Repeater delay sim (tick sim, settled-lamp rule) — design

## Goal
Recreate vanilla Minecraft repeater delays/stages in `sim.py`: torch = 1 tick,
repeater = its `delay=1..4` stage from the block id. Pass = settled lamps match
logic. Flicker before settling is allowed (vanilla behavior).

## Timing model
- 1 tick = 1 redstone tick. Dust/cobble/lever/redstone-block apply instantly
  within the tick. Torch output flips 1 tick after its block changes. Repeater
  output flips N ticks after its input changes (N from
  `minecraft:repeater[…,delay=N]`, default 1).
- Each vector holds inputs steady from tick 0; the event queue runs forward
  (due events first, same-tick dust closure). Today's instant sim is this model
  with all delays at 0.

## Pass rule + limits
- PASS when lamps equal `eval_net` with no events remaining, for every tested
  vector. Intermediate wrong values are allowed, not failures.
- FAIL (loud, current style) on non-settling: events remain past 500 ticks or
  20000 micro-steps, reported as `SIM MISMATCH` with the live map.
- `collect=True` keeps `{inputs, levers, lamps, vectors:{w,t,lamps,ticks}}`
  (final settled states; `ticks` stored inside each vector entry) for the preview.

## Touch points
- `sim.py` only: parse `repdelay{}`, tick-loop `run(vec)`. Signatures of
  `sim_verify`/`layout_retry` unchanged; `layout.py`, `export.py`,
  `redstone_mini.py`, `build.html` JS unchanged.

## Testing
- One assert check (no framework): lever → repeater(delay 4) → lamp settles to
  1 after exactly 4 ticks; staggered-arrival XOR settles right (flicker-allowed
  documented). Existing `demo()`, 3 example recipes, and `build.html` shape
  stay green.
