# MORNING REPORT — 2026-10-05 night loop (GA lane: gates, builds, rig)

Repo `D:\redstone-mini`, branch `phase2-design`. Full trace in `LOG.md`; every
claim below is a run, not a plan. Gate command: `python scratch/coldstart.py`.

## 1. What now builds

| what | state | evidence |
|---|---|---|
| **add8 + 16 lever indicators** | **GREEN, 44,650 blocks** (was 46,518) | dual-engine PASS, lamp_pins 25/25, indicators 64/64 |
| add8 at bank pitch 2 | 44,634 blocks | dual PASS, 32 vectors, **0/610,816 dust**, 0/86,848 rep |
| add8 (default pitch 10) | 46,518 blocks | still exported and green |
| alu8 (8-bit ALU, add/sub/and/or/xor + ZNC) | **all 8 bands route** (first time) | recipe 0 mismatches; merge oscillates — not a working ALU |
| full coldstart | **15/15 green** | incl. hier_alu1 32/32 |

**The lever pitch question, answered with measurements.** The 10-block spacing
is load-bearing: the bank is a set of routing corridors, and the drop from each
row to its band crosses every row south of it, so the gap must hold a 5-cell
hop. Range measured, all smoke 4/4: **10 → 46,502 · 6 → 45,542 · 4 → 45,062 ·
3 → 44,822 · 2 → 44,634 · 1 → STITCH RED** (`wire B0 touches A0` — adjacent
lever cells share dust, so 1-apart is physically impossible, not just tight).

Pinned to **2** for add8 via `recipes/add8.bank` — **1,868 blocks smaller
(-4.0%)** than this morning, dual-engine clean. It is a *per-recipe pin*, not a
new default, because **alu4 goes red at pitch 2** (`no ground for A2`) while
alu1 stays green. That is exactly why it had to be measurable first.

## 2. Live on the 1.21 rig (`localhost:25566`)

**The tighter build is at `z+300`** (pitch 2, 50/50 sampled blocks present).
`/tp 2 65 320` — the 16 levers are now only 2 apart, and each has a sign and
an indicator lamp. The indicator lamps are **perfect live**: they track their
levers on every vector read.

The older 10-apart copy is still at `z 3..153` if you want to compare.

`add2opt` (3,730 blocks) is at z+400 and reads **2/2 vectors green on real
redstone** — still the only build with in-game proof of correctness. add8's sum
lamps do not read correctly in-game (some latch lit; a clear pass re-latches),
which is a **paste** problem, not a circuit one: at 44k the chunked setblock
paste is not reliably complete, and the leftover fragments hold lamps lit. The
build is bit-identical in sim and cmc.

## 3. What I could not deliver, and exactly why

**Sum-bit lamps at the lever row** (your request, three attempts):
1. Composer route — one buffer band per readout: **135,260 blocks**.
2. All readouts in band 0: 20,390 for that band, and the bank stitch dies.
3. `LAMP <name> AT <x> <z>` pin: **works**, and relative pins survive
   `finish_assembly`'s shrink-wrap (band-local (2..26,160) landed correctly
   north of the lever row). But every pinned lamp reads **dark** — a pinned
   lamp is a *placement* feature pretending to be an electrical one. Band 0
   composed 11,775 blocks and produced all 9 lamps at the pins, and the band
   sim gate still read `S1R`/`COUTR` False with the net high.

That last one is the real work: a remote lamp needs an electrical endpoint (a
repeater buffer whose output *is* the pinned cell, or a tap the router proves
powered), not a bare dust cell. It is router work, not a recipe change.
Reverted every attempt rather than bank unproven code.

**alu8's merge** oscillates: churn 52,985, loop torches listed, max_gap 205,950.
The 8 long carry stitches in a 206k field make a loop the per-stitch guards
miss. Band routing is solved; the merge is not.

**add8 at 46k is not established in-game.** It pasted 60/60 present but reads
0/4 — the failing lamps have air on two sides, i.e. paste debris from partial
pastes, not a physics result. Do not cite add8 as hardware-verified. Only
add2opt has that proof.

## 4. New things that work

- `scratch/lamp_pin_check.py` — **now a gate** (16 total) and **negative
  tested**: a ghost pin prints MISSING and exits 1. It earns its slot because
  the rig reads lamps by looking the pin up in the block list, so a lamp
  elsewhere reports dark for a lit lamp.
- `export.py` gains `sign_snbt()` / `label_lines()`; `export_mcfunction(...,
  io=)` bakes 41 labels into any build for **zero redstone**. `io=None`
  reproduces the old file byte for byte. The 1.21 syntax is in the docstring,
  each fact bought with a probe.
- `scratch/lever_lamps.py` — 16 indicator lamps for **16 blocks** (sim 64/64,
  dual PASS, live 16/16).
- Survey: 22 downloaded redstone computers censused (`survey/REPORT.md`),
  `scratch/census_world.py` reads Java *and* Bedrock worlds.

## 5. What I need from you

1. Nothing is blocked on a secret. The three open items above need **time**,
   not access.
2. **Paste `build_add8.schem`** if you want it in your own world — it has the
   indicators and labels, and it is the one artifact here that is not proven
   in-game.
3. Rule on the two physics calls I refuse to make unilaterally: **glass
   down-flow** (sim 0 vs cmc 13; fix mapped to `sim.py:405` + simvec mirror)
   and the **non-pin lever** (needs a directional source in both engines).

## 6. Traps that cost me time, so you don't re-pay them

- An RCON `no response` means the server was **busy** — the command ran. A
  repaste reporting 3 errors still left 60/60 blocks present.
- `setblock` on an existing **lever**, or on stone that is already stone,
  returns "Could not set the block". Clear to air first, then place.
- `forceload` caps at **256 chunks per call**; add8 spans 2,394.
- A probe that samples the wrong stride reports **absence**. I "lost" 16
  indicators and 16 signs that way before checking the actual coordinates.
- `io["lamps"]` is keyed by **cell → name**, not name → cell. Reading it
  backwards cost me a whole wrong conclusion.
