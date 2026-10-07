# Handoff — redstone-mini, branch `phase2-design`

Written by the gates + builds lane, 2026-10-06 morning. Supersedes
`notes/handoff-*.md` and `notes/handoff.md` (those are earlier snapshots from
the other lanes; this file is the current one).

**Read this first if you touch the Minecraft rig:** the single most expensive
waste in this session was three hours chasing a "broken build" that was fine.
Cause and fix are in §4.

---

## 1. Goal

Standing project goal: every recipe generates, verifies, and exports with
evidence that survives an independent implementation (sim AND cmc, per-cell).

The concrete operator request driving this session, verbatim:

> take the wire that powers on the lamp, and create new wires that take the
> signal all the way to where the levers (area) are, maybe put them directly
> above the levers and at the end, like a platform separating them. make the
> lamp one block each separated from each other, add lamps powered by said
> wire.
>
> ...and also add signs to the levers and lamps.

So three deliverables: **sum-bit lamps at the lever row**, **signs**, and the
levers **1 block apart instead of 9**. Status of each is in §2. Signs and
spacing are done. The bank lamps are not, and §5 says exactly why.

---

## 2. Current state

| what | state | evidence |
|---|---|---|
| **add8 + 16 lever indicators** | **GREEN LIVE, 44,650 blocks** | **19/19 vectors in real Minecraft**, overflow included |
| full coldstart | **16/16 green** | new `pin_lamp` gate added |
| lever spacing | **DONE, permanent** | pitch ladder: alu1 settles at 2, alu4 at 10 |
| signs | **DONE in the exports** | 50 labels in `build_add8bank.*`; NOT pasted on the rig |
| sum lamps at lever row | **DONE, 9/9 green** | bank platform at merge x=-8, z=-99..-83 (block x=0, z=5..21): bank_lamp_check 0 wrong 16v; verify2 DUAL PASS sim+cmc 64v, 0/2M cells differ; verify_par 65536/65536; `build_add8bank.*` exported (75,599 blocks) |
| alu8 | all 8 bands route (first time) | merge oscillates: churn 52,985, max_gap 205,950 |
| cpu4 | red by inheritance, untouched | other lane |

### Live rig — ONE BUILD PER REGION

| region | what | state |
|---|---|---|
| **z 803..973** | **add8 pitch-2 + 16 indicators** | **19/19 green** — `/tp 2 68 818` |
| **z 1103..1503** | **add8 + 9 bank lamps + 16 indicators + 50 signs (75,599 blocks)** | **19/19 vectors green live** (sums + bank + indicators, lever readback) — `/tp 2 70 1118` |
| z 404..483 | add2opt | re-pasted, intact |
| z 303..403 | orphaned first add8 paste | ignore |
| z 3..293 | four-deep stale add8 debris | **ignore** — four copies stacked |

5,355 chunks are force-loaded, so the build keeps ticking with no player
nearby. It is pure dust/repeaters/comparators — no pistons, hoppers or
observers — so there is no tick-dependent failure mode.

Harness to trust: `scratch/live_check.py` (reads every lever back, 20s settle,
checks 16 indicators + 9 sum lamps). **Do not use `rig_read.py` for anything
big** — it never reads the levers back and settles too briefly, so a slow carry
chain reads as a wrong bit. For bank builds the settle must cover the ~2000-cell
bank runs (~250 boosters ≈ 25s+ transit alone): poll-to-stable (two consecutive
correct reads), not a fixed sleep. Lever sets must clear to air first
(`setblock` on an existing lever returns "Could not set the block").
Single-shot RCON reads FLIP under load — retry every read 3x and treat only
persistent failure as real; one persistent RCON connection per script (a
connection per command made 18k+ server threads and killed the server 4x).

---

## 3. What changed

18 commits, `e25ef05..6a12dc6`. The three that matter:

**`d57af28` — add8 proven on real redstone, and the red herring killed.**
19/19 vectors green including `0xFF` → 255 with COUT lit, all 16 indicators
correct. Every prior in-game failure was **my own pastes overlapping**:
`build1..4` were one add8 pasted four times at z offsets 0/0/1/2, and add2opt
(z 404..483) sat *inside* tonight's add8 (z 303..473).

**`6e3b227` — `LAMP <name> AT <x> <z>` was a placement feature pretending to be
an electrical one.** It stamped a lamp and one dust tap and routed *nothing* to
it, so every pinned lamp read dark. `build_netspec` never gave the pin a load.
The trap: the ordering is opposite in the two callers — `compose.py` builds
netspec at **1124** and calls `tap_lamps` at **1207**, both *before* routing, so
the pin has to reach netspec through the **recipe**, not through the recs the
tap stamps; `layout.py` builds netspec at 1387 and never calls `tap_lamps` at
all. A fix in the `OUT` branch compiles, runs, and achieves nothing. Fix is
three small pieces: `core.pin_tap_cell` (one cell rule, imported by both so goal
and tap cannot drift), a load registered per pinned output in
`build_netspec`, and `tiles._tap_pinned` using that cell. Band S0 pinned to the
lever row: **1,054 blocks** vs 135,260 for the naive "one buffer band per
readout" route.

