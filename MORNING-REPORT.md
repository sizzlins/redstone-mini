# MORNING REPORT — 2026-10-05 night loop (GA lane: gates, builds, rig)

Repo `D:\redstone-mini`, branch `phase2-design`. Full trace in `LOG.md`; every
claim below is a run, not a plan. Gate command: `python scratch/coldstart.py`.

## 1. What now builds

| what | state | evidence |
|---|---|---|
| **add8 + 16 lever indicators** | **GREEN LIVE, 44,650 blocks** | **19/19 vectors in real Minecraft**, overflow included |
| add8 at bank pitch 2 | 44,634 blocks | dual PASS, 32 vectors, **0/610,816 dust** |
| add8 (default pitch 10) | 46,518 blocks | still exported and green |
| alu8 (8-bit ALU, add/sub/and/or/xor + ZNC) | **all 8 bands route** (first time) | recipe 0 mismatches; merge oscillates — not a working ALU |
| full coldstart | **15/15 green** | incl. hier_alu1 32/32 |

### The 8-bit adder is proven on real redstone

```
LIVE VERDICT: 19/19 vectors green
```

Every power of two, `0x0F`, `0xF0`, `0x55`, `0xAA`, `0x1F`, `0x7F`, `0x8F`,
`0xFE`, and **`0xFF` → 255 with the carry lamp lit**. All 16 indicators correct
on every vector.

It is at **z 803..973** (`/tp 2 68 820`). Pasted alone. Which brings us to the
actual finding of the night:

**Every in-game failure until now was my own pastes overlapping.** The rig's
datapack still had every function ever pasted, with coordinates. `build1..4` are
the same add8 pasted four times at z offsets 0/0/1/2, stacked on itself. And
add2opt (z 404..483) sat *inside* tonight's add8 (z 303..473) — the cells that
first disagreed with sim were at x 39..42, exactly inside add2opt's box. The
circuit was never wrong; I was measuring the union of two builds.

Two of my tools made it worse, both now fixed or replaced:
- `execute if block <full wire NBT>` always fails, because the game recalculates
  wire connection state on placement. Compare the **type**. This produced a fake
  "the paste did not land".
- `rig_read` never read the levers back and settled too briefly, so a slow carry
  chain read as a wrong bit. `scratch/live_check.py` replaces it: reads every
  lever back, waits 20s, checks 16 indicators + 9 sum lamps.

**The lever pitch question, answered with measurements.** The 10-block spacing
is load-bearing: the bank is a set of routing corridors, and the drop from each
row to its band crosses every row south of it, so the gap must hold a 5-cell
hop. Range measured, all smoke 4/4: **10 → 46,502 · 6 → 45,542 · 4 → 45,062 ·
3 → 44,822 · 2 → 44,634 · 1 → STITCH RED** (`wire B0 touches A0` — adjacent
lever cells share dust, so 1-apart is physically impossible, not just tight).

Pinned to **2** for add8 via `recipes/add8.bank` — **1,868 blocks smaller
(-4.0%)** than this morning, and now proven live at that size. It is a
*per-recipe pin*, not a new default, because **alu4 goes red at pitch 2**
(`no ground for A2`) while alu1 stays green. That is exactly why it had to be
measurable first.

## 2. Live on the 1.21 rig (`localhost:25566`)

**One build per region. Do not paste over these.**

| region | what | state |
|---|---|---|
| **z 803..973** | **add8 pitch-2 + 16 indicators, 44,650 blocks** | **19/19 live green** — `/tp 2 68 820` |
| z 404..483 | add2opt, 3,730 blocks | re-pasted, intact (25/25), historically 2/2 |
| z 303..403 | tonight's first add8 paste, orphaned | ignore |
| z 3..293 | four-deep stale add8 debris | **ignore** — four copies stacked |

Use `scratch/live_check.py` against z+800. It reads every lever back, waits 20s,
and checks 16 indicators + 9 sum lamps. It is the harness to trust; `rig_read`
sets levers and reads immediately, which makes a slow carry chain look broken.

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

**add8 at 46k is no longer an open question** — it was never a physics result.
The 0/4 came from four stacked copies of itself plus add2opt pasted inside it.
Pasted alone it is 19/19. Resolved; see §1.

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
  dual PASS, **live correct on all 19 vectors**).
- `scratch/live_check.py` — the live harness: lever readback, 20s settle,
  indicators + sum lamps. Replaces `rig_read` for anything big.
- Survey: 22 downloaded redstone computers censused (`survey/REPORT.md`),
  `scratch/census_world.py` reads Java *and* Bedrock worlds.

## 5. What I need from you

1. Nothing is blocked on a secret. The open items above need **time**, not
   access.
2. **Paste `build_add8.schem`** if you want it in your own world — it has the
   indicators and labels, and it is bit-identical to the build that reads 19/19
   on the rig.
3. Rule on the two physics calls I refuse to make unilaterally: **glass
   down-flow** (sim 0 vs cmc 13; fix mapped to `sim.py:405` + simvec mirror)
   and the **non-pin lever** (needs a directional source in both engines).

## 6. Traps that cost me time, so you don't re-pay them

- **Check the paste log before you measure.** The rig's datapack keeps every
  function ever pasted. Reading it is how the whole night's red herring died:
  `build1..4` were one add8 pasted four times, and add2opt was sitting inside
  tonight's add8. Both were mine.
- Never compare a **wire's full NBT** with `execute if block` — the game
  recalculates `east/west/south/north/power` on placement, so it always says
  false. Compare the **type**.
- A read that does not **read the levers back** cannot distinguish "wrong bit"
  from "lever did not move". `live_check.py` does.
- An RCON `no response` means the server was **busy** — the command ran. A
  repaste reporting 3 errors still left 60/60 blocks present.
- `setblock` on an existing **lever**, or on stone that is already stone,
  returns "Could not set the block". Clear to air first, then place.
- `forceload` caps at **256 chunks per call**; add8 spans 2,394.
- A probe that samples the wrong stride reports **absence**. I "lost" 16
  indicators and 16 signs that way before checking the actual coordinates.
- `io["lamps"]` is keyed by **cell → name**, not name → cell. Reading it
  backwards cost me a whole wrong conclusion.
- Truncating block names to 7 chars makes `redstone_wire` and `redstone_lamp`
  print identically. That briefly convinced me a lamp was a wire.
