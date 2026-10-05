# MORNING REPORT — 2026-10-05 night loop (GA lane: gates, builds, rig)

Repo `D:\redstone-mini`, branch `phase2-design`. Full trace in `LOG.md`; every
claim below is a run, not a plan. Gate command: `python scratch/coldstart.py`.

## 1. What now builds

| what | state | evidence |
|---|---|---|
| **add8 + 16 lever indicators** | **GREEN, 46,518 blocks** | dual-engine PASS (sim n=8, cmc n=8), lamp_pins 25/25, live 16/16 |
| add8 | 46,502 blocks, exported | `.schem` / `.mcfunction` / `.html`, now with 41 labels baked in |
| alu8 (8-bit ALU, add/sub/and/or/xor + ZNC) | **all 8 bands route** (first time) | recipe 0 mismatches; merge oscillates — not a working ALU |
| full coldstart | **15/15 green** | incl. hier_alu1 32/32 |

## 2. Live on the 1.21 rig (`localhost:25566`)

The add8 world is up and standing at `y=65`, levers at `x=3, z=3..153`.
`/tp 2 65 78` and look: 16 levers, a sign naming each, and an indicator lamp
that lights with its own lever. Verified this session: **16/16 levers,
16/16 signs, 16/16 indicator lamps**, and toggling gives 16/16 lit / 0/16 off /
A0-alone lights exactly one.

`add2opt` (3,730 blocks) is also on the rig at z+400 and reads **2/2 vectors
green on real redstone** — the only build with in-game proof of correctness.

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