**`637501e` — lever spacing is now a permanent ladder.** `hier_verify.py` walks
pitch **2 → 3 → 4 → 6 → 10**, and only a green VERIFY settles it. Measured:
alu1 settles at 2; alu4 goes 2 (stitch red) → 3 → 4 → 6 (all verify red) → 10
(1024/1024 green). Only the stitch re-runs per rung — the bank is laid during
the merge, not per band, so the band cache is valid at every rung.

Also: `f7e5b99` per-recipe pitch pin (`recipes/add8.bank`, 46,502 → 44,634
blocks, −1,868), `bc1a303` `lamp_pins` gate, `1ff2227` signs in exports,
`7431a27` alu8 NAND rewrite making all 8 bands route, `7d8b220` + `6a12dc6`
the bank-lamp work below.

---

## 4. What failed, and the traps

**Three hours lost to overlapping pastes.** The rig's datapack still holds every
function ever pasted, with coordinates. Reading it is how the night's red
herring died. **Check the paste log before believing any live measurement.**

**Four of my own claims were wrong, each falsified by a test I wrote to try to
break it.** Do not let these come back:

- ~~"the driver is sealed by its own 3×3 ring"~~ — **wrong.** S0 owns 0 ring
  cells; the driver routes 24 blocks north, 16 south, 8 east. `_walk`'s "no
  ground" fires when it cannot *escape a seal*, and a solid pair 3 cells west
  looks identical from inside. My first probe only ran west into a wall.
- ~~"the router tops out near 300 cells"~~ — **wrong.** COUT routed 2,049 cells
  from x=1997. The real ceiling is *leg length* ~500, not field width.
- ~~"escalate the pitch ladder on stitch exit code"~~ — **wrong**, and it turned
  a green alu4 gate red: alu4 *stitches* fine at pitch 3 then verifies red.
- ~~"the bank lamps read dark"~~ — **wrong**, from a broken harness. My ad-hoc
  `_run_vec` call reported every lamp dark *including the 16 indicators that
  were provably fine*. `verify2.py` is the authoritative path.

**Bank lamps: 7/9 route, then the build FAILS.** Under the one pattern that
carries the bank's own 16 inputs across this field (pre-stamp long rows, route
only short drops — `compose.py:3377`), all 9 rows stamp and 7 nets route in 32
seconds. Then:

```
SIM : ok=False   CMC : ok=False      DUAL-ENGINE VERDICT: FAIL
```

**The obstruction is structural: the lever latitude band (z=3..33) is where the
composer already routes the bank's 16 input rows east.** The strip you want lamps
in and the corridor the adder needs are the same ground. Not a router problem.

Three more traps in that work:

- **`lwire` MUTATES the field (repeaters, supports) even when it finally
  raises.** Any retry loop starts from debris — an adaptive "try the next lamp
  latitude" loop scored 1/9 for that reason alone. One attempt per net.
- **The first net to use the shared drop corridor owns it.** COUT-first scored
  1/9; westernmost-first scored 7/9.
- **z=23 and z=25 can never carry a wire** — they sit *beside* the z=24 trunk,
  and `stamp_wire` refuses a wire with a foreign net beside it.

**General redstone traps on this rig**, each bought with time:

- Never compare a wire's full NBT with `execute if block` — the game
  recalculates `east/west/south/north/power` on placement, so it always says
  false. Compare the **type**.
- An RCON `no response` means the server was **busy** — the command ran.
- `setblock` on an existing lever/stone returns "Could not set the block".
  Clear to air first.
- `forceload` caps at 256 chunks per call; add8 spans 2,394.
- Truncating block names to 7 chars makes `redstone_wire` and `redstone_lamp`
  print identically — briefly convinced me a lamp was a wire.
- `io["lamps"]` is keyed **cell → name**, not name → cell. Reading it backwards
  cost a whole wrong conclusion.

**Unresolved, needs a human call:** glass down-flow (sim 0 vs cmc 13; fix mapped
to `sim.py:405`, NOT applied unilaterally) and the non-pin lever (needs a
directional source in both engines).

---

## 5. What we should do next

