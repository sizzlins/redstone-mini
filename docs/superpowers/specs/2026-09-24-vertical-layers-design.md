# Vertical layers pilot — design

Approved: 2026-09-24. Status: spec, not yet implemented.

## Goal

Prove stacked wires work: a build is a stack of flat layers (chip-style),
each routed by today's untouched 2D machinery, joined by vias. Pilot ends
at a sim-proven crossover demo; the placer still works flat.

## 1. Sim learns y (the only physics change)

- Dust, wire, block, torch, lever, lamp, repeater cells carry levels.
  Adjacency gains the vertical neighbor (same x,z, y±1).
- Rules (all from minecraft.wiki research, Java Edition):
  - Wire on top of, or pointing at, a conductive block gives it weak power.
  - Weakly powered blocks never power adjacent wire (repeaters,
    comparators, mechanism parts only).
  - Wire links to adjacent wire one level higher/lower, unless a
    conductive block sits above the lower wire (lid rule).
  - Diagonal-vertical links through non-conductive blocks: deferred
    (unneeded for the pilot).
- Flat builds must simulate bit-identically to today (no y present =
  old code path results).

## 2. Acceptance

- Unit asserts for the three researched cases: stacked dust-block-dust
  has no link; step-up (wire beside block, wire on top) links; lid on the
  lower wire blocks the up-link.
- Crossover demo (hand-placed blocks, `__main__` asserts + a demo file):
  wire A runs level 1; wire B climbs a block bridge over A and descends.
  Sim proves independence both ways (drive A, B quiet; drive B, A quiet)
  and correct delivery (each output follows its own input).
- 3D preview renders y=2 blocks (verify; expected free from coordinates).

## 3. Out of scope

Placer routing upward by itself, automatic layer distribution, slabs /
stairs / glass subtleties, comparators / pistons / hoppers, timing changes
beyond what levels imply. Each is a separate spec when a build needs it.
