# Phase 1 — Standard tiles (port grid + lamp discipline)

Status: planned. Predecessor: none. Successor: Phase 2 (bus routing).

## Goal
Give every gate tile a documented port grid (west-in/east-out where the
physics allows) without respinning any proven tile. Phase 2 buses need
aligned, predictable ports — not new geometry.

## Context
Audit of current tile ports against west-in/east-out:

| Tile | Inputs | Output | Verdict |
|---|---|---|---|
| AND | west (row), west (row+3) | east (row+1) | conforms, no change |
| NOT | west | east, same row | conforms, no change |
| NOR | west + north | east | exception: 1-wide block, both sides taken; north stays |
| LATCH | west + west | west | exception: adjacent-block design faces west; mirroring is respin risk |
| XOR | east + east | west | exception: comparator facing; mirroring is respin risk |
| OR | any side (point cell) | at cell | exempt by nature |

Per-family pitch recorded alongside (NOT 7, AND 11, LATCH 15).

## Changes
1. This table + pitches committed as the spec (this file is it).
2. Lamp placement prefers east-first (`(1,0),(0,1),(0,-1),(-1,0)` instead
   of west-first): outputs must never face backward into producers.
   One line in `layout.py`.
3. Self-check asserts: every tile's ports match this table (fails on drift).

## Non-goals
No tile respins. No router changes. No new components. No physics changes.

## Verification gate
- Suite green: `recipe.py`, `serve.py --check`, `redstone_mini.py`,
  `sim.py`, examples, `latch_sr.txt`.
- 4-gate latch: 6/6 seeds + set/hold/reset/hold sequence.
- micro1: full `layout_retry(verify=True)` clean.
- Per-tile truth tables unchanged (sim-guarded).

## Risks
- NOR/LATCH/XOR exceptions constrain bus-lane design in Phase 2 (documented here so Phase 2 plans around them, not through them).
