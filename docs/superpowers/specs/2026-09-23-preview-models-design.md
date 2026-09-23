# Preview models: floor, lever sound, torch mount, repeater — design

## Goal
Make `build.html` model-faithful with geometry only (no new textures, sounds,
or deps, offline-safe): grounded floor, clicking levers, block-mounted
redstone torches, and repeaters with facing, delay stages, and on/off states.

## Floor (export.py:105)
- Move the ground plane y from `-0.5` to `0.46`. Derivation, not eyeballed:
  cubes are `.92` per side centered on integer coords (half-size `0.46`);
  y=1 component bottoms sit at `0.54`; the plane stands in for excluded y=0
  stone cubes whose tops are at `0.46`. One-line change.

## Lever sound (export.py:192-193 click handler)
- WebAudio oscillator blip on toggle: higher pitch on on, lower on off.
  ~5 lines, no audio files, fires only on real lever hits (same guard as the
  state flip) so orbit-drags stay silent.

## Torch mount + look (export.py:144-156)
- Parse `facing=` from the block id; inspect the mount-side neighbor cell in
  the shipped block data. Mount block present (cobble/stone) = wall pose
  hugging that face; absent = upright ground pose on the top face.
- Redstone read: dark-red stick, red head, dim when off. Existing `torchHeads`
  recolor path stays, only the base colors change.

## Repeater with stages + on/off (sim.py collect, export_html data + JS)
- Geometry, box-built: flat slab base, 2 torch dots along the facing axis, one
  slider nub. Assembly rotated to parsed `facing=` (preview ignores facing today).
- Stages: slider nub offset along the body by delay stage 1-4, parsed from the
  block id in Python, shipped per-instance in data entries (same precedent as
  the dust `arms` bitmask).
- On/off: sim `collect` gains an `r` map (repeater on/off per vector, same
  shape as torch `t` map); `applyState` recolors each repeater's dots from it
  with per-repeater materials (same lesson as the `glowM` per-torch split).
- Touch points: `sim.py` collect only; `export_html` data + JS only. No caller
  or layout changes.

## Testing
- `node --check` on the template; existing demo + 3-example gate green.
- Asserts: every repeater data entry carries facing/delay; every collected
  vector carries an `r` entry per repeater; `python sim.py` self-check stays green.