**1. Bank lamps: DONE 2026-10-06, west-margin platform.** The "structural
obstruction" (lamp strip IS the input corridor) is RETRACTED: it mixed
block-frame lever latitudes (z=3..33) with merge-frame drop coordinates.
Real fix, four bugs, all in `scratch/bank_rows.py` (zero engine files):
frame-fixed rehydration (shift=(8,104), 19088/19088 gate), wire/repeater
block emission (stamp_wire fills dicts only -- the dump shipped zero new
electrical blocks), tap beside the lamp (not on its cell), booster
planting (lwire plants none; 2000-cell rows arrive dark), lamp-cell
reservation, one drop column per net. Lamps at merge (-8, -99..-83),
alongside the levers in the empty west margin, zero crossings by
construction (eastern-first + staggered row-ends + monotonic lanes/lamps,
proof in LOG). Reproduce: `python scratch/bank_rows.py` (9/9, seconds)
then `python scratch/bank_lamp_check.py` (0 wrong). Also fixed while
there: `bank_lamp_check` fed the sim all-zero input forever
(`{n for _, n in levers.values()}` unpacks 'A0' into chars) and used
3-tuple lamp keys -- every prior "84 wrong" was the harness, not the build.

**2. Paste the labelled export on the rig.** The 42 signs exist in
`build_add8.mcfunction` / `.schem` but the rig copy was pasted as raw blocks, so
it has levers and lamps and no signs. One function run at y+64, z+800. Note the
9 sum lamps will not be in that export until item 1 lands.

**3. alu8 merge.** All 8 bands route for the first time; the 205,979-block merge
oscillates (churn 52,985, listed loop torches, max_gap 205,950). Band routing is
solved, the merge is not.

**4. Clear the stale debris** at z 3..293 (four stacked add8 copies) once
nobody wants it — it is a permanent trap for anyone measuring in-game.

**Do not** resurrect a post-merge router as the permanent implementation. The
nine lamps are the shape the stitch already carries; declaring them as cross-band
nets in `hier_bands` spec generation reuses the proven path instead of
hand-rolling a second router.

---

## 6. Files touched

Engine (the only non-`scratch/` source changes this session):

| file | what |
|---|---|
| `core.py` | `pin_tap_cell` — the shared pin-cell rule |
| `layout.py` | `build_netspec` registers a load per pinned output |
| `tiles.py` | `_tap_pinned` uses that cell |
| `compose.py` | `REDSTONE_BANK_PITCH` env |

Gate / driver:

| file | what |
|---|---|
| `scratch/hier_verify.py` | **pitch ladder 2→3→4→6→10, escalating on VERIFY** |
| `scratch/coldstart.py` | added `pin_lamp` gate (16 total) |
| `scratch/live_check.py` | the live harness — lever readback, 20s settle |
| `scratch/pin_lamp_check.py` | pin gate + negative test |
| `scratch/hier_bands.py`, `hier_stitch.py` | read `<recipe>.bank` |

Bank-lamp investigation (kept as the record of the attempt):
`bank_rows.py` (the working 7/9 method), `bank_lamp_check.py`,
`bank_route.py`, `bank_lamps.py`, `perimeter.py`, `why_fail.py`,
`postmerge_run.py`, `noground_why.py`, `driver_map.py`, `seal_confirm.py`,
`pin_request.py`.

Live/paste: `paste_pitch2.py`, `paste_audit.py`, `overlap_check.py`,
`first_divergence.py`, `chain_walk.py`, `carry_probe.py`, `hotcell_probe.py`,
`rep_state.py`, `s3_probe.py`.

Rig reads: `rig_read.py` (patched to accept 3-part lamp keys — still not the
harness to use for big builds).

Docs: `LOG.md` (append-only, this session's entries at the end),
`MORNING-REPORT.md`, this file.

Artifacts: `recipes/add8.bank`, `scratch/add8p2.pkl`, `scratch/add8p2ind.pkl`,
`scratch/add8merge.pkl`, `scratch/add8_bankrouted.pkl` (**FAILING build, kept
deliberately as the record — do not treat it as progress**), `build_add8.*`.

Pre-existing untracked, not mine, do not touch: `build.mcfunction.bak`,
`build.schem.bak`, `build_testforce.UNGATED.txt`, `recipes/add8b0..7.txt`.

Uncommitted right now: `scratch/add8bands.pkl` (regenerated by the ladder runs),
`scratch/noground_why.py`, `scratch/paste_pitch2.py` (probe edits),
`recipes/stitch.log`.

---

## 7. Reproduce the good result

```
python scratch/coldstart.py --quick          # 16/16
python scratch/verify2.py recipes/add8.txt scratch/add8p2ind.pkl --max-vectors 16
python scratch/live_check.py                 # rig at z+800 -> 19/19
```

The pitch ladder is what a new hier recipe gets for free:

```
python scratch/hier_verify.py recipes/alu1.txt   # settles at pitch 2
python scratch/hier_verify.py recipes/alu4.txt   # climbs to pitch 10
```